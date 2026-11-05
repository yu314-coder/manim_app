//
//  cb_bench_int_c.c — three more integer workloads of `spec`, each standing
//  for one program that used to share a stand-in with another: an SSA
//  optimiser and register allocator of the LLVM kind (llvm), a packet-level
//  network simulator of the ns-3 kind (ns3), and a text-processing script
//  interpreter of the Perl kind, regular expressions and all (perl).
//
//  As everywhere in the suite, these are the KINDS of program SPEC CPU's
//  integer suites hold, written from scratch for CodeBench; no SPEC (or
//  other benchmark) source is used. What sets each apart from its old
//  partner: llvm works on a graph of individually allocated instructions
//  linked through use lists and dominator trees (where `compile` lexes,
//  parses and lowers source in an arena); ns3 serialises real protocol
//  headers into packet buffers and keeps its events in a balanced tree
//  (where `eventsim` moves fixed records through a heap); perl spends its
//  time in a backtracking regular-expression engine, string building and
//  hashes (where `interp` runs a bytecode loop).
//
//  The rules every workload keeps (see cb_bench.h): plain C17, reentrant,
//  deterministic (own PRNG, fixed seeds), stack under 256 KB, everything it
//  allocates freed before it returns. `size` 1 is quick, 2 standard, 3
//  large.
//

#include "cb_bench.h"

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

// ── Shared helpers ──────────────────────────────────────────────────────

typedef struct { uint64_t s; } ic_rng;

