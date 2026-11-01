//
//  cb_bench_int_a.c — the classic integer workloads of `spec`.
//
//  Eleven programs of the kinds an integer CPU suite has always measured:
//  an interpreter, a compiler, a network-flow solver, a discrete-event
//  simulator, an XML transformer, a video encoder core, a chess engine, a
//  Go engine, a puzzle solver and two compressors. Every algorithm here is
//  written from scratch for CodeBench; none of it comes from SPEC.
//
//  The rules every workload keeps (see cb_bench.h): plain C17, one thread
//  per call, no mutable globals or function statics (`spec --rate` runs a
//  copy on every core), its own PRNG with fixed seeds, big arrays on the
//  heap, stack under 256 KB, and everything it allocates freed before it
//  returns. `size` 1 is quick, 2 standard, 3 large.
//

#include "cb_bench.h"

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <dlfcn.h>
#include <compression.h>

// Floating-point results feed some checksums (the video quantiser tables,
// the Go tree's UCB scores), so no fused multiply-adds: every compiler
// setting then rounds the same way.
#pragma STDC FP_CONTRACT OFF

// ── Shared helpers ──────────────────────────────────────────────────────

/// splitmix64: a tiny, fast, well-mixed generator. The state lives with
/// the caller, so two workloads on two threads never share it.
typedef struct { uint64_t s; } ia_rng;

static inline uint64_t ia_next(ia_rng *r) {
    uint64_t z = (r->s += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

/// A uniform integer in [0, n) (n > 0), by multiply-high.
static inline uint32_t ia_below(ia_rng *r, uint32_t n) {
    return (uint32_t)(((ia_next(r) >> 32) * (uint64_t)n) >> 32);
}

#define IA_FNV_BASIS 0xCBF29CE484222325ull
#define IA_FNV_PRIME 0x100000001B3ull

/// FNV-1a over bytes, continuing from `h`.
static inline uint64_t ia_fnv(uint64_t h, const void *p, size_t n) {
    const uint8_t *b = (const uint8_t *)p;
    for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= IA_FNV_PRIME; }
    return h;
}

/// Folds one 64-bit word into a running digest (order-sensitive).
static inline uint64_t ia_mix(uint64_t h, uint64_t v) {
    h ^= v + 0x9E3779B97F4A7C15ull + (h << 6) + (h >> 2);
    h *= 0xFF51AFD7ED558CCDull;
    return h ^ (h >> 33);
}

static inline void ia_fill(cb_bench_result *out, uint64_t checksum,
                           double value, double work, const char *unit) {
    out->checksum = checksum;
    out->value = value;
    out->work = work;
    out->unit = unit;
}

static inline int ia_size(int size) { return size < 1 ? 1 : size > 3 ? 3 : size; }

// ── interp: a bytecode virtual machine ──────────────────────────────────

// The instruction set. Operand kinds: I = 64-bit immediate (two words),
// L = local slot, G = global slot, T = jump target, F = function,
// K = string constant, N = local slot followed by a 32-bit immediate.
enum {
    IP_HALT, IP_PUSHI, IP_PUSHK, IP_POP, IP_DUP, IP_SWAP, IP_LOAD, IP_STORE,
    IP_GLOAD, IP_GSTORE, IP_INCL,
    IP_ADD, IP_SUB, IP_MUL, IP_DIV, IP_MOD, IP_AND, IP_OR, IP_XOR, IP_SHL,
    IP_SHR, IP_NEG, IP_LT, IP_LE, IP_GT, IP_GE, IP_EQ, IP_NE, IP_NOT,
    IP_JMP, IP_JZ, IP_JNZ, IP_CALL, IP_RET,
    IP_TOSTR, IP_SLEN, IP_SAT, IP_SCHR,
    IP_DSET, IP_DGET, IP_DHAS, IP_DCOUNT, IP_DCLEAR,
    IP_LNEW, IP_LPUSH, IP_LGET, IP_LSET, IP_LLEN,
    IP_NOPS
};

static const struct { char name[8]; char kind; } ip_ops[IP_NOPS] = {
    {"halt", 0}, {"pushi", 'I'}, {"pushk", 'K'}, {"pop", 0}, {"dup", 0},
    {"swap", 0}, {"load", 'L'}, {"store", 'L'}, {"gload", 'G'},
    {"gstore", 'G'}, {"incl", 'N'},
    {"add", 0}, {"sub", 0}, {"mul", 0}, {"div", 0}, {"mod", 0}, {"and", 0},
    {"or", 0}, {"xor", 0}, {"shl", 0}, {"shr", 0}, {"neg", 0}, {"lt", 0},
    {"le", 0}, {"gt", 0}, {"ge", 0}, {"eq", 0}, {"ne", 0}, {"not", 0},
    {"jmp", 'T'}, {"jz", 'T'}, {"jnz", 'T'}, {"call", 'F'}, {"ret", 0},
    {"tostr", 0}, {"slen", 0}, {"sat", 0}, {"schr", 0},
    {"dset", 0}, {"dget", 0}, {"dhas", 0}, {"dcount", 0}, {"dclear", 0},
    {"lnew", 0}, {"lpush", 0}, {"lget", 0}, {"lset", 0}, {"llen", 0},
};

// The program the VM runs, in its assembly language. Each batch inserts
// string keys into the dictionary, looks keys up (half hit, half miss),
// calls recursive and iterative functions, builds a CSV line by repeated
// concatenation, and insertion-sorts a list of pseudo-random numbers.
static const char ip_program[] =
    ".global batches .global inner .global listn .global result\n"
    ".func main ( | acc b i j s h v x L k )\n"
    "  pushi 0 store acc  pushi 0 store b\n"
    "batch:\n"
    "  load b gload batches lt jz done\n"
    // phase 1: d[key] = strhash(key) & 4095
    "  pushi 0 store i\n"
    "ins:\n"
    "  load i gload inner lt jz insdone\n"
    "  pushk \"key:\" load i pushi 7919 mul load b add pushi 65521 mod tostr add\n"
    "  pushk \"/\" add load b tostr add store s\n"
    "  load s call strhash store h\n"
    "  load s load h pushi 4095 and dset\n"
    "  load acc load h xor store acc\n"
    "  incl i 1 jmp ins\n"
    "insdone:\n"
    // phase 2: lookups, every third key of a stride-3 walk exists
    "  pushi 0 store j\n"
    "look:\n"
    "  load j gload inner lt jz lookdone\n"
    "  pushk \"key:\" load j pushi 3 mul pushi 7919 mul load b add pushi 65521 mod\n"
    "  tostr add pushk \"/\" add load b tostr add store s\n"
    "  load s dhas jz miss\n"
    "  load s dget load acc add store acc jmp lnext\n"
    "miss:\n"
    "  load acc pushi 31 mul pushi 7 add pushi 1073741823 and store acc\n"
    "lnext:\n"
    "  incl j 1 jmp look\n"
    "lookdone:\n"
    // phase 3: function calls
    "  load b pushi 6 mod pushi 13 add call fib load acc add store acc\n"
    "  pushi 0 store i\n"
    "gcdl:\n"
    "  load i pushi 64 lt jz gcddone\n"
    "  load i pushi 91 mul load b add pushi 1 add load i pushi 35 mul pushi 7 add\n"
    "  call gcd load acc add store acc\n"
    "  load i load b add pushi 27 add call collatz load acc xor store acc\n"
    "  incl i 1 jmp gcdl\n"
    "gcddone:\n"
    // phase 4: CSV line by repeated concatenation
    "  pushk \"\" store s pushi 0 store i\n"
    "csv:\n"
    "  load i pushi 60 lt jz csvdone\n"
    "  load s load i load i mul load b add tostr add pushk \",\" add store s\n"
    "  incl i 1 jmp csv\n"
    "csvdone:\n"
    "  load s call strhash load acc add store acc\n"
    "  load s slen load acc xor store acc\n"
    // phase 5: insertion sort of a list filled by an LCG
    "  pushi 4 lnew store L  load b pushi 12345 add store x  pushi 0 store i\n"
    "fill:\n"
    "  load i gload listn lt jz sort\n"
    "  load x pushi 1103515245 mul pushi 12345 add pushi 2147483647 and store x\n"
    "  load L load x pushi 100000 mod lpush\n"
    "  incl i 1 jmp fill\n"
    "sort:\n"
    "  pushi 1 store i\n"
    "outer:\n"
    "  load i load L llen lt jz sorted\n"
    "  load L load i lget store v  load i pushi 1 sub store j\n"
    "inner:\n"
    "  load j pushi 0 ge jz place\n"
    "  load L load j lget load v gt jz place\n"
    "  load L load j pushi 1 add load L load j lget lset\n"
    "  load j pushi 1 sub store j jmp inner\n"
    "place:\n"
    "  load L load j pushi 1 add load v lset\n"
    "  incl i 1 jmp outer\n"
    "sorted:\n"
    "  pushi 0 store k\n"
    "sum:\n"
    "  load k load L llen lt jz sumdone\n"
    "  load acc pushi 33 mul load L load k lget load k mul add pushi 4294967295 and store acc\n"
    "  incl k 7 jmp sum\n"
    "sumdone:\n"
    "  dcount load acc xor store acc  dclear\n"
    "  incl b 1 jmp batch\n"
    "done:\n"
    "  load acc gstore result halt\n"
    "\n"
    ".func strhash ( s | h i n c )\n"
    "  pushi 2166136261 store h  pushi 0 store i  load s slen store n\n"
    "loop:\n"
    "  load i load n lt jz end\n"
    "  load s load i sat store c\n"
    "  load h load c xor pushi 16777619 mul pushi 4294967295 and store h\n"
    "  incl i 1 jmp loop\n"
    "end:\n"
    "  load h ret\n"
    "\n"
    ".func fib ( n | )\n"
    "  load n pushi 2 lt jz rec  load n ret\n"
    "rec:\n"
    "  load n pushi 1 sub call fib  load n pushi 2 sub call fib  add ret\n"
    "\n"
    ".func gcd ( a b | t )\n"
    "loop:\n"
    "  load b jz end\n"
    "  load a load b mod store t  load b store a  load t store b  jmp loop\n"
    "end:\n"
    "  load a ret\n"
    "\n"
    ".func collatz ( n | c )\n"
    "  pushi 0 store c\n"
    "loop:\n"
    "  load n pushi 1 gt jz end\n"
    "  load n pushi 1 and jz even\n"
    "  load n pushi 3 mul pushi 1 add store n jmp next\n"
    "even:\n"
    "  load n pushi 1 shr store n\n"
    "next:\n"
    "  incl c 1 jmp loop\n"
    "end:\n"
    "  load c ret\n";

#define IP_MAXF 16
#define IP_MAXN 24     // names per function (params + locals)
#define IP_MAXLAB 128
#define IP_MAXK 32
#define IP_MAXG 8
#define IP_NAME 24

typedef struct {
    char name[IP_NAME];
    int nargs, nlocals, entry;
    char vars[IP_MAXN][IP_NAME];
} ip_func;

typedef struct {
    ip_func f[IP_MAXF]; int nf;
    struct { char name[IP_NAME]; int func, addr; } lab[IP_MAXLAB]; int nlab;
    char k[IP_MAXK][IP_NAME]; int nk;
    char g[IP_MAXG][IP_NAME]; int ng;
    int32_t *code; int ncode, capcode;
} ip_asm;

typedef struct { const char *p; char tok[64]; int len; } ip_lex;

// Next token: a word, or a "quoted string" (returned with its quotes).
static int ip_token(ip_lex *lx) {
    const char *p = lx->p;
    for (;;) {
        while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
        if (*p == '#') { while (*p && *p != '\n') p++; continue; }
        break;
    }
    if (!*p) { lx->p = p; lx->len = 0; lx->tok[0] = 0; return 0; }
    int n = 0;
    if (*p == '"') {
        lx->tok[n++] = *p++;
        while (*p && *p != '"' && n < 62) lx->tok[n++] = *p++;
        if (*p == '"') lx->tok[n++] = *p++;
    } else {
        while (*p && *p != ' ' && *p != '\t' && *p != '\n' && *p != '\r' && n < 63)
            lx->tok[n++] = *p++;
    }
    lx->tok[n] = 0; lx->len = n; lx->p = p;
    return 1;
}

static int ip_emit(ip_asm *a, int32_t w) {
    if (a->code) {
        if (a->ncode >= a->capcode) return -1;
        a->code[a->ncode] = w;
    }
    a->ncode++;
    return 0;
}

static int ip_find_func(const ip_asm *a, const char *s) {
    for (int i = 0; i < a->nf; i++) if (!strcmp(a->f[i].name, s)) return i;
    return -1;
}

// One pass over the source. Pass 0 sizes the code and records functions,
// labels and constants; pass 1 (a->code allocated) emits the words.
static int ip_pass(ip_asm *a, int pass) {
    ip_lex lx = { ip_program, {0}, 0 };
    int cur = -1;
    a->ncode = 0;
    while (ip_token(&lx)) {
        const char *t = lx.tok;
        if (!strcmp(t, ".global")) {
            if (!ip_token(&lx)) return -1;
            if (pass == 0) {
                if (a->ng >= IP_MAXG) return -1;
                strncpy(a->g[a->ng++], lx.tok, IP_NAME - 1);
            }
            continue;
        }
        if (!strcmp(t, ".func")) {
            if (!ip_token(&lx)) return -1;
            if (pass == 0) {
                if (a->nf >= IP_MAXF) return -1;
                cur = a->nf++;
                memset(&a->f[cur], 0, sizeof a->f[cur]);
                strncpy(a->f[cur].name, lx.tok, IP_NAME - 1);
            } else {
                cur = ip_find_func(a, lx.tok);
            }
            ip_func *f = &a->f[cur];
            if (!ip_token(&lx) || strcmp(lx.tok, "(")) return -1;
            int inargs = 1, nv = 0;
            for (;;) {
                if (!ip_token(&lx)) return -1;
                if (!strcmp(lx.tok, ")")) break;
                if (!strcmp(lx.tok, "|")) { inargs = 0; continue; }
                if (nv >= IP_MAXN) return -1;
                if (pass == 0) {
                    strncpy(f->vars[nv], lx.tok, IP_NAME - 1);
                    if (inargs) f->nargs++;
                }
                nv++;
            }
            f->nlocals = nv;
            f->entry = a->ncode;
            continue;
        }
        if (lx.len > 1 && t[lx.len - 1] == ':') {
            if (pass == 0) {
                if (a->nlab >= IP_MAXLAB || cur < 0) return -1;
                memcpy(a->lab[a->nlab].name, t, (size_t)lx.len - 1);
                a->lab[a->nlab].name[lx.len - 1] = 0;
                a->lab[a->nlab].func = cur;
                a->lab[a->nlab].addr = a->ncode;
                a->nlab++;
            }
            continue;
        }
        int op = -1;
        for (int i = 0; i < IP_NOPS; i++) if (!strcmp(ip_ops[i].name, t)) { op = i; break; }
        if (op < 0 || cur < 0) return -1;
        if (ip_emit(a, op)) return -1;
        char kind = ip_ops[op].kind;
        if (!kind) continue;
        if (!ip_token(&lx)) return -1;
        int32_t w = 0;
        switch (kind) {
        case 'I': {
            int64_t v = strtoll(lx.tok, NULL, 0);
            if (ip_emit(a, (int32_t)(uint32_t)((uint64_t)v & 0xFFFFFFFFu))) return -1;
            if (ip_emit(a, (int32_t)(uint32_t)((uint64_t)v >> 32))) return -1;
            continue;
        }
        case 'L': case 'N': {
            w = -1;
            for (int i = 0; i < a->f[cur].nlocals; i++)
                if (!strcmp(a->f[cur].vars[i], lx.tok)) { w = i; break; }
            if (w < 0) return -1;
            if (ip_emit(a, w)) return -1;
            if (kind == 'N') {
                if (!ip_token(&lx)) return -1;
                if (ip_emit(a, (int32_t)strtol(lx.tok, NULL, 0))) return -1;
            }
            continue;
        }
        case 'G':
            w = -1;
            for (int i = 0; i < a->ng; i++) if (!strcmp(a->g[i], lx.tok)) { w = i; break; }
            if (w < 0) return -1;
            break;
        case 'T':
            if (pass == 1) {
                w = -1;
                for (int i = 0; i < a->nlab; i++)
                    if (a->lab[i].func == cur && !strcmp(a->lab[i].name, lx.tok)) {
                        w = a->lab[i].addr; break;
                    }
                if (w < 0) return -1;
            }
            break;
        case 'F':
            if (pass == 1 && (w = ip_find_func(a, lx.tok)) < 0) return -1;
            break;
        case 'K': {
            if (lx.len < 2 || lx.tok[0] != '"') return -1;
            char s[IP_NAME];
            int n = lx.len - 2 < IP_NAME - 1 ? lx.len - 2 : IP_NAME - 1;
            memcpy(s, lx.tok + 1, (size_t)n); s[n] = 0;
            w = -1;
            for (int i = 0; i < a->nk; i++) if (!strcmp(a->k[i], s)) { w = i; break; }
            if (w < 0) {
                if (a->nk >= IP_MAXK) return -1;
                memcpy(a->k[a->nk], s, (size_t)n + 1);
                w = a->nk++;
            }
            break;
        }
        }
        if (ip_emit(a, w)) return -1;
    }
    return 0;
}

// Values are tagged: integers, strings (offsets into the string arena)
// and lists (indices into the list table).
enum { IPV_INT = 0, IPV_STR = 1, IPV_LIST = 2 };
typedef struct { int64_t v; int64_t t; } ip_val;

typedef struct { uint32_t off, len, cap; } ip_list;

typedef struct {
    uint8_t *str; size_t str_used, str_cap, str_base;   // string arena
    uint32_t *dk, *dh; int64_t *dv; uint32_t dcap, dcount; // dictionary
    ip_list *lists; uint32_t nlists, cap_lists;
    int64_t *lpool; size_t lp_used, lp_cap;
    ip_val *stack; ip_val *locals;
    struct { int32_t ret_pc, base; } *frames;
    int64_t globals[IP_MAXG];
    int64_t kofs[IP_MAXK];                                  // string constants
} ip_vm;

#define IP_STACK 4096
#define IP_LOCALS 16384
#define IP_FRAMES 1024

static uint32_t ip_strhash(const uint8_t *s, uint32_t n) {
    uint32_t h = 2166136261u;
    for (uint32_t i = 0; i < n; i++) { h ^= s[i]; h *= 16777619u; }
    return h;
}

// Allocates a string of `n` bytes in the arena; returns its offset, or
// -1 when out of memory. Layout: u32 length, u32 hash, bytes.
static int64_t ip_stralloc(ip_vm *vm, uint32_t n) {
    size_t need = (8 + (size_t)n + 7) & ~(size_t)7;
    if (vm->str_used + need > vm->str_cap) {
        size_t nc = vm->str_cap * 2;
        while (nc < vm->str_used + need) nc *= 2;
        uint8_t *p = (uint8_t *)realloc(vm->str, nc);
        if (!p) return -1;
        vm->str = p; vm->str_cap = nc;
    }
    int64_t off = (int64_t)vm->str_used;
    vm->str_used += need;
    memcpy(vm->str + off, &n, 4);
    return off;
}
static inline uint32_t ip_slen(const ip_vm *vm, int64_t off) {
    uint32_t n; memcpy(&n, vm->str + off, 4); return n;
}
static inline uint8_t *ip_sbytes(const ip_vm *vm, int64_t off) { return vm->str + off + 8; }
static inline void ip_sethash(ip_vm *vm, int64_t off) {
    uint32_t h = ip_strhash(ip_sbytes(vm, off), ip_slen(vm, off));
    memcpy(vm->str + off + 4, &h, 4);
}
static inline uint32_t ip_gethash(const ip_vm *vm, int64_t off) {
    uint32_t h; memcpy(&h, vm->str + off + 4, 4); return h;
}

static int ip_streq(const ip_vm *vm, int64_t a, int64_t b) {
    uint32_t n = ip_slen(vm, a);
    return n == ip_slen(vm, b) && ip_gethash(vm, a) == ip_gethash(vm, b) &&
           !memcmp(ip_sbytes(vm, a), ip_sbytes(vm, b), n);
}

// Dictionary: open addressing, linear probing, keys are string offsets + 1.
static int ip_dgrow(ip_vm *vm) {
    uint32_t nc = vm->dcap ? vm->dcap * 2 : 1024;
    uint32_t *nk = (uint32_t *)calloc(nc, 4), *nh = (uint32_t *)malloc((size_t)nc * 4);
    int64_t *nv = (int64_t *)malloc((size_t)nc * 8);
    if (!nk || !nh || !nv) { free(nk); free(nh); free(nv); return -1; }
    for (uint32_t i = 0; i < vm->dcap; i++) {
        if (!vm->dk[i]) continue;
        uint32_t j = vm->dh[i] & (nc - 1);
        while (nk[j]) j = (j + 1) & (nc - 1);
        nk[j] = vm->dk[i]; nh[j] = vm->dh[i]; nv[j] = vm->dv[i];
    }
    free(vm->dk); free(vm->dh); free(vm->dv);
    vm->dk = nk; vm->dh = nh; vm->dv = nv; vm->dcap = nc;
    return 0;
}

// Slot holding `key`, or the empty slot where it would go.
static uint32_t ip_dslot(const ip_vm *vm, int64_t key) {
    uint32_t h = ip_gethash(vm, key), m = vm->dcap - 1, j = h & m;
    while (vm->dk[j]) {
        if (vm->dh[j] == h && ip_streq(vm, (int64_t)vm->dk[j] - 1, key)) break;
        j = (j + 1) & m;
    }
    return j;
}

static int64_t ip_lalloc(ip_vm *vm, uint32_t cap) {
    if (vm->lp_used + cap > vm->lp_cap) {
        size_t nc = vm->lp_cap * 2;
        while (nc < vm->lp_used + cap) nc *= 2;
        int64_t *p = (int64_t *)realloc(vm->lpool, nc * 8);
        if (!p) return -1;
        vm->lpool = p; vm->lp_cap = nc;
    }
    int64_t off = (int64_t)vm->lp_used;
    vm->lp_used += cap;
    return off;
}

enum { IPE_OK = 0, IPE_TYPE = 1, IPE_STACK = 2, IPE_MEM = 3, IPE_RANGE = 4 };

// The dispatch loop. Returns an IPE_ code; counts executed instructions.
static int ip_run(ip_vm *vm, const int32_t *code, const ip_func *fn, int entry_fn,
                  uint64_t *executed) {
    ip_val *st = vm->stack, *lo = vm->locals;
    int sp = 0, fp = 0, base = 0, top = fn[entry_fn].nlocals;
    int pc = fn[entry_fn].entry;
    uint64_t n = 0;
    for (int i = 0; i < top; i++) { lo[i].v = 0; lo[i].t = IPV_INT; }
#define IP_NEED(k) do { if (sp < (k)) return IPE_STACK; } while (0)
#define IP_ROOM(k) do { if (sp + (k) > IP_STACK) return IPE_STACK; } while (0)
#define IP_INTS() do { IP_NEED(2); if ((st[sp-1].t | st[sp-2].t) != IPV_INT) return IPE_TYPE; } while (0)
#define IP_BIN(expr) do { IP_INTS(); int64_t b_ = st[sp-1].v, a_ = st[sp-2].v; (void)a_; (void)b_; \
        st[sp-2].v = (expr); sp--; } while (0)
    for (;;) {
        n++;
        int32_t op = code[pc++];
        switch (op) {
        case IP_HALT: *executed = n; return IPE_OK;
        case IP_PUSHI:
            IP_ROOM(1);
            st[sp].v = (int64_t)((uint64_t)(uint32_t)code[pc] | ((uint64_t)(uint32_t)code[pc + 1] << 32));
            st[sp].t = IPV_INT; sp++; pc += 2; break;
        case IP_PUSHK:
            IP_ROOM(1);
            st[sp].v = vm->kofs[code[pc++]]; st[sp].t = IPV_STR; sp++; break;
        case IP_POP: IP_NEED(1); sp--; break;
        case IP_DUP: IP_NEED(1); IP_ROOM(1); st[sp] = st[sp - 1]; sp++; break;
        case IP_SWAP: { IP_NEED(2); ip_val t = st[sp-1]; st[sp-1] = st[sp-2]; st[sp-2] = t; break; }
        case IP_LOAD: IP_ROOM(1); st[sp++] = lo[base + code[pc++]]; break;
        case IP_STORE: IP_NEED(1); lo[base + code[pc++]] = st[--sp]; break;
        case IP_GLOAD: IP_ROOM(1); st[sp].v = vm->globals[code[pc++]]; st[sp].t = IPV_INT; sp++; break;
        case IP_GSTORE:
            IP_NEED(1); if (st[sp-1].t != IPV_INT) return IPE_TYPE;
            vm->globals[code[pc++]] = st[--sp].v; break;
        case IP_INCL: {
            ip_val *l = &lo[base + code[pc]];
            if (l->t != IPV_INT) return IPE_TYPE;
            l->v = (int64_t)((uint64_t)l->v + (uint64_t)(int64_t)code[pc + 1]);
            pc += 2; break;
        }
        case IP_ADD: {
            IP_NEED(2);
            ip_val *a = &st[sp-2], *b = &st[sp-1];
            if ((a->t | b->t) == IPV_INT) { a->v = (int64_t)((uint64_t)a->v + (uint64_t)b->v); sp--; break; }
            if (a->t != IPV_STR || b->t != IPV_STR) return IPE_TYPE;
            uint32_t la = ip_slen(vm, a->v), lb = ip_slen(vm, b->v);
            int64_t s = ip_stralloc(vm, la + lb);
            if (s < 0) return IPE_MEM;
            memcpy(ip_sbytes(vm, s), ip_sbytes(vm, a->v), la);
            memcpy(ip_sbytes(vm, s) + la, ip_sbytes(vm, b->v), lb);
            ip_sethash(vm, s);
            a->v = s; sp--; break;
        }
        case IP_SUB: IP_BIN((int64_t)((uint64_t)a_ - (uint64_t)b_)); break;
        case IP_MUL: IP_BIN((int64_t)((uint64_t)a_ * (uint64_t)b_)); break;
        case IP_DIV: IP_BIN(b_ == 0 || (b_ == -1 && a_ == INT64_MIN) ? 0 : a_ / b_); break;
        case IP_MOD: IP_BIN(b_ == 0 || b_ == -1 ? 0 : a_ % b_); break;
        case IP_AND: IP_BIN(a_ & b_); break;
        case IP_OR: IP_BIN(a_ | b_); break;
        case IP_XOR: IP_BIN(a_ ^ b_); break;
        case IP_SHL: IP_BIN((int64_t)((uint64_t)a_ << (b_ & 63))); break;
        case IP_SHR: IP_BIN((int64_t)((uint64_t)a_ >> (b_ & 63))); break;
        case IP_NEG:
            IP_NEED(1); if (st[sp-1].t != IPV_INT) return IPE_TYPE;
            st[sp-1].v = (int64_t)(0 - (uint64_t)st[sp-1].v); break;
        case IP_NOT:
            IP_NEED(1); if (st[sp-1].t != IPV_INT) return IPE_TYPE;
            st[sp-1].v = !st[sp-1].v; break;
        case IP_LT: IP_BIN(a_ < b_); break;
        case IP_LE: IP_BIN(a_ <= b_); break;
        case IP_GT: IP_BIN(a_ > b_); break;
        case IP_GE: IP_BIN(a_ >= b_); break;
        case IP_EQ: case IP_NE: {
            IP_NEED(2);
            ip_val *a = &st[sp-2], *b = &st[sp-1];
            int eq;
            if (a->t != b->t) eq = 0;
            else if (a->t == IPV_STR) eq = ip_streq(vm, a->v, b->v);
            else eq = a->v == b->v;
            a->v = op == IP_EQ ? eq : !eq; a->t = IPV_INT; sp--; break;
        }
        case IP_JMP: pc = code[pc]; break;
        case IP_JZ: case IP_JNZ: {
            IP_NEED(1);
            ip_val *a = &st[--sp];
            int truth = a->t == IPV_INT ? a->v != 0 : a->t == IPV_STR ? ip_slen(vm, a->v) != 0 : 1;
            pc = (truth == (op == IP_JNZ)) ? code[pc] : pc + 1;
            break;
        }
        case IP_CALL: {
            const ip_func *f = &fn[code[pc++]];
            if (fp >= IP_FRAMES || top + f->nlocals > IP_LOCALS) return IPE_STACK;
            IP_NEED(f->nargs);
            vm->frames[fp].ret_pc = pc; vm->frames[fp].base = base; fp++;
            base = top; top += f->nlocals;
            sp -= f->nargs;
            for (int i = 0; i < f->nargs; i++) lo[base + i] = st[sp + i];
            for (int i = f->nargs; i < f->nlocals; i++) { lo[base + i].v = 0; lo[base + i].t = IPV_INT; }
            pc = f->entry;
            break;
        }
        case IP_RET:
            if (fp == 0) { *executed = n; return IPE_OK; }
            top = base; fp--;
            pc = vm->frames[fp].ret_pc; base = vm->frames[fp].base;
            break;
        case IP_TOSTR: {
            IP_NEED(1); if (st[sp-1].t != IPV_INT) return IPE_TYPE;
            char buf[24]; int k = 0;
            int64_t v = st[sp-1].v;
            uint64_t u = v < 0 ? 0 - (uint64_t)v : (uint64_t)v;
            do { buf[k++] = (char)('0' + u % 10); u /= 10; } while (u);
            if (v < 0) buf[k++] = '-';
            int64_t s = ip_stralloc(vm, (uint32_t)k);
            if (s < 0) return IPE_MEM;
            uint8_t *d = ip_sbytes(vm, s);
            for (int i = 0; i < k; i++) d[i] = (uint8_t)buf[k - 1 - i];
            ip_sethash(vm, s);
            st[sp-1].v = s; st[sp-1].t = IPV_STR; break;
        }
        case IP_SLEN:
            IP_NEED(1); if (st[sp-1].t != IPV_STR) return IPE_TYPE;
            st[sp-1].v = ip_slen(vm, st[sp-1].v); st[sp-1].t = IPV_INT; break;
        case IP_SAT: {
            IP_NEED(2);
            if (st[sp-2].t != IPV_STR || st[sp-1].t != IPV_INT) return IPE_TYPE;
            int64_t s = st[sp-2].v, i = st[sp-1].v;
            st[sp-2].v = i >= 0 && i < ip_slen(vm, s) ? ip_sbytes(vm, s)[i] : -1;
            st[sp-2].t = IPV_INT; sp--; break;
        }
        case IP_SCHR: {
            IP_NEED(1); if (st[sp-1].t != IPV_INT) return IPE_TYPE;
            int64_t s = ip_stralloc(vm, 1);
            if (s < 0) return IPE_MEM;
            ip_sbytes(vm, s)[0] = (uint8_t)st[sp-1].v;
            ip_sethash(vm, s);
            st[sp-1].v = s; st[sp-1].t = IPV_STR; break;
        }
        case IP_DSET: {
            IP_NEED(2); if (st[sp-2].t != IPV_STR || st[sp-1].t != IPV_INT) return IPE_TYPE;
            if ((vm->dcount + 1) * 4 > vm->dcap * 3 && ip_dgrow(vm)) return IPE_MEM;
            uint32_t j = ip_dslot(vm, st[sp-2].v);
            if (!vm->dk[j]) {
                vm->dk[j] = (uint32_t)st[sp-2].v + 1; vm->dh[j] = ip_gethash(vm, st[sp-2].v);
                vm->dcount++;
            }
            vm->dv[j] = st[sp-1].v; sp -= 2; break;
        }
        case IP_DGET: case IP_DHAS: {
            IP_NEED(1); if (st[sp-1].t != IPV_STR) return IPE_TYPE;
            uint32_t j = ip_dslot(vm, st[sp-1].v);
            st[sp-1].v = op == IP_DHAS ? vm->dk[j] != 0 : vm->dk[j] ? vm->dv[j] : 0;
            st[sp-1].t = IPV_INT; break;
        }
        case IP_DCOUNT: IP_ROOM(1); st[sp].v = vm->dcount; st[sp].t = IPV_INT; sp++; break;
        case IP_DCLEAR:
            memset(vm->dk, 0, (size_t)vm->dcap * 4); vm->dcount = 0;
            vm->str_used = vm->str_base; vm->nlists = 0; vm->lp_used = 0;
            break;
        case IP_LNEW: {
            IP_NEED(1); if (st[sp-1].t != IPV_INT) return IPE_TYPE;
            uint32_t cap = st[sp-1].v < 1 ? 1 : (uint32_t)st[sp-1].v;
            if (vm->nlists >= vm->cap_lists) {
                uint32_t nc = vm->cap_lists * 2;
                ip_list *p = (ip_list *)realloc(vm->lists, (size_t)nc * sizeof *p);
                if (!p) return IPE_MEM;
                vm->lists = p; vm->cap_lists = nc;
            }
            int64_t off = ip_lalloc(vm, cap);
            if (off < 0) return IPE_MEM;
            vm->lists[vm->nlists].off = (uint32_t)off;
            vm->lists[vm->nlists].len = 0; vm->lists[vm->nlists].cap = cap;
            st[sp-1].v = vm->nlists++; st[sp-1].t = IPV_LIST; break;
        }
        case IP_LPUSH: {
            IP_NEED(2); if (st[sp-2].t != IPV_LIST || st[sp-1].t != IPV_INT) return IPE_TYPE;
            ip_list *l = &vm->lists[st[sp-2].v];
            if (l->len == l->cap) {   // grow: move to a block twice the size
                int64_t off = ip_lalloc(vm, l->cap * 2);
                if (off < 0) return IPE_MEM;
                memcpy(vm->lpool + off, vm->lpool + l->off, (size_t)l->len * 8);
                l->off = (uint32_t)off; l->cap *= 2;
            }
            vm->lpool[l->off + l->len++] = st[sp-1].v; sp -= 2; break;
        }
        case IP_LGET: {
            IP_NEED(2); if (st[sp-2].t != IPV_LIST || st[sp-1].t != IPV_INT) return IPE_TYPE;
            const ip_list *l = &vm->lists[st[sp-2].v];
            int64_t i = st[sp-1].v;
            if (i < 0 || i >= l->len) return IPE_RANGE;
            st[sp-2].v = vm->lpool[l->off + i]; st[sp-2].t = IPV_INT; sp--; break;
        }
        case IP_LSET: {
            IP_NEED(3);
            if (st[sp-3].t != IPV_LIST || st[sp-2].t != IPV_INT || st[sp-1].t != IPV_INT) return IPE_TYPE;
            const ip_list *l = &vm->lists[st[sp-3].v];
            int64_t i = st[sp-2].v;
            if (i < 0 || i >= l->len) return IPE_RANGE;
            vm->lpool[l->off + i] = st[sp-1].v; sp -= 3; break;
        }
        case IP_LLEN:
            IP_NEED(1); if (st[sp-1].t != IPV_LIST) return IPE_TYPE;
            st[sp-1].v = vm->lists[st[sp-1].v].len; st[sp-1].t = IPV_INT; break;
        default: return IPE_RANGE;
        }
    }
#undef IP_NEED
#undef IP_ROOM
#undef IP_INTS
#undef IP_BIN
}