static inline uint64_t ic_next(ic_rng *r) {
    uint64_t z = (r->s += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

static inline uint32_t ic_below(ic_rng *r, uint32_t n) {
    return (uint32_t)(((ic_next(r) >> 32) * (uint64_t)n) >> 32);
}

static inline uint64_t ic_mix(uint64_t h, uint64_t v) {
    h ^= v + 0x9E3779B97F4A7C15ull + (h << 6) + (h >> 2);
    h *= 0xFF51AFD7ED558CCDull;
    return h ^ (h >> 33);
}

#define IC_FNV_BASIS 0xCBF29CE484222325ull
static inline uint64_t ic_fnv(uint64_t h, const void *p, size_t n) {
    const uint8_t *b = (const uint8_t *)p;
    for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 0x100000001B3ull; }
    return h;
}

static inline int ic_size(int size) { return size < 1 ? 1 : size > 3 ? 3 : size; }

// ── llvm: an SSA optimiser and register allocator ───────────────────────

enum {
    LV_CONST, LV_ARG, LV_ALLOCA, LV_LOAD, LV_STORE, LV_PHI,
    LV_ADD, LV_SUB, LV_MUL, LV_AND, LV_OR, LV_XOR, LV_SHL, LV_ASHR,
    LV_ICMP_LT, LV_ICMP_EQ, LV_ICMP_NE, LV_SELECT,
    LV_CALL, LV_BR, LV_CONDBR, LV_RET, LV_NOPS
};

typedef struct lv_inst lv_inst;
typedef struct lv_block lv_block;

/// One operand slot: which value it reads, and its place in that value's
/// use list (doubly linked, as LLVM's Use is).
typedef struct lv_use {
    lv_inst *val;
    lv_inst *user;
    struct lv_use *next, **pprev;
} lv_use;

typedef struct lv_loc { uint32_t line, col; struct lv_loc *chain; } lv_loc;

struct lv_inst {
    uint8_t op, nops, dead, inwl;
    int32_t id, reg, slot;
    int64_t imm;                    // constants; alloca: variable; call: callee
    lv_inst *prev, *next;           // in the block
    lv_block *bb;
    lv_use *ops;                    // hung-off operands, allocated apart
    lv_use *uses;                   // who reads this value
    lv_loc *loc;                    // uniqued debug location
    lv_block *tgt[2];               // branch targets
    lv_block **phib;                // a phi's incoming blocks, one per operand
    int32_t start, end;             // live interval
};

struct lv_block {
    lv_inst *head, *tail;
    lv_block **pred; int npred, cpred;
    int32_t id, rpo, dead, depth;
    lv_block *idom, *dfirst, *dnext;    // dominator tree: first child, next sibling
    lv_block **df; int ndf, cdf;
    uint64_t *livein, *liveout;
    lv_block *next_alloc;
};

/// A bump allocator in 1 MB chunks, reset rather than freed: LLVM keeps
/// its IR in allocators of this kind, and a private one per copy keeps
/// `--rate` copies from contending for the process's malloc.
typedef struct lv_chunk { struct lv_chunk *next; size_t used, cap; } lv_chunk;
typedef struct { lv_chunk *head, *cur; } lv_arena;

typedef struct {
    ic_rng r;
    lv_arena fa, ma;                // the function's arena, the module's
    lv_block *blocks;               // every block of the function, for freeing
    lv_block **rpo; int nrpo, nblocks;
    int nvars, ninst;
    // module-wide state shared by all functions
    lv_inst **ctab; uint32_t cmask; uint32_t ccount;     // uniqued constants
    lv_loc **ltab; uint32_t lmask; uint32_t lcount;      // uniqued locations
    lv_inst *consts_head;           // constants live for the whole module
    int err;
    // statistics
    uint64_t folded, cse, removed, phis, spills, moves;
} lv_mod;

static void *lv_alloc(lv_mod *m, size_t n) {
    void *p = calloc(1, n);
    if (!p) m->err = 1;
    return p;
}

static void *lv_bump(lv_mod *m, lv_arena *a, size_t n) {
    n = (n + 15) & ~(size_t)15;
    if (!a->cur || a->cur->used + n > a->cur->cap) {
        lv_chunk *c = a->cur ? a->cur->next : a->head;
        if (!c || c->cap < n) {
            const size_t cap = n > ((size_t)1 << 20) ? n : ((size_t)1 << 20);
            lv_chunk *nc = (lv_chunk *)malloc(sizeof(lv_chunk) + cap);
            if (!nc) { m->err = 1; return NULL; }
            nc->cap = cap;
            if (a->cur) { nc->next = a->cur->next; a->cur->next = nc; }
            else { nc->next = a->head; a->head = nc; }
            c = nc;
        }
        c->used = 0;
        a->cur = c;
    }
    char *p = (char *)(a->cur + 1) + a->cur->used;
    a->cur->used += n;
    memset(p, 0, n);
    return p;
}

static void lv_arena_free(lv_arena *a) {
    for (lv_chunk *c = a->head, *nc; c; c = nc) { nc = c->next; free(c); }
    a->head = a->cur = NULL;
}

static void lv_use_set(lv_use *u, lv_inst *v) {
    if (u->val) {                   // unlink from the old value's list
        *u->pprev = u->next;
        if (u->next) u->next->pprev = u->pprev;
    }
    u->val = v;
    if (v) {
        u->next = v->uses;
        if (v->uses) v->uses->pprev = &u->next;
        u->pprev = &v->uses;
        v->uses = u;
    } else {
        u->next = NULL; u->pprev = NULL;
    }
}

/// Every use of `from` now reads `to` (LLVM's replaceAllUsesWith).
static void lv_rauw(lv_inst *from, lv_inst *to) {
    while (from->uses) lv_use_set(from->uses, to);
}

static lv_loc *lv_location(lv_mod *m, uint32_t line, uint32_t col) {
    uint32_t h = (line * 0x9E3779B1u) ^ (col * 0x85EBCA77u);
    for (uint32_t i = h & m->lmask;; i = (i + 1) & m->lmask) {
        lv_loc *l = m->ltab[i];
        if (!l) {
            if (m->lcount * 4 > m->lmask * 3) { m->err = 1; return NULL; }
            l = (lv_loc *)lv_bump(m, &m->ma, sizeof *l);
            if (!l) return NULL;
            l->line = line; l->col = col;
            m->ltab[i] = l;
            m->lcount++;
            return l;
        }
        if (l->line == line && l->col == col) return l;
    }
}

/// The module's one constant with value v (constants are uniqued, as in
/// LLVM's context), found by open addressing.
static lv_inst *lv_const(lv_mod *m, int64_t v) {
    uint64_t h = (uint64_t)v * 0x9E3779B97F4A7C15ull;
    for (uint32_t i = (uint32_t)(h >> 40) & m->cmask;; i = (i + 1) & m->cmask) {
        lv_inst *c = m->ctab[i];
        if (!c) {
            if (m->ccount * 4 > m->cmask * 3) { m->err = 1; return NULL; }
            c = (lv_inst *)lv_bump(m, &m->ma, sizeof *c);
            if (!c) return NULL;
            c->op = LV_CONST; c->imm = v; c->id = -1;
            c->next = m->consts_head; m->consts_head = c;
            m->ctab[i] = c;
            m->ccount++;
            return c;
        }
        if (c->imm == v) return c;
    }
}

static lv_inst *lv_new(lv_mod *m, lv_block *bb, int op, int nops, uint32_t line) {
    lv_inst *in = (lv_inst *)lv_bump(m, &m->fa, sizeof *in);
    if (!in) return NULL;
    in->op = (uint8_t)op; in->nops = (uint8_t)nops; in->bb = bb; in->reg = -1; in->slot = -1;
    if (nops) {
        in->ops = (lv_use *)lv_bump(m, &m->fa, sizeof(lv_use) * (size_t)nops);
        if (!in->ops) return NULL;
        for (int i = 0; i < nops; i++) in->ops[i].user = in;
    }
    in->loc = lv_location(m, line, 1);       // a source line each, 128 files' worth
    m->ninst++;
    if (bb) {
        in->prev = bb->tail;
        if (bb->tail) bb->tail->next = in; else bb->head = in;
        bb->tail = in;
    }
    return in;
}

static void lv_insert_front(lv_block *bb, lv_inst *in) {
    in->bb = bb; in->prev = NULL; in->next = bb->head;
    if (bb->head) bb->head->prev = in; else bb->tail = in;
    bb->head = in;
}

static void lv_unlink(lv_inst *in) {
    lv_block *bb = in->bb;
    if (in->prev) in->prev->next = in->next; else bb->head = in->next;
    if (in->next) in->next->prev = in->prev; else bb->tail = in->prev;
    in->prev = in->next = NULL;
}

static void lv_erase(lv_mod *m, lv_inst *in) {
    for (int i = 0; i < in->nops; i++) lv_use_set(&in->ops[i], NULL);
    lv_unlink(in);
    m->removed++;                   // its memory goes back with the function's arena
}

static lv_block *lv_block_new(lv_mod *m) {
    lv_block *b = (lv_block *)lv_bump(m, &m->fa, sizeof *b);
    if (!b) return NULL;
    b->id = m->nblocks++;
    b->next_alloc = m->blocks; m->blocks = b;
    return b;
}

static void lv_add_pred(lv_mod *m, lv_block *b, lv_block *p) {
    if (b->npred == b->cpred) {
        int nc = b->cpred ? b->cpred * 2 : 4;
        lv_block **np = (lv_block **)realloc(b->pred, sizeof(*np) * (size_t)nc);
        if (!np) { m->err = 1; return; }
        b->pred = np; b->cpred = nc;
    }
    b->pred[b->npred++] = p;
}

// The generator writes what clang -O0 writes: every local in an alloca,
// every read a load, every write a store; structured ifs and loops.

typedef struct {
    lv_mod *m;
    lv_block *cur;
    lv_inst **vars;                 // the allocas
    int nvars, nargs, budget, depth, nfuncs, self;
    uint32_t line;
} lv_gen;

static lv_inst *lv_load(lv_gen *g, int v) {
    lv_inst *l = lv_new(g->m, g->cur, LV_LOAD, 1, g->line++);
    if (l) lv_use_set(&l->ops[0], g->vars[v]);
    return l;
}

static void lv_store(lv_gen *g, int v, lv_inst *val) {
    lv_inst *s = lv_new(g->m, g->cur, LV_STORE, 2, g->line++);
    if (s) { lv_use_set(&s->ops[0], g->vars[v]); lv_use_set(&s->ops[1], val); }
}

static lv_inst *lv_expr(lv_gen *g, int depth) {
    lv_mod *m = g->m;
    uint32_t k = ic_below(&m->r, 10);
    if (depth <= 0 || k < 3) {
        if (k == 0) return lv_const(m, (int64_t)ic_below(&m->r, 9) - 2);
        return lv_load(g, (int)ic_below(&m->r, (uint32_t)g->nvars));
    }
    static const uint8_t ops[11] = {LV_ADD, LV_ADD, LV_SUB, LV_MUL, LV_AND, LV_OR, LV_XOR, LV_SHL, LV_ASHR, LV_ADD, LV_MUL};
    if (k == 9 && g->nfuncs > 1 && depth >= 2) {
        int callee = (int)ic_below(&m->r, (uint32_t)g->nfuncs);
        lv_inst *a = lv_expr(g, depth - 1), *b = lv_expr(g, depth - 1);
        lv_inst *c = lv_new(m, g->cur, LV_CALL, 2, g->line++);
        if (c) { c->imm = callee; lv_use_set(&c->ops[0], a); lv_use_set(&c->ops[1], b); }
        return c;
    }
    lv_inst *a = lv_expr(g, depth - 1);
    lv_inst *b = ic_below(&m->r, 3) == 0 ? lv_const(m, (int64_t)ic_below(&m->r, 5)) : lv_expr(g, depth - 1);
    int op = ops[ic_below(&m->r, 11)];
    if (op == LV_SHL || op == LV_ASHR) b = lv_const(m, (int64_t)ic_below(&m->r, 4));
    lv_inst *e = lv_new(m, g->cur, op, 2, g->line++);
    if (e) { lv_use_set(&e->ops[0], a); lv_use_set(&e->ops[1], b); }
    return e;
}

static lv_inst *lv_cond(lv_gen *g) {
    lv_inst *a = lv_expr(g, 2), *b = lv_expr(g, 1);
    static const uint8_t c[3] = {LV_ICMP_LT, LV_ICMP_EQ, LV_ICMP_NE};
    lv_inst *e = lv_new(g->m, g->cur, c[ic_below(&g->m->r, 3)], 2, g->line++);
    if (e) { lv_use_set(&e->ops[0], a); lv_use_set(&e->ops[1], b); }
    return e;
}

static void lv_jump(lv_gen *g, lv_block *to) {
    lv_inst *br = lv_new(g->m, g->cur, LV_BR, 0, g->line++);
    if (br) br->tgt[0] = to;
    lv_add_pred(g->m, to, g->cur);
}

static void lv_branch(lv_gen *g, lv_inst *cond, lv_block *t, lv_block *f) {
    lv_inst *br = lv_new(g->m, g->cur, LV_CONDBR, 1, g->line++);
    if (br) { lv_use_set(&br->ops[0], cond); br->tgt[0] = t; br->tgt[1] = f; }
    lv_add_pred(g->m, t, g->cur);
    lv_add_pred(g->m, f, g->cur);
}

static void lv_stmts(lv_gen *g, int n) {
    lv_mod *m = g->m;
    for (int s = 0; s < n && g->budget > 0 && !m->err; s++) {
        g->budget--;
        uint32_t k = ic_below(&m->r, 12);
        if (k < 7 || g->depth >= 4) {
            lv_store(g, (int)ic_below(&m->r, (uint32_t)g->nvars), lv_expr(g, 1 + (int)ic_below(&m->r, 3)));
        } else if (k < 10) {
            lv_inst *c = lv_cond(g);
            lv_block *t = lv_block_new(m), *f = lv_block_new(m), *j = lv_block_new(m);
            if (!t || !f || !j) return;
            lv_branch(g, c, t, f);
            g->depth++;
            g->cur = t; lv_stmts(g, 1 + (int)ic_below(&m->r, 4)); lv_jump(g, j);
            g->cur = f; lv_stmts(g, (int)ic_below(&m->r, 3)); lv_jump(g, j);
            g->depth--;
            g->cur = j;
        } else {
            // i = 0; while (i < n) { body; i = i + 1 }
            int iv = (int)ic_below(&m->r, (uint32_t)g->nvars);
            lv_store(g, iv, lv_const(m, 0));
            lv_block *h = lv_block_new(m), *body = lv_block_new(m), *ex = lv_block_new(m);
            if (!h || !body || !ex) return;
            lv_jump(g, h);
            g->cur = h;
            lv_inst *ld = lv_load(g, iv);
            lv_inst *cmp = lv_new(m, g->cur, LV_ICMP_LT, 2, g->line++);
            if (cmp) { lv_use_set(&cmp->ops[0], ld); lv_use_set(&cmp->ops[1], lv_const(m, 3 + (int64_t)ic_below(&m->r, 30))); }
            lv_branch(g, cmp, body, ex);
            g->depth++;
            g->cur = body;
            lv_stmts(g, 1 + (int)ic_below(&m->r, 5));
            lv_inst *ld2 = lv_load(g, iv);
            lv_inst *inc = lv_new(m, g->cur, LV_ADD, 2, g->line++);
            if (inc) { lv_use_set(&inc->ops[0], ld2); lv_use_set(&inc->ops[1], lv_const(m, 1)); }
            lv_store(g, iv, inc);
            lv_jump(g, h);
            g->depth--;
            g->cur = ex;
        }
    }
}

/// Builds one function at -O0. Returns its entry block.
static lv_block *lv_generate(lv_mod *m, int nfuncs, int self, int size_stmts) {
    lv_gen g;
    memset(&g, 0, sizeof g);
    g.m = m; g.nfuncs = nfuncs; g.self = self; g.line = (uint32_t)(self % 128) * 8192u;
    g.nargs = 2;
    g.nvars = 6 + (int)ic_below(&m->r, 10);
    m->nvars = g.nvars;
    g.vars = (lv_inst **)lv_alloc(m, sizeof(lv_inst *) * (size_t)g.nvars);
    lv_block *entry = lv_block_new(m);
    if (!g.vars || !entry) { free(g.vars); return NULL; }
    g.cur = entry;
    for (int v = 0; v < g.nvars; v++) {
        g.vars[v] = lv_new(m, entry, LV_ALLOCA, 0, g.line++);
        if (g.vars[v]) g.vars[v]->imm = v;
    }
    for (int a = 0; a < g.nargs; a++) {
        lv_inst *arg = lv_new(m, entry, LV_ARG, 0, g.line++);
        if (arg) arg->imm = a;
        lv_store(&g, a, arg);
    }
    for (int v = g.nargs; v < g.nvars; v++) lv_store(&g, v, lv_const(m, v));
    g.budget = size_stmts;
    lv_stmts(&g, size_stmts);
    lv_inst *r = lv_new(m, g.cur, LV_RET, 1, g.line++);
    if (r) lv_use_set(&r->ops[0], lv_load(&g, 0));
    free(g.vars);
    return entry;
}

static int lv_succ(const lv_block *b, lv_block **s) {
    const lv_inst *t = b->tail;
    if (!t) return 0;
    if (t->op == LV_BR) { s[0] = t->tgt[0]; return 1; }
    if (t->op == LV_CONDBR) { s[0] = t->tgt[0]; s[1] = t->tgt[1]; return 2; }
    return 0;
}

/// Reverse post-order of the blocks reachable from the entry (iterative DFS).
static void lv_order(lv_mod *m, lv_block *entry) {
    free(m->rpo);
    m->rpo = (lv_block **)lv_alloc(m, sizeof(lv_block *) * (size_t)m->nblocks);
    lv_block **stack = (lv_block **)lv_alloc(m, sizeof(lv_block *) * (size_t)m->nblocks);
    int *state = (int *)lv_alloc(m, sizeof(int) * (size_t)m->nblocks * 2);
    if (!m->rpo || !stack || !state) { free(stack); free(state); return; }
    for (lv_block *b = m->blocks; b; b = b->next_alloc) b->rpo = -1;
    int sp = 0, n = 0;
    stack[sp++] = entry; entry->rpo = -2;
    while (sp) {
        lv_block *b = stack[sp - 1];
        lv_block *s[2];
        int ns = lv_succ(b, s), pushed = 0;
        for (int i = state[2 * b->id]; i < ns; i++) {
            state[2 * b->id] = i + 1;
            if (s[i]->rpo == -1) { s[i]->rpo = -2; stack[sp++] = s[i]; pushed = 1; break; }
        }
        if (!pushed) { sp--; m->rpo[n++] = b; }
    }
    for (int i = 0; i < n / 2; i++) { lv_block *t = m->rpo[i]; m->rpo[i] = m->rpo[n - 1 - i]; m->rpo[n - 1 - i] = t; }
    for (int i = 0; i < n; i++) m->rpo[i]->rpo = i;
    m->nrpo = n;
    free(stack); free(state);
}

/// Dominators by Cooper, Harvey and Kennedy's iterative algorithm, the
/// dominator tree as child lists, and dominance frontiers.
static void lv_dominators(lv_mod *m) {
    lv_block **rpo = m->rpo;
    for (int i = 0; i < m->nrpo; i++) { rpo[i]->idom = NULL; rpo[i]->dfirst = rpo[i]->dnext = NULL; rpo[i]->ndf = 0; }
    rpo[0]->idom = rpo[0];
    for (int changed = 1; changed;) {
        changed = 0;
        for (int i = 1; i < m->nrpo; i++) {
            lv_block *b = rpo[i], *nd = NULL;
            for (int p = 0; p < b->npred; p++) {
                lv_block *q = b->pred[p];
                if (q->rpo < 0 || !q->idom) continue;
                if (!nd) { nd = q; continue; }
                lv_block *x = q, *y = nd;
                while (x != y) {
                    while (x->rpo > y->rpo) x = x->idom;
                    while (y->rpo > x->rpo) y = y->idom;
                }
                nd = x;
            }
            if (nd && b->idom != nd) { b->idom = nd; changed = 1; }
        }
    }
    for (int i = m->nrpo - 1; i >= 1; i--) {
        lv_block *b = rpo[i];
        b->dnext = b->idom->dfirst; b->idom->dfirst = b;
    }
    for (int i = 0; i < m->nrpo; i++) {
        lv_block *b = rpo[i];
        int live = 0;
        for (int p = 0; p < b->npred; p++) if (b->pred[p]->rpo >= 0) live++;
        if (live < 2) continue;
        for (int p = 0; p < b->npred; p++) {
            lv_block *r = b->pred[p];
            if (r->rpo < 0) continue;
            while (r != b->idom) {
                int dup = 0;
                for (int k = 0; k < r->ndf; k++) if (r->df[k] == b) { dup = 1; break; }
                if (!dup) {
                    if (r->ndf == r->cdf) {
                        int nc = r->cdf ? r->cdf * 2 : 4;
                        lv_block **nd = (lv_block **)realloc(r->df, sizeof(*nd) * (size_t)nc);
                        if (!nd) { m->err = 1; return; }
                        r->df = nd; r->cdf = nc;
                    }
                    r->df[r->ndf++] = b;
                }
                r = r->idom;
            }
        }
    }
}

typedef struct { lv_inst **v; int n, cap; } lv_stack;

static void lv_push(lv_mod *m, lv_stack *s, lv_inst *v) {
    if (s->n == s->cap) {
        int nc = s->cap ? s->cap * 2 : 16;
        lv_inst **p = (lv_inst **)realloc(s->v, sizeof(*p) * (size_t)nc);
        if (!p) { m->err = 1; return; }
        s->v = p; s->cap = nc;
    }
    s->v[s->n++] = v;
}

static lv_inst *lv_phi_new(lv_mod *m, lv_block *b, int var) {
    lv_inst *phi = (lv_inst *)lv_bump(m, &m->fa, sizeof *phi);
    if (!phi) return NULL;
    phi->op = LV_PHI; phi->imm = var; phi->reg = -1; phi->slot = -1;
    phi->nops = (uint8_t)b->npred;
    phi->ops = (lv_use *)lv_bump(m, &m->fa, sizeof(lv_use) * (size_t)(b->npred ? b->npred : 1));
    phi->phib = (lv_block **)lv_bump(m, &m->fa, sizeof(lv_block *) * (size_t)(b->npred ? b->npred : 1));
    if (!phi->ops || !phi->phib) return NULL;
    for (int i = 0; i < b->npred; i++) { phi->ops[i].user = phi; phi->phib[i] = b->pred[i]; }
    phi->loc = b->head ? b->head->loc : NULL;
    lv_insert_front(b, phi);
    m->ninst++; m->phis++;
    return phi;
}

/// mem2reg: allocas become SSA values, with φ-functions placed on the
/// iterated dominance frontier of their stores and the loads renamed by a
/// walk of the dominator tree.
static void lv_mem2reg(lv_mod *m, lv_block *entry) {
    const int nv = m->nvars;
    lv_stack *st = (lv_stack *)lv_alloc(m, sizeof(lv_stack) * (size_t)nv);
    uint8_t *has = (uint8_t *)lv_alloc(m, (size_t)m->nblocks * (size_t)nv);
    lv_block **work = (lv_block **)lv_alloc(m, sizeof(lv_block *) * (size_t)m->nblocks);
    if (!st || !has || !work) { free(st); free(has); free(work); return; }
    // φ placement, per variable
    uint8_t *inwork = (uint8_t *)lv_alloc(m, (size_t)m->nblocks);
    if (!inwork) { free(st); free(has); free(work); return; }
    for (int v = 0; v < nv; v++) {
        int nw = 0;
        memset(inwork, 0, (size_t)m->nblocks);
        for (int i = 0; i < m->nrpo; i++) {
            lv_block *b = m->rpo[i];
            for (lv_inst *in = b->head; in; in = in->next)
                if (in->op == LV_STORE && in->ops[0].val && in->ops[0].val->imm == v) { work[nw++] = b; inwork[b->id] = 1; break; }
        }
        while (nw) {
            lv_block *b = work[--nw];
            for (int k = 0; k < b->ndf; k++) {
                lv_block *d = b->df[k];
                if (has[(size_t)d->id * nv + v]) continue;
                has[(size_t)d->id * nv + v] = 1;
                lv_phi_new(m, d, v);
                if (!inwork[d->id]) { inwork[d->id] = 1; work[nw++] = d; }
            }
        }
    }
    free(inwork);
    // renaming: a walk of the dominator tree, each block's definitions
    // pushed on the variables' stacks and popped when the walk leaves it
    typedef struct { lv_block *b; int mark; lv_block *child; } frame;
    frame *fs = (frame *)lv_alloc(m, sizeof(frame) * (size_t)(m->nblocks + 1));
    lv_stack undo = {0};
    if (!fs) { free(st); free(has); free(work); return; }
    lv_inst *zero = lv_const(m, 0);
    int sp = 0;
    fs[sp++] = (frame){entry, -1, NULL};
    while (sp && !m->err) {
        frame *f = &fs[sp - 1];
        lv_block *b = f->b;
        if (f->mark < 0) {
            f->mark = undo.n;
            for (lv_inst *in = b->head, *nx; in; in = nx) {
                nx = in->next;
                if (in->op == LV_PHI) {
                    lv_push(m, &st[in->imm], in); lv_push(m, &undo, (lv_inst *)(intptr_t)in->imm);
                } else if (in->op == LV_LOAD && in->ops[0].val->op == LV_ALLOCA) {
                    const int v = (int)in->ops[0].val->imm;
                    lv_rauw(in, st[v].n ? st[v].v[st[v].n - 1] : zero);
                    lv_erase(m, in);
                } else if (in->op == LV_STORE && in->ops[0].val->op == LV_ALLOCA) {
                    const int v = (int)in->ops[0].val->imm;
                    lv_push(m, &st[v], in->ops[1].val); lv_push(m, &undo, (lv_inst *)(intptr_t)v);
                    lv_erase(m, in);
                }
            }
            lv_block *s[2];
            const int ns = lv_succ(b, s);
            for (int i = 0; i < ns; i++)
                for (lv_inst *in = s[i]->head; in && in->op == LV_PHI; in = in->next)
                    for (int p = 0; p < in->nops; p++)
                        if (in->phib[p] == b && !in->ops[p].val) {
                            const int v = (int)in->imm;
                            lv_use_set(&in->ops[p], st[v].n ? st[v].v[st[v].n - 1] : zero);
                            break;
                        }
            f->child = b->dfirst;
        }
        if (f->child) {
            lv_block *c = f->child;
            f->child = c->dnext;
            fs[sp++] = (frame){c, -1, NULL};
            continue;
        }
        while (undo.n > f->mark) { const int v = (int)(intptr_t)undo.v[--undo.n]; st[v].n--; }
        sp--;
    }
    // the allocas are dead now
    for (lv_inst *in = entry->head, *nx; in; in = nx) {
        nx = in->next;
        if (in->op == LV_ALLOCA && !in->uses) lv_erase(m, in);
    }
    for (int v = 0; v < nv; v++) free(st[v].v);
    free(undo.v); free(fs); free(st); free(has); free(work);
}

static int lv_eval(int op, int64_t a, int64_t b, int64_t *r) {
    uint64_t ua = (uint64_t)a, ub = (uint64_t)b;
    switch (op) {
    case LV_ADD: *r = (int64_t)(ua + ub); return 1;
    case LV_SUB: *r = (int64_t)(ua - ub); return 1;
    case LV_MUL: *r = (int64_t)(ua * ub); return 1;
    case LV_AND: *r = a & b; return 1;
    case LV_OR: *r = a | b; return 1;
    case LV_XOR: *r = a ^ b; return 1;
    case LV_SHL: *r = (int64_t)(ua << (ub & 63)); return 1;
    case LV_ASHR: *r = a >> (b & 63); return 1;
    case LV_ICMP_LT: *r = a < b; return 1;
    case LV_ICMP_EQ: *r = a == b; return 1;
    case LV_ICMP_NE: *r = a != b; return 1;
    }
    return 0;
}

static int lv_commutes(int op) {
    return op == LV_ADD || op == LV_MUL || op == LV_AND || op == LV_OR || op == LV_XOR || op == LV_ICMP_EQ || op == LV_ICMP_NE;
}

/// What an instruction simplifies to, or NULL: constant folding, identities
/// (x+0, x*1, x&x, x^x, x−x, x*0), a φ whose inputs agree, and
/// reassociation of constants ((x+c1)+c2 → x+(c1+c2)) in place.
static lv_inst *lv_simplify(lv_mod *m, lv_inst *in) {
    if (in->op == LV_PHI) {
        lv_inst *same = NULL;
        for (int i = 0; i < in->nops; i++) {
            lv_inst *v = in->ops[i].val;
            if (v == in || v == same) continue;
            if (same) return NULL;
            same = v;
        }
        return same;
    }
    if (in->op < LV_ADD || in->op > LV_ICMP_NE) return NULL;
    lv_inst *a = in->ops[0].val, *b = in->ops[1].val;
    if (!a || !b) return NULL;
    if (a->op == LV_CONST && b->op == LV_CONST) {
        int64_t r;
        if (lv_eval(in->op, a->imm, b->imm, &r)) { m->folded++; return lv_const(m, r); }
        return NULL;
    }
    if (lv_commutes(in->op) && a->op == LV_CONST) {     // canonical: constant on the right
        lv_use_set(&in->ops[0], b); lv_use_set(&in->ops[1], a);
        lv_inst *t = a; a = b; b = t;
    }
    if (b->op == LV_CONST) {
        const int64_t c = b->imm;
        if (c == 0 && (in->op == LV_ADD || in->op == LV_SUB || in->op == LV_OR || in->op == LV_XOR || in->op == LV_SHL || in->op == LV_ASHR)) return a;
        if (c == 1 && in->op == LV_MUL) return a;
        if (c == 0 && (in->op == LV_MUL || in->op == LV_AND)) return lv_const(m, 0);
        if (in->op == LV_MUL && c > 1 && (c & (c - 1)) == 0) {          // x*2^k → x<<k
            in->op = LV_SHL;
            lv_use_set(&in->ops[1], lv_const(m, __builtin_ctzll((uint64_t)c)));
            m->folded++;
            return NULL;
        }
        if (in->op == LV_ADD && a->op == LV_ADD && a->ops[0].val && a->ops[1].val && a->ops[1].val->op == LV_CONST) {
            lv_use_set(&in->ops[1], lv_const(m, (int64_t)((uint64_t)c + (uint64_t)a->ops[1].val->imm)));
            lv_use_set(&in->ops[0], a->ops[0].val);
            m->folded++;
            return NULL;
        }
    }
    if (a == b) {
        if (in->op == LV_AND || in->op == LV_OR) return a;
        if (in->op == LV_XOR || in->op == LV_SUB || in->op == LV_ICMP_LT || in->op == LV_ICMP_NE) return lv_const(m, 0);
        if (in->op == LV_ICMP_EQ) return lv_const(m, 1);
    }
    return NULL;
}

static int lv_has_effect(const lv_inst *in) {
    return in->op == LV_STORE || in->op == LV_CALL || in->op == LV_BR || in->op == LV_CONDBR || in->op == LV_RET;
}

/// InstCombine-style worklist: simplify, replace every use, queue the
/// users, erase what died.
static void lv_combine(lv_mod *m) {
    lv_stack wl = {0};
    for (int i = m->nrpo - 1; i >= 0; i--)
        for (lv_inst *in = m->rpo[i]->tail; in; in = in->prev) { in->inwl = 1; lv_push(m, &wl, in); }
    while (wl.n && !m->err) {
        lv_inst *in = wl.v[--wl.n];
        in->inwl = 0;
        if (in->dead) continue;
        if (!in->uses && !lv_has_effect(in)) {
            for (int i = 0; i < in->nops; i++) {
                lv_inst *o = in->ops[i].val;
                if (o && o->op != LV_CONST && !o->inwl) { o->inwl = 1; lv_push(m, &wl, o); }
            }
            in->dead = 1;
            continue;
        }
        lv_inst *r = lv_simplify(m, in);
        if (r && r != in) {
            for (lv_use *u = in->uses; u; u = u->next)
                if (!u->user->inwl) { u->user->inwl = 1; lv_push(m, &wl, u->user); }
            lv_rauw(in, r);
            in->inwl = 1; lv_push(m, &wl, in);      // now dead: collect it
        }
    }
    free(wl.v);
    for (int i = 0; i < m->nrpo; i++)
        for (lv_inst *in = m->rpo[i]->head, *nx; in; in = nx) {
            nx = in->next;
            if (in->dead && !in->uses) lv_erase(m, in);
        }
}

/// Global value numbering of pure expressions over the dominator tree with
/// a scoped hash table: an expression already available in a dominator
/// replaces the later one.
typedef struct { lv_inst **t; uint32_t mask; lv_stack log; } lv_vn;

static uint64_t lv_key(const lv_inst *in) {
    uint64_t h = in->op;
    for (int i = 0; i < in->nops; i++) h = ic_mix(h, (uint64_t)(uintptr_t)in->ops[i].val);
    return h;
}

static int lv_same_expr(const lv_inst *a, const lv_inst *b) {
    if (a->op != b->op || a->nops != b->nops) return 0;
    for (int i = 0; i < a->nops; i++) if (a->ops[i].val != b->ops[i].val) return 0;
    return 1;
}

static void lv_gvn(lv_mod *m, lv_block *entry) {
    lv_vn vn = {0};
    uint32_t cap = 1024;
    while (cap < (uint32_t)m->ninst * 2u) cap <<= 1;
    vn.t = (lv_inst **)lv_alloc(m, sizeof(lv_inst *) * cap);
    vn.mask = cap - 1;
    typedef struct { lv_block *b; int mark; lv_block *child; } frame;
    frame *fs = (frame *)lv_alloc(m, sizeof(frame) * (size_t)(m->nblocks + 1));
    if (!vn.t || !fs) { free(vn.t); free(fs); return; }
    int sp = 0;
    fs[sp++] = (frame){entry, -1, NULL};
    while (sp && !m->err) {
        frame *f = &fs[sp - 1];
        if (f->mark < 0) {
            f->mark = vn.log.n;
            for (lv_inst *in = f->b->head, *nx; in; in = nx) {
                nx = in->next;
                if (in->op < LV_ADD || in->op > LV_SELECT) continue;
                uint64_t k = lv_key(in);
                uint32_t i = (uint32_t)(k >> 32) & vn.mask;
                for (;; i = (i + 1) & vn.mask) {
                    lv_inst *e = vn.t[i];
                    if (!e) { vn.t[i] = in; lv_push(m, &vn.log, (lv_inst *)(uintptr_t)i); break; }
                    if (lv_same_expr(e, in)) { lv_rauw(in, e); lv_erase(m, in); m->cse++; break; }
                }
            }
            f->child = f->b->dfirst;
        }
        if (f->child) {
            lv_block *c = f->child;
            f->child = c->dnext;
            fs[sp++] = (frame){c, -1, NULL};
            continue;
        }
        // leaving the scope: forget what this block made available
        while (vn.log.n > f->mark) vn.t[(uintptr_t)vn.log.v[--vn.log.n]] = NULL;
        sp--;
    }
    free(vn.log.v); free(vn.t); free(fs);
}

/// SimplifyCFG: constant branches become jumps (the dropped edge leaves
/// its φ inputs), and blocks no longer reachable are emptied.
static int lv_simplify_cfg(lv_mod *m) {
    int changed = 0;
    for (int i = 0; i < m->nrpo; i++) {
        lv_block *b = m->rpo[i];
        lv_inst *t = b->tail;
        if (!t || t->op != LV_CONDBR || !t->ops[0].val || t->ops[0].val->op != LV_CONST) continue;
        const int taken = t->ops[0].val->imm ? 0 : 1;
        lv_block *keep = t->tgt[taken], *drop = t->tgt[1 - taken];
        if (keep != drop) {
            for (int p = 0; p < drop->npred; p++)
                if (drop->pred[p] == b) {
                    for (lv_inst *phi = drop->head; phi && phi->op == LV_PHI; phi = phi->next) {
                        for (int q = p; q + 1 < phi->nops; q++) {
                            lv_use_set(&phi->ops[q], phi->ops[q + 1].val);
                            phi->phib[q] = phi->phib[q + 1];
                        }
                        lv_use_set(&phi->ops[phi->nops - 1], NULL);
                        phi->nops--;
                    }
                    for (int q = p; q + 1 < drop->npred; q++) drop->pred[q] = drop->pred[q + 1];
                    drop->npred--;
                    break;
                }
        }
        lv_inst *br = lv_new(m, b, LV_BR, 0, t->loc ? t->loc->line : 0);
        if (br) br->tgt[0] = keep;
        lv_erase(m, t);
        changed = 1;
    }
    return changed;
}

/// Blocks no longer reachable let go of what they read, and φ inputs
/// arriving from them are dropped, so nothing reachable is held alive by
/// dead code.
static void lv_prune(lv_mod *m) {
    for (lv_block *b = m->blocks; b; b = b->next_alloc) {
        if (b->rpo >= 0) {
            for (lv_inst *phi = b->head; phi && phi->op == LV_PHI; phi = phi->next)
                for (int p = 0; p < phi->nops; p++)
                    if (phi->phib[p] && phi->phib[p]->rpo < 0) lv_use_set(&phi->ops[p], NULL);
            continue;
        }
        if (b->dead) continue;
        b->dead = 1;
        for (lv_inst *in = b->head; in; in = in->next)
            for (int k = 0; k < in->nops; k++) lv_use_set(&in->ops[k], NULL);
    }
}

/// Removes what nothing uses and nothing needs (mark from the effects).
static void lv_dce(lv_mod *m) {
    lv_stack wl = {0};
    for (int i = 0; i < m->nrpo; i++)
        for (lv_inst *in = m->rpo[i]->head; in; in = in->next) {
            in->dead = 1;
            if (lv_has_effect(in)) { in->dead = 0; lv_push(m, &wl, in); }
        }
    while (wl.n) {
        lv_inst *in = wl.v[--wl.n];
        for (int i = 0; i < in->nops; i++) {
            lv_inst *o = in->ops[i].val;
            if (o && o->op != LV_CONST && o->dead) { o->dead = 0; lv_push(m, &wl, o); }
        }
    }
    free(wl.v);
    for (int i = 0; i < m->nrpo; i++)
        for (lv_inst *in = m->rpo[i]->head; in; in = in->next)
            if (in->dead) for (int k = 0; k < in->nops; k++) lv_use_set(&in->ops[k], NULL);
    for (int i = 0; i < m->nrpo; i++)
        for (lv_inst *in = m->rpo[i]->head, *nx; in; in = nx) {
            nx = in->next;
            if (in->dead) lv_erase(m, in);
        }
}

/// Liveness by iterative backward data flow over bit sets of values, live
/// intervals over the linear order, and linear-scan allocation to 14
/// registers, spilling the interval that ends last.
static void lv_regalloc(lv_mod *m, uint64_t *h) {
    int n = 0;
    for (int i = 0; i < m->nrpo; i++)
        for (lv_inst *in = m->rpo[i]->head; in; in = in->next) { in->id = n++; in->start = 1 << 30; in->end = -1; in->reg = -1; }
    const int W = (n + 63) / 64;
    uint64_t *bits = (uint64_t *)lv_alloc(m, sizeof(uint64_t) * (size_t)W * ((size_t)m->nrpo * 2 + 1) + 8);
    lv_inst **byid = (lv_inst **)lv_alloc(m, sizeof(lv_inst *) * (size_t)(n + 1));
    if (!bits || !byid) { free(bits); free(byid); return; }
    for (int i = 0; i < m->nrpo; i++) {
        m->rpo[i]->livein = bits + (size_t)(2 * i) * W;
        m->rpo[i]->liveout = bits + (size_t)(2 * i + 1) * W;
        for (lv_inst *in = m->rpo[i]->head; in; in = in->next) byid[in->id] = in;
    }
    for (int changed = 1, guard = 0; changed && guard < 64; guard++) {
        changed = 0;
        for (int i = m->nrpo - 1; i >= 0; i--) {
            lv_block *b = m->rpo[i], *s[2];
            const int ns = lv_succ(b, s);
            for (int w = 0; w < W; w++) {
                uint64_t o = 0;
                for (int k = 0; k < ns; k++) if (s[k]->rpo >= 0) o |= s[k]->livein[w];
                b->liveout[w] = o;
            }
            for (int k = 0; k < ns; k++)            // φ inputs are live out of their block
                for (lv_inst *phi = s[k]->head; phi && phi->op == LV_PHI; phi = phi->next)
                    for (int p = 0; p < phi->nops; p++)
                        if (phi->phib[p] == b && phi->ops[p].val && phi->ops[p].val->op != LV_CONST)
                            b->liveout[phi->ops[p].val->id >> 6] |= 1ull << (phi->ops[p].val->id & 63);
            uint64_t *live = bits + (size_t)W * (size_t)m->nrpo * 2;
            memcpy(live, b->liveout, sizeof(uint64_t) * (size_t)W);
            for (lv_inst *in = b->tail; in; in = in->prev) {
                live[in->id >> 6] &= ~(1ull << (in->id & 63));
                if (in->op == LV_PHI) continue;
                for (int k = 0; k < in->nops; k++) {
                    const lv_inst *o = in->ops[k].val;
                    if (o && o->op != LV_CONST) live[o->id >> 6] |= 1ull << (o->id & 63);
                }
            }
            for (int w = 0; w < W; w++) if (live[w] != b->livein[w]) { b->livein[w] = live[w]; changed = 1; }
        }
    }
    // intervals: a value is live from its definition to its last use, and
    // across every block it is live through.
    for (int i = 0; i < m->nrpo; i++) {
        lv_block *b = m->rpo[i];
        const int first = b->head ? b->head->id : 0, last = b->tail ? b->tail->id : 0;
        for (int w = 0; w < W; w++) {
            uint64_t x = b->livein[w] | b->liveout[w];
            while (x) {
                const int v = w * 64 + __builtin_ctzll(x);
                x &= x - 1;
                if (v >= n) break;
                lv_inst *in = byid[v];
                if ((b->livein[w] >> (v & 63)) & 1) { if (first < in->start) in->start = first; }
                if ((b->liveout[w] >> (v & 63)) & 1) { if (last > in->end) in->end = last; }
            }
        }
        for (lv_inst *in = b->head; in; in = in->next) {
            if (in->id < in->start) in->start = in->id;
            if (in->id > in->end) in->end = in->id;
            for (int k = 0; k < in->nops; k++) {
                lv_inst *o = in->ops[k].val;
                if (o && o->op != LV_CONST && in->id > o->end) o->end = in->id;
            }
        }
    }
    // linear scan in order of start
    enum { R = 14 };
    lv_inst *active[R];
    int nact = 0;
    uint32_t freeregs = (1u << R) - 1;
    for (int v = 0; v < n; v++) {
        lv_inst *in = byid[v];
        if (in->op == LV_STORE || in->op == LV_BR || in->op == LV_CONDBR || in->op == LV_RET) continue;
        for (int a = 0; a < nact;) {            // expire
            if (active[a]->end < in->start) { freeregs |= 1u << active[a]->reg; active[a] = active[--nact]; }
            else a++;
        }
        if (freeregs) {
            in->reg = __builtin_ctz(freeregs);
            freeregs &= freeregs - 1;
            active[nact++] = in;
        } else {
            int far = 0;
            for (int a = 1; a < nact; a++) if (active[a]->end > active[far]->end) far = a;
            if (active[far]->end > in->end) {
                in->reg = active[far]->reg; active[far]->reg = -1; active[far] = in;
            }
            m->spills++;
        }
        *h = ic_mix(*h, (uint64_t)(in->reg + 1) | ((uint64_t)in->op << 8) | ((uint64_t)(uint32_t)(in->end - in->start) << 16));
    }
    // φ moves the allocator would emit: one per input in a different register
    for (int i = 0; i < m->nrpo; i++)
        for (lv_inst *phi = m->rpo[i]->head; phi && phi->op == LV_PHI; phi = phi->next)
            for (int p = 0; p < phi->nops; p++)
                if (phi->ops[p].val && phi->ops[p].val->reg != phi->reg) m->moves++;
    free(bits); free(byid);
    for (int i = 0; i < m->nrpo; i++) m->rpo[i]->livein = m->rpo[i]->liveout = NULL;
}

static void lv_free_function(lv_mod *m) {
    // the module's constants must forget this function's uses of them
    for (lv_block *b = m->blocks, *nb; b; b = nb) {
        nb = b->next_alloc;
        for (lv_inst *in = b->head, *nx; in; in = nx) { nx = in->next; for (int k = 0; k < in->nops; k++) lv_use_set(&in->ops[k], NULL); }
    }
    for (lv_block *b = m->blocks, *nb; b; b = nb) { nb = b->next_alloc; free(b->pred); free(b->df); }
    m->fa.cur = NULL;               // the arena starts over for the next function
    m->blocks = NULL; m->nblocks = 0; m->ninst = 0;
}

/// llvm — an optimiser and code generator of the LLVM kind working on a
/// module of functions in SSA form: each function arrives as clang -O0
/// writes it (every local in memory, structured ifs and loops, calls), as
/// a graph of individually allocated instructions whose operands are
/// linked into use lists, with uniqued constants and debug locations in
/// module-wide hash tables. The pipeline: reverse post-order, dominators
/// (Cooper–Harvey–Kennedy) and dominance frontiers; mem2reg (φ placement
/// on the iterated frontier, renaming down the dominator tree); an
/// InstCombine worklist (folding, identities, canonicalisation,
/// strength reduction, reassociation); GVN with a scoped hash table;
/// SimplifyCFG; dead-code elimination; liveness, live intervals and
/// linear-scan register allocation with spilling. `size` 1: 550 functions;
/// 2: 4000; 3: 16800 (of about 180 statements each). `checksum` digests
/// every function's final instruction stream and register assignment;
/// `work` is instructions built.
int cbk_llvm(int size, cb_bench_result *out) {
    static const int funcs[3] = {550, 4000, 16800};
    size = ic_size(size);
    lv_mod *m = (lv_mod *)calloc(1, sizeof *m);
    if (!m) return 1;
    m->r.s = 0x11E7A1A900000000ull;
    m->cmask = (1u << 20) - 1;
    m->lmask = (1u << 21) - 1;
    m->ctab = (lv_inst **)calloc((size_t)m->cmask + 1, sizeof(lv_inst *));
    m->ltab = (lv_loc **)calloc((size_t)m->lmask + 1, sizeof(lv_loc *));
    int rc = 1;
    uint64_t h = IC_FNV_BASIS, built = 0;
    if (!m->ctab || !m->ltab) goto done;
    const int nf = funcs[size - 1];
    for (int f = 0; f < nf && !m->err; f++) {
        lv_block *entry = lv_generate(m, nf, f, 120 + (int)ic_below(&m->r, 120));
        if (!entry || m->err) break;
        built += (uint64_t)m->ninst;
        lv_order(m, entry);
        lv_dominators(m);
        lv_mem2reg(m, entry);
        for (int round = 0; round < 3 && !m->err; round++) {
            lv_combine(m);
            lv_gvn(m, entry);
            if (!lv_simplify_cfg(m)) break;
            lv_order(m, entry);
            lv_prune(m);
            lv_dominators(m);
        }
        lv_dce(m);
        lv_regalloc(m, &h);
        for (int i = 0; i < m->nrpo; i++)
            for (lv_inst *in = m->rpo[i]->head; in; in = in->next) {
                uint64_t w = in->op | ((uint64_t)in->nops << 8) | ((uint64_t)(uint32_t)(in->reg + 1) << 16);
                for (int k = 0; k < in->nops; k++)
                    if (in->ops[k].val) w = ic_mix(w, in->ops[k].val->op == LV_CONST ? (uint64_t)in->ops[k].val->imm : (uint64_t)(uint32_t)in->ops[k].val->id);
                h = ic_mix(h, w);
            }
        lv_free_function(m);
    }
    if (m->err) goto done;
    h = ic_mix(h, m->folded); h = ic_mix(h, m->cse); h = ic_mix(h, m->removed);
    h = ic_mix(h, m->phis); h = ic_mix(h, m->spills); h = ic_mix(h, m->moves);
    h = ic_mix(h, m->ccount); h = ic_mix(h, m->lcount);
    out->checksum = h;
    out->value = (double)m->spills;
    out->work = (double)built;
    out->unit = "instructions";
    rc = 0;
done:
    if (m->blocks) lv_free_function(m);
    lv_arena_free(&m->fa); lv_arena_free(&m->ma);
    free(m->ctab); free(m->ltab); free(m->rpo); free(m);
    return rc;
}

// ── ns3: a packet-level network simulator ───────────────────────────────

// The scheduler: a red–black tree of events ordered by (time, uid), one
// heap node per event, as ns-3's map scheduler keeps them. Cancelled
// events stay in the tree and are skipped when they come up.

typedef struct ns_ev ns_ev;
typedef struct ns_sim ns_sim;
typedef void (*ns_fn)(ns_sim *, ns_ev *);

struct ns_ev {
    uint64_t t, uid;
    ns_ev *l, *r, *p;
    uint8_t red, cancelled;
    ns_fn fn;
    int32_t a, b;
    void *pkt;
};

typedef struct ns_pkt_s {
    int32_t refs, len, cap;
    uint8_t buf[64];                // serialised headers
    struct ns_pkt_s *next_free;
    int32_t payload;                // bytes of payload (virtual, as ns-3's zero area)
    uint32_t tag_flow;              // a byte tag: the flow the packet belongs to
    uint64_t tag_sent;
} ns_pkt;

enum { NS_QCAP = 64, NS_HDR = 2 + 20 + 20, NS_POOL = 512 };

typedef struct {
    int32_t node, peer_dev;         // device on the other end
    int64_t ns_per_byte, delay;
    int32_t busy, qhead, qlen;
    ns_pkt *q[NS_QCAP];
    uint32_t loss_ppm;
    uint64_t tx, drops;
} ns_dev;

typedef struct {
    int32_t id, flow;
    // sender
    uint32_t snd_una, snd_nxt, total, cwnd, ssthresh, dupacks, recover, inflight_max;
    int32_t in_recovery;
    int64_t srtt, rttvar, rto;
    ns_ev *rto_ev;
    uint64_t retx, timeouts;
    // receiver
    uint32_t rcv_nxt;
    uint8_t *ooo;                   // segment received out of order, by segment index
    uint32_t nseg;
    int32_t delack;
    ns_ev *delack_ev;
    uint64_t delivered, ts_echo;     // ts_echo: the timestamp to echo in the next ACK
} ns_tcp;

/// Events and packets come from free lists refilled a block at a time —
/// a simulator's own allocator, which also keeps `--rate` copies from
/// contending for the process's malloc.
typedef struct ns_block { struct ns_block *next; } ns_block;

struct ns_sim {
    ns_ev nil;
    ns_ev *free_ev;
    ns_pkt *free_pkt;
    ns_block *blocks;
    ns_ev *root;
    uint64_t now, uid, events;
    ic_rng r;
    int nnodes, nhosts, ndevs;
    ns_dev *dev;
    int32_t *dev_first, *dev_count;          // node → its devices
    int16_t *route;                          // node × node → device index on that node
    ns_tcp *tcp;
    int nflows;
    int32_t *flow_src, *flow_dst;
    uint64_t hdr_bytes, csum_fail, ttl_drops;
    int err;
};

#define NS_MSS 1448u

static void ns_rot_left(ns_sim *s, ns_ev *x) {
    ns_ev *y = x->r;
    x->r = y->l;
    if (y->l != &s->nil) y->l->p = x;
    y->p = x->p;
    if (x->p == &s->nil) s->root = y; else if (x == x->p->l) x->p->l = y; else x->p->r = y;
    y->l = x; x->p = y;
}

static void ns_rot_right(ns_sim *s, ns_ev *x) {
    ns_ev *y = x->l;
    x->l = y->r;
    if (y->r != &s->nil) y->r->p = x;
    y->p = x->p;
    if (x->p == &s->nil) s->root = y; else if (x == x->p->r) x->p->r = y; else x->p->l = y;
    y->r = x; x->p = y;
}

static int ns_less(const ns_ev *a, const ns_ev *b) {
    return a->t < b->t || (a->t == b->t && a->uid < b->uid);
}

static void *ns_block_new(ns_sim *s, size_t item, int n) {
    ns_block *b = (ns_block *)malloc(sizeof(ns_block) + item * (size_t)n);
    if (!b) { s->err = 1; return NULL; }
    b->next = s->blocks; s->blocks = b;
    return b + 1;
}

static ns_ev *ns_ev_alloc(ns_sim *s) {
    if (!s->free_ev) {
        ns_ev *blk = (ns_ev *)ns_block_new(s, sizeof(ns_ev), NS_POOL);
        if (!blk) return NULL;
        for (int i = 0; i < NS_POOL; i++) { blk[i].l = s->free_ev; s->free_ev = &blk[i]; }
    }
    ns_ev *e = s->free_ev;
    s->free_ev = e->l;
    memset(e, 0, sizeof *e);
    return e;
}

static void ns_ev_free(ns_sim *s, ns_ev *e) { e->l = s->free_ev; s->free_ev = e; }

static ns_ev *ns_schedule(ns_sim *s, uint64_t delay, ns_fn fn, int a, int b, void *pkt) {
    ns_ev *z = ns_ev_alloc(s);
    if (!z) return NULL;
    z->t = s->now + delay; z->uid = s->uid++; z->fn = fn; z->a = a; z->b = b; z->pkt = pkt;
    ns_ev *y = &s->nil, *x = s->root;
    while (x != &s->nil) { y = x; x = ns_less(z, x) ? x->l : x->r; }
    z->p = y;
    if (y == &s->nil) s->root = z; else if (ns_less(z, y)) y->l = z; else y->r = z;
    z->l = z->r = &s->nil; z->red = 1;
    ns_ev *const node = z;          // the fix-up below walks z up the tree
    while (z->p->red) {
        if (z->p == z->p->p->l) {
            ns_ev *u = z->p->p->r;
            if (u->red) { z->p->red = 0; u->red = 0; z->p->p->red = 1; z = z->p->p; }
            else {
                if (z == z->p->r) { z = z->p; ns_rot_left(s, z); }
                z->p->red = 0; z->p->p->red = 1; ns_rot_right(s, z->p->p);
            }
        } else {
            ns_ev *u = z->p->p->l;
            if (u->red) { z->p->red = 0; u->red = 0; z->p->p->red = 1; z = z->p->p; }
            else {
                if (z == z->p->l) { z = z->p; ns_rot_right(s, z); }
                z->p->red = 0; z->p->p->red = 1; ns_rot_left(s, z->p->p);
            }
        }
    }
    s->root->red = 0;
    return node;
}

static void ns_transplant(ns_sim *s, ns_ev *u, ns_ev *v) {
    if (u->p == &s->nil) s->root = v; else if (u == u->p->l) u->p->l = v; else u->p->r = v;
    v->p = u->p;
}

/// Removes and returns the earliest event (the leftmost node).
static ns_ev *ns_pop(ns_sim *s) {
    if (s->root == &s->nil) return NULL;
    ns_ev *z = s->root;
    while (z->l != &s->nil) z = z->l;
    ns_ev *x = z->r;                 // z has no left child
    int was_red = z->red;
    ns_transplant(s, z, x);
    if (!was_red) {
        while (x != s->root && !x->red) {
            if (x == x->p->l) {
                ns_ev *w = x->p->r;
                if (w->red) { w->red = 0; x->p->red = 1; ns_rot_left(s, x->p); w = x->p->r; }
                if (!w->l->red && !w->r->red) { w->red = 1; x = x->p; }
                else {
                    if (!w->r->red) { w->l->red = 0; w->red = 1; ns_rot_right(s, w); w = x->p->r; }
                    w->red = x->p->red; x->p->red = 0; w->r->red = 0; ns_rot_left(s, x->p); x = s->root;
                }
            } else {
                ns_ev *w = x->p->l;
                if (w->red) { w->red = 0; x->p->red = 1; ns_rot_right(s, x->p); w = x->p->l; }
                if (!w->r->red && !w->l->red) { w->red = 1; x = x->p; }
                else {
                    if (!w->l->red) { w->r->red = 0; w->red = 1; ns_rot_left(s, w); w = x->p->l; }
                    w->red = x->p->red; x->p->red = 0; w->l->red = 0; ns_rot_right(s, x->p); x = s->root;
                }
            }
        }
        x->red = 0;
    }
    s->nil.p = &s->nil;
    return z;
}

static ns_pkt *ns_pkt_new(ns_sim *s, int payload) {
    if (!s->free_pkt) {
        ns_pkt *blk = (ns_pkt *)ns_block_new(s, sizeof(ns_pkt), NS_POOL);
        if (!blk) return NULL;
        for (int i = 0; i < NS_POOL; i++) { blk[i].next_free = s->free_pkt; s->free_pkt = &blk[i]; }
    }
    ns_pkt *p = s->free_pkt;
    s->free_pkt = p->next_free;
    memset(p, 0, sizeof *p);
    p->refs = 1; p->cap = 64; p->payload = payload;
    return p;
}

static void ns_pkt_unref(ns_sim *s, ns_pkt *p) {
    if (p && --p->refs == 0) { p->next_free = s->free_pkt; s->free_pkt = p; }
}

static inline void ns_w16(uint8_t *b, uint16_t v) { b[0] = (uint8_t)(v >> 8); b[1] = (uint8_t)v; }
static inline void ns_w32(uint8_t *b, uint32_t v) { b[0] = (uint8_t)(v >> 24); b[1] = (uint8_t)(v >> 16); b[2] = (uint8_t)(v >> 8); b[3] = (uint8_t)v; }
static inline uint16_t ns_r16(const uint8_t *b) { return (uint16_t)((b[0] << 8) | b[1]); }
static inline uint32_t ns_r32(const uint8_t *b) { return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 8) | b[3]; }

/// The Internet checksum (RFC 1071) over n bytes.
static uint16_t ns_csum(const uint8_t *b, int n) {
    uint32_t sum = 0;
    for (int i = 0; i + 1 < n; i += 2) sum += (uint32_t)((b[i] << 8) | b[i + 1]);
    if (n & 1) sum += (uint32_t)(b[n - 1] << 8);
    while (sum >> 16) sum = (sum & 0xFFFF) + (sum >> 16);
    return (uint16_t)~sum;
}

/// Writes PPP, IPv4 and TCP headers into the packet's buffer, network byte
/// order, with the IPv4 header checksum.
static void ns_headers(ns_pkt *p, int src, int dst, uint32_t seq, uint32_t ack, uint8_t flags, uint16_t win) {
    uint8_t *b = p->buf;
    ns_w16(b, 0x0021);                                   // PPP: IPv4
    uint8_t *ip = b + 2;
    ip[0] = 0x45; ip[1] = 0;
    ns_w16(ip + 2, (uint16_t)(20 + 20 + p->payload));
    ns_w16(ip + 4, (uint16_t)(seq ^ ack)); ns_w16(ip + 6, 0x4000);
    ip[8] = 64; ip[9] = 6;
    ns_w16(ip + 10, 0);
    ns_w32(ip + 12, 0x0A000000u | (uint32_t)src); ns_w32(ip + 16, 0x0A000000u | (uint32_t)dst);
    ns_w16(ip + 10, ns_csum(ip, 20));
    uint8_t *tcp = ip + 20;
    ns_w16(tcp, (uint16_t)(49152 + (src & 1023))); ns_w16(tcp + 2, 80);
    ns_w32(tcp + 4, seq); ns_w32(tcp + 8, ack);
    tcp[12] = 5 << 4; tcp[13] = flags;
    ns_w16(tcp + 14, win); ns_w16(tcp + 16, 0); ns_w16(tcp + 18, 0);
    ns_w16(tcp + 16, ns_csum(tcp, 20));
    p->len = NS_HDR;
}