static int ip_global(const ip_asm *a, const char *name) {
    for (int i = 0; i < a->ng; i++) if (!strcmp(a->g[i], name)) return i;
    return 0;
}

/// interp — a scripting-language interpreter: assembles a program written
/// in a small stack-machine assembly (two passes: label and function
/// resolution, then code emission) and runs it on a dynamically typed VM
/// with a switch dispatch loop, call frames, an arena of immutable strings,
/// a string-keyed hash table and growable integer lists. Each batch of the
/// program builds and hashes string keys, does dictionary inserts and
/// lookups, recursive and iterative calls (fib, gcd, collatz), builds a
/// CSV line by concatenation and insertion-sorts a list. The class of the
/// perl and python interpreters in a CPU suite. Sizes run 220, 1200 and
/// 5400 batches. `checksum` digests the program's result and the VM's
/// final state; `work` is bytecodes executed.
int cbk_interp(int size, cb_bench_result *out) {
    static const int batches[3] = {220, 1200, 5400};
    size = ia_size(size);
    int rc = 1;
    ip_asm *a = (ip_asm *)calloc(1, sizeof *a);
    ip_vm *vm = (ip_vm *)calloc(1, sizeof *vm);
    if (!a || !vm) goto fail;
    if (ip_pass(a, 0)) { rc = 2; goto fail; }
    a->capcode = a->ncode;
    a->code = (int32_t *)malloc((size_t)a->capcode * 4);
    if (!a->code) goto fail;
    if (ip_pass(a, 1) || a->ncode != a->capcode) { rc = 2; goto fail; }
    int entry = ip_find_func(a, "main");
    if (entry < 0) { rc = 2; goto fail; }

    vm->stack = (ip_val *)malloc(IP_STACK * sizeof(ip_val));
    vm->locals = (ip_val *)malloc(IP_LOCALS * sizeof(ip_val));
    vm->frames = malloc(IP_FRAMES * sizeof *vm->frames);
    vm->str_cap = 1 << 20; vm->str = (uint8_t *)malloc(vm->str_cap);
    vm->cap_lists = 64; vm->lists = (ip_list *)malloc(vm->cap_lists * sizeof(ip_list));
    vm->lp_cap = 4096; vm->lpool = (int64_t *)malloc(vm->lp_cap * 8);
    if (!vm->stack || !vm->locals || !vm->frames || !vm->str || !vm->lists || !vm->lpool ||
        ip_dgrow(vm))
        goto fail;
    for (int i = 0; i < a->nk; i++) {
        uint32_t n = (uint32_t)strlen(a->k[i]);
        int64_t s = ip_stralloc(vm, n);
        if (s < 0) goto fail;
        memcpy(ip_sbytes(vm, s), a->k[i], n);
        ip_sethash(vm, s);
        vm->kofs[i] = s;
    }
    vm->str_base = vm->str_used;
    vm->globals[ip_global(a, "batches")] = batches[size - 1];
    vm->globals[ip_global(a, "inner")] = 1500;
    vm->globals[ip_global(a, "listn")] = 240;

    uint64_t executed = 0;
    int err = ip_run(vm, a->code, a->f, entry, &executed);
    if (err) { rc = 10 + err; goto fail; }

    uint64_t h = IA_FNV_BASIS;
    h = ia_mix(h, (uint64_t)vm->globals[ip_global(a, "result")]);
    h = ia_mix(h, executed);
    h = ia_mix(h, vm->dcap);
    h = ia_mix(h, (uint64_t)a->ncode);
    h = ia_fnv(h, a->code, (size_t)a->ncode * 4);
    ia_fill(out, h, (double)vm->globals[ip_global(a, "result")], (double)executed, "bytecodes");
    rc = 0;
fail:
    if (vm) {
        free(vm->stack); free(vm->locals); free(vm->frames); free(vm->str);
        free(vm->dk); free(vm->dh); free(vm->dv); free(vm->lists); free(vm->lpool);
    }
    if (a) free(a->code);
    free(a); free(vm);
    return rc;
}

// ── compile: a compiler front and middle end ────────────────────────────

/// A growable byte buffer; `fail` latches on allocation failure.
typedef struct { char *p; size_t n, cap; int fail; } cc_buf;

static void cc_put(cc_buf *b, const char *s, size_t n) {
    if (b->fail) return;
    if (b->n + n + 1 > b->cap) {
        size_t nc = b->cap ? b->cap * 2 : 4096;
        while (nc < b->n + n + 1) nc *= 2;
        char *p = (char *)realloc(b->p, nc);
        if (!p) { b->fail = 1; return; }
        b->p = p; b->cap = nc;
    }
    memcpy(b->p + b->n, s, n);
    b->n += n;
    b->p[b->n] = 0;
}
static void cc_puts(cc_buf *b, const char *s) { cc_put(b, s, strlen(s)); }
static void cc_puti(cc_buf *b, int64_t v) {
    char t[24]; int k = 0;
    uint64_t u = v < 0 ? 0 - (uint64_t)v : (uint64_t)v;
    do { t[k++] = (char)('0' + u % 10); u /= 10; } while (u);
    if (v < 0) t[k++] = '-';
    char r[24];
    for (int i = 0; i < k; i++) r[i] = t[k - 1 - i];
    cc_put(b, r, (size_t)k);
}

// Binary operators, shared by the AST, the folder and the IR.
enum { CO_ADD, CO_SUB, CO_MUL, CO_DIV, CO_MOD, CO_AND, CO_OR, CO_XOR,
       CO_LT, CO_GT, CO_LE, CO_GE, CO_EQ, CO_NE, CO_NOPS };
static const char cc_opsrc[CO_NOPS][3] = {"+", "-", "*", "/", "%", "&", "|", "^",
                                          "<", ">", "<=", ">=", "==", "!="};
static const char cc_opasm[CO_NOPS][6] = {"add", "sub", "mul", "sdiv", "srem", "and",
                                          "orr", "eor", "slt", "sgt", "sle", "sge",
                                          "seq", "sne"};

static int cc_commutes(int op) {
    return op == CO_ADD || op == CO_MUL || op == CO_AND || op == CO_OR ||
           op == CO_XOR || op == CO_EQ || op == CO_NE;
}

// Folds `a op b` with the target's wrap-around semantics; 0 if it traps.
static int cc_eval(int op, int64_t a, int64_t b, int64_t *r) {
    uint64_t ua = (uint64_t)a, ub = (uint64_t)b;
    switch (op) {
    case CO_ADD: *r = (int64_t)(ua + ub); return 1;
    case CO_SUB: *r = (int64_t)(ua - ub); return 1;
    case CO_MUL: *r = (int64_t)(ua * ub); return 1;
    case CO_DIV: if (b == 0 || (b == -1 && a == INT64_MIN)) return 0; *r = a / b; return 1;
    case CO_MOD: if (b == 0 || (b == -1 && a == INT64_MIN)) return 0; *r = a % b; return 1;
    case CO_AND: *r = a & b; return 1;
    case CO_OR: *r = a | b; return 1;
    case CO_XOR: *r = a ^ b; return 1;
    case CO_LT: *r = a < b; return 1;
    case CO_GT: *r = a > b; return 1;
    case CO_LE: *r = a <= b; return 1;
    case CO_GE: *r = a >= b; return 1;
    case CO_EQ: *r = a == b; return 1;
    case CO_NE: *r = a != b; return 1;
    }
    return 0;
}

// ── Source generator: a module of functions in a small C-like language ──

typedef struct {
    ia_rng r; cc_buf *b;
    int vars[96]; int nvars;     // in scope: id < 0 → param -id-1, else local
    int nextvar, nfuncs_before, nparams, depth;
    size_t rep_off, rep_len; int rep_nvars, pops; int rep_pops;
} cc_gen;

static void cc_gvar(cc_gen *g, int id) {
    if (id < 0) { cc_puts(g->b, "a"); cc_puti(g->b, -id - 1); }
    else { cc_puts(g->b, "v"); cc_puti(g->b, id); }
}

static void cc_gexpr(cc_gen *g, int depth) {
    uint32_t c = ia_below(&g->r, 100);
    if (depth <= 0 || c < 22) {
        uint32_t k = ia_below(&g->r, 100);
        if (k < 55 && g->nvars) cc_gvar(g, g->vars[ia_below(&g->r, (uint32_t)g->nvars)]);
        else if (k < 70) cc_puti(g->b, (int64_t)ia_below(&g->r, 3));   // 0, 1, 2: identities
        else cc_puti(g->b, (int64_t)ia_below(&g->r, 1000));
        return;
    }
    if (c < 30 && g->nfuncs_before > 0 && depth >= 2) {          // call an earlier function
        int f = (int)ia_below(&g->r, (uint32_t)g->nfuncs_before);
        int na = 1 + (int)((uint32_t)f % 3);
        cc_puts(g->b, "f"); cc_puti(g->b, f); cc_puts(g->b, "(");
        for (int i = 0; i < na; i++) {
            if (i) cc_puts(g->b, ", ");
            cc_gexpr(g, depth - 2);
        }
        cc_puts(g->b, ")");
        return;
    }
    if (c < 35) { cc_puts(g->b, "-"); cc_gexpr(g, depth - 1); return; }
    if (c < 42) {                                                // a constant subtree
        cc_puts(g->b, "(");
        cc_puti(g->b, (int64_t)ia_below(&g->r, 50));
        cc_puts(g->b, cc_opsrc[ia_below(&g->r, 3)]);
        cc_puti(g->b, (int64_t)ia_below(&g->r, 50) + 1);
        cc_puts(g->b, ")");
        return;
    }
    static const uint8_t pick[20] = {CO_ADD, CO_ADD, CO_ADD, CO_SUB, CO_SUB, CO_MUL, CO_MUL,
                                     CO_MUL, CO_DIV, CO_MOD, CO_AND, CO_OR, CO_XOR, CO_LT,
                                     CO_GT, CO_LE, CO_GE, CO_EQ, CO_NE, CO_ADD};
    int op = pick[ia_below(&g->r, 20)];
    cc_puts(g->b, "(");
    cc_gexpr(g, depth - 1);
    cc_puts(g->b, " "); cc_puts(g->b, cc_opsrc[op]); cc_puts(g->b, " ");
    cc_gexpr(g, depth - 1);
    cc_puts(g->b, ")");
}

static void cc_gindent(cc_gen *g) { for (int i = 0; i <= g->depth; i++) cc_puts(g->b, "  "); }

static void cc_gblock(cc_gen *g, int nstmts);

static void cc_gstmt(cc_gen *g) {
    uint32_t c = ia_below(&g->r, 100);
    cc_gindent(g);
    if (c < 34 || g->nvars == 0) {                               // declaration
        int id = g->nextvar++;
        cc_puts(g->b, "var "); cc_gvar(g, id); cc_puts(g->b, " = ");
        size_t at = g->b->n;
        cc_gexpr(g, 4);
        g->rep_off = at; g->rep_len = g->b->n - at; g->rep_nvars = g->nvars; g->rep_pops = g->pops;
        cc_puts(g->b, ";\n");
        if (g->nvars < 96) g->vars[g->nvars++] = id;
    } else if (c < 62) {                                         // assignment
        cc_gvar(g, g->vars[ia_below(&g->r, (uint32_t)g->nvars)]);
        cc_puts(g->b, " = ");
        cc_gexpr(g, 4);
        cc_puts(g->b, ";\n");
    } else if (c < 72 && g->rep_len && g->rep_pops == g->pops && g->rep_len < 400) {
        // repeat an earlier expression: food for common-subexpression elimination
        int id = g->nextvar++;
        cc_puts(g->b, "var "); cc_gvar(g, id); cc_puts(g->b, " = ");
        char tmp[400];
        memcpy(tmp, g->b->p + g->rep_off, g->rep_len);
        cc_put(g->b, tmp, g->rep_len);
        cc_puts(g->b, " + 1;\n");
        if (g->nvars < 96) g->vars[g->nvars++] = id;
    } else if (c < 86 && g->depth < 3) {
        cc_puts(g->b, "if (");
        cc_gexpr(g, 2);
        cc_puts(g->b, ") {\n");
        cc_gblock(g, 2 + (int)ia_below(&g->r, 4));
        cc_gindent(g);
        if (ia_below(&g->r, 2)) {
            cc_puts(g->b, "} else {\n");
            cc_gblock(g, 1 + (int)ia_below(&g->r, 4));
            cc_gindent(g);
        }
        cc_puts(g->b, "}\n");
    } else if (c < 95 && g->depth < 3) {
        cc_puts(g->b, "while (");
        cc_gexpr(g, 2);
        cc_puts(g->b, ") {\n");
        cc_gblock(g, 2 + (int)ia_below(&g->r, 4));
        cc_gindent(g);
        cc_puts(g->b, "}\n");
    } else {
        cc_puts(g->b, "if (");
        cc_gexpr(g, 1);
        cc_puts(g->b, ") {\n");
        g->depth++; cc_gindent(g); g->depth--;
        cc_puts(g->b, "return ");
        cc_gexpr(g, 3);
        cc_puts(g->b, ";\n");
        cc_gindent(g);
        cc_puts(g->b, "}\n");
    }
}

static void cc_gblock(cc_gen *g, int nstmts) {
    int saved = g->nvars;
    g->depth++;
    for (int i = 0; i < nstmts; i++) cc_gstmt(g);
    g->depth--;
    g->nvars = saved;
    g->pops++;
}

static void cc_generate(cc_buf *b, uint64_t seed, int nfuncs) {
    cc_gen g;
    memset(&g, 0, sizeof g);
    g.r.s = seed; g.b = b;
    for (int f = 0; f < nfuncs; f++) {
        g.nfuncs_before = f;
        g.nparams = 1 + (f % 3);
        g.nvars = 0; g.nextvar = 0; g.rep_len = 0; g.depth = 0; g.pops = 0;
        cc_puts(b, "fn f"); cc_puti(b, f); cc_puts(b, "(");
        for (int i = 0; i < g.nparams; i++) {
            if (i) cc_puts(b, ", ");
            cc_puts(b, "a"); cc_puti(b, i);
            g.vars[g.nvars++] = -i - 1;
        }
        cc_puts(b, ") {\n");
        int n = 14 + (int)ia_below(&g.r, 18);
        for (int i = 0; i < n; i++) cc_gstmt(&g);
        cc_puts(b, "  return ");
        cc_gexpr(&g, 3);
        cc_puts(b, ";\n}\n\n");
    }
}

// ── Lexer ───────────────────────────────────────────────────────────────

enum { TK_EOF, TK_NUM, TK_ID, TK_FN, TK_VAR, TK_IF, TK_ELSE, TK_WHILE, TK_RETURN,
       TK_LP, TK_RP, TK_LB, TK_RB, TK_COMMA, TK_SEMI, TK_ASSIGN, TK_BANG,
       TK_OP /* binary operator, v = CO_ */ };
typedef struct { uint8_t k; int32_t sym; int64_t v; } cc_tok;

#define CC_SYMCAP 4096
typedef struct {
    int32_t slot[CC_SYMCAP];          // hash → sym + 1
    uint32_t off[CC_SYMCAP], len[CC_SYMCAP];
    char *names; size_t nnames, capnames;
    int nsyms;
} cc_syms;

static int cc_intern(cc_syms *s, const char *p, uint32_t n) {
    uint32_t h = (uint32_t)ia_fnv(IA_FNV_BASIS, p, n), j = h & (CC_SYMCAP - 1);
    while (s->slot[j]) {
        int id = s->slot[j] - 1;
        if (s->len[id] == n && !memcmp(s->names + s->off[id], p, n)) return id;
        j = (j + 1) & (CC_SYMCAP - 1);
    }
    if (s->nsyms >= CC_SYMCAP / 2) return -1;
    if (s->nnames + n > s->capnames) {
        size_t nc = s->capnames ? s->capnames * 2 : 8192;
        while (nc < s->nnames + n) nc *= 2;
        char *q = (char *)realloc(s->names, nc);
        if (!q) return -1;
        s->names = q; s->capnames = nc;
    }
    int id = s->nsyms++;
    memcpy(s->names + s->nnames, p, n);
    s->off[id] = (uint32_t)s->nnames; s->len[id] = n; s->nnames += n;
    s->slot[j] = id + 1;
    return id;
}

typedef struct { cc_tok *t; int n, cap; } cc_toks;

static int cc_lex(const char *src, size_t len, cc_syms *sy, cc_toks *out, const int kw[6]) {
    out->n = 0;
    size_t i = 0;
    for (;;) {
        while (i < len && (src[i] == ' ' || src[i] == '\n' || src[i] == '\t')) i++;
        if (out->n + 1 >= out->cap) {
            int nc = out->cap ? out->cap * 2 : 4096;
            cc_tok *p = (cc_tok *)realloc(out->t, (size_t)nc * sizeof *p);
            if (!p) return -1;
            out->t = p; out->cap = nc;
        }
        cc_tok *t = &out->t[out->n++];
        t->sym = -1; t->v = 0;
        if (i >= len) { t->k = TK_EOF; return 0; }
        char c = src[i];
        if (c >= '0' && c <= '9') {
            int64_t v = 0;
            while (i < len && src[i] >= '0' && src[i] <= '9')
                v = (int64_t)((uint64_t)v * 10 + (uint64_t)(src[i++] - '0'));
            t->k = TK_NUM; t->v = v;
            continue;
        }
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_') {
            size_t s = i;
            while (i < len && ((src[i] >= 'a' && src[i] <= 'z') || (src[i] >= 'A' && src[i] <= 'Z') ||
                               (src[i] >= '0' && src[i] <= '9') || src[i] == '_'))
                i++;
            int id = cc_intern(sy, src + s, (uint32_t)(i - s));
            if (id < 0) return -1;
            t->k = TK_ID; t->sym = id;
            for (int k = 0; k < 6; k++) if (kw[k] == id) t->k = (uint8_t)(TK_FN + k);
            continue;
        }
        char d = i + 1 < len ? src[i + 1] : 0;
        i++;
        switch (c) {
        case '(': t->k = TK_LP; break;
        case ')': t->k = TK_RP; break;
        case '{': t->k = TK_LB; break;
        case '}': t->k = TK_RB; break;
        case ',': t->k = TK_COMMA; break;
        case ';': t->k = TK_SEMI; break;
        case '+': t->k = TK_OP; t->v = CO_ADD; break;
        case '-': t->k = TK_OP; t->v = CO_SUB; break;
        case '*': t->k = TK_OP; t->v = CO_MUL; break;
        case '/': t->k = TK_OP; t->v = CO_DIV; break;
        case '%': t->k = TK_OP; t->v = CO_MOD; break;
        case '&': t->k = TK_OP; t->v = CO_AND; break;
        case '|': t->k = TK_OP; t->v = CO_OR; break;
        case '^': t->k = TK_OP; t->v = CO_XOR; break;
        case '<': t->k = TK_OP; t->v = CO_LT; if (d == '=') { i++; t->v = CO_LE; } break;
        case '>': t->k = TK_OP; t->v = CO_GT; if (d == '=') { i++; t->v = CO_GE; } break;
        case '=': if (d == '=') { i++; t->k = TK_OP; t->v = CO_EQ; } else t->k = TK_ASSIGN; break;
        case '!': if (d == '=') { i++; t->k = TK_OP; t->v = CO_NE; } else t->k = TK_BANG; break;
        default: return -1;
        }
    }
}

// ── Parser: recursive descent to an AST ─────────────────────────────────

enum { N_NUM, N_VAR, N_BIN, N_NEG, N_NOT, N_CALL, N_ARG,
       N_DECL, N_ASSIGN, N_IF, N_WHILE, N_RET, N_BLOCK };
typedef struct { uint8_t kind, op; int32_t a, b, c, next; int64_t v; } cc_node;

#define CC_MAXF 1024
typedef struct {
    const cc_tok *t; int pos;
    cc_node *nd; int nn, capn;
    int scope_sym[256], scope_slot[256], nscope;
    int nslots;
    int *sym_func;                  // sym → function index + 1
    struct { int body, nparams, nslots, sym; } fn[CC_MAXF];
    int nfn;
    int err;
} cc_parser;

static int cc_node_new(cc_parser *p, int kind) {
    if (p->nn >= p->capn) {
        int nc = p->capn ? p->capn * 2 : 8192;
        cc_node *q = (cc_node *)realloc(p->nd, (size_t)nc * sizeof *q);
        if (!q) { p->err = 1; return 0; }
        p->nd = q; p->capn = nc;
    }
    cc_node *n = &p->nd[p->nn];
    memset(n, 0, sizeof *n);
    n->kind = (uint8_t)kind; n->a = n->b = n->c = n->next = -1;
    return p->nn++;
}

static int cc_expect(cc_parser *p, int k) {
    if (p->t[p->pos].k != k) { p->err = 1; return 0; }
    p->pos++;
    return 1;
}

static int cc_lookup(cc_parser *p, int sym) {
    for (int i = p->nscope - 1; i >= 0; i--) if (p->scope_sym[i] == sym) return p->scope_slot[i];
    p->err = 1;
    return 0;
}

static int cc_pexpr(cc_parser *p, int minprec);

static int cc_pprimary(cc_parser *p) {
    if (p->err) return 0;
    const cc_tok *t = &p->t[p->pos];
    if (t->k == TK_NUM) { int n = cc_node_new(p, N_NUM); if (!p->err) p->nd[n].v = t->v; p->pos++; return n; }
    if (t->k == TK_OP && t->v == CO_SUB) {
        p->pos++;
        int a = cc_pprimary(p), n = cc_node_new(p, N_NEG);
        if (!p->err) p->nd[n].a = a;
        return n;
    }
    if (t->k == TK_BANG) {
        p->pos++;
        int a = cc_pprimary(p), n = cc_node_new(p, N_NOT);
        if (!p->err) p->nd[n].a = a;
        return n;
    }
    if (t->k == TK_LP) {
        p->pos++;
        int e = cc_pexpr(p, 0);
        cc_expect(p, TK_RP);
        return e;
    }
    if (t->k == TK_ID) {
        p->pos++;
        if (p->t[p->pos].k == TK_LP) {                         // call
            p->pos++;
            int f = p->sym_func[t->sym] - 1;
            if (f < 0) { p->err = 1; return 0; }
            int n = cc_node_new(p, N_CALL), last = -1, na = 0;
            if (p->err) return 0;
            p->nd[n].a = f;
            while (!p->err && p->t[p->pos].k != TK_RP) {
                if (na) cc_expect(p, TK_COMMA);
                int e = cc_pexpr(p, 0), arg = cc_node_new(p, N_ARG);
                if (p->err) return 0;
                p->nd[arg].a = e;
                if (last < 0) p->nd[n].b = arg; else p->nd[last].next = arg;
                last = arg; na++;
            }
            cc_expect(p, TK_RP);
            if (!p->err) p->nd[n].c = na;
            return n;
        }
        int n = cc_node_new(p, N_VAR);
        if (!p->err) p->nd[n].a = cc_lookup(p, t->sym);
        return n;
    }
    p->err = 1;
    return 0;
}

static int cc_prec(int op) {
    switch (op) {
    case CO_MUL: case CO_DIV: case CO_MOD: return 6;
    case CO_ADD: case CO_SUB: return 5;
    case CO_LT: case CO_GT: case CO_LE: case CO_GE: return 4;
    case CO_EQ: case CO_NE: return 3;
    case CO_AND: return 2;
    case CO_XOR: return 1;
    default: return 0;   // CO_OR
    }
}

// Precedence climbing over the binary operators (all left-associative).
static int cc_pexpr(cc_parser *p, int minprec) {
    int lhs = cc_pprimary(p);
    while (!p->err && p->t[p->pos].k == TK_OP) {
        int op = (int)p->t[p->pos].v, pr = cc_prec(op);
        if (pr < minprec) break;
        p->pos++;
        int rhs = cc_pexpr(p, pr + 1), n = cc_node_new(p, N_BIN);
        if (p->err) return 0;
        p->nd[n].op = (uint8_t)op; p->nd[n].a = lhs; p->nd[n].b = rhs;
        lhs = n;
    }
    return lhs;
}

static int cc_pblock(cc_parser *p);