static void ns_dev_send(ns_sim *s, int d, ns_pkt *p);

static void ns_ev_txdone(ns_sim *s, ns_ev *e) {
    ns_dev *dv = &s->dev[e->a];
    dv->busy = 0;
    if (dv->qlen) {
        ns_pkt *p = dv->q[dv->qhead];
        dv->qhead = (dv->qhead + 1) % NS_QCAP; dv->qlen--;
        ns_dev_send(s, e->a, p);
    }
}

static void ns_receive(ns_sim *s, int node, ns_pkt *p);

static void ns_ev_arrive(ns_sim *s, ns_ev *e) {
    ns_receive(s, e->a, (ns_pkt *)e->pkt);
}

/// Puts a packet on the wire: the transmission takes its length at the
/// device's rate, then propagates; the error model may lose it.
static void ns_dev_send(ns_sim *s, int d, ns_pkt *p) {
    ns_dev *dv = &s->dev[d];
    if (dv->busy) {
        if (dv->qlen == NS_QCAP) { dv->drops++; ns_pkt_unref(s, p); return; }
        dv->q[(dv->qhead + dv->qlen) % NS_QCAP] = p; dv->qlen++;
        return;
    }
    dv->busy = 1;
    dv->tx++;
    const int64_t bytes = p->len + p->payload;
    const uint64_t txt = (uint64_t)(bytes * dv->ns_per_byte);
    ns_schedule(s, txt, ns_ev_txdone, d, 0, NULL);
    if (dv->loss_ppm && ic_below(&s->r, 1000000) < dv->loss_ppm) { ns_pkt_unref(s, p); return; }
    const ns_dev *peer = &s->dev[dv->peer_dev];
    ns_schedule(s, txt + (uint64_t)dv->delay, ns_ev_arrive, peer->node, 0, p);
}

static void ns_tcp_send_data(ns_sim *s, ns_tcp *t);
static void ns_tcp_ack(ns_sim *s, ns_tcp *t, int dst, int src);

static void ns_ev_rto(ns_sim *s, ns_ev *e) {
    ns_tcp *t = &s->tcp[e->a];
    if (t->rto_ev != e) return;
    t->rto_ev = NULL;
    if (t->snd_una >= t->total) return;
    t->timeouts++;
    t->ssthresh = t->cwnd / 2 > 2 * NS_MSS ? t->cwnd / 2 : 2 * NS_MSS;
    t->cwnd = NS_MSS;
    t->snd_nxt = t->snd_una;
    t->in_recovery = 0; t->dupacks = 0;
    t->rto = t->rto * 2 > 60000000000ll ? 60000000000ll : t->rto * 2;
    ns_tcp_send_data(s, t);
}

static void ns_ev_delack(ns_sim *s, ns_ev *e) {
    ns_tcp *t = &s->tcp[e->a];
    if (t->delack_ev != e) return;
    t->delack_ev = NULL;
    if (t->delack) { t->delack = 0; ns_tcp_ack(s, t, s->flow_src[t->flow], s->flow_dst[t->flow]); }
}

static void ns_ev_start(ns_sim *s, ns_ev *e) { ns_tcp_send_data(s, &s->tcp[e->a]); }

static void ns_arm_rto(ns_sim *s, ns_tcp *t) {
    if (t->rto_ev) t->rto_ev->cancelled = 1;
    t->rto_ev = ns_schedule(s, (uint64_t)t->rto, ns_ev_rto, t->id, 0, NULL);
}

/// One data segment starting at `seq`, handed to the local IP layer.
static uint32_t ns_tcp_segment(ns_sim *s, ns_tcp *t, uint32_t seq) {
    const uint32_t len = t->total - seq < NS_MSS ? t->total - seq : NS_MSS;
    ns_pkt *p = ns_pkt_new(s, (int)len);
    if (!p) return 0;
    ns_headers(p, s->flow_src[t->flow], s->flow_dst[t->flow], seq, 0, 0x18, 65535);
    p->tag_flow = (uint32_t)t->flow; p->tag_sent = s->now;
    s->hdr_bytes += (uint64_t)p->len;
    ns_receive(s, s->flow_src[t->flow], p);
    return len;
}

/// Sends as much new data as the congestion window allows.
static void ns_tcp_send_data(ns_sim *s, ns_tcp *t) {
    while (t->snd_nxt < t->total && t->snd_nxt - t->snd_una < t->cwnd && !s->err) {
        const uint32_t len = ns_tcp_segment(s, t, t->snd_nxt);
        if (!len) return;
        t->snd_nxt += len;
        if (t->snd_nxt - t->snd_una > t->inflight_max) t->inflight_max = t->snd_nxt - t->snd_una;
    }
    if (!t->rto_ev && t->snd_una < t->snd_nxt) ns_arm_rto(s, t);
}

static void ns_tcp_ack(ns_sim *s, ns_tcp *t, int dst, int src) {
    ns_pkt *p = ns_pkt_new(s, 0);
    if (!p) return;
    ns_headers(p, src, dst, 0, t->rcv_nxt, 0x10, 65535);
    p->tag_flow = (uint32_t)t->flow; p->tag_sent = t->ts_echo;     // the timestamp echoed back
    ns_receive(s, src, p);
}

/// The receiving end of a data segment: in-order data advances rcv_nxt
/// (and drains segments that arrived early), out-of-order data is kept
/// and acknowledged at once (a duplicate ACK), in-order data is ACKed
/// every second segment or after 40 ms.
static void ns_tcp_data(ns_sim *s, ns_tcp *t, uint32_t seq, uint32_t len, uint64_t sent) {
    const uint32_t seg = seq / NS_MSS;
    t->ts_echo = sent;
    if (seq == t->rcv_nxt) {
        t->rcv_nxt += len;
        t->delivered += len;
        for (uint32_t k = seg + 1; k < t->nseg && t->ooo[k]; k++) {
            t->ooo[k] = 0;
            const uint32_t l = (k + 1) * NS_MSS <= t->total ? NS_MSS : t->total - k * NS_MSS;
            t->rcv_nxt += l; t->delivered += l;
        }
        if (++t->delack >= 2) {
            t->delack = 0;
            ns_tcp_ack(s, t, s->flow_src[t->flow], s->flow_dst[t->flow]);
        } else if (!t->delack_ev) {
            t->delack_ev = ns_schedule(s, 40000000ull, ns_ev_delack, t->id, 0, NULL);
        }
    } else {
        if (seq > t->rcv_nxt && seg < t->nseg) t->ooo[seg] = 1;
        ns_tcp_ack(s, t, s->flow_src[t->flow], s->flow_dst[t->flow]);
    }
}

/// The sending end of an ACK: RTT estimate (Jacobson/Karels), slow start
/// and congestion avoidance, fast retransmit and NewReno fast recovery.
static void ns_tcp_ackin(ns_sim *s, ns_tcp *t, uint32_t ack, uint64_t sent) {
    if (ack > t->snd_una) {
        const int64_t rtt = (int64_t)(s->now - sent);
        if (t->srtt == 0) { t->srtt = rtt; t->rttvar = rtt / 2; }
        else {
            const int64_t err = rtt - t->srtt;
            t->srtt += err / 8;
            t->rttvar += ((err < 0 ? -err : err) - t->rttvar) / 4;
        }
        t->rto = t->srtt + 4 * t->rttvar;
        if (t->rto < 200000000ll) t->rto = 200000000ll;
        const uint32_t acked = ack - t->snd_una;
        t->snd_una = ack;
        if (t->snd_nxt < ack) t->snd_nxt = ack;     // after a timeout's go-back, data already received
        if (t->in_recovery) {
            if (ack >= t->recover) { t->in_recovery = 0; t->cwnd = t->ssthresh; }
            else {                                   // partial ACK: resend the next hole
                t->retx++;
                ns_tcp_segment(s, t, ack);
                t->cwnd = t->cwnd > acked ? t->cwnd - acked + NS_MSS : NS_MSS;
            }
        } else if (t->cwnd < t->ssthresh) t->cwnd += acked < NS_MSS ? acked : NS_MSS;
        else t->cwnd += NS_MSS * NS_MSS / t->cwnd + 1;
        t->dupacks = 0;
        if (t->snd_una < t->snd_nxt) ns_arm_rto(s, t);
        else if (t->rto_ev) { t->rto_ev->cancelled = 1; t->rto_ev = NULL; }
    } else if (ack == t->snd_una && t->snd_una < t->snd_nxt) {
        if (++t->dupacks == 3 && !t->in_recovery) {
            t->ssthresh = (t->snd_nxt - t->snd_una) / 2 > 2 * NS_MSS ? (t->snd_nxt - t->snd_una) / 2 : 2 * NS_MSS;
            t->recover = t->snd_nxt;
            t->in_recovery = 1;
            t->cwnd = t->ssthresh + 3 * NS_MSS;
            t->retx++;
            ns_tcp_segment(s, t, t->snd_una);         // fast retransmit
            ns_arm_rto(s, t);
            return;
        } else if (t->in_recovery) t->cwnd += NS_MSS;
    }
    ns_tcp_send_data(s, t);
}

/// IPv4 at a node: deserialise and check the header, deliver it to TCP
/// if it is for this node, else decrement the TTL, re-checksum and forward
/// it by the routing table.
static void ns_receive(ns_sim *s, int node, ns_pkt *p) {
    s->events++;
    uint8_t *ip = p->buf + 2;
    if (ns_csum(ip, 20) != 0) { s->csum_fail++; ns_pkt_unref(s, p); return; }
    const int src = (int)(ns_r32(ip + 12) & 0xFFFFFF), dst = (int)(ns_r32(ip + 16) & 0xFFFFFF);
    if (dst == node) {
        const uint8_t *tcp = ip + 20;
        const uint32_t seq = ns_r32(tcp + 4), ack = ns_r32(tcp + 8);
        const uint8_t flags = tcp[13];
        const uint32_t len = (uint32_t)(ns_r16(ip + 2) - 40);
        ns_tcp *t = &s->tcp[p->tag_flow];
        if (len > 0) ns_tcp_data(s, t, seq, len, p->tag_sent);
        else if (flags & 0x10) ns_tcp_ackin(s, t, ack, p->tag_sent);
        (void)src;
        ns_pkt_unref(s, p);
        return;
    }
    if (ip[8] <= 1) { s->ttl_drops++; ns_pkt_unref(s, p); return; }
    ip[8]--;
    ns_w16(ip + 10, 0);
    ns_w16(ip + 10, ns_csum(ip, 20));
    const int d = s->dev_first[node] + s->route[(size_t)node * s->nnodes + dst];
    ns_dev_send(s, d, p);
}