static int cc_pstmt(cc_parser *p) {
    if (p->err) return 0;
    const cc_tok *t = &p->t[p->pos];
    int n;
    switch (t->k) {
    case TK_VAR: {
        p->pos++;
        int sym = p->t[p->pos].sym;
        cc_expect(p, TK_ID); cc_expect(p, TK_ASSIGN);
        int e = cc_pexpr(p, 0);
        cc_expect(p, TK_SEMI);
        n = cc_node_new(p, N_DECL);
        if (p->err || p->nscope >= 256) { p->err = 1; return 0; }
        p->scope_sym[p->nscope] = sym; p->scope_slot[p->nscope++] = p->nslots;
        p->nd[n].a = p->nslots++; p->nd[n].b = e;
        return n;
    }
    case TK_ID: {
        int slot = cc_lookup(p, t->sym);
        p->pos++;
        cc_expect(p, TK_ASSIGN);
        int e = cc_pexpr(p, 0);
        cc_expect(p, TK_SEMI);
        n = cc_node_new(p, N_ASSIGN);
        if (!p->err) { p->nd[n].a = slot; p->nd[n].b = e; }
        return n;
    }
    case TK_IF: {
        p->pos++;
        cc_expect(p, TK_LP);
        int c = cc_pexpr(p, 0);
        cc_expect(p, TK_RP);
        int th = cc_pblock(p), el = -1;
        if (!p->err && p->t[p->pos].k == TK_ELSE) { p->pos++; el = cc_pblock(p); }
        n = cc_node_new(p, N_IF);
        if (!p->err) { p->nd[n].a = c; p->nd[n].b = th; p->nd[n].c = el; }
        return n;
    }
    case TK_WHILE: {
        p->pos++;
        cc_expect(p, TK_LP);
        int c = cc_pexpr(p, 0);
        cc_expect(p, TK_RP);
        int body = cc_pblock(p);
        n = cc_node_new(p, N_WHILE);
        if (!p->err) { p->nd[n].a = c; p->nd[n].b = body; }
        return n;
    }
    case TK_RETURN: {
        p->pos++;
        int e = cc_pexpr(p, 0);
        cc_expect(p, TK_SEMI);
        n = cc_node_new(p, N_RET);
        if (!p->err) p->nd[n].a = e;
        return n;
    }
    default:
        p->err = 1;
        return 0;
    }
}

static int cc_pblock(cc_parser *p) {
    cc_expect(p, TK_LB);
    int saved = p->nscope;
    int blk = cc_node_new(p, N_BLOCK), last = -1;
    while (!p->err && p->t[p->pos].k != TK_RB && p->t[p->pos].k != TK_EOF) {
        int s = cc_pstmt(p);
        if (p->err) break;
        if (last < 0) p->nd[blk].a = s; else p->nd[last].next = s;
        last = s;
    }
    cc_expect(p, TK_RB);
    p->nscope = saved;
    return blk;
}

static void cc_parse(cc_parser *p) {
    while (!p->err && p->t[p->pos].k == TK_FN) {
        p->pos++;
        int sym = p->t[p->pos].sym;
        cc_expect(p, TK_ID);
        if (p->err || p->nfn >= CC_MAXF) { p->err = 1; return; }
        int f = p->nfn;
        p->nscope = 0; p->nslots = 0;
        cc_expect(p, TK_LP);
        while (!p->err && p->t[p->pos].k == TK_ID) {
            p->scope_sym[p->nscope] = p->t[p->pos].sym; p->scope_slot[p->nscope++] = p->nslots++;
            p->pos++;
            if (p->t[p->pos].k == TK_COMMA) p->pos++;
        }
        cc_expect(p, TK_RP);
        p->fn[f].nparams = p->nslots;
        p->fn[f].sym = sym;
        p->sym_func[sym] = f + 1;    // visible to its own body (recursion) and later ones
        p->fn[f].body = cc_pblock(p);
        p->fn[f].nslots = p->nslots;
        p->nfn++;
    }
    if (!p->err && p->t[p->pos].k != TK_EOF) p->err = 1;
}

// ── Constant folding and algebraic simplification on the AST ────────────

static int cc_pure(const cc_node *nd, int n) {
    switch (nd[n].kind) {
    case N_NUM: case N_VAR: return 1;
    case N_BIN: return cc_pure(nd, nd[n].a) && cc_pure(nd, nd[n].b);
    case N_NEG: case N_NOT: return cc_pure(nd, nd[n].a);
    default: return 0;
    }
}

static int cc_isnum(const cc_node *nd, int n, int64_t v) { return nd[n].kind == N_NUM && nd[n].v == v; }

// Returns the (possibly replaced) node index; counts folds in *folds.
static int cc_fold(cc_node *nd, int n, int *folds) {
    cc_node *x = &nd[n];
    switch (x->kind) {
    case N_NEG: case N_NOT:
        x->a = cc_fold(nd, x->a, folds);
        if (nd[x->a].kind == N_NUM) {
            int64_t v = nd[x->a].v;
            x->v = x->kind == N_NEG ? (int64_t)(0 - (uint64_t)v) : (int64_t)(v == 0);
            x->kind = N_NUM;
            (*folds)++;
        }
        return n;
    case N_BIN: {
        x->a = cc_fold(nd, x->a, folds);
        x->b = cc_fold(nd, x->b, folds);
        int a = x->a, b = x->b;
        int64_t r;
        if (nd[a].kind == N_NUM && nd[b].kind == N_NUM && cc_eval(x->op, nd[a].v, nd[b].v, &r)) {
            x->kind = N_NUM; x->v = r; (*folds)++;
            return n;
        }
        switch (x->op) {
        case CO_ADD: case CO_OR: case CO_XOR:
            if (cc_isnum(nd, b, 0)) { (*folds)++; return a; }
            if (cc_isnum(nd, a, 0)) { (*folds)++; return b; }
            break;
        case CO_SUB:
            if (cc_isnum(nd, b, 0)) { (*folds)++; return a; }
            break;
        case CO_MUL:
            if (cc_isnum(nd, b, 1)) { (*folds)++; return a; }
            if (cc_isnum(nd, a, 1)) { (*folds)++; return b; }
            if ((cc_isnum(nd, a, 0) && cc_pure(nd, b)) || (cc_isnum(nd, b, 0) && cc_pure(nd, a))) {
                x->kind = N_NUM; x->v = 0; (*folds)++;
                return n;
            }
            if (cc_isnum(nd, b, 2) && cc_pure(nd, a)) { x->op = CO_ADD; x->b = a; (*folds)++; return n; }  // x*2 → x+x
            break;
        case CO_DIV:
            if (cc_isnum(nd, b, 1)) { (*folds)++; return a; }
            break;
        case CO_AND:
            if ((cc_isnum(nd, a, 0) && cc_pure(nd, b)) || (cc_isnum(nd, b, 0) && cc_pure(nd, a))) {
                x->kind = N_NUM; x->v = 0; (*folds)++;
                return n;
            }
            break;
        }
        return n;
    }
    case N_CALL:
        for (int arg = x->b; arg >= 0; arg = nd[arg].next) nd[arg].a = cc_fold(nd, nd[arg].a, folds);
        return n;
    default:
        return n;
    }
}

// Folds statements; `if` on a constant keeps one arm, `while (0)` goes.
static void cc_fold_block(cc_node *nd, int blk, int *folds) {
    int prev = -1;
    for (int s = nd[blk].a; s >= 0; s = nd[s].next) {
        cc_node *x = &nd[s];
        switch (x->kind) {
        case N_DECL: case N_ASSIGN: x->b = cc_fold(nd, x->b, folds); break;
        case N_RET: x->a = cc_fold(nd, x->a, folds); break;
        case N_IF:
            x->a = cc_fold(nd, x->a, folds);
            cc_fold_block(nd, x->b, folds);
            if (x->c >= 0) cc_fold_block(nd, x->c, folds);
            if (nd[x->a].kind == N_NUM) {     // becomes a plain block
                int keep = nd[x->a].v ? x->b : x->c;
                (*folds)++;
                if (keep < 0) { x->kind = N_BLOCK; x->a = -1; }
                else { x->kind = N_BLOCK; x->a = nd[keep].a; }
            }
            break;
        case N_WHILE:
            x->a = cc_fold(nd, x->a, folds);
            cc_fold_block(nd, x->b, folds);
            if (cc_isnum(nd, x->a, 0)) { x->kind = N_BLOCK; x->a = -1; (*folds)++; }
            break;
        case N_BLOCK:
            cc_fold_block(nd, s, folds);
            break;
        }
        prev = s;
    }
    (void)prev;
}

// ── Lowering to three-address IR ───────────────────────────────────────

enum { I_NOP, I_CONST, I_MOV, I_BIN, I_NEG, I_NOT, I_ARG, I_CALL, I_JMP, I_BRZ,
       I_LABEL, I_RET };
typedef struct { uint8_t op, bop; int32_t d, a, b; int64_t imm; } cc_ins;

typedef struct { cc_ins *ins; int n, cap, nv, nlab, nslots, err; } cc_ir;

static void cc_emit_ir(cc_ir *ir, int op, int bop, int d, int a, int b, int64_t imm) {
    if (ir->n >= ir->cap) {
        int nc = ir->cap ? ir->cap * 2 : 1024;
        cc_ins *p = (cc_ins *)realloc(ir->ins, (size_t)nc * sizeof *p);
        if (!p) { ir->err = 1; return; }
        ir->ins = p; ir->cap = nc;
    }
    cc_ins *x = &ir->ins[ir->n++];
    x->op = (uint8_t)op; x->bop = (uint8_t)bop; x->d = d; x->a = a; x->b = b; x->imm = imm;
}

static int cc_lexpr(cc_ir *ir, const cc_node *nd, int n) {
    const cc_node *x = &nd[n];
    int t, a, b;
    switch (x->kind) {
    case N_NUM: t = ir->nv++; cc_emit_ir(ir, I_CONST, 0, t, -1, -1, x->v); return t;
    case N_VAR: return x->a;
    case N_BIN:
        a = cc_lexpr(ir, nd, x->a); b = cc_lexpr(ir, nd, x->b);
        t = ir->nv++; cc_emit_ir(ir, I_BIN, x->op, t, a, b, 0); return t;
    case N_NEG: case N_NOT:
        a = cc_lexpr(ir, nd, x->a);
        t = ir->nv++; cc_emit_ir(ir, x->kind == N_NEG ? I_NEG : I_NOT, 0, t, a, -1, 0); return t;
    case N_CALL: {
        int args[16], na = 0;
        for (int g = x->b; g >= 0 && na < 16; g = nd[g].next) args[na++] = cc_lexpr(ir, nd, nd[g].a);
        for (int i = 0; i < na; i++) cc_emit_ir(ir, I_ARG, 0, -1, args[i], -1, i);
        t = ir->nv++; cc_emit_ir(ir, I_CALL, 0, t, -1, na, x->a); return t;
    }
    }
    ir->err = 1;
    return 0;
}

static void cc_lstmts(cc_ir *ir, const cc_node *nd, int s) {
    for (; s >= 0 && !ir->err; s = nd[s].next) {
        const cc_node *x = &nd[s];
        switch (x->kind) {
        case N_DECL: case N_ASSIGN: {
            int v = cc_lexpr(ir, nd, x->b);
            if (v >= ir->nslots && ir->n > 0 && ir->ins[ir->n - 1].d == v) ir->ins[ir->n - 1].d = x->a;
            else cc_emit_ir(ir, I_MOV, 0, x->a, v, -1, 0);
            break;
        }
        case N_IF: {
            int c = cc_lexpr(ir, nd, x->a), le = ir->nlab++, lend = ir->nlab++;
            cc_emit_ir(ir, I_BRZ, 0, -1, c, -1, le);
            cc_lstmts(ir, nd, nd[x->b].a);
            if (x->c >= 0) {
                cc_emit_ir(ir, I_JMP, 0, -1, -1, -1, lend);
                cc_emit_ir(ir, I_LABEL, 0, -1, -1, -1, le);
                cc_lstmts(ir, nd, nd[x->c].a);
                cc_emit_ir(ir, I_LABEL, 0, -1, -1, -1, lend);
            } else {
                cc_emit_ir(ir, I_LABEL, 0, -1, -1, -1, le);
            }
            break;
        }
        case N_WHILE: {
            int ltop = ir->nlab++, lend = ir->nlab++;
            cc_emit_ir(ir, I_LABEL, 0, -1, -1, -1, ltop);
            int c = cc_lexpr(ir, nd, x->a);
            cc_emit_ir(ir, I_BRZ, 0, -1, c, -1, lend);
            cc_lstmts(ir, nd, nd[x->b].a);
            cc_emit_ir(ir, I_JMP, 0, -1, -1, -1, ltop);
            cc_emit_ir(ir, I_LABEL, 0, -1, -1, -1, lend);
            break;
        }
        case N_RET: {
            int v = cc_lexpr(ir, nd, x->a);
            cc_emit_ir(ir, I_RET, 0, -1, v, -1, 0);
            break;
        }
        case N_BLOCK:
            cc_lstmts(ir, nd, x->a);
            break;
        }
    }
}

// Which operands an instruction reads; returns how many (0..2).
static int cc_uses(const cc_ins *x, int32_t **u) {
    switch (x->op) {
    case I_MOV: case I_NEG: case I_NOT: case I_ARG: case I_BRZ: case I_RET:
        u[0] = (int32_t *)&x->a; return 1;
    case I_BIN: u[0] = (int32_t *)&x->a; u[1] = (int32_t *)&x->b; return 2;
    default: return 0;
    }
}
static int cc_defines(const cc_ins *x) {
    return x->op == I_CONST || x->op == I_MOV || x->op == I_BIN || x->op == I_NEG ||
           x->op == I_NOT || x->op == I_CALL;
}

// ── Per-function analysis scratch ───────────────────────────────────────

typedef struct { uint8_t *p; size_t used, cap; int fail; } cc_arena;
static void *cc_alloc(cc_arena *a, size_t n) {
    n = (n + 15) & ~(size_t)15;
    if (a->fail || a->used + n > a->cap) { a->fail = 1; return NULL; }
    void *r = a->p + a->used;
    a->used += n;
    memset(r, 0, n);
    return r;
}

typedef struct {
    int nb, W;
    int *bstart, *bend, *succ;          // succ: 2 per block, -1 = none
    uint64_t *use, *def, *in, *out;
} cc_cfg;

static int cc_build_cfg(cc_arena *ar, const cc_ir *ir, cc_cfg *g) {
    int n = ir->n;
    int *lead = (int *)cc_alloc(ar, (size_t)(n + 1) * sizeof(int));
    int *lab_block = (int *)cc_alloc(ar, (size_t)(ir->nlab + 1) * sizeof(int));
    if (ar->fail) return -1;
    int nb = 0;
    for (int i = 0; i < n; i++) {
        int op = ir->ins[i].op, pop = i ? ir->ins[i - 1].op : I_JMP;
        lead[i] = i == 0 || op == I_LABEL || pop == I_JMP || pop == I_BRZ || pop == I_RET;
        nb += lead[i];
    }
    g->nb = nb;
    g->W = (ir->nv + 63) / 64;
    g->bstart = (int *)cc_alloc(ar, (size_t)nb * sizeof(int));
    g->bend = (int *)cc_alloc(ar, (size_t)nb * sizeof(int));
    g->succ = (int *)cc_alloc(ar, (size_t)nb * 2 * sizeof(int));
    size_t bs = (size_t)nb * (size_t)g->W * 8;
    g->use = (uint64_t *)cc_alloc(ar, bs); g->def = (uint64_t *)cc_alloc(ar, bs);
    g->in = (uint64_t *)cc_alloc(ar, bs); g->out = (uint64_t *)cc_alloc(ar, bs);
    if (ar->fail) return -1;
    int b = -1;
    for (int i = 0; i < n; i++) {
        if (lead[i]) { if (b >= 0) g->bend[b] = i; g->bstart[++b] = i; }
        if (ir->ins[i].op == I_LABEL) lab_block[ir->ins[i].imm] = b;
    }
    if (b >= 0) g->bend[b] = n;
    for (b = 0; b < nb; b++) {
        const cc_ins *last = &ir->ins[g->bend[b] - 1];
        int *s = &g->succ[2 * b];
        s[0] = s[1] = -1;
        if (last->op == I_JMP) s[0] = lab_block[last->imm];
        else if (last->op == I_BRZ) { s[0] = lab_block[last->imm]; s[1] = b + 1 < nb ? b + 1 : -1; }
        else if (last->op != I_RET) s[0] = b + 1 < nb ? b + 1 : -1;
    }
    return 0;
}

#define CC_BSET(s, v) ((s)[(v) >> 6] |= 1ull << ((v) & 63))
#define CC_BCLR(s, v) ((s)[(v) >> 6] &= ~(1ull << ((v) & 63)))
#define CC_BTST(s, v) (((s)[(v) >> 6] >> ((v) & 63)) & 1)

/// Backward liveness to a fixed point.
static void cc_liveness(const cc_ir *ir, cc_cfg *g) {
    int W = g->W;
    memset(g->use, 0, (size_t)g->nb * W * 8); memset(g->def, 0, (size_t)g->nb * W * 8);
    memset(g->in, 0, (size_t)g->nb * W * 8); memset(g->out, 0, (size_t)g->nb * W * 8);
    for (int b = 0; b < g->nb; b++) {
        uint64_t *U = g->use + (size_t)b * W, *D = g->def + (size_t)b * W;
        for (int i = g->bstart[b]; i < g->bend[b]; i++) {
            const cc_ins *x = &ir->ins[i];
            int32_t *u[2]; int nu = cc_uses(x, u);
            for (int k = 0; k < nu; k++) if (!CC_BTST(D, *u[k])) CC_BSET(U, *u[k]);
            if (cc_defines(x)) CC_BSET(D, x->d);
        }
    }
    int changed = 1;
    while (changed) {
        changed = 0;
        for (int b = g->nb - 1; b >= 0; b--) {
            uint64_t *O = g->out + (size_t)b * W, *I = g->in + (size_t)b * W;
            const uint64_t *U = g->use + (size_t)b * W, *D = g->def + (size_t)b * W;
            for (int k = 0; k < 2; k++) {
                int s = g->succ[2 * b + k];
                if (s < 0) continue;
                const uint64_t *SI = g->in + (size_t)s * W;
                for (int w = 0; w < W; w++) O[w] |= SI[w];
            }
            for (int w = 0; w < W; w++) {
                uint64_t ni = U[w] | (O[w] & ~D[w]);
                if (ni != I[w]) { I[w] = ni; changed = 1; }
            }
        }
    }
}

/// Dead-code elimination against liveness; returns instructions removed.
static int cc_dce(cc_ir *ir, const cc_cfg *g, uint64_t *live) {
    int removed = 0, W = g->W;
    for (int b = 0; b < g->nb; b++) {
        memcpy(live, g->out + (size_t)b * W, (size_t)W * 8);
        for (int i = g->bend[b] - 1; i >= g->bstart[b]; i--) {
            cc_ins *x = &ir->ins[i];
            if (x->op == I_NOP) continue;
            if (x->op == I_MOV && x->d == x->a) { x->op = I_NOP; removed++; continue; }
            if (cc_defines(x)) {
                if (x->op != I_CALL && !CC_BTST(live, x->d)) { x->op = I_NOP; removed++; continue; }
                CC_BCLR(live, x->d);
            }
            int32_t *u[2]; int nu = cc_uses(x, u);
            for (int k = 0; k < nu; k++) CC_BSET(live, *u[k]);
        }
    }
    return removed;
}

/// Local value numbering per basic block: common subexpressions become
/// copies, and copies propagate into later uses. Returns rewrites made.
#define CC_CSE 1024
typedef struct { int stamp; uint8_t op, bop; int32_t a, av, b, bv, d, dv; int64_t imm; } cc_cse;

static int cc_local_cse(cc_ir *ir, const cc_cfg *g, cc_arena *ar) {
    int nv = ir->nv, hits = 0;
    int *ver = (int *)cc_alloc(ar, (size_t)nv * sizeof(int));
    int *cps = (int *)cc_alloc(ar, (size_t)nv * sizeof(int));
    int *cpsv = (int *)cc_alloc(ar, (size_t)nv * sizeof(int));
    int *cpdv = (int *)cc_alloc(ar, (size_t)nv * sizeof(int));
    int *cpst = (int *)cc_alloc(ar, (size_t)nv * sizeof(int));
    cc_cse *tab = (cc_cse *)cc_alloc(ar, CC_CSE * sizeof(cc_cse));
    if (ar->fail) return -1;
    for (int b = 0; b < g->nb; b++) {
        int stamp = b + 1;
        for (int i = g->bstart[b]; i < g->bend[b]; i++) {
            cc_ins *x = &ir->ins[i];
            int32_t *u[2]; int nu = cc_uses(x, u);
            for (int k = 0; k < nu; k++) {
                int v = *u[k];
                if (cpst[v] == stamp && cpdv[v] == ver[v] && ver[cps[v]] == cpsv[v]) { *u[k] = cps[v]; hits++; }
            }
            if (x->op == I_CONST || x->op == I_BIN || x->op == I_NEG || x->op == I_NOT) {
                int a = x->a, bb = x->b;
                if (x->op == I_BIN && cc_commutes(x->bop) && a > bb) { int t = a; a = bb; bb = t; }
                int av = a >= 0 ? ver[a] : 0, bv = bb >= 0 ? ver[bb] : 0;
                uint64_t h = ia_mix(ia_mix(ia_mix((uint64_t)x->op * 31 + x->bop, (uint64_t)(uint32_t)a),
                                           (uint64_t)(uint32_t)bb), (uint64_t)x->imm);
                uint32_t j = (uint32_t)h & (CC_CSE - 1), probes = 0, slot = UINT32_MAX;
                int found = -1;
                while (probes++ < 64) {
                    cc_cse *e = &tab[j];
                    if (e->stamp != stamp) { slot = j; break; }
                    if (e->op == x->op && e->bop == x->bop && e->a == a && e->av == av && e->b == bb &&
                        e->bv == bv && e->imm == x->imm && ver[e->d] == e->dv) { found = e->d; break; }
                    j = (j + 1) & (CC_CSE - 1);
                }
                int d = x->d;
                if (found >= 0) {
                    x->op = I_MOV; x->a = found; x->b = -1; x->imm = 0; hits++;
                    ver[d]++;
                    if (found != d) { cpst[d] = stamp; cps[d] = found; cpsv[d] = ver[found]; cpdv[d] = ver[d]; }
                    continue;
                }
                ver[d]++;
                if (slot != UINT32_MAX) {
                    cc_cse *e = &tab[slot];
                    e->stamp = stamp; e->op = x->op; e->bop = x->bop; e->a = a; e->av = av;
                    e->b = bb; e->bv = bv; e->imm = x->imm; e->d = d; e->dv = ver[d];
                }
                continue;
            }
            if (cc_defines(x)) {
                ver[x->d]++;
                if (x->op == I_MOV && x->a != x->d) {
                    cpst[x->d] = stamp; cps[x->d] = x->a; cpsv[x->d] = ver[x->a]; cpdv[x->d] = ver[x->d];
                }
            }
        }
    }
    return hits;
}

// ── Linear-scan register allocation ─────────────────────────────────────

#define CC_K 6
typedef struct { int start, end, v; } cc_iv;

static int cc_iv_cmp(const void *pa, const void *pb) {
    const cc_iv *a = (const cc_iv *)pa, *b = (const cc_iv *)pb;
    if (a->start != b->start) return a->start < b->start ? -1 : 1;
    return a->v < b->v ? -1 : a->v > b->v;
}

/// Assigns loc[v] = register 0..K-1, or -(spill slot + 1). Returns the
/// number of spill slots used.
static int cc_linear_scan(const cc_ir *ir, const cc_cfg *g, cc_arena *ar, int *loc) {
    int nv = ir->nv, W = g->W;
    int *st = (int *)cc_alloc(ar, (size_t)nv * sizeof(int));
    int *en = (int *)cc_alloc(ar, (size_t)nv * sizeof(int));
    cc_iv *iv = (cc_iv *)cc_alloc(ar, (size_t)nv * sizeof(cc_iv));
    if (ar->fail) return -1;
    for (int v = 0; v < nv; v++) { st[v] = INT32_MAX; en[v] = -1; loc[v] = 0; }
    for (int v = 0; v < ir->nslots && v < nv; v++) { st[v] = 0; if (en[v] < 0) en[v] = 0; }
    int pos = 0;
    for (int b = 0; b < g->nb; b++) {
        int bs = pos;
        for (int i = g->bstart[b]; i < g->bend[b]; i++) {
            const cc_ins *x = &ir->ins[i];
            if (x->op == I_NOP) continue;
            pos++;
            int32_t *u[2]; int nu = cc_uses(x, u);
            for (int k = 0; k < nu; k++) {
                int v = *u[k];
                if (pos < st[v]) st[v] = pos;
                if (pos > en[v]) en[v] = pos;
            }
            if (cc_defines(x)) {
                if (pos < st[x->d]) st[x->d] = pos;
                if (pos > en[x->d]) en[x->d] = pos;
            }
        }
        int be = pos > bs ? pos : bs;
        const uint64_t *I = g->in + (size_t)b * W, *O = g->out + (size_t)b * W;
        for (int w = 0; w < W; w++) {
            uint64_t m = I[w] | O[w];
            while (m) {
                int v = w * 64 + __builtin_ctzll(m);
                m &= m - 1;
                if (CC_BTST(I, v)) { if (bs < st[v]) st[v] = bs; if (bs > en[v]) en[v] = bs; }
                if (CC_BTST(O, v)) { if (be > en[v]) en[v] = be; if (bs < st[v]) st[v] = bs; }
            }
        }
    }
    int n = 0;
    for (int v = 0; v < nv; v++) if (en[v] >= 0) { iv[n].start = st[v]; iv[n].end = en[v]; iv[n].v = v; n++; }
    qsort(iv, (size_t)n, sizeof *iv, cc_iv_cmp);
    int active[CC_K], na = 0, freeregs = (1 << CC_K) - 1, slots = 0;
    for (int i = 0; i < n; i++) {
        int k = 0;
        for (int j = 0; j < na; j++) {          // expire intervals that ended
            if (iv[active[j]].end < iv[i].start) freeregs |= 1 << loc[iv[active[j]].v];
            else active[k++] = active[j];
        }
        na = k;
        if (na == CC_K) {
            int last = active[na - 1];
            if (iv[last].end > iv[i].end) {     // spill the one that lives longest
                loc[iv[i].v] = loc[iv[last].v];
                loc[iv[last].v] = -(++slots);
                na--;
            } else {
                loc[iv[i].v] = -(++slots);
                continue;
            }
        } else {
            int r = __builtin_ctz((unsigned)freeregs);
            freeregs &= ~(1 << r);
            loc[iv[i].v] = r;
        }
        int j = na;                              // insert sorted by end
        while (j > 0 && iv[active[j - 1]].end > iv[i].end) { active[j] = active[j - 1]; j--; }
        active[j] = i; na++;
    }
    return slots;
}

// ── Emission of pseudo-assembly ─────────────────────────────────────────

static void cc_reg(cc_buf *o, int r) { cc_puts(o, "x"); cc_puti(o, 19 + r); }

// Reads operand v into a register name; spilled values load into `scratch`.
static void cc_src(cc_buf *o, const int *loc, int v, int scratch, int *count) {
    if (loc[v] >= 0) return;
    cc_puts(o, "  ldr x"); cc_puti(o, 9 + scratch); cc_puts(o, ", [fp, #-");
    cc_puti(o, -loc[v] * 8); cc_puts(o, "]\n");
    (*count)++;
}
static void cc_name(cc_buf *o, const int *loc, int v, int scratch) {
    if (loc[v] >= 0) cc_reg(o, loc[v]); else { cc_puts(o, "x"); cc_puti(o, 9 + scratch); }
}
static void cc_store(cc_buf *o, const int *loc, int v, int *count) {
    if (loc[v] >= 0) return;
    cc_puts(o, "  str x9, [fp, #-"); cc_puti(o, -loc[v] * 8); cc_puts(o, "]\n");
    (*count)++;
}