/// ns3 — a packet-level network simulator of the ns-3 kind: hosts on a
/// random mesh of routers joined by point-to-point links (rates from
/// 10 Mb/s to 10 Gb/s, delays of a few milliseconds, DropTail queues, some
/// links with a rate error model), shortest-path routing tables, and TCP
/// NewReno bulk transfers between random host pairs — slow start,
/// congestion avoidance, delayed ACKs, fast retransmit and recovery,
/// retransmission timeouts with RTT estimation. Every packet carries real
/// PPP, IPv4 and TCP headers serialised in network byte order, the IPv4
/// checksum checked and rewritten at every hop; events are heap objects
/// in a red–black tree, timers cancelled lazily. `size` 1: 80 flows of 2.8
/// MB; 2: 200 flows of 4.3 MB; 3: 400 flows of 4 MB. `checksum`
/// digests every flow's delivered bytes, retransmissions, timeouts and
/// largest window and every device's counters; `work` is events.
int cbk_ns3(int size, cb_bench_result *out) {
    static const int cfg[3][3] = {{32, 80, 2800}, {64, 200, 4300}, {96, 400, 4000}};    // routers, flows, KB
    size = ic_size(size);
    ns_sim *s = (ns_sim *)calloc(1, sizeof *s);
    if (!s) return 1;
    int rc = 1;
    s->nil.l = s->nil.r = s->nil.p = &s->nil;
    s->root = &s->nil;
    s->r.s = 0x0453A11CE0000000ull;
    const int R = cfg[size - 1][0], F = cfg[size - 1][1];
    const uint32_t bytes = (uint32_t)cfg[size - 1][2] * 1024u;
    const int H = 2 * F > 4 * R ? 4 * R : 2 * F;
    s->nnodes = R + H; s->nhosts = H; s->nflows = F;
    // links: a ring of routers, chords, and one access link per host
    const int maxlinks = R + R + H;
    s->dev = (ns_dev *)calloc((size_t)maxlinks * 2, sizeof(ns_dev));
    s->dev_first = (int32_t *)calloc((size_t)s->nnodes, sizeof(int32_t));
    s->dev_count = (int32_t *)calloc((size_t)s->nnodes, sizeof(int32_t));
    s->route = (int16_t *)calloc((size_t)s->nnodes * s->nnodes, sizeof(int16_t));
    s->tcp = (ns_tcp *)calloc((size_t)F, sizeof(ns_tcp));
    s->flow_src = (int32_t *)calloc((size_t)F, sizeof(int32_t));
    s->flow_dst = (int32_t *)calloc((size_t)F, sizeof(int32_t));
    int32_t *la = (int32_t *)calloc((size_t)maxlinks * 2, sizeof(int32_t));
    int32_t *adj = (int32_t *)calloc((size_t)maxlinks * 2, sizeof(int32_t));
    int32_t *queue = (int32_t *)calloc((size_t)s->nnodes, sizeof(int32_t));
    int32_t *via = (int32_t *)calloc((size_t)s->nnodes, sizeof(int32_t));
    if (!s->dev || !s->dev_first || !s->dev_count || !s->route || !s->tcp || !s->flow_src || !s->flow_dst || !la || !adj || !queue || !via) goto done;
    int nl = 0;
    static const int64_t rates[4] = {800, 80, 8, 1};          // ns per byte: 10M, 100M, 1G, 8G
    for (int i = 0; i < R + R; i++) {
        int a, b;
        if (i < R) { a = i; b = (i + 1) % R; }
        else { a = (int)ic_below(&s->r, (uint32_t)R); do b = (int)ic_below(&s->r, (uint32_t)R); while (b == a); }
        la[2 * nl] = a; la[2 * nl + 1] = b; nl++;
    }
    for (int h = 0; h < H; h++) { la[2 * nl] = R + h; la[2 * nl + 1] = (int)ic_below(&s->r, (uint32_t)R); nl++; }
    for (int l = 0; l < nl; l++) { s->dev_count[la[2 * l]]++; s->dev_count[la[2 * l + 1]]++; }
    for (int n = 1; n < s->nnodes; n++) s->dev_first[n] = s->dev_first[n - 1] + s->dev_count[n - 1];
    memset(s->dev_count, 0, sizeof(int32_t) * (size_t)s->nnodes);
    for (int l = 0; l < nl; l++) {
        const int a = la[2 * l], b = la[2 * l + 1];
        const int da = s->dev_first[a] + s->dev_count[a]++, db = s->dev_first[b] + s->dev_count[b]++;
        const int64_t rate = rates[a >= R || b >= R ? 1 + (int)ic_below(&s->r, 2) : 2 + (int)ic_below(&s->r, 2)];
        const int64_t delay = 500000 + (int64_t)ic_below(&s->r, 4500000);
        const uint32_t loss = ic_below(&s->r, 8) == 0 ? 200 + ic_below(&s->r, 2000) : 0;
        s->dev[da] = (ns_dev){.node = a, .peer_dev = db, .ns_per_byte = rate, .delay = delay, .loss_ppm = loss};
        s->dev[db] = (ns_dev){.node = b, .peer_dev = da, .ns_per_byte = rate, .delay = delay, .loss_ppm = loss};
        adj[da] = b; adj[db] = a;
    }
    s->ndevs = 2 * nl;
    // routing: BFS from every destination, next hop = the device leading back
    for (int dst = 0; dst < s->nnodes; dst++) {
        for (int n = 0; n < s->nnodes; n++) via[n] = -1;
        int qh = 0, qt = 0;
        queue[qt++] = dst; via[dst] = 0;
        while (qh < qt) {
            const int u = queue[qh++];
            for (int k = 0; k < s->dev_count[u]; k++) {
                const int v = adj[s->dev_first[u] + k];
                if (via[v] >= 0) continue;
                // v reaches dst through the device on v whose peer is u
                int dev_on_v = -1;
                for (int j = 0; j < s->dev_count[v]; j++) if (adj[s->dev_first[v] + j] == u) { dev_on_v = j; break; }
                via[v] = dev_on_v;
                s->route[(size_t)v * s->nnodes + dst] = (int16_t)dev_on_v;
                queue[qt++] = v;
            }
        }
    }
    for (int f = 0; f < F; f++) {
        const int a = R + (int)ic_below(&s->r, (uint32_t)H);
        int b;
        do b = R + (int)ic_below(&s->r, (uint32_t)H); while (b == a);
        s->flow_src[f] = a; s->flow_dst[f] = b;
        ns_tcp *t = &s->tcp[f];
        t->id = f; t->flow = f; t->total = bytes; t->cwnd = 2 * NS_MSS; t->ssthresh = 1u << 30;
        t->rto = 1000000000ll;
        t->nseg = (bytes + NS_MSS - 1) / NS_MSS;
        t->ooo = (uint8_t *)calloc(t->nseg + 1, 1);
        if (!t->ooo) goto done;
        ns_schedule(s, (uint64_t)ic_below(&s->r, 100000000), ns_ev_start, f, 0, NULL);
    }
    // run
    uint64_t steps = 0;
    for (ns_ev *e; (e = ns_pop(s)) != NULL && !s->err;) {
        s->now = e->t;
        if (!e->cancelled) { e->fn(s, e); steps++; }
        else if (e->pkt) ns_pkt_unref(s, (ns_pkt *)e->pkt);
        ns_ev_free(s, e);
    }
    if (s->err) goto done;
    uint64_t h = IC_FNV_BASIS, del = 0;
    for (int f = 0; f < F; f++) {
        const ns_tcp *t = &s->tcp[f];
        h = ic_mix(h, t->delivered); h = ic_mix(h, t->retx); h = ic_mix(h, t->timeouts);
        h = ic_mix(h, t->inflight_max);
        del += t->delivered;
        if (t->delivered != bytes) { rc = 3; goto done; }     // every byte must arrive
    }
    for (int d = 0; d < s->ndevs; d++) { h = ic_mix(h, s->dev[d].tx); h = ic_mix(h, s->dev[d].drops); }
    h = ic_mix(h, s->events); h = ic_mix(h, s->hdr_bytes); h = ic_mix(h, s->ttl_drops); h = ic_mix(h, s->csum_fail);
    out->checksum = h;
    out->value = (double)del;
    out->work = (double)steps;
    out->unit = "events";
    rc = 0;
done:
    while (s->root != &s->nil) { ns_ev *e = ns_pop(s); if (e->pkt) ns_pkt_unref(s, (ns_pkt *)e->pkt); ns_ev_free(s, e); }
    if (s->dev) for (int d = 0; d < s->ndevs; d++) for (int k = 0; k < s->dev[d].qlen; k++) ns_pkt_unref(s, s->dev[d].q[(s->dev[d].qhead + k) % NS_QCAP]);
    if (s->tcp) for (int f = 0; f < F; f++) free(s->tcp[f].ooo);
    free(s->dev); free(s->dev_first); free(s->dev_count); free(s->route); free(s->tcp);
    for (ns_block *b = s->blocks, *nb; b; b = nb) { nb = b->next; free(b); }
    free(s->flow_src); free(s->flow_dst); free(la); free(adj); free(queue); free(via); free(s);
    return rc;
}

// ── perl: a text-processing script interpreter ──────────────────────────

// Strings are heap scalars that grow as they are appended to, as Perl's
// SVs do; hashes chain their entries; the "script" is a list of ops run
// by a dispatch loop for every message; the regular expressions are
// compiled once and run by a backtracking matcher.

typedef struct { char *p; int n, cap; } pl_str;

static int pl_reserve(pl_str *s, int need) {
    if (need + 1 <= s->cap) return 0;
    int nc = s->cap ? s->cap : 32;
    while (nc < need + 1) nc *= 2;
    char *p = (char *)realloc(s->p, (size_t)nc);
    if (!p) return 1;
    s->p = p; s->cap = nc;
    return 0;
}
static int pl_cat(pl_str *s, const char *t, int n) {
    if (pl_reserve(s, s->n + n)) return 1;
    memcpy(s->p + s->n, t, (size_t)n);
    s->n += n; s->p[s->n] = 0;
    return 0;
}
static int pl_cats(pl_str *s, const char *t) { return pl_cat(s, t, (int)strlen(t)); }
static int pl_catu(pl_str *s, uint64_t v) {
    char t[24]; int k = 0;
    do { t[k++] = (char)('0' + v % 10); v /= 10; } while (v);
    char r[24];
    for (int i = 0; i < k; i++) r[i] = t[k - 1 - i];
    return pl_cat(s, r, k);
}

// ── the regular-expression engine

enum { RE_CHAR, RE_ANY, RE_CLASS, RE_BOL, RE_EOL, RE_WORDB, RE_OPEN, RE_CLOSE, RE_SPLIT, RE_JMP, RE_STAR, RE_LOOP, RE_MATCH };

typedef struct {
    uint8_t op, ch, lazy, cap;
    int16_t min, max;
    int32_t x, y;                   // SPLIT: two branches; JMP: target; STAR: body end; LOOP: STAR node
    uint8_t cls[32];
} re_node;

typedef struct {
    re_node *n; int nn, cap;
    int ncap, icase, err;
    const char *src; int pos;
} re_prog;

static int re_emit(re_prog *r, uint8_t op) {
    if (r->nn == r->cap) {
        int nc = r->cap ? r->cap * 2 : 32;
        re_node *p = (re_node *)realloc(r->n, sizeof(re_node) * (size_t)nc);
        if (!p) { r->err = 1; return 0; }
        r->n = p; r->cap = nc;
    }
    memset(&r->n[r->nn], 0, sizeof(re_node));
    r->n[r->nn].op = op;
    return r->nn++;
}

static void re_setc(uint8_t *cls, int c) { cls[c >> 3] |= (uint8_t)(1u << (c & 7)); }
static int re_hasc(const uint8_t *cls, int c) { return (cls[c >> 3] >> (c & 7)) & 1; }

static void re_escape_class(uint8_t *cls, int e) {
    for (int c = 0; c < 256; c++) {
        const int d = c >= '0' && c <= '9', w = d || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
        const int sp = c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f';
        if ((e == 'd' && d) || (e == 'D' && !d) || (e == 'w' && w) || (e == 'W' && !w) || (e == 's' && sp) || (e == 'S' && !sp))
            re_setc(cls, c);
    }
}

static int re_lower(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

static void re_alt(re_prog *r);

/// One atom: a character, ., a class, an escape, an anchor or a group.
static int re_atom(re_prog *r) {
    const char *s = r->src;
    const int c = (unsigned char)s[r->pos];
    if (c == '(') {
        r->pos++;
        int cap = 0;
        if (s[r->pos] == '?' && s[r->pos + 1] == ':') r->pos += 2;
        else cap = ++r->ncap;
        const int open = re_emit(r, RE_OPEN);
        if (open < r->nn) r->n[open].cap = (uint8_t)cap;
        re_alt(r);
        if (s[r->pos] == ')') r->pos++; else r->err = 1;
        const int close = re_emit(r, RE_CLOSE);
        if (!r->err) r->n[close].cap = (uint8_t)cap;
        return open;
    }
    int at;
    if (c == '.') { at = re_emit(r, RE_ANY); r->pos++; }
    else if (c == '^') { at = re_emit(r, RE_BOL); r->pos++; }
    else if (c == '$') { at = re_emit(r, RE_EOL); r->pos++; }
    else if (c == '[') {
        at = re_emit(r, RE_CLASS);
        if (r->err) return at;
        uint8_t *cls = r->n[at].cls;
        r->pos++;
        int neg = 0;
        if (s[r->pos] == '^') { neg = 1; r->pos++; }
        int first = 1;
        while (s[r->pos] && (s[r->pos] != ']' || first)) {
            first = 0;
            int a = (unsigned char)s[r->pos++];
            if (a == '\\') {
                const int e = (unsigned char)s[r->pos++];
                if (strchr("dDwWsS", e)) { re_escape_class(cls, e); continue; }
                a = e == 'n' ? '\n' : e == 't' ? '\t' : e;
            }
            int b = a;
            if (s[r->pos] == '-' && s[r->pos + 1] && s[r->pos + 1] != ']') { b = (unsigned char)s[r->pos + 1]; r->pos += 2; }
            for (int x = a; x <= b; x++) {
                re_setc(cls, x);
                if (r->icase) { re_setc(cls, re_lower(x)); if (x >= 'a' && x <= 'z') re_setc(cls, x - 32); }
            }
        }
        if (s[r->pos] == ']') r->pos++; else r->err = 1;
        if (neg) for (int k = 0; k < 32; k++) cls[k] = (uint8_t)~cls[k];
    } else if (c == '\\') {
        const int e = (unsigned char)s[r->pos + 1];
        r->pos += 2;
        if (e == 'b') at = re_emit(r, RE_WORDB);
        else if (strchr("dDwWsS", e)) { at = re_emit(r, RE_CLASS); if (!r->err) re_escape_class(r->n[at].cls, e); }
        else { at = re_emit(r, RE_CHAR); if (!r->err) r->n[at].ch = (uint8_t)(e == 'n' ? '\n' : e == 't' ? '\t' : e); }
    } else {
        at = re_emit(r, RE_CHAR);
        if (!r->err) r->n[at].ch = (uint8_t)(r->icase ? re_lower(c) : c);
        r->pos++;
    }
    return at;
}

/// An atom with its quantifier: STAR(min, max, lazy) followed by the body
/// and a LOOP back, so a quantified group backtracks through its body.
static void re_piece(re_prog *r) {
    const int start = r->nn;
    re_atom(r);
    const char *s = r->src;
    int min = -1, max = -1;
    const char q = s[r->pos];
    if (q == '*') { min = 0; max = 30000; r->pos++; }
    else if (q == '+') { min = 1; max = 30000; r->pos++; }
    else if (q == '?') { min = 0; max = 1; r->pos++; }
    else if (q == '{' && s[r->pos + 1] >= '0' && s[r->pos + 1] <= '9') {
        int p = r->pos + 1, a = 0, b;
        while (s[p] >= '0' && s[p] <= '9') a = a * 10 + (s[p++] - '0');
        b = a;
        if (s[p] == ',') { p++; if (s[p] == '}') b = 30000; else { b = 0; while (s[p] >= '0' && s[p] <= '9') b = b * 10 + (s[p++] - '0'); } }
        if (s[p] == '}') { min = a; max = b; r->pos = p + 1; }
    }
    if (min < 0 || r->err) return;
    int lazy = 0;
    if (s[r->pos] == '?') { lazy = 1; r->pos++; }
    // move the body one slot down and put STAR in front
    if (re_emit(r, RE_JMP) < 0 || r->err) return;
    memmove(&r->n[start + 1], &r->n[start], sizeof(re_node) * (size_t)(r->nn - 1 - start));
    for (int i = start + 1; i < r->nn; i++) {
        if (r->n[i].op == RE_SPLIT) { if (r->n[i].x >= start) r->n[i].x++; if (r->n[i].y >= start) r->n[i].y++; }
        if (r->n[i].op == RE_JMP && r->n[i].x >= start) r->n[i].x++;
        if (r->n[i].op == RE_STAR && r->n[i].x >= start) r->n[i].x++;
        if (r->n[i].op == RE_LOOP && r->n[i].x >= start) r->n[i].x++;
    }
    memset(&r->n[start], 0, sizeof(re_node));
    r->n[start].op = RE_STAR; r->n[start].min = (int16_t)min; r->n[start].max = (int16_t)max; r->n[start].lazy = (uint8_t)lazy;
    const int loop = re_emit(r, RE_LOOP);
    if (r->err) return;
    r->n[loop].x = start;
    r->n[start].x = loop;              // where the body ends
}

static void re_seq(re_prog *r) {
    while (r->src[r->pos] && r->src[r->pos] != '|' && r->src[r->pos] != ')' && !r->err) re_piece(r);
}

/// Alternatives: SPLIT(first, next) … each branch ending in a JMP past the
/// whole alternation.
static void re_alt(re_prog *r) {
    const int start = r->nn;
    re_seq(r);
    if (r->src[r->pos] != '|') return;
    int jumps[64], nj = 0;
    // insert a SPLIT before the first branch
    if (re_emit(r, RE_JMP) < 0 || r->err) return;
    memmove(&r->n[start + 1], &r->n[start], sizeof(re_node) * (size_t)(r->nn - 1 - start));
    for (int i = start + 1; i < r->nn; i++) {
        if (r->n[i].op == RE_SPLIT) { if (r->n[i].x >= start) r->n[i].x++; if (r->n[i].y >= start) r->n[i].y++; }
        if ((r->n[i].op == RE_JMP || r->n[i].op == RE_STAR || r->n[i].op == RE_LOOP) && r->n[i].x >= start) r->n[i].x++;
    }
    int split = start;
    memset(&r->n[split], 0, sizeof(re_node));
    r->n[split].op = RE_SPLIT; r->n[split].x = split + 1;
    while (r->src[r->pos] == '|' && !r->err) {
        r->pos++;
        if (nj < 64) jumps[nj++] = re_emit(r, RE_JMP);
        const int nb = r->nn;
        r->n[split].y = nb;
        // the next branch may itself be followed by another alternative
        const int bstart = r->nn;
        re_seq(r);
        if (r->src[r->pos] == '|') {
            if (re_emit(r, RE_JMP) < 0 || r->err) return;
            memmove(&r->n[bstart + 1], &r->n[bstart], sizeof(re_node) * (size_t)(r->nn - 1 - bstart));
            for (int i = bstart + 1; i < r->nn; i++) {
                if (r->n[i].op == RE_SPLIT) { if (r->n[i].x >= bstart) r->n[i].x++; if (r->n[i].y >= bstart) r->n[i].y++; }
                if ((r->n[i].op == RE_JMP || r->n[i].op == RE_STAR || r->n[i].op == RE_LOOP) && r->n[i].x >= bstart) r->n[i].x++;
            }
            split = bstart;
            memset(&r->n[split], 0, sizeof(re_node));
            r->n[split].op = RE_SPLIT; r->n[split].x = split + 1;
        }
    }
    for (int j = 0; j < nj; j++) r->n[jumps[j]].x = r->nn;
}

static int re_compile(re_prog *r, const char *pat, int icase) {
    memset(r, 0, sizeof *r);
    r->src = pat; r->icase = icase;
    re_alt(r);
    if (r->src[r->pos]) r->err = 1;
    re_emit(r, RE_MATCH);
    return r->err;
}

typedef struct {
    const re_prog *r;
    const char *s; int len;
    int cap[2 * 10];
    int cnt[64];                    // per-STAR repetition counters (by node, mod 64)
    int lpos[64];                   // position at the last LOOP, to stop empty loops
    uint64_t steps;
} re_vm;

static int re_word(int c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'; }

/// Backtracking match of node `pc` at `pos`: the position the match ends
/// at, or −1. Single-character bodies of a STAR are counted in a loop;
/// other bodies recurse through LOOP.
static int re_run(re_vm *v, int pc, int pos, int depth) {
    const re_prog *r = v->r;
    if (depth > 4000) return -1;
    for (;;) {
        v->steps++;
        const re_node *n = &r->n[pc];
        switch (n->op) {
        case RE_MATCH: return pos;
        case RE_CHAR: {
            if (pos >= v->len) return -1;
            int c = (unsigned char)v->s[pos];
            if (r->icase) c = re_lower(c);
            if (c != n->ch) return -1;
            pos++; pc++; break;
        }
        case RE_ANY: if (pos >= v->len || v->s[pos] == '\n') return -1; pos++; pc++; break;
        case RE_CLASS: if (pos >= v->len || !re_hasc(n->cls, (unsigned char)v->s[pos])) return -1; pos++; pc++; break;
        case RE_BOL: if (pos != 0 && v->s[pos - 1] != '\n') return -1; pc++; break;
        case RE_EOL: if (pos != v->len && v->s[pos] != '\n') return -1; pc++; break;
        case RE_WORDB: {
            const int a = pos > 0 && re_word((unsigned char)v->s[pos - 1]), b = pos < v->len && re_word((unsigned char)v->s[pos]);
            if (a == b) return -1;
            pc++; break;
        }
        case RE_OPEN: {
            if (n->cap && n->cap < 10) {
                const int old = v->cap[2 * n->cap];
                v->cap[2 * n->cap] = pos;
                const int e = re_run(v, pc + 1, pos, depth + 1);
                if (e < 0) v->cap[2 * n->cap] = old;
                return e;
            }
            pc++; break;
        }
        case RE_CLOSE: {
            if (n->cap && n->cap < 10) {
                const int old = v->cap[2 * n->cap + 1];
                v->cap[2 * n->cap + 1] = pos;
                const int e = re_run(v, pc + 1, pos, depth + 1);
                if (e < 0) v->cap[2 * n->cap + 1] = old;
                return e;
            }
            pc++; break;
        }
        case RE_JMP: pc = n->x; break;
        case RE_SPLIT: {
            const int e = re_run(v, n->x, pos, depth + 1);
            if (e >= 0) return e;
            pc = n->y; break;
        }
        case RE_STAR: {
            const re_node *body = &r->n[pc + 1];
            const int after = n->x + 1;
            if (n->x == pc + 2 && (body->op == RE_CHAR || body->op == RE_ANY || body->op == RE_CLASS)) {
                // one-character body: count how far it can go, then back off
                int k = 0;
                while (k < n->max && pos + k < v->len) {
                    int c = (unsigned char)v->s[pos + k];
                    int ok = body->op == RE_ANY ? c != '\n' : body->op == RE_CLASS ? re_hasc(body->cls, c)
                           : (r->icase ? re_lower(c) : c) == body->ch;
                    if (!ok) break;
                    k++;
                }
                if (k < n->min) return -1;
                if (n->lazy) {
                    for (int i = n->min; i <= k; i++) { const int e = re_run(v, after, pos + i, depth + 1); if (e >= 0) return e; }
                } else {
                    for (int i = k; i >= n->min; i--) { const int e = re_run(v, after, pos + i, depth + 1); if (e >= 0) return e; }
                }
                return -1;
            }
            const int slot = pc & 63;
            const int oc = v->cnt[slot], op = v->lpos[slot];
            v->cnt[slot] = 0; v->lpos[slot] = -1;
            int e;
            if (n->min > 0 || !n->lazy) e = re_run(v, pc + 1, pos, depth + 1);
            else e = -1;
            if (e < 0 && n->min == 0) e = re_run(v, after, pos, depth + 1);
            if (e < 0 && n->min == 0 && n->lazy) { v->cnt[slot] = 0; e = re_run(v, pc + 1, pos, depth + 1); }
            v->cnt[slot] = oc; v->lpos[slot] = op;
            return e;
        }
        case RE_LOOP: {
            const int st = n->x, slot = st & 63;
            const re_node *sn = &r->n[st];
            const int count = ++v->cnt[slot];
            if (pos == v->lpos[slot]) { v->cnt[slot]--; return -1; }      // no progress
            const int saved = v->lpos[slot];
            v->lpos[slot] = pos;
            int e = -1;
            if (count < sn->min) e = re_run(v, st + 1, pos, depth + 1);
            else if (!sn->lazy) {
                if (count < sn->max) e = re_run(v, st + 1, pos, depth + 1);
                if (e < 0) e = re_run(v, sn->x + 1, pos, depth + 1);
            } else {
                e = re_run(v, sn->x + 1, pos, depth + 1);
                if (e < 0 && count < sn->max) e = re_run(v, st + 1, pos, depth + 1);
            }
            v->lpos[slot] = saved;
            v->cnt[slot] = count - 1;
            return e;
        }
        default: return -1;
        }
    }
}

/// First match at or after `from`: its start in *ms, its end returned.
static int re_find(re_vm *v, const re_prog *r, const char *s, int len, int from, int *ms) {
    v->r = r; v->s = s; v->len = len;
    // a literal first character lets the scan skip ahead, as Perl's does
    const re_node *f = &r->n[0];
    for (int st = from; st <= len; st++) {
        if (f->op == RE_CHAR && !r->icase) {
            const char *q = st < len ? (const char *)memchr(s + st, f->ch, (size_t)(len - st)) : NULL;
            if (!q) return -1;
            st = (int)(q - s);
        }
        for (int i = 0; i < 20; i++) v->cap[i] = -1;
        const int e = re_run(v, 0, st, 0);
        if (e >= 0) { *ms = st; return e; }
    }
    return -1;
}

// ── hashes

typedef struct pl_ent { struct pl_ent *next; uint64_t h; int64_t val; int klen; char key[]; } pl_ent;
typedef struct { pl_ent **b; uint32_t mask, n; } pl_hash;

static uint64_t pl_hk(const char *k, int n) {
    uint64_t h = 0x84222325CBF29CE4ull;
    for (int i = 0; i < n; i++) { h ^= (unsigned char)k[i]; h *= 0x100000001B3ull; }
    return h ^ (h >> 29);
}

static pl_ent *pl_hget(pl_hash *H, const char *k, int n, int create) {
    const uint64_t h = pl_hk(k, n);
    for (pl_ent *e = H->b[h & H->mask]; e; e = e->next)
        if (e->h == h && e->klen == n && memcmp(e->key, k, (size_t)n) == 0) return e;
    if (!create) return NULL;
    if (H->n > H->mask) {                       // split: double the buckets, as Perl does
        const uint32_t nm = H->mask * 2 + 1;
        pl_ent **nb = (pl_ent **)calloc((size_t)nm + 1, sizeof(pl_ent *));
        if (!nb) return NULL;
        for (uint32_t i = 0; i <= H->mask; i++)
            for (pl_ent *e = H->b[i], *nx; e; e = nx) { nx = e->next; e->next = nb[e->h & nm]; nb[e->h & nm] = e; }
        free(H->b); H->b = nb; H->mask = nm;
    }
    pl_ent *e = (pl_ent *)malloc(sizeof(pl_ent) + (size_t)n + 1);
    if (!e) return NULL;
    e->h = h; e->val = 0; e->klen = n;
    memcpy(e->key, k, (size_t)n); e->key[n] = 0;
    e->next = H->b[h & H->mask]; H->b[h & H->mask] = e;
    H->n++;
    return e;
}

static void pl_hfree(pl_hash *H) {
    if (!H->b) return;
    for (uint32_t i = 0; i <= H->mask; i++) for (pl_ent *e = H->b[i], *nx; e; e = nx) { nx = e->next; free(e); }
    free(H->b); H->b = NULL;
}

// ── the mail and the script

static const char *const pl_words[] = {
    "the", "meeting", "report", "budget", "please", "review", "attached", "schedule", "project", "team",
    "update", "thanks", "regards", "tomorrow", "office", "client", "invoice", "account", "deadline", "draft",
    "free", "winner", "click", "offer", "limited", "money", "credit", "urgent", "guaranteed", "prize",
    "unsubscribe", "viagra", "casino", "lottery", "cheap", "discount", "order", "now", "act", "today",
    "server", "build", "release", "patch", "kernel", "memory", "cache", "latency", "branch", "commit"};
#define PL_NWORDS (int)(sizeof pl_words / sizeof pl_words[0])

static void pl_mail(pl_str *m, ic_rng *r, int idx) {
    const int spam = ic_below(r, 3) == 0;
    static const char *const doms[6] = {"example.com", "mail.example.org", "corp.example.net", "promo.example.biz", "x7.example.ru", "lists.example.edu"};
    static const char *const mons[12] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    static const char *const days[7] = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"};
    m->n = 0;
    const int hops = 2 + (int)ic_below(r, 5);
    for (int h = 0; h < hops; h++) {
        pl_cats(m, "Received: from relay"); pl_catu(m, ic_below(r, 90)); pl_cats(m, ".");
        pl_cats(m, doms[ic_below(r, 6)]); pl_cats(m, " (10."); pl_catu(m, ic_below(r, 255)); pl_cats(m, ".");
        pl_catu(m, ic_below(r, 255)); pl_cats(m, ".1) by mx"); pl_catu(m, h); pl_cats(m, " with ESMTP id ");
        pl_catu(m, ic_next(r) & 0xFFFFFFFFu); pl_cats(m, "\n");
    }
    pl_cats(m, "From: "); pl_cats(m, spam ? "Prize Desk <winner" : "Alex Doe <alex.doe");
    pl_catu(m, spam ? ic_below(r, 100000) : (uint64_t)idx % 7); pl_cats(m, "@"); pl_cats(m, doms[spam ? 3 + ic_below(r, 2) : ic_below(r, 3)]); pl_cats(m, ">\n");
    pl_cats(m, "To: team@example.com\n");
    pl_cats(m, "Date: "); pl_cats(m, days[ic_below(r, 7)]); pl_cats(m, ", "); pl_catu(m, 1 + ic_below(r, 28)); pl_cats(m, " ");
    pl_cats(m, mons[ic_below(r, 12)]); pl_cats(m, " 2026 "); pl_catu(m, 10 + ic_below(r, 14)); pl_cats(m, ":");
    pl_catu(m, 10 + ic_below(r, 50)); pl_cats(m, ":"); pl_catu(m, 10 + ic_below(r, 50)); pl_cats(m, spam ? " -0500\n" : " +0000\n");
    pl_cats(m, "Subject: ");
    const int sw = 3 + (int)ic_below(r, 6);
    for (int w = 0; w < sw; w++) {
        const char *word = pl_words[spam ? 20 + ic_below(r, 20) : ic_below(r, 20)];
        if (spam && ic_below(r, 4) == 0) { for (const char *q = word; *q; q++) { char u = (char)(*q - 32); pl_cat(m, &u, 1); } }
        else pl_cats(m, word);
        pl_cats(m, w + 1 < sw ? " " : "\n");
    }
    pl_cats(m, "Message-ID: <"); pl_catu(m, ic_next(r) & 0xFFFFFFFFFFull); pl_cats(m, "@"); pl_cats(m, doms[ic_below(r, 6)]); pl_cats(m, ">\n");
    pl_cats(m, spam ? "Content-Type: text/html; charset=\"iso-8859-1\"\n\n" : "Content-Type: text/plain; charset=utf-8\n\n");
    const int lines = 8 + (int)ic_below(r, 30);
    for (int l = 0; l < lines; l++) {
        const int nw = 4 + (int)ic_below(r, 12);
        if (spam && ic_below(r, 4) == 0) { pl_cats(m, "<a href=\"http://www."); pl_cats(m, doms[3 + ic_below(r, 2)]); pl_cats(m, "/c?id="); pl_catu(m, ic_below(r, 99999)); pl_cats(m, "\">"); }
        for (int w = 0; w < nw; w++) {
            const uint32_t k = ic_below(r, 100);
            if (k < 4) { pl_cats(m, "$"); pl_catu(m, 1 + ic_below(r, 9999)); if (ic_below(r, 2)) { pl_cats(m, ","); pl_catu(m, 100 + ic_below(r, 900)); } pl_cats(m, ".00"); }
            else if (k < 6) { pl_cats(m, "=3D"); pl_catu(m, ic_below(r, 10)); }
            else if (k < 8) { pl_cats(m, "https://"); pl_cats(m, doms[ic_below(r, 6)]); pl_cats(m, "/p/"); pl_catu(m, ic_below(r, 1000)); }
            else {
                const char *word = pl_words[spam ? (ic_below(r, 2) ? 20 + ic_below(r, 20) : ic_below(r, PL_NWORDS)) : (ic_below(r, 10) ? ic_below(r, 20) : 40 + ic_below(r, 10))];
                pl_cats(m, word);
            }
            pl_cats(m, ic_below(r, 9) == 0 ? ",  " : " ");
        }
        if (spam && ic_below(r, 4) == 0) pl_cats(m, "click here</a>");
        pl_cats(m, ic_below(r, 5) == 0 ? "!!\n" : ".\n");
    }
}

typedef struct {
    re_prog re[24];
    int nre;
    pl_hash tokens, headers;
    pl_str body, work, report, line;
    re_vm vm;
    uint64_t h, matches, subst, ntok;
    int err;
} pl_ctx;

typedef void (*pl_op)(pl_ctx *, const pl_str *, int);

/// s/PAT/REPL/g over `in` into `out`: REPL may use $1.
static void pl_subst(pl_ctx *c, const re_prog *re, const pl_str *in, pl_str *out, const char *repl, int hexdecode) {
    out->n = 0;
    if (pl_reserve(out, in->n)) { c->err = 1; return; }
    out->p[0] = 0;
    int pos = 0;
    for (;;) {
        int ms;
        const int me = re_find(&c->vm, re, in->p, in->n, pos, &ms);
        if (me < 0) break;
        pl_cat(out, in->p + pos, ms - pos);
        if (hexdecode && c->vm.cap[2] >= 0) {
            int v = 0;
            for (int k = c->vm.cap[2]; k < c->vm.cap[3]; k++) {
                const int ch = in->p[k];
                v = v * 16 + (ch <= '9' ? ch - '0' : (ch | 32) - 'a' + 10);
            }
            const char b = (char)v;
            pl_cat(out, &b, 1);
        } else pl_cats(out, repl);
        c->subst++;
        pos = me > ms ? me : me + 1;
        if (me == ms && ms < in->n) pl_cat(out, in->p + ms, 1);
        if (pos > in->n) break;
    }
    if (pos < in->n) pl_cat(out, in->p + pos, in->n - pos);
}

static void pl_op_headers(pl_ctx *c, const pl_str *msg, int arg) {
    (void)arg;
    // split off the header block, one line at a time, through /^([\w-]+):\s*(.*)$/
    int pos = 0, received = 0;
    while (pos < msg->n) {
        const char *nl = (const char *)memchr(msg->p + pos, '\n', (size_t)(msg->n - pos));
        const int end = nl ? (int)(nl - msg->p) : msg->n;
        if (end == pos) { pos = end + 1; break; }
        int ms;
        const int me = re_find(&c->vm, &c->re[0], msg->p + pos, end - pos, 0, &ms);
        if (me >= 0 && c->vm.cap[2] >= 0) {
            pl_ent *e = pl_hget(&c->headers, msg->p + pos + c->vm.cap[2], c->vm.cap[3] - c->vm.cap[2], 1);
            if (!e) { c->err = 1; return; }
            e->val = (int64_t)(((uint64_t)pos << 20) | (uint64_t)(end - pos));
            if (c->vm.cap[3] - c->vm.cap[2] == 8 && !memcmp(msg->p + pos, "Received", 8)) received++;
        }
        pos = end + 1;
    }
    c->body.n = 0;
    if (pos < msg->n) pl_cat(&c->body, msg->p + pos, msg->n - pos);
    c->h = ic_mix(c->h, (uint64_t)received);
}

static int pl_field(pl_ctx *c, const pl_str *msg, const char *name, const char **p, int *n) {
    pl_ent *e = pl_hget(&c->headers, name, (int)strlen(name), 0);
    if (!e) return 0;
    *p = msg->p + (e->val >> 20); *n = (int)(e->val & 0xFFFFF);
    return 1;
}

/// A rule: does the field (or the body) match the pattern? Adds the score.
static void pl_op_rule(pl_ctx *c, const pl_str *msg, int arg) {
    static const char *const fields[] = {"Subject", "Subject", "From", "Date", "Message-ID", NULL, NULL, NULL, NULL, NULL, "Subject", NULL, NULL, NULL};
    static const int scores[] = {25, 18, 30, 12, 7, 22, 15, 20, 9, 14, 11, 16, 13, 8};
    const char *p; int n;
    const char *fname = fields[arg - 1];
    if (fname) { if (!pl_field(c, msg, fname, &p, &n)) return; }
    else { p = c->body.p; n = c->body.n; }
    int ms, count = 0, pos = 0;
    while (count < 50) {
        const int me = re_find(&c->vm, &c->re[arg], p, n, pos, &ms);
        if (me < 0) break;
        count++;
        pos = me > ms ? me : ms + 1;
    }
    c->matches += (uint64_t)count;
    c->h = ic_mix(c->h, (uint64_t)(count * scores[arg - 1]) | ((uint64_t)arg << 32));
}

static void pl_op_clean(pl_ctx *c, const pl_str *msg, int arg) {
    (void)msg; (void)arg;
    // decode quoted-printable, strip tags, squeeze white space
    pl_subst(c, &c->re[15], &c->body, &c->work, "", 1);
    pl_subst(c, &c->re[16], &c->work, &c->line, "", 0);
    pl_subst(c, &c->re[17], &c->line, &c->work, " ", 0);
    c->h = ic_fnv(c->h, c->work.p, (size_t)c->work.n);
}

/// Tokenises the cleaned body, lower-cased, counting every token in the
/// corpus-wide hash, and scores the message the way a Bayes filter does.
static void pl_op_tokens(pl_ctx *c, const pl_str *msg, int arg) {
    (void)msg; (void)arg;
    const char *p = c->work.p;
    const int n = c->work.n;
    char tok[64];
    int64_t score = 0;
    for (int i = 0; i < n;) {
        while (i < n && !re_word((unsigned char)p[i]) && p[i] != '$') i++;
        int k = 0;
        while (i < n && (re_word((unsigned char)p[i]) || p[i] == '$') && k < 63) tok[k++] = (char)re_lower((unsigned char)p[i++]);
        if (k < 2) continue;
        pl_ent *e = pl_hget(&c->tokens, tok, k, 1);
        if (!e) { c->err = 1; return; }
        e->val++;
        score += (int64_t)(e->h & 255) - 128 + (e->val > 50 ? 3 : 0);
        c->ntok++;
    }
    c->h = ic_mix(c->h, (uint64_t)score);
}

static void pl_op_report(pl_ctx *c, const pl_str *msg, int arg) {
    (void)arg;
    c->report.n = 0;
    const char *p; int n;
    pl_cats(&c->report, "X-Spam-Report: ");
    if (pl_field(c, msg, "From", &p, &n)) pl_cat(&c->report, p, n > 40 ? 40 : n);
    pl_cats(&c->report, " matches="); pl_catu(&c->report, c->matches);
    pl_cats(&c->report, " subst="); pl_catu(&c->report, c->subst);
    pl_cats(&c->report, " tokens="); pl_catu(&c->report, c->tokens.n);
    c->h = ic_fnv(c->h, c->report.p, (size_t)c->report.n);
    // forget this message's headers
    for (uint32_t i = 0; i <= c->headers.mask; i++) {
        for (pl_ent *e = c->headers.b[i], *nx; e; e = nx) { nx = e->next; free(e); }
        c->headers.b[i] = NULL;
    }
    c->headers.n = 0;
}

/// perl — a text-processing script interpreter of the Perl kind, running
/// a spam-assassin style script over a stream of generated mail: header
/// parsing through a regular expression and a hash, fourteen scoring
/// rules (case-insensitive words, money amounts, shouting, links to odd
/// domains, date formats, numeric senders, …) matched by a backtracking
/// regular-expression engine with classes, captures, alternation, greedy
/// and lazy quantifiers and word boundaries, three global substitutions
/// (quoted-printable decoding with a captured hex pair, tag stripping,
/// white-space squeezing) over strings that grow as they are built, and
/// a Bayes-style tokeniser counting every word of the corpus in a hash
/// that splits as it grows. The script is a list of ops run by a dispatch
/// loop for each message. `size` 1: 2300 messages; 2: 12000; 3: 52000.
/// `checksum` digests every rule's hit count, every cleaned body and
/// report; `work` is regex steps.
int cbk_perl(int size, cb_bench_result *out) {
    static const int msgs[3] = {2300, 12000, 52000};
    static const char *const pats[18] = {
        "^([A-Za-z-]+):[ \t]*(.*)$",
        "\\b(?:free|winner|prize|guaranteed|lottery)\\b",
        "[A-Z]{4,}",
        "^[\\w ]*<?[a-z]+\\d{3,}@[\\w.-]+\\.(?:biz|ru)>?$",
        "^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \\d{4} \\d\\d:\\d\\d:\\d\\d [-+]\\d{4}$",
        "<\\d+@[\\w.]+>",
        "\\$\\d{1,3}(?:,\\d{3})*(?:\\.\\d\\d)?",
        "click\\s+here",
        "https?://[\\w.-]+\\.(?:biz|ru)(?:/[\\w?=&.-]*)?",
        "<a\\s+href=\"[^\"]*\">",
        "!{2,}",
        "\\b(?:act|order) now\\b",
        "(?:unsubscribe|discount|cheap).*?(?:today|now)",
        "\\b(\\w+) \\1\\b",
        "\\b(?:kernel|cache|branch|commit|latency)\\b",
        "=([0-9A-F]{2})",
        "<[^>]*>",
        "[ \t]{2,}"};
    static const int icase[18] = {0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 0, 1, 0, 0, 0};
    size = ic_size(size);
    pl_ctx *c = (pl_ctx *)calloc(1, sizeof *c);
    if (!c) return 1;
    int rc = 1;
    pl_str msg = {0};
    for (int i = 0; i < 18; i++) {
        // \1 back-references are outside this engine: that rule matches a doubled word by hand
        if (i == 13) { re_compile(&c->re[i], "\\b(\\w+) (\\w+)\\b", icase[i]); continue; }
        if (re_compile(&c->re[i], pats[i], icase[i])) { rc = 2; goto done; }
    }
    c->nre = 18;
    c->tokens.mask = 255; c->tokens.b = (pl_ent **)calloc(256, sizeof(pl_ent *));
    c->headers.mask = 31; c->headers.b = (pl_ent **)calloc(32, sizeof(pl_ent *));
    if (!c->tokens.b || !c->headers.b) goto done;
    static const pl_op prog[] = {pl_op_headers, pl_op_rule, pl_op_rule, pl_op_rule, pl_op_rule, pl_op_rule, pl_op_rule,
                                 pl_op_rule, pl_op_rule, pl_op_rule, pl_op_rule, pl_op_rule, pl_op_rule, pl_op_rule,
                                 pl_op_rule, pl_op_clean, pl_op_tokens, pl_op_report};
    static const int args[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 0, 0, 0};
    ic_rng r = {0x9E71BE4C00000000ull};
    c->h = IC_FNV_BASIS;
    for (int i = 0; i < msgs[size - 1] && !c->err; i++) {
        pl_mail(&msg, &r, i);
        for (size_t k = 0; k < sizeof prog / sizeof prog[0] && !c->err; k++) prog[k](c, &msg, args[k]);
    }
    if (c->err) goto done;
    c->h = ic_mix(c->h, c->matches); c->h = ic_mix(c->h, c->subst); c->h = ic_mix(c->h, c->ntok); c->h = ic_mix(c->h, c->tokens.n);
    out->checksum = c->h;
    out->value = (double)c->matches;
    out->work = (double)c->vm.steps;
    out->unit = "regex steps";
    rc = 0;
done:
    for (int i = 0; i < 18; i++) free(c->re[i].n);
    pl_hfree(&c->tokens); pl_hfree(&c->headers);
    free(c->body.p); free(c->work.p); free(c->report.p); free(c->line.p); free(msg.p); free(c);
    return rc;
}