static int cc_emit_asm(cc_buf *o, const cc_ir *ir, const int *loc, int slots, int fidx, int nparams) {
    int count = 0;
    cc_puts(o, "f"); cc_puti(o, fidx); cc_puts(o, ":\n  stp fp, lr, [sp, #-16]!\n  mov fp, sp\n");
    if (slots) { cc_puts(o, "  sub sp, sp, #"); cc_puti(o, ((slots * 8) + 15) & ~15); cc_puts(o, "\n"); }
    for (int p = 0; p < nparams; p++) {
        if (loc[p] >= 0) { cc_puts(o, "  mov "); cc_reg(o, loc[p]); cc_puts(o, ", x"); cc_puti(o, p); cc_puts(o, "\n"); }
        else { cc_puts(o, "  str x"); cc_puti(o, p); cc_puts(o, ", [fp, #-"); cc_puti(o, -loc[p] * 8); cc_puts(o, "]\n"); }
        count++;
    }
    for (int i = 0; i < ir->n; i++) {
        const cc_ins *x = &ir->ins[i];
        switch (x->op) {
        case I_NOP: continue;
        case I_CONST:
            cc_puts(o, "  mov "); cc_name(o, loc, x->d, 0); cc_puts(o, ", #"); cc_puti(o, x->imm); cc_puts(o, "\n");
            count++; cc_store(o, loc, x->d, &count);
            break;
        case I_MOV:
            if (loc[x->d] == loc[x->a] && loc[x->d] >= 0) break;
            cc_src(o, loc, x->a, 0, &count);
            if (loc[x->d] >= 0) {
                cc_puts(o, "  mov "); cc_reg(o, loc[x->d]); cc_puts(o, ", "); cc_name(o, loc, x->a, 0);
                cc_puts(o, "\n"); count++;
            } else {
                if (loc[x->a] >= 0) { cc_puts(o, "  mov x9, "); cc_reg(o, loc[x->a]); cc_puts(o, "\n"); count++; }
                cc_store(o, loc, x->d, &count);
            }
            break;
        case I_BIN: case I_NEG: case I_NOT:
            cc_src(o, loc, x->a, 0, &count);
            if (x->op == I_BIN) cc_src(o, loc, x->b, 1, &count);
            cc_puts(o, "  ");
            cc_puts(o, x->op == I_BIN ? cc_opasm[x->bop] : x->op == I_NEG ? "neg" : "seqz");
            cc_puts(o, " "); cc_name(o, loc, x->d, 0); cc_puts(o, ", "); cc_name(o, loc, x->a, 0);
            if (x->op == I_BIN) { cc_puts(o, ", "); cc_name(o, loc, x->b, 1); }
            cc_puts(o, "\n"); count++;
            cc_store(o, loc, x->d, &count);
            break;
        case I_ARG:
            cc_src(o, loc, x->a, 0, &count);
            cc_puts(o, "  mov x"); cc_puti(o, x->imm); cc_puts(o, ", "); cc_name(o, loc, x->a, 0);
            cc_puts(o, "\n"); count++;
            break;
        case I_CALL:
            cc_puts(o, "  bl f"); cc_puti(o, x->imm); cc_puts(o, "\n  mov "); cc_name(o, loc, x->d, 0);
            cc_puts(o, ", x0\n"); count += 2;
            cc_store(o, loc, x->d, &count);
            break;
        case I_JMP:
            cc_puts(o, "  b .L"); cc_puti(o, fidx); cc_puts(o, "_"); cc_puti(o, x->imm); cc_puts(o, "\n"); count++;
            break;
        case I_BRZ:
            cc_src(o, loc, x->a, 0, &count);
            cc_puts(o, "  cbz "); cc_name(o, loc, x->a, 0); cc_puts(o, ", .L"); cc_puti(o, fidx);
            cc_puts(o, "_"); cc_puti(o, x->imm); cc_puts(o, "\n"); count++;
            break;
        case I_LABEL:
            cc_puts(o, ".L"); cc_puti(o, fidx); cc_puts(o, "_"); cc_puti(o, x->imm); cc_puts(o, ":\n");
            break;
        case I_RET:
            cc_src(o, loc, x->a, 0, &count);
            cc_puts(o, "  mov x0, "); cc_name(o, loc, x->a, 0);
            cc_puts(o, "\n  mov sp, fp\n  ldp fp, lr, [sp], #16\n  ret\n"); count += 4;
            break;
        }
    }
    return count;
}

/// compile — a compiler's front and middle end: generates modules of
/// source text in a small C-like language (functions, block-scoped
/// variables, if/else, while, calls, arithmetic and comparisons), then for
/// each module runs a lexer with an identifier hash table, a recursive-
/// descent / precedence-climbing parser to an AST, constant folding and
/// algebraic simplification, lowering to three-address IR, basic blocks
/// and a CFG, local value numbering (common subexpressions and copy
/// propagation), iterative liveness with dead-code elimination, linear-scan
/// register allocation over six registers with spilling, and emission of
/// arm64-flavoured pseudo-assembly. The class of gcc and llvm in a CPU
/// suite. Sizes compile 22, 120 and 550 modules of 60 functions.
/// `checksum` digests the emitted assembly text and the pass statistics;
/// `value` is instructions emitted; `work` is source tokens compiled.
int cbk_compile(int size, cb_bench_result *out) {
    static const int modules[3] = {22, 120, 550};
    enum { FUNCS = 60 };
    size = ia_size(size);
    int rc = 1;
    cc_buf src = {0}, asmb = {0};
    cc_syms *sy = (cc_syms *)calloc(1, sizeof *sy);
    cc_parser *ps = (cc_parser *)calloc(1, sizeof *ps);
    cc_toks toks = {0};
    cc_ir ir = {0};
    cc_arena ar = {0};
    int *sym_func = (int *)calloc(CC_SYMCAP, sizeof(int));
    ar.cap = 8u << 20;
    ar.p = (uint8_t *)malloc(ar.cap);
    if (!sy || !ps || !sym_func || !ar.p) goto done;

    static const char *const kwn[6] = {"fn", "var", "if", "else", "while", "return"};
    int kw[6];
    for (int k = 0; k < 6; k++) if ((kw[k] = cc_intern(sy, kwn[k], (uint32_t)strlen(kwn[k]))) < 0) goto done;

    uint64_t h = IA_FNV_BASIS, ntok = 0, nemit = 0;
    uint64_t folds = 0, cse = 0, dce = 0, spills = 0;
    for (int m = 0; m < modules[size - 1]; m++) {
        src.n = 0;
        cc_generate(&src, 0xC0DEC0DE00000000ull + (uint64_t)m * 7919, FUNCS);
        if (src.fail) goto done;
        if (cc_lex(src.p, src.n, sy, &toks, kw)) { rc = 2; goto done; }
        ntok += (uint64_t)toks.n;
        memset(sym_func, 0, CC_SYMCAP * sizeof(int));
        ps->t = toks.t; ps->pos = 0; ps->nn = 0; ps->nfn = 0; ps->err = 0; ps->sym_func = sym_func;
        cc_parse(ps);
        if (ps->err || ps->nfn != FUNCS) { rc = 2; goto done; }
        for (int f = 0; f < ps->nfn; f++) {
            int fo = 0;
            cc_fold_block(ps->nd, ps->fn[f].body, &fo);
            folds += (uint64_t)fo;
            ir.n = 0; ir.nlab = 0; ir.nslots = ps->fn[f].nslots; ir.nv = ir.nslots; ir.err = 0;
            cc_lstmts(&ir, ps->nd, ps->nd[ps->fn[f].body].a);
            int z = ir.nv++;
            cc_emit_ir(&ir, I_CONST, 0, z, -1, -1, 0);
            cc_emit_ir(&ir, I_RET, 0, -1, z, -1, 0);
            if (ir.err) goto done;
            ar.used = 0; ar.fail = 0;
            cc_cfg g;
            if (cc_build_cfg(&ar, &ir, &g)) goto done;
            int hits = cc_local_cse(&ir, &g, &ar);
            uint64_t *live = (uint64_t *)cc_alloc(&ar, (size_t)g.W * 8);
            int *loc = (int *)cc_alloc(&ar, (size_t)ir.nv * sizeof(int));
            if (hits < 0 || ar.fail) goto done;
            cse += (uint64_t)hits;
            for (int it = 0; it < 16; it++) {
                cc_liveness(&ir, &g);
                int r = cc_dce(&ir, &g, live);
                dce += (uint64_t)r;
                if (!r) break;
            }
            int slots = cc_linear_scan(&ir, &g, &ar, loc);
            if (slots < 0) goto done;
            spills += (uint64_t)slots;
            asmb.n = 0;
            nemit += (uint64_t)cc_emit_asm(&asmb, &ir, loc, slots, f, ps->fn[f].nparams);
            if (asmb.fail) goto done;
            h = ia_fnv(h, asmb.p, asmb.n);
        }
    }
    h = ia_mix(h, ntok); h = ia_mix(h, nemit); h = ia_mix(h, folds);
    h = ia_mix(h, cse); h = ia_mix(h, dce); h = ia_mix(h, spills);
    ia_fill(out, h, (double)nemit, (double)ntok, "tokens");
    rc = 0;
done:
    free(src.p); free(asmb.p); free(sy ? sy->names : NULL); free(sy);
    free(ps ? ps->nd : NULL); free(ps); free(toks.t); free(ir.ins); free(ar.p); free(sym_func);
    return rc;
}

// ── mcf: min-cost flow for vehicle scheduling ───────────────────────────

typedef struct { int32_t to, rev, cap, cost; } mf_arc;
typedef struct { int64_t d; int32_t v; } mf_heap_item;

static void mf_push(mf_heap_item *h, int *n, int64_t d, int32_t v) {
    int i = (*n)++;
    while (i > 0) {
        int p = (i - 1) >> 1;
        if (h[p].d < d || (h[p].d == d && h[p].v <= v)) break;
        h[i] = h[p]; i = p;
    }
    h[i].d = d; h[i].v = v;
}

static mf_heap_item mf_pop(mf_heap_item *h, int *n) {
    mf_heap_item top = h[0], last = h[--(*n)];
    int i = 0, m = *n;
    for (;;) {
        int c = 2 * i + 1;
        if (c >= m) break;
        if (c + 1 < m && (h[c + 1].d < h[c].d || (h[c + 1].d == h[c].d && h[c + 1].v < h[c].v))) c++;
        if (last.d < h[c].d || (last.d == h[c].d && last.v <= h[c].v)) break;
        h[i] = h[c]; i = c;
    }
    h[i] = last;
    return top;
}

/// mcf — single-depot vehicle scheduling as min-cost flow, the kind of
/// network optimisation a transit operator's route planner runs. A day of
/// timetabled trips between terminals is generated; each trip's end may
/// chain to a later trip's start (deadhead travel plus waiting cost) or
/// return to the depot, and every trip start is fed by a chained trip or a
/// fresh vehicle pulled from the depot at a fixed cost. The network (trip
/// ends → trip starts, through the depot) is solved by successive shortest
/// paths: Dijkstra with a binary heap over reduced costs, node potentials
/// kept valid with an early stop at the sink, one unit augmented per
/// path. Optimality is then certified (no residual arc has negative
/// reduced cost). Sizes schedule 1400, 3200 and 6800 trips. `checksum`
/// digests the minimum cost, fleet size and every trip's successor;
/// `value` is the minimum cost; `work` is arcs scanned by Dijkstra.
int cbk_mcf(int size, cb_bench_result *out) {
    static const int trips_by_size[3] = {1400, 3200, 6800};
    enum { NLOC = 48, MAXWAIT = 150 * 60, MAXSUCC = 28, FIXED = 180000, DEAD = 12 };
    size = ia_size(size);
    const int T = trips_by_size[size - 1];
    const int S = 0, D = 1, SINK = 2, OUT0 = 3, IN0 = 3 + T, V = 3 + 2 * T;
    int rc = 1;
    int32_t *tstart = (int32_t *)malloc((size_t)T * 4), *tend = (int32_t *)malloc((size_t)T * 4);
    int32_t *tsl = (int32_t *)malloc((size_t)T * 4), *tel = (int32_t *)malloc((size_t)T * 4);
    int32_t *eu = NULL, *ev = NULL, *ec = NULL, *first = NULL, *fill = NULL, *parent = NULL;
    mf_arc *arcs = NULL; mf_heap_item *heap = NULL;
    int64_t *dist = NULL, *pot = NULL; uint8_t *done = NULL;
    int nedge = 0;
    if (!tstart || !tend || !tsl || !tel) goto out;

    ia_rng r = { 0x3CF0000000000000ull ^ (uint64_t)T };
    int32_t lx[NLOC], ly[NLOC];
    for (int i = 0; i < NLOC; i++) { lx[i] = (int32_t)ia_below(&r, 120); ly[i] = (int32_t)ia_below(&r, 120); }
    const int depot_loc = 0;
#define MF_TRAVEL(a, b) ((abs(lx[a] - lx[b]) + abs(ly[a] - ly[b])) * 30)   // seconds
    int32_t clock = 5 * 3600;                             // 05:00, times in seconds
    const int32_t day = 20 * 3600;
    for (int i = 0; i < T; i++) {
        clock += (int32_t)ia_below(&r, (uint32_t)(2 * day / T + 1));
        tstart[i] = clock;
        tsl[i] = (int32_t)ia_below(&r, NLOC);
        do tel[i] = (int32_t)ia_below(&r, NLOC); while (tel[i] == tsl[i]);
        tend[i] = clock + MF_TRAVEL(tsl[i], tel[i]) + 480 + (int32_t)ia_below(&r, 3000);
    }

    // Edge list: S→out, in→SINK, out→D, D→in, out_i→in_j for compatible pairs.
    int maxe = T * (4 + MAXSUCC);
    eu = (int32_t *)malloc((size_t)maxe * 4); ev = (int32_t *)malloc((size_t)maxe * 4);
    ec = (int32_t *)malloc((size_t)maxe * 4);
    if (!eu || !ev || !ec) goto out;
#define MF_EDGE(u, v, c) do { eu[nedge] = (u); ev[nedge] = (v); ec[nedge] = (c); nedge++; } while (0)
    for (int i = 0; i < T; i++) {
        MF_EDGE(S, OUT0 + i, 0);
        MF_EDGE(IN0 + i, SINK, 0);
        MF_EDGE(OUT0 + i, D, DEAD * MF_TRAVEL(tel[i], depot_loc));
        MF_EDGE(D, IN0 + i, FIXED + DEAD * MF_TRAVEL(depot_loc, tsl[i]));
        int lo = 0, hi = T;                               // first trip starting at/after tend[i]
        while (lo < hi) { int mid = (lo + hi) >> 1; if (tstart[mid] < tend[i]) lo = mid + 1; else hi = mid; }
        int added = 0;
        for (int j = lo; j < T && added < MAXSUCC && tstart[j] <= tend[i] + MAXWAIT; j++) {
            int dh = MF_TRAVEL(tel[i], tsl[j]);
            int wait = tstart[j] - tend[i] - dh;
            if (wait < 0) continue;
            MF_EDGE(OUT0 + i, IN0 + j, DEAD * dh + wait);
            added++;
        }
    }
#undef MF_EDGE
#undef MF_TRAVEL

    // Residual graph in CSR form: each edge gives a forward and a reverse arc.
    first = (int32_t *)calloc((size_t)V + 1, 4); fill = (int32_t *)malloc((size_t)V * 4);
    arcs = (mf_arc *)malloc((size_t)nedge * 2 * sizeof(mf_arc));
    if (!first || !fill || !arcs) goto out;
    for (int e = 0; e < nedge; e++) { first[eu[e] + 1]++; first[ev[e] + 1]++; }
    for (int v = 0; v < V; v++) first[v + 1] += first[v];
    memcpy(fill, first, (size_t)V * 4);
    for (int e = 0; e < nedge; e++) {
        int a = fill[eu[e]]++, b = fill[ev[e]]++;
        arcs[a].to = ev[e]; arcs[a].cap = 1; arcs[a].cost = ec[e]; arcs[a].rev = b;
        arcs[b].to = eu[e]; arcs[b].cap = 0; arcs[b].cost = -ec[e]; arcs[b].rev = a;
    }
    free(eu); free(ev); free(ec); eu = ev = ec = NULL;
    // The depot's arcs carry any number of vehicles.
    for (int a = first[D]; a < first[D + 1]; a++) if (arcs[a].cost > 0) arcs[a].cap = T;

    dist = (int64_t *)malloc((size_t)V * 8); pot = (int64_t *)calloc((size_t)V, 8);
    parent = (int32_t *)malloc((size_t)V * 4); done = (uint8_t *)malloc((size_t)V);
    heap = (mf_heap_item *)malloc(((size_t)nedge * 2 + (size_t)V) * sizeof *heap);
    if (!dist || !pot || !parent || !done || !heap) goto out;

    const int64_t INF = INT64_MAX / 4;
    int64_t total = 0;
    uint64_t scanned = 0;
    int flow = 0;
    while (flow < T) {
        for (int v = 0; v < V; v++) dist[v] = INF;
        memset(done, 0, (size_t)V);
        int hn = 0;
        dist[S] = 0; parent[S] = -1;
        mf_push(heap, &hn, 0, S);
        while (hn) {
            mf_heap_item it = mf_pop(heap, &hn);
            int u = it.v;
            if (done[u]) continue;
            done[u] = 1;
            if (u == SINK) break;
            int64_t du = dist[u] + pot[u];
            for (int a = first[u]; a < first[u + 1]; a++) {
                const mf_arc *x = &arcs[a];
                scanned++;
                if (x->cap <= 0 || done[x->to]) continue;
                int64_t nd = du + x->cost - pot[x->to];
                if (nd < dist[x->to]) { dist[x->to] = nd; parent[x->to] = a; mf_push(heap, &hn, nd, x->to); }
            }
        }
        if (!done[SINK]) { rc = 2; goto out; }            // infeasible: cannot happen
        int64_t dt = dist[SINK];
        for (int v = 0; v < V; v++) pot[v] += done[v] && dist[v] < dt ? dist[v] : dt;
        for (int v = SINK; v != S;) {
            mf_arc *x = &arcs[parent[v]];
            x->cap--; arcs[x->rev].cap++;
            total += x->cost;
            v = arcs[x->rev].to;
        }
        flow++;
    }

    // Certificate: every residual arc has non-negative reduced cost.
    for (int u = 0; u < V; u++)
        for (int a = first[u]; a < first[u + 1]; a++)
            if (arcs[a].cap > 0 && arcs[a].cost + pot[u] - pot[arcs[a].to] < 0) { rc = 3; goto out; }

    uint64_t h = IA_FNV_BASIS;
    int vehicles = 0;
    for (int a = first[D]; a < first[D + 1]; a++)
        if (arcs[a].cost > 0) vehicles += T - arcs[a].cap;
    for (int i = 0; i < T; i++) {
        int succ = -1;
        for (int a = first[OUT0 + i]; a < first[OUT0 + i + 1]; a++)
            if (arcs[a].cost >= 0 && arcs[a].to != S && arcs[a].cap == 0) { succ = arcs[a].to; break; }
        h = ia_mix(h, (uint64_t)(int64_t)succ);
    }
    h = ia_mix(h, (uint64_t)total);
    h = ia_mix(h, (uint64_t)vehicles);
    ia_fill(out, h, (double)total, (double)scanned, "arcs");
    rc = 0;
out:
    free(tstart); free(tend); free(tsl); free(tel); free(eu); free(ev); free(ec);
    free(first); free(fill); free(arcs); free(dist); free(pot); free(parent); free(done); free(heap);
    return rc;
}

// ── eventsim: discrete-event simulation of a packet network ─────────────

enum { ES_GEN, ES_TXDONE, ES_ARRIVE, ES_ROUTE };

typedef struct { uint64_t t; uint32_t seq; int32_t type, a, b; } es_ev;

typedef struct {
    int32_t from, to, delay_ns, ns_per_byte;
    int32_t qhead, qlen, busy, drops;
    uint64_t bytes, sent;
} es_link;

typedef struct { int32_t src, dst, size, hops, ttl, flow, ack; uint64_t birth; } es_pkt;
typedef struct { int32_t src, dst; uint32_t mean_ns; int32_t delivered, acked; } es_flow;

typedef struct {
    es_ev *heap; int hn, hcap; uint32_t seq;
    es_link *link; int nlinks;
    int32_t *qbuf;                 // QCAP slots per link
    int32_t *adj_first, *adj;      // node → outgoing links
    int32_t *nexthop;              // N*N → link id
    es_pkt *pkt; int32_t *freelist; int nfree;
    es_flow *flow; int nflows;
    int N;
    int64_t *dist; uint8_t *seen;  // routing scratch
    ia_rng r;
    uint64_t now, end;
    uint64_t delivered, acked, dropped, ttl_drops, lat_sum, rtt_sum, hop_sum, events, reroutes;
    int err;
} es_sim;

#define ES_QCAP 48

static void es_schedule(es_sim *s, uint64_t t, int type, int a, int b) {
    if (s->hn >= s->hcap) {
        int nc = s->hcap * 2;
        es_ev *p = (es_ev *)realloc(s->heap, (size_t)nc * sizeof *p);
        if (!p) { s->err = 1; return; }
        s->heap = p; s->hcap = nc;
    }
    es_ev e = { t, s->seq++, type, a, b };
    int i = s->hn++;
    while (i > 0) {
        int p = (i - 1) >> 1;
        const es_ev *q = &s->heap[p];
        if (q->t < e.t || (q->t == e.t && q->seq < e.seq)) break;
        s->heap[i] = *q; i = p;
    }
    s->heap[i] = e;
}

static es_ev es_pop(es_sim *s) {
    es_ev top = s->heap[0], last = s->heap[--s->hn];
    int i = 0, n = s->hn;
    for (;;) {
        int c = 2 * i + 1;
        if (c >= n) break;
        const es_ev *x = &s->heap[c], *y = &s->heap[c + 1];
        if (c + 1 < n && (y->t < x->t || (y->t == x->t && y->seq < x->seq))) { c++; x = y; }
        if (last.t < x->t || (last.t == x->t && last.seq < x->seq)) break;
        s->heap[i] = *x; i = c;
    }
    s->heap[i] = last;
    return top;
}

/// Shortest-path next hops from every node (O(N²) Dijkstra per source),
/// weighting each link by its propagation delay plus the time to drain
/// its current queue: adaptive routing.
static void es_route(es_sim *s) {
    int N = s->N;
    for (int src = 0; src < N; src++) {
        // Dijkstra rooted at the destination over reversed links gives every
        // node's next hop towards `src` in one pass.
        int64_t *d = s->dist;
        for (int v = 0; v < N; v++) { d[v] = INT64_MAX; s->seen[v] = 0; }
        d[src] = 0;
        for (int it = 0; it < N; it++) {
            int u = -1; int64_t best = INT64_MAX;
            for (int v = 0; v < N; v++) if (!s->seen[v] && d[v] < best) { best = d[v]; u = v; }
            if (u < 0) break;
            s->seen[u] = 1;
            // incoming links of u are the reverse of u's outgoing (links come in pairs)
            for (int k = s->adj_first[u]; k < s->adj_first[u + 1]; k++) {
                int back = s->adj[k] ^ 1;            // link v→u
                const es_link *L = &s->link[back];
                int64_t w = L->delay_ns + (int64_t)L->qlen * L->ns_per_byte * 1000;
                int v = L->from;
                if (!s->seen[v] && d[u] + w < d[v]) { d[v] = d[u] + w; s->nexthop[v * N + src] = back; }
            }
        }
    }
    s->reroutes++;
}

static void es_start_tx(es_sim *s, int l) {
    es_link *L = &s->link[l];
    const es_pkt *p = &s->pkt[s->qbuf[l * ES_QCAP + L->qhead]];
    L->busy = 1;
    es_schedule(s, s->now + (uint64_t)p->size * (uint64_t)L->ns_per_byte, ES_TXDONE, l, 0);
}

static void es_free_pkt(es_sim *s, int p) { s->freelist[s->nfree++] = p; }

/// Packet `p` is at `node`: deliver it, or queue it on the next hop's link.
static void es_forward(es_sim *s, int p, int node) {
    es_pkt *P = &s->pkt[p];
    if (P->dst == node) {
        if (!P->ack) {
            s->delivered++;
            s->lat_sum += s->now - P->birth;
            s->hop_sum += (uint64_t)P->hops;
            s->flow[P->flow].delivered++;
            // turn the packet round as a 64-byte acknowledgement
            P->ack = 1; P->dst = P->src; P->src = node; P->size = 64; P->hops = 0; P->ttl = 32;
        } else {
            s->acked++;
            s->rtt_sum += s->now - P->birth;
            s->flow[P->flow].acked++;
            es_free_pkt(s, p);
            return;
        }
    }
    int l = s->nexthop[node * s->N + P->dst];
    es_link *L = &s->link[l];
    if (L->qlen >= ES_QCAP) { L->drops++; s->dropped++; es_free_pkt(s, p); return; }
    s->qbuf[l * ES_QCAP + (L->qhead + L->qlen) % ES_QCAP] = p;
    L->qlen++;
    if (!L->busy) es_start_tx(s, l);
}

/// eventsim — a discrete-event network simulator of the omnetpp / ns-3
/// kind: 96 routers joined by a ring plus random chords, each direction a
/// link with its own propagation delay, bandwidth (100 Mb/s, 1 Gb/s or
/// 10 Gb/s) and drop-tail queue. Flows between random pairs emit packets
/// of mixed sizes at jittered intervals; every delivered packet returns
/// as an acknowledgement, giving round-trip times. Events (generation,
/// end of transmission, arrival, routing update) sit in a binary heap
/// ordered by time then sequence; routing is adaptive, recomputing
/// shortest paths over delay plus queue backlog every 4 simulated
/// milliseconds. Sizes simulate 120, 680 and 3000 ms. `checksum` digests
/// the delivery, drop, latency and per-flow statistics; `value` is
/// packets delivered; `work` is events processed.
int cbk_eventsim(int size, cb_bench_result *out) {
    static const int sim_ms[3] = {120, 680, 3000};
    enum { N = 96, FLOWS = 640, MAXPKT = 1 << 16 };
    size = ia_size(size);
    int rc = 1;
    es_sim *s = (es_sim *)calloc(1, sizeof *s);
    if (!s) return 1;
    s->N = N;
    s->r.s = 0xE7E57E5700000000ull;
    s->end = (uint64_t)sim_ms[size - 1] * 1000000ull;

    // Topology: ring + chords; links stored in pairs (2k: a→b, 2k+1: b→a).
    int maxlinks = 2 * (N + N);
    s->link = (es_link *)calloc((size_t)maxlinks, sizeof(es_link));
    int32_t *deg = (int32_t *)calloc(N + 1, 4);
    if (!s->link || !deg) { free(deg); goto out; }
    static const int32_t nspb[4] = {80, 8, 8, 1};
    for (int i = 0; i < 2 * N; i++) {
        int a, b;
        if (i < N) { a = i; b = (i + 1) % N; }
        else {
            a = (int)ia_below(&s->r, N);
            do b = (int)ia_below(&s->r, N); while (b == a || b == (a + 1) % N || a == (b + 1) % N);
        }
        int32_t delay = 2000 + (int32_t)ia_below(&s->r, 400000);
        int32_t bw = nspb[ia_below(&s->r, 4)];
        for (int dir = 0; dir < 2; dir++) {
            es_link *L = &s->link[s->nlinks++];
            L->from = dir ? b : a; L->to = dir ? a : b; L->delay_ns = delay; L->ns_per_byte = bw;
            deg[L->from + 1]++;
        }
    }
    s->adj_first = deg;
    for (int v = 0; v < N; v++) s->adj_first[v + 1] += s->adj_first[v];
    s->adj = (int32_t *)malloc((size_t)s->nlinks * 4);
    int32_t *fillp = (int32_t *)malloc(N * 4);
    s->nexthop = (int32_t *)malloc((size_t)N * N * 4);
    s->qbuf = (int32_t *)malloc((size_t)s->nlinks * ES_QCAP * 4);
    s->pkt = (es_pkt *)malloc(MAXPKT * sizeof(es_pkt));
    s->freelist = (int32_t *)malloc(MAXPKT * 4);
    s->flow = (es_flow *)calloc(FLOWS, sizeof(es_flow));
    s->dist = (int64_t *)malloc(N * 8); s->seen = (uint8_t *)malloc(N);
    s->hcap = 4096; s->heap = (es_ev *)malloc((size_t)s->hcap * sizeof(es_ev));
    if (!s->adj || !fillp || !s->nexthop || !s->qbuf || !s->pkt || !s->freelist || !s->flow ||
        !s->dist || !s->seen || !s->heap) { free(fillp); goto out; }
    memcpy(fillp, s->adj_first, N * 4);
    for (int l = 0; l < s->nlinks; l++) s->adj[fillp[s->link[l].from]++] = l;
    free(fillp);
    for (int i = 0; i < MAXPKT; i++) s->freelist[i] = MAXPKT - 1 - i;
    s->nfree = MAXPKT;
    for (int v = 0; v < N * N; v++) s->nexthop[v] = 0;
    es_route(s);

    static const int32_t sizes[4] = {64, 576, 1500, 1500};
    for (int f = 0; f < FLOWS; f++) {
        es_flow *F = &s->flow[f];
        F->src = (int32_t)ia_below(&s->r, N);
        do F->dst = (int32_t)ia_below(&s->r, N); while (F->dst == F->src);
        F->mean_ns = 150000 + ia_below(&s->r, 900000);
        es_schedule(s, ia_below(&s->r, F->mean_ns), ES_GEN, f, 0);
    }
    es_schedule(s, 4000000, ES_ROUTE, 0, 0);

    while (s->hn && !s->err) {
        es_ev e = es_pop(s);
        if (e.t > s->end) break;
        s->now = e.t;
        s->events++;
        switch (e.type) {
        case ES_GEN: {
            es_flow *F = &s->flow[e.a];
            if (s->nfree) {
                int p = s->freelist[--s->nfree];
                es_pkt *P = &s->pkt[p];
                P->src = F->src; P->dst = F->dst; P->size = sizes[ia_below(&s->r, 4)];
                P->hops = 0; P->ttl = 32; P->flow = e.a; P->ack = 0; P->birth = s->now;
                es_forward(s, p, F->src);
            } else {
                s->dropped++;
            }
            es_schedule(s, s->now + F->mean_ns / 2 + ia_below(&s->r, F->mean_ns), ES_GEN, e.a, 0);
            break;
        }
        case ES_TXDONE: {
            es_link *L = &s->link[e.a];
            int p = s->qbuf[e.a * ES_QCAP + L->qhead];
            L->qhead = (L->qhead + 1) % ES_QCAP; L->qlen--;
            L->bytes += (uint64_t)s->pkt[p].size; L->sent++;
            es_schedule(s, s->now + (uint64_t)L->delay_ns, ES_ARRIVE, e.a, p);
            if (L->qlen) es_start_tx(s, e.a); else L->busy = 0;
            break;
        }
        case ES_ARRIVE: {
            es_pkt *P = &s->pkt[e.b];
            P->hops++;
            if (--P->ttl <= 0) { s->ttl_drops++; es_free_pkt(s, e.b); break; }
            es_forward(s, e.b, s->link[e.a].to);
            break;
        }
        case ES_ROUTE:
            es_route(s);
            es_schedule(s, s->now + 4000000, ES_ROUTE, 0, 0);
            break;
        }
    }
    if (s->err) goto out;

    uint64_t h = IA_FNV_BASIS;
    h = ia_mix(h, s->events); h = ia_mix(h, s->delivered); h = ia_mix(h, s->acked);
    h = ia_mix(h, s->dropped); h = ia_mix(h, s->ttl_drops); h = ia_mix(h, s->lat_sum);
    h = ia_mix(h, s->rtt_sum); h = ia_mix(h, s->hop_sum); h = ia_mix(h, s->reroutes);
    for (int f = 0; f < FLOWS; f++) h = ia_mix(h, ((uint64_t)s->flow[f].delivered << 32) | (uint32_t)s->flow[f].acked);
    for (int l = 0; l < s->nlinks; l++) h = ia_mix(h, s->link[l].bytes ^ ((uint64_t)s->link[l].drops << 40));
    ia_fill(out, h, (double)s->delivered, (double)s->events, "events");
    rc = 0;
out:
    free(s->heap); free(s->link); free(s->adj_first); free(s->adj); free(s->nexthop); free(s->qbuf);
    free(s->pkt); free(s->freelist); free(s->flow); free(s->dist); free(s->seen);
    free(s);
    return rc;
}

// ── xml: parse, transform and serialise a document ──────────────────────

static const char *const xm_first[16] = {
    "Ana", "Bruno", "Chloe", "Dmitri", "Elif", "Farid", "Greta", "Hiro",
    "Ines", "Jonas", "Kalinda", "Luca", "Mei", "Nadia", "Oskar", "Priya"};
static const char *const xm_last[24] = {
    "Moreno", "Okafor", "Lindqvist", "Tanaka", "Haddad", "Novak", "Fischer", "Rossi",
    "Kowalski", "Dubois", "Silva", "Nguyen", "O'Brien", "Petrov", "Schmidt", "Yilmaz",
    "Andersen", "Costa", "Ibrahim", "Larsen", "Mendes", "Sato", "Varga", "Walsh"};
static const char *const xm_word[32] = {
    "River", "Silent", "Glass", "Winter", "Harbour", "Engine", "Garden", "Night",
    "Copper", "Letters", "Distant", "Orchard", "Signal", "Paper", "Mountain", "Echo",
    "Salt", "Lantern", "Hidden", "Atlas", "Thread", "Quiet", "Iron", "Northern",
    "Summer", "Tides", "Market", "Shadow", "Bridge", "Clock", "Velvet", "Storm"};
static const char *const xm_tag[20] = {
    "history", "sea", "science", "poetry", "travel", "war", "family", "music",
    "crime", "food", "art", "nature", "politics", "space", "sport", "myth",
    "cities", "letters", "childhood", "machines"};
static const char *const xm_lang[5] = {"en", "fr", "de", "ja", "pt"};

/// Writes one generated catalogue (entities, CDATA, comments included).
static void xm_generate(cc_buf *b, ia_rng *r, int records, int docno) {
    cc_puts(b, "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!-- catalogue ");
    cc_puti(b, docno);
    cc_puts(b, " -->\n<catalog region=\"r");
    cc_puti(b, docno % 9);
    cc_puts(b, "\">\n");
    for (int i = 0; i < records; i++) {
        cc_puts(b, "  <book id=\"b"); cc_puti(b, (int64_t)docno * 100000 + i);
        cc_puts(b, "\" lang=\""); cc_puts(b, xm_lang[ia_below(r, 5) * ia_below(r, 2)]);
        cc_puts(b, ia_below(r, 3) ? "\" format=\"paperback\">\n" : "\" format=\"hardcover\">\n");
        cc_puts(b, "    <title>");
        int nw = 1 + (int)ia_below(r, 4);
        if (ia_below(r, 3) == 0) cc_puts(b, "The ");
        for (int w = 0; w < nw; w++) {
            if (w) cc_puts(b, ia_below(r, 6) == 0 ? " &amp; " : " ");
            cc_puts(b, xm_word[ia_below(r, 32)]);
        }
        cc_puts(b, "</title>\n    <author><first>");
        cc_puts(b, xm_first[ia_below(r, 16)]);
        cc_puts(b, "</first><last>");
        const char *ln = xm_last[ia_below(r, 24)];
        if (strchr(ln, '\'')) cc_puts(b, "O&apos;Brien"); else cc_puts(b, ln);
        cc_puts(b, "</last></author>\n    <year>");
        cc_puti(b, 1900 + (int64_t)ia_below(r, 125));
        cc_puts(b, "</year>\n    <price currency=\"EUR\">");
        uint32_t cents = 199 + ia_below(r, 6000);
        cc_puti(b, cents / 100); cc_puts(b, ".");
        cc_puti(b, (cents % 100) / 10); cc_puti(b, cents % 10);
        cc_puts(b, "</price>\n    <tags>");
        int nt = (int)ia_below(r, 4);
        for (int t = 0; t < nt; t++) {
            cc_puts(b, "<tag>"); cc_puts(b, xm_tag[ia_below(r, 20)]); cc_puts(b, "</tag>");
        }
        cc_puts(b, "</tags>\n");
        if (ia_below(r, 4) == 0)
            cc_puts(b, "    <summary><![CDATA[Contains <markup> & \"quotes\" verbatim]]></summary>\n");
        if (ia_below(r, 8) == 0) cc_puts(b, "    <!-- reviewed -->\n");
        cc_puts(b, "    <stock>&#"); cc_puti(b, 48 + (int64_t)ia_below(r, 10)); cc_puts(b, ";</stock>\n");
        cc_puts(b, "  </book>\n");
    }
    cc_puts(b, "</catalog>\n");
}

enum { XM_ELEM = 1, XM_TEXT = 2 };
typedef struct { uint8_t kind; int32_t name, parent, first, last, next, attr0, nattr, off, len; } xm_node;
typedef struct { int32_t name, off, len; } xm_attr;

typedef struct {
    xm_node *nd; int nn, capn;
    xm_attr *at; int na, capa;
    cc_buf text;                     // decoded text and attribute values
    int err;
} xm_doc;

#define XM_NAMECAP 1024
typedef struct {                     // the name pool shared by both trees
    int32_t slot[XM_NAMECAP];
    uint32_t off[XM_NAMECAP / 2], len[XM_NAMECAP / 2];
    char pool[XM_NAMECAP * 8]; size_t used;
    int n;
} xm_names;

static int xm_intern(xm_names *t, const char *p, size_t n) {
    uint32_t h = (uint32_t)ia_fnv(IA_FNV_BASIS, p, n), j = h & (XM_NAMECAP - 1);
    while (t->slot[j]) {
        int id = t->slot[j] - 1;
        if (t->len[id] == n && !memcmp(t->pool + t->off[id], p, n)) return id;
        j = (j + 1) & (XM_NAMECAP - 1);
    }
    if (t->n >= XM_NAMECAP / 2 || t->used + n > sizeof t->pool) return -1;
    int id = t->n++;
    memcpy(t->pool + t->used, p, n);
    t->off[id] = (uint32_t)t->used; t->len[id] = (uint32_t)n; t->used += n;
    t->slot[j] = id + 1;
    return id;
}

static int xm_new(xm_doc *d, int kind, int name, int parent) {
    if (d->nn >= d->capn) {
        int nc = d->capn ? d->capn * 2 : 4096;
        xm_node *p = (xm_node *)realloc(d->nd, (size_t)nc * sizeof *p);
        if (!p) { d->err = 1; return -1; }
        d->nd = p; d->capn = nc;
    }
    int i = d->nn++;
    xm_node *x = &d->nd[i];
    x->kind = (uint8_t)kind; x->name = name; x->parent = parent;
    x->first = x->last = x->next = -1; x->attr0 = 0; x->nattr = 0; x->off = x->len = 0;
    if (parent >= 0) {
        xm_node *p = &d->nd[parent];
        if (p->last >= 0) d->nd[p->last].next = i; else p->first = i;
        p->last = i;
    }
    return i;
}

static int xm_add_attr(xm_doc *d, int name, int32_t off, int32_t len) {
    if (d->na >= d->capa) {
        int nc = d->capa ? d->capa * 2 : 4096;
        xm_attr *p = (xm_attr *)realloc(d->at, (size_t)nc * sizeof *p);
        if (!p) { d->err = 1; return -1; }
        d->at = p; d->capa = nc;
    }
    d->at[d->na].name = name; d->at[d->na].off = off; d->at[d->na].len = len;
    return d->na++;
}

static void xm_put_utf8(cc_buf *b, uint32_t c) {
    char u[4]; size_t n;
    if (c < 0x80) { u[0] = (char)c; n = 1; }
    else if (c < 0x800) { u[0] = (char)(0xC0 | (c >> 6)); u[1] = (char)(0x80 | (c & 63)); n = 2; }
    else { u[0] = (char)(0xE0 | (c >> 12)); u[1] = (char)(0x80 | ((c >> 6) & 63)); u[2] = (char)(0x80 | (c & 63)); n = 3; }
    cc_put(b, u, n);
}

/// Appends [p, e) to the text pool with entity references decoded.
static int xm_decode(cc_buf *b, const char *p, const char *e) {
    while (p < e) {
        const char *amp = (const char *)memchr(p, '&', (size_t)(e - p));
        if (!amp) { cc_put(b, p, (size_t)(e - p)); break; }
        cc_put(b, p, (size_t)(amp - p));
        const char *semi = (const char *)memchr(amp, ';', (size_t)(e - amp));
        if (!semi) return -1;
        size_t n = (size_t)(semi - amp - 1);
        const char *nm = amp + 1;
        if (n == 3 && !memcmp(nm, "amp", 3)) cc_put(b, "&", 1);
        else if (n == 2 && !memcmp(nm, "lt", 2)) cc_put(b, "<", 1);
        else if (n == 2 && !memcmp(nm, "gt", 2)) cc_put(b, ">", 1);
        else if (n == 4 && !memcmp(nm, "quot", 4)) cc_put(b, "\"", 1);
        else if (n == 4 && !memcmp(nm, "apos", 4)) cc_put(b, "'", 1);
        else if (n >= 2 && nm[0] == '#') {
            uint32_t c = 0;
            if (nm[1] == 'x') for (size_t i = 2; i < n; i++) {
                char ch = nm[i];
                c = c * 16 + (uint32_t)(ch <= '9' ? ch - '0' : (ch | 32) - 'a' + 10);
            }
            else for (size_t i = 1; i < n; i++) c = c * 10 + (uint32_t)(nm[i] - '0');
            xm_put_utf8(b, c);
        } else return -1;
        p = semi + 1;
    }
    return b->fail ? -1 : 0;
}

static int xm_isname(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
           c == '_' || c == '-' || c == ':' || c == '.';
}

/// Parses an XML document into a DOM. Returns the root element or -1.
static int xm_parse(xm_doc *d, xm_names *names, const char *s, size_t n) {
    const char *p = s, *e = s + n;
    int cur = -1, root = -1;
    d->nn = 0; d->na = 0; d->text.n = 0; d->err = 0;
    while (p < e) {
        if (*p != '<') {                                     // character data
            const char *lt = (const char *)memchr(p, '<', (size_t)(e - p));
            if (!lt) lt = e;
            const char *q = p;
            while (q < lt && (*q == ' ' || *q == '\n' || *q == '\t' || *q == '\r')) q++;
            if (q < lt) {                                    // not just whitespace
                if (cur < 0) return -1;
                int32_t off = (int32_t)d->text.n;
                if (xm_decode(&d->text, p, lt)) return -1;
                int t = xm_new(d, XM_TEXT, -1, cur);
                if (t < 0) return -1;
                d->nd[t].off = off; d->nd[t].len = (int32_t)d->text.n - off;
            }
            p = lt;
            continue;
        }
        if (p + 4 <= e && !memcmp(p, "<!--", 4)) {
            const char *q = p + 4;
            while (q + 3 <= e && memcmp(q, "-->", 3)) q++;
            if (q + 3 > e) return -1;
            p = q + 3;
            continue;
        }
        if (p + 9 <= e && !memcmp(p, "<![CDATA[", 9)) {
            const char *q = p + 9;
            while (q + 3 <= e && memcmp(q, "]]>", 3)) q++;
            if (q + 3 > e || cur < 0) return -1;
            int32_t off = (int32_t)d->text.n;
            cc_put(&d->text, p + 9, (size_t)(q - p - 9));
            int t = xm_new(d, XM_TEXT, -1, cur);
            if (t < 0) return -1;
            d->nd[t].off = off; d->nd[t].len = (int32_t)d->text.n - off;
            p = q + 3;
            continue;
        }
        if (p + 1 < e && p[1] == '?') {                      // processing instruction
            const char *q = p + 2;
            while (q + 2 <= e && memcmp(q, "?>", 2)) q++;
            if (q + 2 > e) return -1;
            p = q + 2;
            continue;
        }
        if (p + 1 < e && p[1] == '/') {                      // end tag
            const char *q = p + 2;
            while (q < e && xm_isname(*q)) q++;
            int nm = xm_intern(names, p + 2, (size_t)(q - p - 2));
            if (cur < 0 || nm != d->nd[cur].name) return -1;   // mismatched end tag
            while (q < e && *q != '>') q++;
            cur = d->nd[cur].parent;
            p = q + 1;
            continue;
        }
        const char *q = p + 1;                               // start tag
        while (q < e && xm_isname(*q)) q++;
        int nm = xm_intern(names, p + 1, (size_t)(q - p - 1));
        if (nm < 0) return -1;
        int el = xm_new(d, XM_ELEM, nm, cur);
        if (el < 0) return -1;
        if (cur < 0) { if (root >= 0) return -1; root = el; }
        d->nd[el].attr0 = d->na;
        for (;;) {
            while (q < e && (*q == ' ' || *q == '\n' || *q == '\t')) q++;
            if (q >= e) return -1;
            if (*q == '>' || *q == '/') break;
            const char *an = q;
            while (q < e && xm_isname(*q)) q++;
            int aname = xm_intern(names, an, (size_t)(q - an));
            if (aname < 0 || q + 1 >= e || *q != '=' || (q[1] != '"' && q[1] != '\'')) return -1;
            char quote = q[1];
            const char *v = q + 2, *ve = (const char *)memchr(v, quote, (size_t)(e - v));
            if (!ve) return -1;
            int32_t off = (int32_t)d->text.n;
            if (xm_decode(&d->text, v, ve)) return -1;
            if (xm_add_attr(d, aname, off, (int32_t)d->text.n - off) < 0) return -1;
            d->nd[el].nattr++;
            q = ve + 1;
        }
        if (*q == '/') { if (q + 1 >= e || q[1] != '>') return -1; p = q + 2; }
        else { cur = el; p = q + 1; }
    }
    if (cur >= 0 || d->err || d->text.fail) return -1;
    return root;
}

// ── A small path language: /a/b[@x='v'][c>=123]/d ──────────────────────

enum { XP_ATTR_EQ, XP_CHILD_GE, XP_CHILD_LT };
typedef struct { int kind, name; int64_t num; char str[16]; } xm_pred;
typedef struct { int name, npred; xm_pred pred[3]; } xm_step;
typedef struct { xm_step step[6]; int nsteps; } xm_path;

static int xm_compile_path(xm_path *pt, xm_names *names, const char *s) {
    pt->nsteps = 0;
    while (*s == '/') s++;
    while (*s) {
        if (pt->nsteps >= 6) return -1;
        xm_step *st = &pt->step[pt->nsteps++];
        const char *b = s;
        while (xm_isname(*s)) s++;
        if ((st->name = xm_intern(names, b, (size_t)(s - b))) < 0) return -1;
        st->npred = 0;
        while (*s == '[') {
            if (st->npred >= 3) return -1;
            xm_pred *pr = &st->pred[st->npred++];
            s++;
            int attr = *s == '@';
            if (attr) s++;
            b = s;
            while (xm_isname(*s)) s++;
            if ((pr->name = xm_intern(names, b, (size_t)(s - b))) < 0) return -1;
            if (attr) {
                if (s[0] != '=' || s[1] != '\'') return -1;
                s += 2;
                size_t k = 0;
                while (*s && *s != '\'' && k < 15) pr->str[k++] = *s++;
                pr->str[k] = 0;
                if (*s++ != '\'') return -1;
                pr->kind = XP_ATTR_EQ;
            } else {
                if (s[0] == '>' && s[1] == '=') { pr->kind = XP_CHILD_GE; s += 2; }
                else if (s[0] == '<') { pr->kind = XP_CHILD_LT; s += 1; }
                else return -1;
                pr->num = strtoll(s, (char **)&s, 10);
            }
            if (*s++ != ']') return -1;
        }
        if (*s == '/') s++;
    }
    return 0;
}

static int xm_child(const xm_doc *d, int el, int name) {
    for (int c = d->nd[el].first; c >= 0; c = d->nd[c].next)
        if (d->nd[c].kind == XM_ELEM && d->nd[c].name == name) return c;
    return -1;
}

/// The element's first text child as (pointer, length); "" if none.
static const char *xm_text(const xm_doc *d, int el, int32_t *len) {
    if (el >= 0)
        for (int c = d->nd[el].first; c >= 0; c = d->nd[c].next)
            if (d->nd[c].kind == XM_TEXT) { *len = d->nd[c].len; return d->text.p + d->nd[c].off; }
    *len = 0;
    return "";
}

static const char *xm_attr_val(const xm_doc *d, int el, int name, int32_t *len) {
    for (int a = 0; a < d->nd[el].nattr; a++) {
        const xm_attr *x = &d->at[d->nd[el].attr0 + a];
        if (x->name == name) { *len = x->len; return d->text.p + x->off; }
    }
    *len = 0;
    return NULL;
}

/// Decimal text to a fixed-point number with two decimals ("12.5" → 1250).
static int64_t xm_fixed(const char *p, int32_t n) {
    int64_t v = 0; int frac = -1;
    for (int32_t i = 0; i < n; i++) {
        if (p[i] == '.') { frac = 0; continue; }
        if (p[i] < '0' || p[i] > '9') break;
        if (frac >= 2) break;
        v = v * 10 + (p[i] - '0');
        if (frac >= 0) frac++;
    }
    if (frac < 0) frac = 0;
    while (frac++ < 2) v *= 10;
    return v;
}

static int xm_match(const xm_doc *d, int el, const xm_step *st) {
    for (int k = 0; k < st->npred; k++) {
        const xm_pred *pr = &st->pred[k];
        int32_t len;
        if (pr->kind == XP_ATTR_EQ) {
            const char *v = xm_attr_val(d, el, pr->name, &len);
            if (!v || (size_t)len != strlen(pr->str) || memcmp(v, pr->str, (size_t)len)) return 0;
        } else {
            const char *t = xm_text(d, xm_child(d, el, pr->name), &len);
            int64_t v = xm_fixed(t, len) / 100;
            if (pr->kind == XP_CHILD_GE ? v < pr->num : v >= pr->num) return 0;
        }
    }
    return 1;
}

/// Evaluates a path from the root; fills `set` (capacity `cap`), returns count.
static int xm_select(const xm_doc *d, int root, const xm_path *pt, int *set, int *tmp, int cap) {
    int n = 0;
    if (d->nd[root].name == pt->step[0].name && xm_match(d, root, &pt->step[0])) set[n++] = root;
    for (int s = 1; s < pt->nsteps; s++) {
        int m = 0;
        for (int i = 0; i < n; i++)
            for (int c = d->nd[set[i]].first; c >= 0; c = d->nd[c].next)
                if (d->nd[c].kind == XM_ELEM && d->nd[c].name == pt->step[s].name &&
                    xm_match(d, c, &pt->step[s]) && m < cap)
                    tmp[m++] = c;
        memcpy(set, tmp, (size_t)m * sizeof(int));
        n = m;
    }
    return n;
}

typedef struct { const char *last, *first, *title, *id; int32_t ll, fl, tl, il; int node; } xm_row;

static int xm_cmpstr(const char *a, int32_t la, const char *b, int32_t lb) {
    int32_t n = la < lb ? la : lb;
    int c = memcmp(a, b, (size_t)n);
    return c ? c : (la > lb) - (la < lb);
}
static int xm_rowcmp(const xm_row *a, const xm_row *b) {
    int c = xm_cmpstr(a->last, a->ll, b->last, b->ll);
    if (!c) c = xm_cmpstr(a->first, a->fl, b->first, b->fl);
    if (!c) c = xm_cmpstr(a->title, a->tl, b->title, b->tl);
    if (!c) c = xm_cmpstr(a->id, a->il, b->id, b->il);
    return c;
}
static void xm_msort(xm_row *a, xm_row *tmp, int n) {
    if (n < 2) return;
    int h = n / 2;
    xm_msort(a, tmp, h);
    xm_msort(a + h, tmp, n - h);
    int i = 0, j = h, k = 0;
    while (i < h && j < n) tmp[k++] = xm_rowcmp(&a[j], &a[i]) < 0 ? a[j++] : a[i++];
    while (i < h) tmp[k++] = a[i++];
    while (j < n) tmp[k++] = a[j++];
    memcpy(a, tmp, (size_t)n * sizeof *a);
}

// Result-tree building helpers.
static int xm_el(xm_doc *o, xm_names *nm, int parent, const char *name) {
    int id = xm_intern(nm, name, strlen(name));
    if (id < 0) { o->err = 1; return -1; }
    return xm_new(o, XM_ELEM, id, parent);
}
static void xm_txt(xm_doc *o, int parent, const char *s, size_t n) {
    int32_t off = (int32_t)o->text.n;
    cc_put(&o->text, s, n);
    int t = xm_new(o, XM_TEXT, -1, parent);
    if (t >= 0) { o->nd[t].off = off; o->nd[t].len = (int32_t)(o->text.n - (size_t)off); }
}
static void xm_txtnum(xm_doc *o, int parent, int64_t v, int fixed2) {
    cc_buf *b = &o->text;
    int32_t off = (int32_t)b->n;
    if (fixed2) {
        cc_puti(b, v / 100); cc_puts(b, ".");
        cc_puti(b, (v % 100) / 10); cc_puti(b, v % 10);
    } else cc_puti(b, v);
    int t = xm_new(o, XM_TEXT, -1, parent);
    if (t >= 0) { o->nd[t].off = off; o->nd[t].len = (int32_t)(b->n - (size_t)off); }
}
static void xm_setattr(xm_doc *o, xm_names *nm, int el, const char *name, const char *val) {
    int id = xm_intern(nm, name, strlen(name));
    int32_t off = (int32_t)o->text.n;
    cc_puts(&o->text, val);
    if (id < 0 || el < 0) { o->err = 1; return; }
    if (o->nd[el].nattr == 0) o->nd[el].attr0 = o->na;
    if (o->na != o->nd[el].attr0 + o->nd[el].nattr) { o->err = 1; return; }
    xm_add_attr(o, id, off, (int32_t)(o->text.n - (size_t)off));
    o->nd[el].nattr++;
}

static void xm_escape(cc_buf *b, const char *s, int32_t n, int attr) {
    int32_t run = 0;
    for (int32_t i = 0; i < n; i++) {
        const char *rep = NULL;
        switch (s[i]) {
        case '&': rep = "&amp;"; break;
        case '<': rep = "&lt;"; break;
        case '>': rep = "&gt;"; break;
        case '"': if (attr) rep = "&quot;"; break;
        }
        if (rep) { cc_put(b, s + run, (size_t)(i - run)); cc_puts(b, rep); run = i + 1; }
    }
    cc_put(b, s + run, (size_t)(n - run));
}

/// Serialises a result tree as HTML (iteratively: no recursion depth).
static void xm_serialise(const xm_doc *o, const xm_names *nm, int root, cc_buf *b) {
    int n = root;
    while (n >= 0) {
        const xm_node *x = &o->nd[n];
        if (x->kind == XM_TEXT) xm_escape(b, o->text.p + x->off, x->len, 0);
        else {
            cc_puts(b, "<");
            cc_put(b, nm->pool + nm->off[x->name], nm->len[x->name]);
            for (int a = 0; a < x->nattr; a++) {
                const xm_attr *at = &o->at[x->attr0 + a];
                cc_puts(b, " ");
                cc_put(b, nm->pool + nm->off[at->name], nm->len[at->name]);
                cc_puts(b, "=\"");
                xm_escape(b, o->text.p + at->off, at->len, 1);
                cc_puts(b, "\"");
            }
            cc_puts(b, ">");
            if (x->first >= 0) { n = x->first; continue; }
            cc_puts(b, "</"); cc_put(b, nm->pool + nm->off[x->name], nm->len[x->name]); cc_puts(b, ">");
        }
        // next: sibling, or climb, closing elements on the way up
        while (n >= 0 && o->nd[n].next < 0) {
            n = o->nd[n].parent;
            if (n < 0) break;
            const xm_node *p = &o->nd[n];
            cc_puts(b, "</"); cc_put(b, nm->pool + nm->off[p->name], nm->len[p->name]); cc_puts(b, ">");
            if (n == root) { n = -1; break; }
        }
        if (n == root) break;
        if (n >= 0) n = o->nd[n].next;
    }
}

// Ends a text node begun at text offset `off` (pieces appended since).
static void xm_txt_end(xm_doc *o, int parent, int32_t off) {
    int t = xm_new(o, XM_TEXT, -1, parent);
    if (t >= 0) { o->nd[t].off = off; o->nd[t].len = (int32_t)(o->text.n - (size_t)off); }
}

/// xml — an XSLT-style transformation of the xalancbmk kind. Each round
/// generates a book catalogue (attributes, entity and character
/// references, CDATA sections, comments), parses it into a DOM with an
/// interned name pool and end-tag checking, evaluates path expressions
/// with attribute and numeric predicates (/catalog/book[@lang='en']
/// [year>=1960]), sorts the selection by author and title with a merge
/// sort, aggregates prices per language and counts tags, builds an HTML
/// result tree with renamed elements, and serialises it with escaping.
/// Sizes transform 120, 660 and 3000 catalogues of 1500 books (about
/// 0.47 MB each). `checksum` digests the HTML; `value` is HTML bytes
/// produced; `work` is MB of XML parsed.
int cbk_xml(int size, cb_bench_result *out) {
    static const int docs_by_size[3] = {120, 660, 3000};
    enum { RECORDS = 1500 };
    size = ia_size(size);
    int rc = 1;
    xm_names *nm = (xm_names *)calloc(1, sizeof *nm);
    xm_doc in = {0}, res = {0};
    cc_buf src = {0}, html = {0};
    int cap = RECORDS * 4;
    int *set = (int *)malloc((size_t)cap * sizeof(int)), *tmp = (int *)malloc((size_t)cap * sizeof(int));
    xm_row *rows = (xm_row *)malloc(RECORDS * sizeof(xm_row)), *rtmp = (xm_row *)malloc(RECORDS * sizeof(xm_row));
    if (!nm || !set || !tmp || !rows || !rtmp) goto done;

    xm_path p_sel, p_all, p_tags;
    if (xm_compile_path(&p_sel, nm, "/catalog/book[@lang='en'][year>=1960]") ||
        xm_compile_path(&p_all, nm, "/catalog/book") ||
        xm_compile_path(&p_tags, nm, "/catalog/book/tags/tag"))
        goto done;
    int n_author = xm_intern(nm, "author", 6), n_first = xm_intern(nm, "first", 5);
    int n_last = xm_intern(nm, "last", 4), n_title = xm_intern(nm, "title", 5);
    int n_year = xm_intern(nm, "year", 4), n_price = xm_intern(nm, "price", 5);
    int n_tags = xm_intern(nm, "tags", 4), n_id = xm_intern(nm, "id", 2);
    int n_lang = xm_intern(nm, "lang", 4), n_region = xm_intern(nm, "region", 6);

    ia_rng r = { 0x0000C0FFEE5EED00ull };
    uint64_t h = IA_FNV_BASIS, inbytes = 0, outbytes = 0;
    for (int doc = 0; doc < docs_by_size[size - 1]; doc++) {
        src.n = 0;
        xm_generate(&src, &r, RECORDS, doc);
        if (src.fail) goto done;
        inbytes += src.n;
        int root = xm_parse(&in, nm, src.p, src.n);
        if (root < 0) { rc = 2; goto done; }

        // Select, then sort by author and title.
        int n = xm_select(&in, root, &p_sel, set, tmp, cap);
        for (int i = 0; i < n; i++) {
            xm_row *w = &rows[i];
            int au = xm_child(&in, set[i], n_author);
            w->node = set[i];
            w->last = xm_text(&in, au >= 0 ? xm_child(&in, au, n_last) : -1, &w->ll);
            w->first = xm_text(&in, au >= 0 ? xm_child(&in, au, n_first) : -1, &w->fl);
            w->title = xm_text(&in, xm_child(&in, set[i], n_title), &w->tl);
            w->id = xm_attr_val(&in, set[i], n_id, &w->il);
            if (!w->id) w->id = "";
        }
        xm_msort(rows, rtmp, n);

        // The result tree.
        res.nn = 0; res.na = 0; res.text.n = 0; res.err = 0;
        int ht = xm_el(&res, nm, -1, "html");
        int head = xm_el(&res, nm, ht, "head");
        int ti = xm_el(&res, nm, head, "title");
        int32_t off = (int32_t)res.text.n, rl;
        const char *region = xm_attr_val(&in, root, n_region, &rl);
        cc_puts(&res.text, "Catalogue ");
        if (region) cc_put(&res.text, region, (size_t)rl);
        xm_txt_end(&res, ti, off);
        int body = xm_el(&res, nm, ht, "body");
        xm_txt(&res, xm_el(&res, nm, body, "h1"), "English books since 1960", 24);
        int table = xm_el(&res, nm, body, "table");
        xm_setattr(&res, nm, table, "class", "books");
        int tr = xm_el(&res, nm, table, "tr");
        static const char *const heads[5] = {"Author", "Title", "Year", "Price", "Tags"};
        for (int k = 0; k < 5; k++) xm_txt(&res, xm_el(&res, nm, tr, "th"), heads[k], strlen(heads[k]));
        for (int i = 0; i < n; i++) {
            const xm_row *w = &rows[i];
            tr = xm_el(&res, nm, table, "tr");
            xm_setattr(&res, nm, tr, "class", i & 1 ? "odd" : "even");
            int td = xm_el(&res, nm, tr, "td");
            off = (int32_t)res.text.n;
            cc_put(&res.text, w->last, (size_t)w->ll); cc_puts(&res.text, ", ");
            cc_put(&res.text, w->first, (size_t)w->fl);
            xm_txt_end(&res, td, off);
            xm_txt(&res, xm_el(&res, nm, tr, "td"), w->title, (size_t)w->tl);
            int32_t len;
            const char *t = xm_text(&in, xm_child(&in, w->node, n_year), &len);
            xm_txt(&res, xm_el(&res, nm, tr, "td"), t, (size_t)len);
            t = xm_text(&in, xm_child(&in, w->node, n_price), &len);
            td = xm_el(&res, nm, tr, "td");
            xm_setattr(&res, nm, td, "class", "num");
            xm_txtnum(&res, td, xm_fixed(t, len), 1);
            td = xm_el(&res, nm, tr, "td");
            off = (int32_t)res.text.n;
            int tg = xm_child(&in, w->node, n_tags), k = 0;
            for (int c = tg >= 0 ? in.nd[tg].first : -1; c >= 0; c = in.nd[c].next) {
                t = xm_text(&in, c, &len);
                if (k++) cc_puts(&res.text, ", ");
                cc_put(&res.text, t, (size_t)len);
            }
            xm_txt_end(&res, td, off);
        }

        // Aggregate: books and average price per language.
        int na = xm_select(&in, root, &p_all, set, tmp, cap);
        int64_t cnt[5] = {0}, sum[5] = {0};
        for (int i = 0; i < na; i++) {
            int32_t len, pl;
            const char *lg = xm_attr_val(&in, set[i], n_lang, &len);
            const char *pr = xm_text(&in, xm_child(&in, set[i], n_price), &pl);
            for (int k = 0; k < 5; k++)
                if (lg && len == 2 && !memcmp(lg, xm_lang[k], 2)) { cnt[k]++; sum[k] += xm_fixed(pr, pl); break; }
        }
        xm_txt(&res, xm_el(&res, nm, body, "h2"), "By language", 11);
        int ul = xm_el(&res, nm, body, "ul");
        for (int k = 0; k < 5; k++) {
            int li = xm_el(&res, nm, ul, "li");
            off = (int32_t)res.text.n;
            cc_puts(&res.text, xm_lang[k]); cc_puts(&res.text, ": "); cc_puti(&res.text, cnt[k]);
            cc_puts(&res.text, " books, average ");
            int64_t avg = cnt[k] ? sum[k] / cnt[k] : 0;
            cc_puti(&res.text, avg / 100); cc_puts(&res.text, ".");
            cc_puti(&res.text, (avg % 100) / 10); cc_puti(&res.text, avg % 10);
            xm_txt_end(&res, li, off);
        }

        // Tag frequencies, most common first.
        int nt = xm_select(&in, root, &p_tags, set, tmp, cap);
        const char *tname[32]; int32_t tlen[32]; int64_t tcount[32]; int ntags = 0;
        for (int i = 0; i < nt; i++) {
            int32_t len;
            const char *t = xm_text(&in, set[i], &len);
            int k = 0;
            while (k < ntags && xm_cmpstr(tname[k], tlen[k], t, len)) k++;
            if (k == ntags) { if (ntags == 32) continue; tname[k] = t; tlen[k] = len; tcount[k] = 0; ntags++; }
            tcount[k]++;
        }
        for (int i = 1; i < ntags; i++)                       // insertion sort: count desc, name asc
            for (int j = i; j > 0; j--) {
                int sw = tcount[j] > tcount[j - 1] ||
                         (tcount[j] == tcount[j - 1] && xm_cmpstr(tname[j], tlen[j], tname[j - 1], tlen[j - 1]) < 0);
                if (!sw) break;
                const char *a = tname[j]; tname[j] = tname[j - 1]; tname[j - 1] = a;
                int32_t l = tlen[j]; tlen[j] = tlen[j - 1]; tlen[j - 1] = l;
                int64_t c = tcount[j]; tcount[j] = tcount[j - 1]; tcount[j - 1] = c;
            }
        xm_txt(&res, xm_el(&res, nm, body, "h2"), "Tags", 4);
        int ol = xm_el(&res, nm, body, "ol");
        for (int k = 0; k < ntags; k++) {
            int li = xm_el(&res, nm, ol, "li");
            off = (int32_t)res.text.n;
            cc_put(&res.text, tname[k], (size_t)tlen[k]); cc_puts(&res.text, " (");
            cc_puti(&res.text, tcount[k]); cc_puts(&res.text, ")");
            xm_txt_end(&res, li, off);
        }
        if (res.err || res.text.fail || in.err) goto done;

        html.n = 0;
        cc_puts(&html, "<!DOCTYPE html>\n");
        xm_serialise(&res, nm, ht, &html);
        if (html.fail) goto done;
        outbytes += html.n;
        h = ia_fnv(h, html.p, html.n);
    }
    h = ia_mix(h, inbytes);
    h = ia_mix(h, outbytes);
    ia_fill(out, h, (double)outbytes, (double)inbytes / 1e6, "MB");
    rc = 0;
done:
    free(nm); free(in.nd); free(in.at); free(in.text.p); free(res.nd); free(res.at); free(res.text.p);
    free(src.p); free(html.p); free(set); free(tmp); free(rows); free(rtmp);
    return rc;
}

// ── video: the core of a block-based video encoder ──────────────────────

#define VD_W 640
#define VD_H 352
#define VD_PAD 48
#define VD_STRIDE (VD_W + 2 * VD_PAD)
#define VD_RANGE 24

// Integer transforms: rows are mutually orthogonal, so the inverse is
// Cᵀ·D⁻¹·Y·D⁻¹·C with D the diagonal of squared row norms.
static const int8_t vd_c4[4][4] = {{1, 1, 1, 1}, {2, 1, -1, -2}, {1, -1, -1, 1}, {1, -2, 2, -1}};
static const int8_t vd_c8[8][8] = {
    {8, 8, 8, 8, 8, 8, 8, 8},          {12, 10, 6, 3, -3, -6, -10, -12},
    {8, 4, -4, -8, -8, -4, 4, 8},      {10, -3, -12, -6, 6, 12, 3, -10},
    {8, -8, -8, 8, 8, -8, -8, 8},      {6, -12, 3, 10, -10, -3, 12, -6},
    {4, -8, 8, -4, -4, 8, -8, 4},      {3, -6, 10, -12, 12, -10, 6, -3}};

typedef struct {
    int32_t mf4[16], dq4[16], mf8[64], dq8[64];   // quantiser / dequantiser per position
    uint8_t zz4[16], zz8[64];                     // zigzag scan orders
    int lambda_mv, lambda_rd;
} vd_tables;

typedef struct { uint8_t *buf; size_t cap, pos; uint64_t acc; int nacc; uint64_t bits; } vd_bits;

static void vd_put(vd_bits *b, uint32_t code, int len) {
    b->bits += (uint64_t)len;
    b->acc = (b->acc << len) | code;
    b->nacc += len;
    while (b->nacc >= 8) {
        b->nacc -= 8;
        if (b->pos < b->cap) b->buf[b->pos++] = (uint8_t)(b->acc >> b->nacc);
    }
}
static int vd_ue_len(uint32_t v) { return 2 * (31 - __builtin_clz(v + 1)) + 1; }
static void vd_ue(vd_bits *b, uint32_t v) { vd_put(b, v + 1, vd_ue_len(v)); }
static uint32_t vd_se_map(int32_t v) { return v > 0 ? (uint32_t)(2 * v - 1) : (uint32_t)(-2 * v); }

static void vd_zigzag(uint8_t *zz, int n) {
    int k = 0;
    for (int s = 0; s < 2 * n - 1; s++)
        for (int i = 0; i < n; i++) {
            int a = s & 1 ? i : s - i, b = s - a;        // alternate direction per diagonal
            if (a >= 0 && a < n && b >= 0 && b < n) zz[k++] = (uint8_t)(a * n + b);
        }
}

/// Builds quantiser tables for `qstep` (a multiple of 1/16) with norms
/// taken from the transform rows.
static void vd_make_tables(vd_tables *t, int qstep16) {
    double q = qstep16 / 16.0;
    for (int n = 4; n <= 8; n += 4) {
        for (int i = 0; i < n; i++)
            for (int j = 0; j < n; j++) {
                double ri = 0, rj = 0;
                for (int k = 0; k < n; k++) {
                    int ci = n == 4 ? vd_c4[i][k] : vd_c8[i][k], cj = n == 4 ? vd_c4[j][k] : vd_c8[j][k];
                    ri += ci * ci; rj += cj * cj;
                }
                double norm = sqrt(ri * rj);
                int32_t mf = (int32_t)(65536.0 / (q * norm) + 0.5);
                int32_t dq = (int32_t)(q * 4096.0 / norm + 0.5);
                if (n == 4) { t->mf4[i * 4 + j] = mf; t->dq4[i * 4 + j] = dq; }
                else { t->mf8[i * 8 + j] = mf; t->dq8[i * 8 + j] = dq; }
            }
    }
    vd_zigzag(t->zz4, 4);
    vd_zigzag(t->zz8, 8);
    t->lambda_mv = (int)(q * 0.9 + 0.5);
    t->lambda_rd = (int)(q * q * 0.85 + 0.5);
}

/// Forward transform of an n×n residual (stride n), Y = C·X·Cᵀ.
static void vd_fdct(const int16_t *x, int32_t *y, int n) {
    int32_t tmp[64];
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            int32_t s = 0;
            for (int k = 0; k < n; k++) s += (n == 4 ? vd_c4[i][k] : vd_c8[i][k]) * x[k * n + j];
            tmp[i * n + j] = s;
        }
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            int32_t s = 0;
            for (int k = 0; k < n; k++) s += tmp[i * n + k] * (n == 4 ? vd_c4[j][k] : vd_c8[j][k]);
            y[i * n + j] = s;
        }
}

/// Inverse from dequantised Z (scaled by 4096): X = Cᵀ·Z·C, rounded.
static void vd_idct(const int64_t *z, int16_t *x, int n) {
    int64_t tmp[64];
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            int64_t s = 0;
            for (int k = 0; k < n; k++) s += (n == 4 ? vd_c4[k][i] : vd_c8[k][i]) * z[k * n + j];
            tmp[i * n + j] = s;
        }
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            int64_t s = 0;
            for (int k = 0; k < n; k++) s += tmp[i * n + k] * (n == 4 ? vd_c4[k][j] : vd_c8[k][j]);
            x[i * n + j] = (int16_t)((s + 2048) >> 12);
        }
}

/// Transform, quantise, entropy-cost and reconstruct one n×n block.
/// Writes levels (zigzag order) and the reconstructed residual; returns bits.
static int vd_code_block(const vd_tables *t, const int16_t *res, int n, int intra,
                         int16_t *levels, int16_t *recres) {
    int32_t y[64]; int64_t z[64];
    vd_fdct(res, y, n);
    const int32_t *mf = n == 4 ? t->mf4 : t->mf8, *dq = n == 4 ? t->dq4 : t->dq8;
    const uint8_t *zz = n == 4 ? t->zz4 : t->zz8;
    int64_t dead = intra ? 65536 / 3 : 65536 / 6;
    int nn = n * n, bits = 0, nz = 0, run = 0;
    for (int k = 0; k < nn; k++) {
        int p = zz[k];
        int32_t v = y[p];
        int64_t a = v < 0 ? -(int64_t)v : v;
        int32_t l = (int32_t)((a * mf[p] + dead) >> 16);
        if (v < 0) l = -l;
        levels[k] = (int16_t)l;
        z[p] = (int64_t)l * dq[p];
        if (l) { bits += vd_ue_len((uint32_t)run) + vd_ue_len(vd_se_map(l)); run = 0; nz++; }
        else run++;
    }
    bits += vd_ue_len((uint32_t)nz);
    if (nz) vd_idct(z, recres, n);
    else memset(recres, 0, (size_t)nn * sizeof(int16_t));
    return bits;
}

static void vd_write_block(vd_bits *b, const int16_t *levels, int nn) {
    int nz = 0;
    for (int k = 0; k < nn; k++) nz += levels[k] != 0;
    vd_ue(b, (uint32_t)nz);
    int run = 0;
    for (int k = 0; k < nn; k++) {
        if (!levels[k]) { run++; continue; }
        vd_ue(b, (uint32_t)run);
        vd_ue(b, vd_se_map(levels[k]));
        run = 0;
    }
}

static int vd_sad16(const uint8_t *a, int sa, const uint8_t *b, int sb) {
    int s = 0;
    for (int y = 0; y < 16; y++, a += sa, b += sb)
        for (int x = 0; x < 16; x++) s += abs(a[x] - b[x]);
    return s;
}

/// Half-pel prediction: (hx, hy) in half pixels relative to `ref` (0,0).
static void vd_halfpel(const uint8_t *ref, int hx, int hy, uint8_t *dst) {
    const uint8_t *p = ref + (hy >> 1) * VD_STRIDE + (hx >> 1);
    int fx = hx & 1, fy = hy & 1;
    for (int y = 0; y < 16; y++, p += VD_STRIDE)
        for (int x = 0; x < 16; x++) {
            int v = p[x] + p[x + fx] + p[x + fy * VD_STRIDE] + p[x + fx + fy * VD_STRIDE];
            dst[y * 16 + x] = (uint8_t)((v + 2) >> 2);
        }
}

static int vd_se_len(int v) { return vd_ue_len(vd_se_map(v)); }
static int vd_median(int a, int b, int c) {
    int mx = a > b ? a : b, mn = a < b ? a : b;
    return c > mx ? mx : c < mn ? mn : c;
}

static void vd_pad(uint8_t *f) {   // replicate edges into the border
    for (int y = 0; y < VD_H; y++) {
        uint8_t *row = f + y * VD_STRIDE;
        memset(row - VD_PAD, row[0], VD_PAD);
        memset(row + VD_W, row[VD_W - 1], VD_PAD);
    }
    for (int y = 1; y <= VD_PAD; y++) {
        memcpy(f - y * VD_STRIDE - VD_PAD, f - VD_PAD, VD_STRIDE);
        memcpy(f + (VD_H - 1 + y) * VD_STRIDE - VD_PAD, f + (VD_H - 1) * VD_STRIDE - VD_PAD, VD_STRIDE);
    }
}

/// One synthetic frame: a panning textured background, six textured
/// objects moving and bouncing, and a little sensor noise.
static void vd_synth(uint8_t *cur, const uint8_t *tex, int t, int32_t obj[6][6], ia_rng *r) {
    int px = t * 2, py = t;
    for (int y = 0; y < VD_H; y++)
        for (int x = 0; x < VD_W; x++)
            cur[y * VD_W + x] = tex[((y + py) & 255) * 256 + ((x + px) & 255)];
    for (int k = 0; k < 6; k++) {
        int32_t *o = obj[k];                // x, y, w, h, vx, vy
        for (int y = 0; y < o[3]; y++)
            for (int x = 0; x < o[2]; x++) {
                int X = o[0] + x, Y = o[1] + y;
                if (X < 0 || Y < 0 || X >= VD_W || Y >= VD_H) continue;
                cur[Y * VD_W + X] = (uint8_t)(255 - tex[((y + 37 * k) & 255) * 256 + ((x + 91 * k) & 255)]);
            }
        o[0] += o[4]; o[1] += o[5];
        if (o[0] < -o[2] / 2 || o[0] > VD_W - o[2] / 2) o[4] = -o[4];
        if (o[1] < -o[3] / 2 || o[1] > VD_H - o[3] / 2) o[5] = -o[5];
    }
    for (int i = 0; i < VD_W * VD_H; i += 1 + (int)ia_below(r, 3)) {
        int v = cur[i] + (int)ia_below(r, 5) - 2;
        cur[i] = (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
    }
}

typedef struct { int16_t mx, my; uint8_t intra; } vd_mb;

static const int8_t vd_hex[6][2] = {{-2, 0}, {2, 0}, {-1, -2}, {1, -2}, {-1, 2}, {1, 2}};
static const int8_t vd_dia[4][2] = {{-1, 0}, {1, 0}, {0, -1}, {0, 1}};

typedef struct {
    const uint8_t *src; const uint8_t *ref0;
    int pmx, pmy, lam, xmin, xmax, ymin, ymax;
    uint64_t evals;
} vd_search;

static int vd_cost_full(vd_search *s, int mx, int my) {
    s->evals++;
    return vd_sad16(s->src, VD_W, s->ref0 + my * VD_STRIDE + mx, VD_STRIDE) +
           s->lam * (vd_se_len(2 * mx - s->pmx) + vd_se_len(2 * my - s->pmy));
}

/// Encodes one macroblock; returns its distortion (SSD).
static int64_t vd_encode_mb(const vd_tables *t, vd_bits *bw, const uint8_t *cur, const uint8_t *ref,
                            uint8_t *rec, vd_mb *mbs, int mbx, int mby, int pframe,
                            uint64_t *evals, uint64_t *modes) {
    const int MBW = VD_W / 16;
    const uint8_t *src = cur + mby * 16 * VD_W + mbx * 16;
    uint8_t *rmb = rec + mby * 16 * VD_STRIDE + mbx * 16;
    uint8_t pred[256], tmp[256];
    vd_mb *m = &mbs[mby * MBW + mbx];

    // Intra DC prediction from reconstructed neighbours.
    int dcs = 0, dcn = 0;
    if (mby > 0) { for (int x = 0; x < 16; x++) dcs += rmb[-VD_STRIDE + x]; dcn += 16; }
    if (mbx > 0) { for (int y = 0; y < 16; y++) dcs += rmb[y * VD_STRIDE - 1]; dcn += 16; }
    int dc = dcn ? (dcs + dcn / 2) / dcn : 128;
    int intra_cost = 0;
    for (int y = 0; y < 16; y++) for (int x = 0; x < 16; x++) intra_cost += abs(src[y * VD_W + x] - dc);
    intra_cost += t->lambda_mv * 6;

    int intra = 1, bmx = 0, bmy = 0, pmx = 0, pmy = 0;
    if (pframe) {
        // Motion-vector predictor: median of left, top and top-right.
        int ax = 0, ay = 0, bx = 0, by = 0, cx = 0, cy = 0;
        if (mbx > 0) { ax = m[-1].mx; ay = m[-1].my; }
        if (mby > 0) {
            bx = m[-MBW].mx; by = m[-MBW].my;
            const vd_mb *c = mbx + 1 < MBW ? &m[-MBW + 1] : mbx > 0 ? &m[-MBW - 1] : &m[-MBW];
            cx = c->mx; cy = c->my;
        }
        pmx = vd_median(ax, bx, cx); pmy = vd_median(ay, by, cy);
        vd_search s = { src, ref + mby * 16 * VD_STRIDE + mbx * 16, pmx, pmy, t->lambda_mv,
                        0, 0, 0, 0, 0 };
        s.xmin = -mbx * 16 - (VD_PAD - 8); if (s.xmin < -VD_RANGE) s.xmin = -VD_RANGE;
        s.xmax = VD_W - 16 - mbx * 16 + (VD_PAD - 8); if (s.xmax > VD_RANGE) s.xmax = VD_RANGE;
        s.ymin = -mby * 16 - (VD_PAD - 8); if (s.ymin < -VD_RANGE) s.ymin = -VD_RANGE;
        s.ymax = VD_H - 16 - mby * 16 + (VD_PAD - 8); if (s.ymax > VD_RANGE) s.ymax = VD_RANGE;
#define VD_CLAMPX(v) ((v) < s.xmin ? s.xmin : (v) > s.xmax ? s.xmax : (v))
#define VD_CLAMPY(v) ((v) < s.ymin ? s.ymin : (v) > s.ymax ? s.ymax : (v))
        int cand[4][2] = {{0, 0}, {pmx >> 1, pmy >> 1}, {ax >> 1, ay >> 1}, {bx >> 1, by >> 1}};
        int best = INT32_MAX, cxm = 0, cym = 0;
        for (int k = 0; k < 4; k++) {
            int x = VD_CLAMPX(cand[k][0]), y = VD_CLAMPY(cand[k][1]);
            int c = vd_cost_full(&s, x, y);
            if (c < best) { best = c; cxm = x; cym = y; }
        }
        for (int it = 0; it < 16; it++) {                   // large hexagon
            int bi = -1;
            for (int k = 0; k < 6; k++) {
                int x = cxm + vd_hex[k][0], y = cym + vd_hex[k][1];
                if (x < s.xmin || x > s.xmax || y < s.ymin || y > s.ymax) continue;
                int c = vd_cost_full(&s, x, y);
                if (c < best) { best = c; bi = k; }
            }
            if (bi < 0) break;
            cxm += vd_hex[bi][0]; cym += vd_hex[bi][1];
        }
        for (int it = 0; it < 4; it++) {                    // small diamond
            int bi = -1;
            for (int k = 0; k < 4; k++) {
                int x = cxm + vd_dia[k][0], y = cym + vd_dia[k][1];
                if (x < s.xmin || x > s.xmax || y < s.ymin || y > s.ymax) continue;
                int c = vd_cost_full(&s, x, y);
                if (c < best) { best = c; bi = k; }
            }
            if (bi < 0) break;
            cxm += vd_dia[bi][0]; cym += vd_dia[bi][1];
        }
#undef VD_CLAMPX
#undef VD_CLAMPY
        // Half-pel refinement around the integer best.
        int hx = 2 * cxm, hy = 2 * cym;
        const uint8_t *r0 = ref + mby * 16 * VD_STRIDE + mbx * 16;
        int bhx = hx, bhy = hy;
        for (int dy = -1; dy <= 1; dy++)
            for (int dx = -1; dx <= 1; dx++) {
                if (!dx && !dy) continue;
                int qx = hx + dx, qy = hy + dy;
                vd_halfpel(r0, qx, qy, tmp);
                s.evals++;
                int c = vd_sad16(src, VD_W, tmp, 16) + s.lam * (vd_se_len(qx - pmx) + vd_se_len(qy - pmy));
                if (c < best) { best = c; bhx = qx; bhy = qy; }
            }
        *evals += s.evals;
        if (best < intra_cost) { intra = 0; bmx = bhx; bmy = bhy; }
    }

    if (intra) memset(pred, dc, sizeof pred);
    else vd_halfpel(ref + mby * 16 * VD_STRIDE + mbx * 16, bmx, bmy, pred);
    m->intra = (uint8_t)intra; m->mx = (int16_t)(intra ? 0 : bmx); m->my = (int16_t)(intra ? 0 : bmy);

    // Residual, then both transform sizes; keep the cheaper in rate-distortion.
    int16_t res[256], blk[64], rr[64], lev4[16][16], lev8[4][64];
    uint8_t rec4[256], rec8[256];
    for (int i = 0; i < 256; i++) res[i] = (int16_t)(src[(i >> 4) * VD_W + (i & 15)] - pred[i]);
    int64_t bits4 = 0, bits8 = 0, ssd4 = 0, ssd8 = 0;
    for (int n = 4; n <= 8; n += 4) {
        int nb = 16 / n;
        for (int by = 0; by < nb; by++)
            for (int bx = 0; bx < nb; bx++) {
                for (int y = 0; y < n; y++)
                    for (int x = 0; x < n; x++) blk[y * n + x] = res[(by * n + y) * 16 + bx * n + x];
                int16_t *lv = n == 4 ? lev4[by * 4 + bx] : lev8[by * 2 + bx];
                int b = vd_code_block(t, blk, n, intra, lv, rr);
                uint8_t *rc = n == 4 ? rec4 : rec8;
                int64_t ssd = 0;
                for (int y = 0; y < n; y++)
                    for (int x = 0; x < n; x++) {
                        int p = (by * n + y) * 16 + bx * n + x;
                        int v = pred[p] + rr[y * n + x];
                        v = v < 0 ? 0 : v > 255 ? 255 : v;
                        rc[p] = (uint8_t)v;
                        int d = src[(p >> 4) * VD_W + (p & 15)] - v;
                        ssd += d * d;
                    }
                if (n == 4) { bits4 += b; ssd4 += ssd; } else { bits8 += b; ssd8 += ssd; }
            }
    }
    int use8 = ssd8 + (int64_t)t->lambda_rd * bits8 < ssd4 + (int64_t)t->lambda_rd * bits4;

    vd_ue(bw, (uint32_t)intra);
    if (!intra) { vd_ue(bw, vd_se_map(bmx - pmx)); vd_ue(bw, vd_se_map(bmy - pmy)); }
    vd_put(bw, (uint32_t)use8, 1);
    if (use8) for (int k = 0; k < 4; k++) vd_write_block(bw, lev8[k], 64);
    else for (int k = 0; k < 16; k++) vd_write_block(bw, lev4[k], 16);
    const uint8_t *rc = use8 ? rec8 : rec4;
    for (int y = 0; y < 16; y++) memcpy(rmb + y * VD_STRIDE, rc + y * 16, 16);
    modes[intra * 2 + use8]++;
    return use8 ? ssd8 : ssd4;
}

/// video — the core of an H.264-class encoder (the x264 kind) on synthetic
/// 640×352 frames (a panning texture, six moving textured objects,
/// sensor noise). Every 16×16 macroblock gets a median motion-vector
/// predictor, an integer hexagon search refined by a small diamond and
/// then half-pel (bilinear) refinement, all costed as SAD plus
/// λ·(exp-Golomb bits of the vector difference), against an intra DC
/// alternative. The residual is coded both with 4×4 and with 8×8
/// integer transforms (quantised with a dead zone, zigzag-scanned,
/// run/level exp-Golomb costed, dequantised and inverse-transformed) and
/// the cheaper in rate-distortion is written to the bitstream; the
/// reconstruction becomes the next reference, edge-padded. An I-frame
/// starts every group of 50. Sizes encode 36, 200 and 820 frames.
/// `checksum` digests the bitstream and the final reconstruction;
/// `value` is the bitstream size in bits; `work` is macroblocks encoded.
int cbk_video(int size, cb_bench_result *out) {
    static const int frames_by_size[3] = {36, 200, 820};
    enum { MBW = VD_W / 16, MBH = VD_H / 16, GOP = 50 };
    size = ia_size(size);
    int rc = 1;
    const size_t fsz = (size_t)VD_STRIDE * (VD_H + 2 * VD_PAD);
    uint8_t *tex = (uint8_t *)malloc(256 * 256), *cur = (uint8_t *)malloc(VD_W * VD_H);
    uint8_t *fa = (uint8_t *)calloc(fsz, 1), *fb = (uint8_t *)calloc(fsz, 1);
    int32_t *acc = (int32_t *)malloc(256 * 256 * sizeof(int32_t));
    vd_mb *mbs = (vd_mb *)calloc(MBW * MBH, sizeof(vd_mb));
    vd_tables *tp = (vd_tables *)malloc(sizeof *tp), *ti = (vd_tables *)malloc(sizeof *ti);
    vd_bits bw = {0};
    bw.cap = 1 << 20;
    bw.buf = (uint8_t *)malloc(bw.cap);
    if (!tex || !cur || !fa || !fb || !acc || !mbs || !tp || !ti || !bw.buf) goto done;
    vd_make_tables(tp, 13 * 16);
    vd_make_tables(ti, 10 * 16);

    // A smooth random texture with sharp-edged tiles on top.
    ia_rng r = { 0x51DE0F00D0000000ull };
    for (int i = 0; i < 256 * 256; i++) tex[i] = (uint8_t)ia_below(&r, 256);
    for (int pass = 0; pass < 2; pass++) {
        for (int y = 0; y < 256; y++)
            for (int x = 0; x < 256; x++) {
                int s = 0;
                for (int k = -3; k <= 3; k++) s += tex[y * 256 + ((x + k) & 255)];
                acc[y * 256 + x] = s;
            }
        for (int y = 0; y < 256; y++)
            for (int x = 0; x < 256; x++) {
                int s = 0;
                for (int k = -3; k <= 3; k++) s += acc[((y + k) & 255) * 256 + x];
                tex[y * 256 + x] = (uint8_t)(s / 49);
            }
    }
    for (int y = 0; y < 256; y++)
        for (int x = 0; x < 256; x++) {
            int v = (tex[y * 256 + x] - 128) * 3 + 128 + (((x >> 5) + (y >> 5)) & 1 ? 30 : -30);
            tex[y * 256 + x] = (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
        }
    int32_t obj[6][6];
    for (int k = 0; k < 6; k++) {
        obj[k][2] = 24 + (int32_t)ia_below(&r, 72); obj[k][3] = 24 + (int32_t)ia_below(&r, 56);
        obj[k][0] = (int32_t)ia_below(&r, VD_W - (uint32_t)obj[k][2]);
        obj[k][1] = (int32_t)ia_below(&r, VD_H - (uint32_t)obj[k][3]);
        obj[k][4] = (int32_t)ia_below(&r, 9) - 4; obj[k][5] = (int32_t)ia_below(&r, 7) - 3;
    }

    uint8_t *ref = fa + VD_PAD * VD_STRIDE + VD_PAD, *rec = fb + VD_PAD * VD_STRIDE + VD_PAD;
    uint64_t h = IA_FNV_BASIS, evals = 0, modes[4] = {0}, nmb = 0;
    int64_t ssd = 0;
    for (int f = 0; f < frames_by_size[size - 1]; f++) {
        vd_synth(cur, tex, f, obj, &r);
        int pframe = f % GOP != 0;
        const vd_tables *t = pframe ? tp : ti;
        vd_ue(&bw, (uint32_t)f);
        vd_put(&bw, (uint32_t)pframe, 1);
        for (int my = 0; my < MBH; my++)
            for (int mx = 0; mx < MBW; mx++) {
                ssd += vd_encode_mb(t, &bw, cur, ref, rec, mbs, mx, my, pframe, &evals, modes);
                nmb++;
            }
        vd_pad(rec);
        uint8_t *sw = ref; ref = rec; rec = sw;
        h = ia_fnv(h, bw.buf, bw.pos);
        bw.pos = 0;
    }
    for (int y = 0; y < VD_H; y++) h = ia_fnv(h, ref + y * VD_STRIDE, VD_W);
    h = ia_mix(h, bw.bits); h = ia_mix(h, (uint64_t)ssd); h = ia_mix(h, evals);
    for (int k = 0; k < 4; k++) h = ia_mix(h, modes[k]);
    ia_fill(out, h, (double)bw.bits, (double)nmb, "macroblocks");
    rc = 0;
done:
    free(tex); free(cur); free(fa); free(fb); free(acc); free(mbs); free(tp); free(ti); free(bw.buf);
    return rc;
}

// ── chess: bitboard move generation, perft and alpha-beta ───────────────

enum { CH_P, CH_N, CH_B, CH_R, CH_Q, CH_K };
enum { CH_CAP = 1, CH_EP = 2, CH_CASTLE = 4, CH_DOUBLE = 8 };
#define CH_MV(from, to, fl, promo) ((uint32_t)(from) | ((uint32_t)(to) << 6) | ((uint32_t)(promo) << 12) | ((uint32_t)(fl) << 16))
#define CH_FROM(m) ((int)((m) & 63))
#define CH_TO(m) ((int)(((m) >> 6) & 63))
#define CH_PROMO(m) ((int)(((m) >> 12) & 7))
#define CH_FL(m) ((int)((m) >> 16))
#define CH_MAXMV 320

typedef struct {
    uint64_t knight[64], king[64], patt[2][64], ray[8][64];
    uint64_t zob[12][64], zcastle[16], zep[65], zside;
    uint8_t castle_mask[64];
    int16_t pst[6][64], kend[64];
} ch_tab;

typedef struct {
    uint64_t bb[2][6], occ[2], key;
    int8_t sq[64];                  // color * 6 + piece, or -1
    uint8_t side, castle, ep;       // ep: square behind a double push, 64 if none
} ch_pos;

static void ch_init(ch_tab *t) {
    static const int df[8] = {0, 1, 1, -1, 0, -1, -1, 1}, dr[8] = {1, 0, 1, 1, -1, 0, -1, -1};
    static const int nf[8] = {1, 2, 2, 1, -1, -2, -2, -1}, nr[8] = {2, 1, -1, -2, -2, -1, 1, 2};
    memset(t, 0, sizeof *t);
    for (int s = 0; s < 64; s++) {
        int f = s & 7, r = s >> 3;
        for (int d = 0; d < 8; d++) {
            for (int k = 1; k < 8; k++) {
                int ff = f + df[d] * k, rr = r + dr[d] * k;
                if (ff < 0 || ff > 7 || rr < 0 || rr > 7) break;
                t->ray[d][s] |= 1ull << (rr * 8 + ff);
            }
            int ff = f + df[d], rr = r + dr[d];
            if (ff >= 0 && ff <= 7 && rr >= 0 && rr <= 7) t->king[s] |= 1ull << (rr * 8 + ff);
            ff = f + nf[d]; rr = r + nr[d];
            if (ff >= 0 && ff <= 7 && rr >= 0 && rr <= 7) t->knight[s] |= 1ull << (rr * 8 + ff);
        }
        if (r < 7) { if (f > 0) t->patt[0][s] |= 1ull << (s + 7); if (f < 7) t->patt[0][s] |= 1ull << (s + 9); }
        if (r > 0) { if (f > 0) t->patt[1][s] |= 1ull << (s - 9); if (f < 7) t->patt[1][s] |= 1ull << (s - 7); }
        t->castle_mask[s] = 15;
        // Piece-square terms from White's side (Black mirrors the rank).
        int cent = 6 - (abs(2 * f - 7) + abs(2 * r - 7)) / 2;
        t->pst[CH_P][s] = (int16_t)(r * 6 + ((f == 3 || f == 4) ? r * 4 : 0));
        t->pst[CH_N][s] = (int16_t)(cent * 6 - 10);
        t->pst[CH_B][s] = (int16_t)(cent * 4);
        t->pst[CH_R][s] = (int16_t)((r == 6 ? 20 : 0) + ((f == 3 || f == 4) ? 5 : 0));
        t->pst[CH_Q][s] = (int16_t)(cent * 2);
        t->pst[CH_K][s] = (int16_t)(r == 0 ? ((f <= 2 || f >= 6) ? 20 : 0) : -r * 12);
        t->kend[s] = (int16_t)(cent * 8);
    }
    t->castle_mask[0] = 15 & ~2; t->castle_mask[4] = 15 & ~3; t->castle_mask[7] = 15 & ~1;
    t->castle_mask[56] = 15 & ~8; t->castle_mask[60] = 15 & ~12; t->castle_mask[63] = 15 & ~4;
    ia_rng r = { 0xC4E55B0A2D000000ull };
    for (int p = 0; p < 12; p++) for (int s = 0; s < 64; s++) t->zob[p][s] = ia_next(&r);
    for (int c = 0; c < 16; c++) t->zcastle[c] = ia_next(&r);
    for (int s = 0; s < 64; s++) t->zep[s] = ia_next(&r);
    t->zep[64] = 0;
    t->zside = ia_next(&r);
}

static inline uint64_t ch_ray(const ch_tab *t, int d, int sq, uint64_t occ) {
    uint64_t a = t->ray[d][sq], b = a & occ;
    if (b) a &= ~t->ray[d][d < 4 ? __builtin_ctzll(b) : 63 - __builtin_clzll(b)];
    return a;
}
static inline uint64_t ch_rook(const ch_tab *t, int sq, uint64_t occ) {
    return ch_ray(t, 0, sq, occ) | ch_ray(t, 1, sq, occ) | ch_ray(t, 4, sq, occ) | ch_ray(t, 5, sq, occ);
}
static inline uint64_t ch_bishop(const ch_tab *t, int sq, uint64_t occ) {
    return ch_ray(t, 2, sq, occ) | ch_ray(t, 3, sq, occ) | ch_ray(t, 6, sq, occ) | ch_ray(t, 7, sq, occ);
}

static int ch_attacked(const ch_tab *t, const ch_pos *p, int sq, int by) {
    if (t->patt[by ^ 1][sq] & p->bb[by][CH_P]) return 1;
    if (t->knight[sq] & p->bb[by][CH_N]) return 1;
    if (t->king[sq] & p->bb[by][CH_K]) return 1;
    uint64_t occ = p->occ[0] | p->occ[1];
    uint64_t bq = p->bb[by][CH_B] | p->bb[by][CH_Q], rq = p->bb[by][CH_R] | p->bb[by][CH_Q];
    if (bq && (ch_bishop(t, sq, occ) & bq)) return 1;
    if (rq && (ch_rook(t, sq, occ) & rq)) return 1;
    return 0;
}

static inline int ch_in_check(const ch_tab *t, const ch_pos *p) {
    return ch_attacked(t, p, __builtin_ctzll(p->bb[p->side][CH_K]), p->side ^ 1);
}

static void ch_put(const ch_tab *t, ch_pos *p, int c, int pc, int sq) {
    p->bb[c][pc] |= 1ull << sq; p->occ[c] |= 1ull << sq; p->sq[sq] = (int8_t)(c * 6 + pc);
    p->key ^= t->zob[c * 6 + pc][sq];
}
static void ch_lift(const ch_tab *t, ch_pos *p, int c, int pc, int sq) {
    p->bb[c][pc] &= ~(1ull << sq); p->occ[c] &= ~(1ull << sq); p->sq[sq] = -1;
    p->key ^= t->zob[c * 6 + pc][sq];
}

static int ch_fen(const ch_tab *t, ch_pos *p, const char *fen) {
    memset(p, 0, sizeof *p);
    memset(p->sq, -1, sizeof p->sq);
    int r = 7, f = 0;
    for (; *fen && *fen != ' '; fen++) {
        char c = *fen;
        if (c == '/') { r--; f = 0; continue; }
        if (c >= '1' && c <= '8') { f += c - '0'; continue; }
        const char *pcs = "pnbrqk";
        int col = c >= 'a' ? 1 : 0;
        const char *k = strchr(pcs, col ? c : c + 32);
        if (!k || r < 0 || f > 7) return -1;
        ch_put(t, p, col, (int)(k - pcs), r * 8 + f);
        f++;
    }
    if (*fen++ != ' ') return -1;
    p->side = *fen == 'b';
    fen += 2;
    for (; *fen && *fen != ' '; fen++) {
        if (*fen == 'K') p->castle |= 1;
        if (*fen == 'Q') p->castle |= 2;
        if (*fen == 'k') p->castle |= 4;
        if (*fen == 'q') p->castle |= 8;
    }
    p->ep = 64;
    if (*fen == ' ' && fen[1] != '-' && fen[1]) p->ep = (uint8_t)((fen[2] - '1') * 8 + (fen[1] - 'a'));
    p->key ^= t->zcastle[p->castle] ^ t->zep[p->ep] ^ (p->side ? t->zside : 0);
    return 0;
}

static int ch_push(uint32_t *mv, int n, uint32_t m) { if (n < CH_MAXMV) mv[n++] = m; return n; }

/// Pseudo-legal moves; `noisy` limits to captures and queen promotions.
static int ch_gen(const ch_tab *t, const ch_pos *p, uint32_t *mv, int noisy) {
    int us = p->side, them = us ^ 1, n = 0;
    uint64_t own = p->occ[us], opp = p->occ[them], all = own | opp, empty = ~all;
    uint64_t pawns = p->bb[us][CH_P];
    const uint64_t FA = 0x0101010101010101ull, FH = FA << 7, R8 = 0xFFull << 56, R1 = 0xFFull;
    uint64_t prom = us ? R1 : R8;
    uint64_t push1 = us ? (pawns >> 8) & empty : (pawns << 8) & empty;
    uint64_t push2 = us ? ((push1 & (0xFFull << 40)) >> 8) & empty : ((push1 & (0xFFull << 16)) << 8) & empty;
    uint64_t capl = us ? (pawns >> 9) & ~FH & opp : (pawns << 7) & ~FH & opp;
    uint64_t capr = us ? (pawns >> 7) & ~FA & opp : (pawns << 9) & ~FA & opp;
    int up = us ? -8 : 8;
    for (uint64_t b = push1; b; b &= b - 1) {
        int to = __builtin_ctzll(b), from = to - up;
        if ((1ull << to) & prom) {
            n = ch_push(mv, n, CH_MV(from, to, 0, CH_Q));
            if (!noisy) for (int k = CH_N; k <= CH_R; k++) n = ch_push(mv, n, CH_MV(from, to, 0, k));
        } else if (!noisy) n = ch_push(mv, n, CH_MV(from, to, 0, 0));
    }
    if (!noisy)
        for (uint64_t b = push2; b; b &= b - 1) {
            int to = __builtin_ctzll(b);
            n = ch_push(mv, n, CH_MV(to - 2 * up, to, CH_DOUBLE, 0));
        }
    for (int side = 0; side < 2; side++) {
        uint64_t caps = side ? capr : capl;
        int delta = us ? (side ? -7 : -9) : (side ? 9 : 7);
        for (uint64_t b = caps; b; b &= b - 1) {
            int to = __builtin_ctzll(b), from = to - delta;
            if ((1ull << to) & prom) {
                n = ch_push(mv, n, CH_MV(from, to, CH_CAP, CH_Q));
                if (!noisy) for (int k = CH_N; k <= CH_R; k++) n = ch_push(mv, n, CH_MV(from, to, CH_CAP, k));
            } else n = ch_push(mv, n, CH_MV(from, to, CH_CAP, 0));
        }
    }
    if (p->ep < 64)
        for (uint64_t b = t->patt[them][p->ep] & pawns; b; b &= b - 1)
            n = ch_push(mv, n, CH_MV(__builtin_ctzll(b), p->ep, CH_CAP | CH_EP, 0));
    uint64_t target = noisy ? opp : ~own;
    for (int pc = CH_N; pc <= CH_K; pc++)
        for (uint64_t b = p->bb[us][pc]; b; b &= b - 1) {
            int from = __builtin_ctzll(b);
            uint64_t a = pc == CH_N ? t->knight[from] : pc == CH_B ? ch_bishop(t, from, all)
                       : pc == CH_R ? ch_rook(t, from, all)
                       : pc == CH_Q ? ch_rook(t, from, all) | ch_bishop(t, from, all) : t->king[from];
            for (a &= target; a; a &= a - 1) {
                int to = __builtin_ctzll(a);
                n = ch_push(mv, n, CH_MV(from, to, (opp >> to) & 1 ? CH_CAP : 0, 0));
            }
        }
    if (!noisy) {
        int base = us ? 56 : 0;
        uint8_t ks = us ? 4 : 1, qs = us ? 8 : 2;
        if ((p->castle & ks) && !(all & (0x60ull << base)) && !ch_attacked(t, p, base + 4, them) &&
            !ch_attacked(t, p, base + 5, them) && !ch_attacked(t, p, base + 6, them))
            n = ch_push(mv, n, CH_MV(base + 4, base + 6, CH_CASTLE, 0));
        if ((p->castle & qs) && !(all & (14ull << base)) && !ch_attacked(t, p, base + 4, them) &&
            !ch_attacked(t, p, base + 3, them) && !ch_attacked(t, p, base + 2, them))
            n = ch_push(mv, n, CH_MV(base + 4, base + 2, CH_CASTLE, 0));
    }
    return n;
}

/// Copy-make: writes the position after `m` into `c`; returns 0 if the
/// move leaves the mover's king in check (illegal).
static int ch_make(const ch_tab *t, const ch_pos *p, uint32_t m, ch_pos *c) {
    *c = *p;
    int from = CH_FROM(m), to = CH_TO(m), promo = CH_PROMO(m), fl = CH_FL(m);
    int us = p->side, them = us ^ 1, pc = p->sq[from] - us * 6;
    c->key ^= t->zcastle[p->castle] ^ t->zep[p->ep];
    if (fl & CH_EP) ch_lift(t, c, them, CH_P, us ? to + 8 : to - 8);
    else if (p->sq[to] >= 0) ch_lift(t, c, them, p->sq[to] - them * 6, to);
    ch_lift(t, c, us, pc, from);
    ch_put(t, c, us, promo ? promo : pc, to);
    if (fl & CH_CASTLE) {
        int base = us ? 56 : 0;
        if (to == base + 6) { ch_lift(t, c, us, CH_R, base + 7); ch_put(t, c, us, CH_R, base + 5); }
        else { ch_lift(t, c, us, CH_R, base); ch_put(t, c, us, CH_R, base + 3); }
    }
    c->castle = p->castle & t->castle_mask[from] & t->castle_mask[to];
    c->ep = (fl & CH_DOUBLE) ? (uint8_t)((from + to) >> 1) : 64;
    c->side = (uint8_t)them;
    c->key ^= t->zcastle[c->castle] ^ t->zep[c->ep] ^ t->zside;
    return !ch_attacked(t, c, __builtin_ctzll(c->bb[us][CH_K]), them);
}

static uint64_t ch_perft(const ch_tab *t, const ch_pos *p, int depth) {
    uint32_t mv[CH_MAXMV];
    int n = ch_gen(t, p, mv, 0);
    uint64_t count = 0;
    ch_pos q;
    for (int i = 0; i < n; i++)
        if (ch_make(t, p, mv[i], &q)) count += depth <= 1 ? 1 : ch_perft(t, &q, depth - 1);
    return count;
}

// ── Search ──────────────────────────────────────────────────────────────

enum { CH_EXACT = 1, CH_LOWER = 2, CH_UPPER = 3 };
#define CH_INF 32000
#define CH_MATE 30000
typedef struct { uint64_t key; uint32_t move; int16_t score; int8_t depth; uint8_t flag; } ch_tt;

typedef struct {
    const ch_tab *t;
    ch_tt *tt; uint64_t mask;
    uint32_t killer[96][2];
    uint64_t nodes;
    uint32_t root_best;
} ch_search;

static const int ch_value[6] = {100, 320, 330, 500, 900, 0};

static int ch_eval(const ch_tab *t, const ch_pos *p) {
    int s[2] = {0, 0}, npm = 0;
    uint64_t all = p->occ[0] | p->occ[1];
    for (int c = 0; c < 2; c++)
        for (int pc = CH_N; pc <= CH_Q; pc++) npm += __builtin_popcountll(p->bb[c][pc]) * ch_value[pc];
    for (int c = 0; c < 2; c++) {
        uint64_t mine = p->occ[c];
        int flip = c ? 56 : 0;
        for (int pc = CH_P; pc <= CH_K; pc++)
            for (uint64_t b = p->bb[c][pc]; b; b &= b - 1) {
                int sq = __builtin_ctzll(b), rel = sq ^ flip;
                s[c] += ch_value[pc] + (pc == CH_K && npm < 1300 ? t->kend[rel] : t->pst[pc][rel]);
                switch (pc) {
                case CH_N: s[c] += 4 * __builtin_popcountll(t->knight[sq] & ~mine); break;
                case CH_B: s[c] += 4 * __builtin_popcountll(ch_bishop(t, sq, all) & ~mine); break;
                case CH_R: s[c] += 2 * __builtin_popcountll(ch_rook(t, sq, all) & ~mine); break;
                case CH_Q: s[c] += __builtin_popcountll((ch_rook(t, sq, all) | ch_bishop(t, sq, all)) & ~mine); break;
                }
            }
        if (__builtin_popcountll(p->bb[c][CH_B]) >= 2) s[c] += 30;
    }
    return p->side ? s[1] - s[0] : s[0] - s[1];
}

static int ch_mvv_lva(const ch_pos *p, uint32_t m) {
    int victim = (CH_FL(m) & CH_EP) ? CH_P : p->sq[CH_TO(m)] >= 0 ? p->sq[CH_TO(m)] % 6 : 0;
    int attacker = p->sq[CH_FROM(m)] % 6;
    return ch_value[victim] * 10 - ch_value[attacker] / 10 + (CH_PROMO(m) ? 8000 : 0);
}

static inline void ch_pick(uint32_t *mv, int *sc, int i, int n) {
    int b = i;
    for (int j = i + 1; j < n; j++) if (sc[j] > sc[b]) b = j;
    uint32_t m = mv[i]; mv[i] = mv[b]; mv[b] = m;
    int s = sc[i]; sc[i] = sc[b]; sc[b] = s;
}

static int ch_qsearch(ch_search *s, const ch_pos *p, int alpha, int beta, int ply) {
    s->nodes++;
    int stand = ch_eval(s->t, p);
    if (stand >= beta || ply >= 80) return stand;
    if (stand > alpha) alpha = stand;
    uint32_t mv[CH_MAXMV]; int sc[CH_MAXMV];
    int n = ch_gen(s->t, p, mv, 1);
    for (int i = 0; i < n; i++) sc[i] = ch_mvv_lva(p, mv[i]);
    ch_pos q;
    for (int i = 0; i < n; i++) {
        ch_pick(mv, sc, i, n);
        if (!ch_make(s->t, p, mv[i], &q)) continue;
        int v = -ch_qsearch(s, &q, -beta, -alpha, ply + 1);
        if (v >= beta) return v;
        if (v > alpha) alpha = v;
    }
    return alpha;
}

static int ch_alphabeta(ch_search *s, const ch_pos *p, int depth, int alpha, int beta, int ply, int null_ok) {
    const ch_tab *t = s->t;
    int incheck = ch_in_check(t, p);
    if (incheck && ply < 48) depth++;
    if (depth <= 0) return ch_qsearch(s, p, alpha, beta, ply);
    s->nodes++;
    ch_tt *e = &s->tt[p->key & s->mask];
    uint32_t ttmove = 0;
    if (e->key == p->key) {
        ttmove = e->move;
        if (ply > 0 && e->depth >= depth) {
            if (e->flag == CH_EXACT) return e->score;
            if (e->flag == CH_LOWER && e->score >= beta) return e->score;
            if (e->flag == CH_UPPER && e->score <= alpha) return e->score;
        }
    }
    int us = p->side;
    uint64_t heavy = p->bb[us][CH_N] | p->bb[us][CH_B] | p->bb[us][CH_R] | p->bb[us][CH_Q];
    if (null_ok && !incheck && depth >= 3 && ply > 0 && heavy) {     // null-move pruning
        ch_pos q = *p;
        q.side ^= 1;
        q.key ^= t->zside ^ t->zep[q.ep] ^ t->zep[64];
        q.ep = 64;
        int v = -ch_alphabeta(s, &q, depth - 3, -beta, -beta + 1, ply + 1, 0);
        if (v >= beta) return beta;
    }
    uint32_t mv[CH_MAXMV]; int sc[CH_MAXMV];
    int n = ch_gen(t, p, mv, 0);
    int kp = ply < 96 ? ply : 95;
    for (int i = 0; i < n; i++) {
        uint32_t m = mv[i];
        sc[i] = m == ttmove ? 1000000 : (CH_FL(m) & CH_CAP) ? 100000 + ch_mvv_lva(p, m)
              : m == s->killer[kp][0] ? 90000 : m == s->killer[kp][1] ? 80000 : 0;
    }
    int best = -CH_INF, legal = 0, a0 = alpha;
    uint32_t bestmove = 0;
    ch_pos q;
    for (int i = 0; i < n; i++) {
        ch_pick(mv, sc, i, n);
        uint32_t m = mv[i];
        if (!ch_make(t, p, m, &q)) continue;
        legal++;
        int v = -ch_alphabeta(s, &q, depth - 1, -beta, -alpha, ply + 1, 1);
        if (v > best) {
            best = v; bestmove = m;
            if (ply == 0) s->root_best = m;
            if (v > alpha) {
                alpha = v;
                if (alpha >= beta) {
                    if (!(CH_FL(m) & CH_CAP) && s->killer[kp][0] != m) {
                        s->killer[kp][1] = s->killer[kp][0]; s->killer[kp][0] = m;
                    }
                    break;
                }
            }
        }
    }
    if (!legal) return incheck ? -CH_MATE + ply : 0;
    e->key = p->key; e->move = bestmove; e->score = (int16_t)best; e->depth = (int8_t)depth;
    e->flag = best <= a0 ? CH_UPPER : best >= beta ? CH_LOWER : CH_EXACT;
    return best;
}

/// chess — a bitboard chess engine of the deepsjeng / stockfish kind.
/// Move generation uses ray bitboards with first-blocker scans, covers
/// castling, en passant and promotions, and is verified by perft on six
/// standard test positions whose node counts are published (the run
/// fails if any count differs). Then each position is searched by
/// iterative-deepening negamax alpha-beta with a Zobrist-keyed
/// transposition table, null-move pruning, check extension, killer and
/// MVV-LVA move ordering, and a capture quiescence search over an
/// evaluation of material, piece-square terms, mobility and the bishop
/// pair. Sizes: perft to depths 5/3/5/4/3/3 (6.2 M leaves) and a 6-ply
/// search; depths 5/4/6/5/4/4 (42 M) and 7 plies; depths 5/5/6/5/5/4
/// (319 M) and 8 plies. `checksum` digests the perft counts and every
/// search's best move, score and node count; `value` is the perft total;
/// `work` is nodes (perft leaves plus search nodes).
int cbk_chess(int size, cb_bench_result *out) {
    static const char *const fens[6] = {
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"};
    // Published perft counts, depths 1..6 (0 where not used).
    static const uint64_t known[6][6] = {
        {20, 400, 8902, 197281, 4865609, 119060324},
        {48, 2039, 97862, 4085603, 193690690, 0},
        {14, 191, 2812, 43238, 674624, 11030083},
        {6, 264, 9467, 422333, 15833292, 0},
        {44, 1486, 62379, 2103487, 89941194, 0},
        {46, 2079, 89890, 3894594, 164075551, 0}};
    static const int8_t pdepth[3][6] = {{5, 3, 5, 4, 3, 3}, {5, 4, 6, 5, 4, 4}, {5, 5, 6, 5, 5, 4}};
    static const int sdepth[3] = {6, 7, 8};
    size = ia_size(size);
    int rc = 1;
    ch_tab *t = (ch_tab *)malloc(sizeof *t);
    ch_search *s = (ch_search *)calloc(1, sizeof *s);
    const uint64_t ttsize = 1u << 18;
    ch_tt *tt = (ch_tt *)malloc(ttsize * sizeof(ch_tt));
    if (!t || !s || !tt) goto done;
    ch_init(t);
    s->t = t; s->tt = tt; s->mask = ttsize - 1;

    uint64_t h = IA_FNV_BASIS, ptotal = 0, work = 0;
    for (int i = 0; i < 6; i++) {
        ch_pos p;
        if (ch_fen(t, &p, fens[i])) { rc = 2; goto done; }
        int d = pdepth[size - 1][i];
        uint64_t c = ch_perft(t, &p, d);
        if (c != known[i][d - 1]) { rc = 3; goto done; }     // move generator self-check
        ptotal += c;
        h = ia_mix(h, c);
    }
    work = ptotal;
    for (int i = 0; i < 6; i++) {
        ch_pos p;
        ch_fen(t, &p, fens[i]);
        memset(tt, 0, ttsize * sizeof(ch_tt));
        memset(s->killer, 0, sizeof s->killer);
        s->nodes = 0;
        int score = 0;
        for (int d = 1; d <= sdepth[size - 1]; d++) {
            score = ch_alphabeta(s, &p, d, -CH_INF, CH_INF, 0, 1);
            h = ia_mix(h, ((uint64_t)s->root_best << 20) ^ (uint64_t)(uint32_t)score);
        }
        h = ia_mix(h, s->nodes);
        work += s->nodes;
    }
    ia_fill(out, h, (double)ptotal, (double)work, "nodes");
    rc = 0;
done:
    free(t); free(s); free(tt);
    return rc;
}

// ── go: 9×9 Go with Monte-Carlo tree search ─────────────────────────────

#define GO_S 9
#define GO_W (GO_S + 2)
#define GO_N (GO_W * GO_W)
#define GO_PASS 0
enum { GO_EMPTY = 0, GO_BLACK = 1, GO_WHITE = 2, GO_EDGE = 3 };

typedef struct {
    uint8_t c[GO_N];
    int16_t head[GO_N], next[GO_N], size[GO_N];
    uint64_t lib[GO_N][2];          // liberty bitset, valid at string heads
    int16_t empty[GO_N], epos[GO_N]; int nempty;
    int ko, to_move, passes, last, moves;
} go_board;

static const int go_dir[4] = {-GO_W, -1, 1, GO_W};
static const int go_diag[4] = {-GO_W - 1, -GO_W + 1, GO_W - 1, GO_W + 1};

static inline int go_nlibs(const go_board *b, int h) {
    return __builtin_popcountll(b->lib[h][0]) + __builtin_popcountll(b->lib[h][1]);
}
static inline void go_libset(uint64_t *l, int p) { l[p >> 6] |= 1ull << (p & 63); }
static inline void go_libclr(uint64_t *l, int p) { l[p >> 6] &= ~(1ull << (p & 63)); }
static inline int go_onelib(const go_board *b, int h) {   // the liberty of a one-liberty string
    return b->lib[h][0] ? __builtin_ctzll(b->lib[h][0]) : 64 + __builtin_ctzll(b->lib[h][1]);
}

static void go_init(go_board *b) {
    memset(b, 0, sizeof *b);
    b->nempty = 0;
    for (int p = 0; p < GO_N; p++) {
        int x = p % GO_W, y = p / GO_W;
        if (x == 0 || y == 0 || x == GO_W - 1 || y == GO_W - 1) { b->c[p] = GO_EDGE; continue; }
        b->epos[p] = (int16_t)b->nempty;
        b->empty[b->nempty++] = (int16_t)p;
    }
    b->ko = -1; b->to_move = GO_BLACK; b->last = GO_PASS;
}

static void go_empty_add(go_board *b, int p) { b->epos[p] = (int16_t)b->nempty; b->empty[b->nempty++] = (int16_t)p; }
static void go_empty_del(go_board *b, int p) {
    int i = b->epos[p], q = b->empty[--b->nempty];
    b->empty[i] = (int16_t)q; b->epos[q] = (int16_t)i;
}

static int go_legal(const go_board *b, int p, int col) {
    if (p == GO_PASS) return 1;
    if (b->c[p] != GO_EMPTY || p == b->ko) return 0;
    for (int k = 0; k < 4; k++) {
        int q = p + go_dir[k], c = b->c[q];
        if (c == GO_EMPTY) return 1;
        if (c == GO_EDGE) continue;
        int n = go_nlibs(b, b->head[q]);
        if (c == col ? n > 1 : n == 1) return 1;   // friendly string keeps a liberty / enemy captured
    }
    return 0;
}

/// An eye of `col`: all neighbours friendly (or edge), few enemy diagonals.
static int go_eye(const go_board *b, int p, int col) {
    int edge = 0, bad = 0;
    for (int k = 0; k < 4; k++) {
        int c = b->c[p + go_dir[k]];
        if (c == GO_EDGE) edge = 1; else if (c != col) return 0;
    }
    for (int k = 0; k < 4; k++) {
        int c = b->c[p + go_diag[k]];
        if (c != GO_EDGE && c != GO_EMPTY && c != col) bad++;
    }
    return edge ? bad == 0 : bad < 2;
}

static int go_capture(go_board *b, int h) {
    int n = 0, s = h;
    do {                                           // lift the stones
        b->c[s] = GO_EMPTY; go_empty_add(b, s); n++;
        s = b->next[s];
    } while (s != h);
    s = h;
    do {                                           // give neighbours their liberties back
        for (int k = 0; k < 4; k++) {
            int q = s + go_dir[k];
            if (b->c[q] == GO_BLACK || b->c[q] == GO_WHITE) go_libset(b->lib[b->head[q]], s);
        }
        s = b->next[s];
    } while (s != h);
    return n;
}

/// Plays a legal move for the side to move. Returns stones captured.
static int go_play(go_board *b, int p) {
    int col = b->to_move, opp = 3 - col, captured = 0, cap_at = -1;
    b->moves++;
    b->to_move = opp; b->last = p;
    if (p == GO_PASS) { b->passes++; b->ko = -1; return 0; }
    b->passes = 0;
    go_empty_del(b, p);
    b->c[p] = (uint8_t)col; b->head[p] = (int16_t)p; b->next[p] = (int16_t)p; b->size[p] = 1;
    b->lib[p][0] = b->lib[p][1] = 0;
    for (int k = 0; k < 4; k++) if (b->c[p + go_dir[k]] == GO_EMPTY) go_libset(b->lib[p], p + go_dir[k]);
    for (int k = 0; k < 4; k++) {
        int q = p + go_dir[k];
        if (b->c[q] == opp) {
            int h = b->head[q];
            go_libclr(b->lib[h], p);
            if (!b->lib[h][0] && !b->lib[h][1]) { captured += go_capture(b, h); cap_at = q; }
        } else if (b->c[q] == col) {
            int h = b->head[q], me = b->head[p];
            if (h == me) continue;
            go_libclr(b->lib[h], p);
            int big = b->size[h] >= b->size[me] ? h : me, small = big == h ? me : h;
            int s = small;
            do { b->head[s] = (int16_t)big; s = b->next[s]; } while (s != small);
            int16_t t = b->next[big]; b->next[big] = b->next[small]; b->next[small] = t;
            b->lib[big][0] |= b->lib[small][0]; b->lib[big][1] |= b->lib[small][1];
            b->size[big] = (int16_t)(b->size[big] + b->size[small]);
        }
    }
    int me = b->head[p];
    b->ko = (captured == 1 && b->size[me] == 1 && go_nlibs(b, me) == 1) ? cap_at : -1;
    return captured;
}

/// Area score, Black minus White (komi not included).
static int go_score(const go_board *b) {
    int s = 0;
    for (int p = 0; p < GO_N; p++) {
        int c = b->c[p];
        if (c == GO_BLACK) s++;
        else if (c == GO_WHITE) s--;
        else if (c == GO_EMPTY) {
            int seen = 0;
            for (int k = 0; k < 4; k++) { int q = b->c[p + go_dir[k]]; if (q == GO_BLACK || q == GO_WHITE) seen |= q; }
            s += seen == GO_BLACK ? 1 : seen == GO_WHITE ? -1 : 0;
        }
    }
    return s;
}

/// Playout policy: capture a string the last move left in atari, save one
/// of ours it put in atari, else a random legal move that fills no eye.
static int go_policy(const go_board *b, ia_rng *r) {
    int col = b->to_move;
    if (b->last != GO_PASS) {
        int lp = b->last;
        if (b->c[lp] != GO_EMPTY && go_nlibs(b, b->head[lp]) == 1) {
            int m = go_onelib(b, b->head[lp]);
            if (go_legal(b, m, col)) return m;
        }
        for (int k = 0; k < 4; k++) {
            int q = lp + go_dir[k];
            if (b->c[q] == col && go_nlibs(b, b->head[q]) == 1) {
                int m = go_onelib(b, b->head[q]);
                if (go_legal(b, m, col) && !go_eye(b, m, col)) return m;
            }
        }
    }
    int n = b->nempty;
    if (!n) return GO_PASS;
    int start = (int)ia_below(r, (uint32_t)n);
    for (int i = 0; i < n; i++) {
        int p = b->empty[(start + i) % n];
        if (go_legal(b, p, col) && !go_eye(b, p, col)) return p;
    }
    return GO_PASS;
}

/// Plays to the end; returns the winner (komi 7.5 for White).
static int go_playout(go_board *b, ia_rng *r, uint64_t *moves) {
    while (b->passes < 2 && b->moves < 3 * GO_S * GO_S) {
        go_play(b, go_policy(b, r));
        (*moves)++;
    }
    return 2 * go_score(b) > 15 ? GO_BLACK : GO_WHITE;
}

/// Natural log from frexp and an atanh series: only exact IEEE operations,
/// so every device computes the same bits.
static double go_ln(double x) {
    int e;
    double m = frexp(x, &e);                      // x = m·2^e, m in [0.5, 1)
    double t = (m - 1) / (m + 1), t2 = t * t, s = 0, pw = t;
    for (int k = 1; k <= 23; k += 2) { s += pw / k; pw *= t2; }
    return 2 * s + e * 0.69314718055994530942;
}

typedef struct { int32_t first, visits, wins; int16_t nchild, move; uint8_t color; } go_node;

typedef struct { go_node *n; int used, cap; } go_tree;

static int go_expand(go_tree *t, int node, const go_board *b) {
    int col = b->to_move, first = t->used, k = 0;
    for (int i = 0; i < GO_N && t->used < t->cap; i++) {
        if (b->c[i] != GO_EMPTY || !go_legal(b, i, col) || go_eye(b, i, col)) continue;
        go_node *c = &t->n[t->used++];
        c->first = -1; c->visits = c->wins = 0; c->nchild = 0; c->move = (int16_t)i; c->color = (uint8_t)col;
        k++;
    }
    if (!k && t->used < t->cap) {
        go_node *c = &t->n[t->used++];
        c->first = -1; c->visits = c->wins = 0; c->nchild = 0; c->move = GO_PASS; c->color = (uint8_t)col;
        k = 1;
    }
    if (!k) return -1;
    t->n[node].first = first; t->n[node].nchild = (int16_t)k;
    return 0;
}

static int go_select(const go_tree *t, int node) {
    const go_node *p = &t->n[node];
    double lnN = go_ln((double)p->visits), best = -1;
    int bi = p->first;
    for (int i = 0; i < p->nchild; i++) {
        const go_node *c = &t->n[p->first + i];
        if (!c->visits) return p->first + i;
        double v = (double)c->wins / c->visits + 0.8 * sqrt(lnN / c->visits);
        if (v > best) { best = v; bi = p->first + i; }
    }
    return bi;
}

/// go — a Monte-Carlo Go engine of the leela kind on a 9×9 board: strings
/// with liberty bitsets merged on contact, captures, simple ko and
/// suicide rules, area scoring with komi 7.5. Random playouts use a light
/// policy (capture or rescue strings in atari after the last move,
/// otherwise a random legal move that does not fill an own eye). Each move
/// of a self-play game is chosen by UCT tree search (UCB1, children
/// expanded on a node's second visit, the most-visited child played).
/// Sizes play 16 moves × 1800 playouts, 36 × 4000, and 60 × 13000.
/// `checksum` digests every chosen move and its visit and win counts plus
/// the final score; `value` is the final area score (Black − White);
/// `work` is playouts.
int cbk_go(int size, cb_bench_result *out) {
    static const int moves_by_size[3] = {16, 36, 60}, playouts_by_size[3] = {1800, 4000, 13000};
    size = ia_size(size);
    const int P = playouts_by_size[size - 1];
    int rc = 1;
    go_board *game = (go_board *)malloc(sizeof *game), *b = (go_board *)malloc(sizeof *b);
    go_tree t = {0};
    t.cap = P * (GO_S * GO_S + 1) + 1;
    t.n = (go_node *)malloc((size_t)t.cap * sizeof(go_node));
    int *path = (int *)malloc(4 * GO_N * sizeof(int));
    if (!game || !b || !t.n || !path) goto done;
    go_init(game);
    ia_rng r = { 0x60600D5EED000000ull };
    uint64_t h = IA_FNV_BASIS, playouts = 0, pmoves = 0;
    for (int mv = 0; mv < moves_by_size[size - 1] && game->passes < 2; mv++) {
        t.used = 1;
        go_node *root = &t.n[0];
        root->first = -1; root->visits = root->wins = 0; root->nchild = 0; root->move = GO_PASS;
        root->color = (uint8_t)(3 - game->to_move);
        for (int it = 0; it < P; it++) {
            memcpy(b, game, sizeof *b);
            int node = 0, depth = 0;
            path[depth++] = 0;
            while (t.n[node].nchild && depth < 4 * GO_N - 1) {
                node = go_select(&t, node);
                go_play(b, t.n[node].move);
                path[depth++] = node;
            }
            if ((node == 0 || t.n[node].visits > 0) && b->passes < 2 && depth < 4 * GO_N - 1 &&
                go_expand(&t, node, b) == 0) {
                node = go_select(&t, node);
                go_play(b, t.n[node].move);
                path[depth++] = node;
            }
            int winner = go_playout(b, &r, &pmoves);
            playouts++;
            for (int i = 0; i < depth; i++) {
                go_node *x = &t.n[path[i]];
                x->visits++;
                if (x->color == winner) x->wins++;
            }
        }
        int best = -1, bv = -1;
        for (int i = 0; i < t.n[0].nchild; i++) {
            const go_node *c = &t.n[t.n[0].first + i];
            if (c->visits > bv) { bv = c->visits; best = t.n[0].first + i; }
        }
        if (best < 0) { rc = 2; goto done; }
        go_play(game, t.n[best].move);
        h = ia_mix(h, ((uint64_t)t.n[best].move << 40) ^ ((uint64_t)t.n[best].visits << 20) ^ (uint64_t)t.n[best].wins);
    }
    int score = go_score(game);
    h = ia_mix(h, (uint64_t)(int64_t)score);
    h = ia_mix(h, pmoves);
    ia_fill(out, h, (double)score, (double)playouts, "playouts");
    rc = 0;
done:
    free(game); free(b); free(t.n); free(path);
    return rc;
}

// ── sudoku: puzzle generation and solving with constraint propagation ───

typedef struct {
    uint8_t peers[81][20];
    uint8_t units[27][9];
} sd_tab;

typedef struct { uint16_t cand[81]; uint8_t val[81]; } sd_grid;   // cand: bits 1..9

static void sd_init(sd_tab *t) {
    for (int i = 0; i < 9; i++)
        for (int j = 0; j < 9; j++) {
            t->units[i][j] = (uint8_t)(i * 9 + j);                       // rows
            t->units[9 + i][j] = (uint8_t)(j * 9 + i);                   // columns
            t->units[18 + i][j] = (uint8_t)(((i / 3) * 3 + j / 3) * 9 + (i % 3) * 3 + j % 3);  // boxes
        }
    for (int c = 0; c < 81; c++) {
        int n = 0, r = c / 9, k = c % 9;
        for (int o = 0; o < 81; o++) {
            if (o == c) continue;
            int orow = o / 9, ocol = o % 9;
            if (orow == r || ocol == k || (orow / 3 == r / 3 && ocol / 3 == k / 3)) t->peers[c][n++] = (uint8_t)o;
        }
    }
}

static void sd_clear(sd_grid *g) {
    for (int c = 0; c < 81; c++) { g->cand[c] = 0x3FE; g->val[c] = 0; }
}

/// Places digit d in cell c and propagates naked singles. 0 on contradiction.
static int sd_assign(const sd_tab *t, sd_grid *g, int c, int d) {
    uint8_t qc[96], qd[96];
    int qh = 0, qt = 0;
    qc[qt] = (uint8_t)c; qd[qt++] = (uint8_t)d;
    while (qh < qt) {
        int cc = qc[qh], dd = qd[qh++];
        uint16_t bit = (uint16_t)(1u << dd);
        if (g->val[cc]) { if (g->val[cc] != dd) return 0; continue; }
        if (!(g->cand[cc] & bit)) return 0;
        g->val[cc] = (uint8_t)dd; g->cand[cc] = bit;
        for (int k = 0; k < 20; k++) {
            int p = t->peers[cc][k];
            if (!(g->cand[p] & bit)) continue;
            if (g->val[p]) return 0;
            uint16_t m = g->cand[p] &= (uint16_t)~bit;
            if (!m) return 0;
            if (!(m & (m - 1))) {
                if (qt >= 96) return 0;
                qc[qt] = (uint8_t)p; qd[qt++] = (uint8_t)__builtin_ctz(m);
            }
        }
    }
    return 1;
}

/// Hidden singles over every unit, to a fixed point. 0 on contradiction.
static int sd_propagate(const sd_tab *t, sd_grid *g) {
    for (;;) {
        int changed = 0;
        for (int u = 0; u < 27; u++) {
            const uint8_t *cells = t->units[u];
            uint16_t once = 0, twice = 0, placed = 0;
            for (int k = 0; k < 9; k++) {
                uint16_t m = g->cand[cells[k]];
                twice |= once & m; once |= m;
                if (g->val[cells[k]]) placed |= m;
            }
            if (once != 0x3FE) return 0;
            uint16_t single = once & ~twice & ~placed;
            while (single) {
                int d = __builtin_ctz(single);
                single &= single - 1;
                for (int k = 0; k < 9; k++)
                    if (g->cand[cells[k]] & (1u << d)) {
                        if (!sd_assign(t, g, cells[k], d)) return 0;
                        changed = 1;
                        break;
                    }
            }
        }
        if (!changed) return 1;
    }
}

/// Counts solutions up to `limit`, branching on the cell with the fewest
/// candidates; the first solution found goes to `sol`. With `r` set, the
/// candidates are tried from a random rotation (for generating grids).
static int sd_solve(const sd_tab *t, sd_grid *g, int limit, sd_grid *sol, uint64_t *nodes, ia_rng *r) {
    (*nodes)++;
    if (!sd_propagate(t, g)) return 0;
    int best = -1, bc = 10;
    for (int c = 0; c < 81; c++) {
        if (g->val[c]) continue;
        int n = __builtin_popcount(g->cand[c]);
        if (n < bc) { bc = n; best = c; if (n == 2) break; }
    }
    if (best < 0) {
        if (sol) *sol = *g;
        return 1;
    }
    int count = 0, rot = r ? (int)ia_below(r, 9) : 0;
    for (int i = 0; i < 9 && count < limit; i++) {
        int d = 1 + (i + rot) % 9;
        if (!(g->cand[best] & (1u << d))) continue;
        sd_grid child = *g;
        if (!sd_assign(t, &child, best, d)) continue;
        count += sd_solve(t, &child, limit - count, count ? NULL : sol, nodes, r);
    }
    return count;
}

/// Builds the propagated grid for a clue string; 0 if the clues clash.
static int sd_load(const sd_tab *t, sd_grid *g, const uint8_t *clues) {
    sd_clear(g);
    for (int c = 0; c < 81; c++) if (clues[c] && !sd_assign(t, g, c, clues[c])) return 0;
    return 1;
}

/// sudoku — puzzle generation and solving, the kind of work in exchange2.
/// Each round fills a random complete grid (randomised backtracking),
/// then digs it into a puzzle: clue pairs are removed in random order,
/// keeping 180° symmetry, and a removal stands only if the puzzle still
/// has exactly one solution (a counting search to two); single clues are
/// then removed the same way until the puzzle is minimal. The finished
/// puzzle is solved again and must reproduce the grid. The solver keeps
/// 9-bit candidate masks per cell, propagates naked and hidden singles to
/// a fixed point, and branches on the cell with fewest candidates. Sizes
/// generate 700, 3800 and 17500 puzzles. `checksum` digests every puzzle
/// and solution; `value` is the total number of clues; `work` is search
/// nodes.
int cbk_sudoku(int size, cb_bench_result *out) {
    static const int puzzles_by_size[3] = {700, 3800, 17500};
    size = ia_size(size);
    sd_tab *t = (sd_tab *)malloc(sizeof *t);
    if (!t) return 1;
    sd_init(t);
    ia_rng r = { 0x5D0C0DE500000000ull };
    uint64_t h = IA_FNV_BASIS, nodes = 0, clues_total = 0;
    for (int pz = 0; pz < puzzles_by_size[size - 1]; pz++) {
        sd_grid g, full, sol;
        sd_clear(&g);
        if (sd_solve(t, &g, 1, &full, &nodes, &r) != 1) { free(t); return 2; }
        uint8_t clues[81], order[41];
        for (int c = 0; c < 81; c++) clues[c] = full.val[c];
        for (int i = 0; i < 41; i++) order[i] = (uint8_t)i;
        for (int i = 40; i > 0; i--) {                         // Fisher-Yates
            int j = (int)ia_below(&r, (uint32_t)i + 1);
            uint8_t x = order[i]; order[i] = order[j]; order[j] = x;
        }
        for (int i = 0; i < 41; i++) {
            int a = order[i], b = 80 - a;
            uint8_t va = clues[a], vb = clues[b];
            clues[a] = clues[b] = 0;
            if (!sd_load(t, &g, clues) || sd_solve(t, &g, 2, NULL, &nodes, NULL) != 1) {
                clues[a] = va; clues[b] = vb;
            }
        }
        uint8_t cells[81];                                      // then single clues: a minimal puzzle
        for (int i = 0; i < 81; i++) cells[i] = (uint8_t)i;
        for (int i = 80; i > 0; i--) {
            int j = (int)ia_below(&r, (uint32_t)i + 1);
            uint8_t x = cells[i]; cells[i] = cells[j]; cells[j] = x;
        }
        for (int i = 0; i < 81; i++) {
            int a = cells[i];
            uint8_t va = clues[a];
            if (!va) continue;
            clues[a] = 0;
            if (!sd_load(t, &g, clues) || sd_solve(t, &g, 2, NULL, &nodes, NULL) != 1) clues[a] = va;
        }
        if (!sd_load(t, &g, clues) || sd_solve(t, &g, 2, &sol, &nodes, NULL) != 1 ||
            memcmp(sol.val, full.val, 81)) { free(t); return 3; }
        int n = 0;
        for (int c = 0; c < 81; c++) n += clues[c] != 0;
        clues_total += (uint64_t)n;
        h = ia_fnv(h, clues, 81);
        h = ia_fnv(h, sol.val, 81);
    }
    h = ia_mix(h, nodes);
    ia_fill(out, h, (double)clues_total, (double)nodes, "nodes");
    free(t);
    return 0;
}

// ── lzma / lzfast: compression through Apple's libcompression ───────────

/// Text-like data from a word model: a generated vocabulary with Zipf
/// frequencies, favoured successors per word (a sparse bigram model),
/// sentences, punctuation, numbers and paragraphs.
typedef struct {
    ia_rng r;
    char words[4096 * 12]; uint32_t woff[4096]; uint8_t wlen[4096];
    uint32_t cum[4096]; uint32_t total;
    uint16_t succ[4096][8];
    int prev, in_sentence, sentences;
} lz_text;

enum { LZ_VOCAB = 4096 };

static void lz_text_init(lz_text *t, uint64_t seed) {
    static const char *const syl[40] = {
        "ka", "ri", "ston", "el", "ma", "ver", "an", "to", "li", "que", "dor", "en",
        "sa", "mon", "tri", "o", "be", "la", "nis", "gar", "u", "fe", "port", "ch",
        "in", "ra", "de", "mil", "os", "ta", "vel", "har", "e", "ne", "ul", "sk",
        "is", "pa", "ron", "a"};
    t->r.s = seed;
    uint32_t off = 0;
    for (int w = 0; w < LZ_VOCAB; w++) {
        int ns = 1 + (int)ia_below(&t->r, 3) + (w > 600 ? (int)ia_below(&t->r, 2) : 0);
        t->woff[w] = off;
        int len = 0;
        for (int k = 0; k < ns; k++) {
            const char *s = syl[ia_below(&t->r, 40)];
            size_t n = strlen(s);
            if (len + (int)n > 11) break;
            memcpy(t->words + off + len, s, n);
            len += (int)n;
        }
        t->wlen[w] = (uint8_t)len;
        off += (uint32_t)len;
    }
    uint32_t c = 0;
    for (int w = 0; w < LZ_VOCAB; w++) { c += 1000000u / (uint32_t)(w + 1); t->cum[w] = c; }
    t->total = c;
    for (int w = 0; w < LZ_VOCAB; w++)
        for (int k = 0; k < 8; k++) t->succ[w][k] = (uint16_t)ia_below(&t->r, k < 4 ? 200 : LZ_VOCAB);
    t->prev = -1; t->in_sentence = 0; t->sentences = 0;
}

static int lz_zipf(lz_text *t) {
    uint32_t x = ia_below(&t->r, t->total);
    int lo = 0, hi = LZ_VOCAB - 1;
    while (lo < hi) { int mid = (lo + hi) >> 1; if (t->cum[mid] <= x) lo = mid + 1; else hi = mid; }
    return lo;
}

/// Fills buf[0..n) with the next n bytes of text.
static void lz_text_fill(lz_text *t, uint8_t *buf, size_t n) {
    size_t pos = 0;
    char tmp[32];
    while (pos < n) {
        size_t k = 0;
        uint32_t roll = ia_below(&t->r, 100);
        if (roll < 2) {                                   // a number
            uint32_t v = ia_below(&t->r, 100000);
            char d[12]; int nd = 0;
            do { d[nd++] = (char)('0' + v % 10); v /= 10; } while (v);
            while (nd) tmp[k++] = d[--nd];
        } else {
            int w = t->prev >= 0 && roll < 70 ? t->succ[t->prev][ia_below(&t->r, 8)] : lz_zipf(t);
            memcpy(tmp, t->words + t->woff[w], t->wlen[w]);
            if (!t->in_sentence && t->wlen[w]) tmp[0] = (char)(tmp[0] - 32);
            k = t->wlen[w];
            t->prev = w;
        }
        t->in_sentence++;
        uint32_t p = ia_below(&t->r, 100);
        if (t->in_sentence > 4 && p < 9) {
            tmp[k++] = '.';
            t->in_sentence = 0;
            if (++t->sentences % (3 + ia_below(&t->r, 5)) == 0) { tmp[k++] = '\n'; tmp[k++] = '\n'; }
            else tmp[k++] = ' ';
        } else if (p < 16) { tmp[k++] = ','; tmp[k++] = ' '; }
        else tmp[k++] = ' ';
        size_t m = k < n - pos ? k : n - pos;
        memcpy(buf + pos, tmp, m);
        pos += m;
    }
}

typedef size_t (*lz_codec_fn)(uint8_t *, size_t, const uint8_t *, size_t, void *, compression_algorithm);
typedef size_t (*lz_scratch_fn)(compression_algorithm);

typedef struct {
    void *lib;
    lz_codec_fn enc, dec;
    lz_scratch_fn enc_scratch, dec_scratch;
} lz_api;

static int lz_open(lz_api *a) {
    memset(a, 0, sizeof *a);
    a->lib = dlopen("/usr/lib/libcompression.dylib", RTLD_LAZY);
    if (!a->lib) return -1;
    a->enc = (lz_codec_fn)dlsym(a->lib, "compression_encode_buffer");
    a->dec = (lz_codec_fn)dlsym(a->lib, "compression_decode_buffer");
    a->enc_scratch = (lz_scratch_fn)dlsym(a->lib, "compression_encode_scratch_buffer_size");
    a->dec_scratch = (lz_scratch_fn)dlsym(a->lib, "compression_decode_scratch_buffer_size");
    if (!a->enc || !a->dec || !a->enc_scratch || !a->dec_scratch) { dlclose(a->lib); a->lib = NULL; return -1; }
    return 0;
}

/// Compresses and decompresses `n` bytes with `alg`; 1 if the round trip
/// reproduced the input exactly, 0 if not, -1 if the codec failed.
static int lz_roundtrip(const lz_api *a, compression_algorithm alg, const uint8_t *src, size_t n,
                        uint8_t *comp, size_t compcap, uint8_t *back, void *es, void *ds) {
    size_t c = a->enc(comp, compcap, src, n, es, alg);
    if (!c) return -1;
    size_t d = a->dec(back, n, comp, c, ds, alg);
    return d == n && !memcmp(back, src, n);
}

/// lzma — LZMA compression, the class of xz: text-like data from a word
/// model (Zipf vocabulary, favoured successors, sentences, numbers) is
/// compressed in 512 KB blocks with the system's LZMA encoder (Apple's
/// libcompression, loaded with dlopen), decompressed, and compared byte
/// for byte. The compressed bytes depend on the OS's encoder, so the
/// checksum covers only the original data and whether every round trip
/// matched. Sizes round-trip 1, 4 and 24 MB. `value` is bytes
/// round-tripped; `work` is MB.
int cbk_lzma(int size, cb_bench_result *out) {
    static const int blocks_by_size[3] = {2, 8, 48};
    enum { BLOCK = 512 << 10 };
    size = ia_size(size);
    lz_api api;
    if (lz_open(&api)) return 2;
    int rc = 1;
    lz_text *tx = (lz_text *)malloc(sizeof *tx);
    size_t compcap = BLOCK + BLOCK / 8 + 65536;
    uint8_t *src = (uint8_t *)malloc(BLOCK), *comp = (uint8_t *)malloc(compcap), *back = (uint8_t *)malloc(BLOCK);
    size_t esz = api.enc_scratch(COMPRESSION_LZMA), dsz = api.dec_scratch(COMPRESSION_LZMA);
    void *es = malloc(esz ? esz : 1), *ds = malloc(dsz ? dsz : 1);
    if (!tx || !src || !comp || !back || !es || !ds) goto done;
    lz_text_init(tx, 0x1A2A3A4A00000000ull);
    uint64_t h = IA_FNV_BASIS, total = 0;
    int all_ok = 1;
    int blocks = blocks_by_size[size - 1];
    for (int b = 0; b < blocks; b++) {
        lz_text_fill(tx, src, BLOCK);
        h = ia_fnv(h, src, BLOCK);
        int ok = lz_roundtrip(&api, COMPRESSION_LZMA, src, BLOCK, comp, compcap, back, es, ds);
        if (ok < 0) { rc = 3; goto done; }
        all_ok &= ok;
        total += BLOCK;
    }
    h = ia_mix(h, (uint64_t)all_ok);
    ia_fill(out, h, (double)total, (double)total / 1e6, "MB");
    rc = 0;
done:
    free(tx); free(src); free(comp); free(back); free(es); free(ds);
    dlclose(api.lib);
    return rc;
}

/// lzfast — fast compressors, the class of zstd: an 8 MB text-like corpus
/// (the word model of `lzma`) is cut into 1 MB blocks at a shifting
/// offset each pass, and every block is round-tripped through LZ4 and
/// through LZFSE (Apple's libcompression via dlopen) and compared byte
/// for byte. The checksum covers the original data and whether every
/// round trip matched, not the compressed bytes (they depend on the OS).
/// Sizes make 2, 12 and 58 passes over the corpus. `value` is bytes
/// round-tripped per codec; `work` is MB through both codecs.
int cbk_lzfast(int size, cb_bench_result *out) {
    static const int passes_by_size[3] = {2, 12, 58};
    enum { CORPUS = 8 << 20, BLOCK = 1 << 20 };
    size = ia_size(size);
    lz_api api;
    if (lz_open(&api)) return 2;
    int rc = 1;
    lz_text *tx = (lz_text *)malloc(sizeof *tx);
    size_t compcap = BLOCK + BLOCK / 8 + 65536;
    uint8_t *corpus = (uint8_t *)malloc(CORPUS), *comp = (uint8_t *)malloc(compcap), *back = (uint8_t *)malloc(BLOCK);
    size_t e1 = api.enc_scratch(COMPRESSION_LZ4), e2 = api.enc_scratch(COMPRESSION_LZFSE);
    size_t d1 = api.dec_scratch(COMPRESSION_LZ4), d2 = api.dec_scratch(COMPRESSION_LZFSE);
    void *es = malloc((e1 > e2 ? e1 : e2) + 1), *ds = malloc((d1 > d2 ? d1 : d2) + 1);
    if (!tx || !corpus || !comp || !back || !es || !ds) goto done;
    lz_text_init(tx, 0x2B3B4B5B00000000ull);
    lz_text_fill(tx, corpus, CORPUS);
    uint64_t h = ia_fnv(IA_FNV_BASIS, corpus, CORPUS), total = 0;
    int all_ok = 1;
    for (int p = 0; p < passes_by_size[size - 1]; p++) {
        size_t shift = (size_t)p * 40961 % BLOCK;          // block boundaries move each pass
        for (size_t off = shift; off + BLOCK <= CORPUS; off += BLOCK) {
            for (int c = 0; c < 2; c++) {
                int ok = lz_roundtrip(&api, c ? COMPRESSION_LZFSE : COMPRESSION_LZ4, corpus + off, BLOCK,
                                      comp, compcap, back, es, ds);
                if (ok < 0) { rc = 3; goto done; }
                all_ok &= ok;
            }
            total += BLOCK;
        }
    }
    h = ia_mix(h, total);
    h = ia_mix(h, (uint64_t)all_ok);
    ia_fill(out, h, (double)total, 2.0 * (double)total / 1e6, "MB");
    rc = 0;
done:
    free(tx); free(corpus); free(comp); free(back); free(es); free(ds);
    dlclose(api.lib);
    return rc;
}
