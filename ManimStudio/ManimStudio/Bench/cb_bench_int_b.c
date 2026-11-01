//
//  cb_bench_int_b.c — the newer integer workloads behind `spec`, modelled
//  on the kinds of work in SPEC CPU 2017 and 2026 (Othello search, SQL,
//  static analysis, SAT, place-and-route, architecture simulation,
//  homomorphic-encryption arithmetic, graph analytics, protein alignment,
//  constraint programming, lossless audio). None of it is SPEC code:
//  every algorithm here is written from scratch for this file.
//
//  Rules every workload follows (see cb_bench.h): plain C17, one thread
//  per call, no mutable globals or function statics (`spec --rate` runs a
//  copy per core), its own PRNG with fixed seeds, big arrays on the heap,
//  and an exact digest of the answer in `checksum`.
//

#include "cb_bench.h"

#include <limits.h>
#include <math.h>
#include <sqlite3.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

// Floating point here must round the same way at every optimisation
// level: no fused multiply-add contraction.
#pragma STDC FP_CONTRACT OFF

// ── Shared helpers ──────────────────────────────────────────────────────

/// xoshiro256** state; every workload owns one on its stack.
typedef struct { uint64_t s[4]; } ib_rng;

static uint64_t ib_splitmix(uint64_t *x) {
    uint64_t z = (*x += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

static void ib_seed(ib_rng *r, uint64_t seed) {
    for (int i = 0; i < 4; i++) r->s[i] = ib_splitmix(&seed);
}

static inline uint64_t ib_rotl(uint64_t x, int k) {
    return (x << k) | (x >> (64 - k));
}

static inline uint64_t ib_next(ib_rng *r) {
    uint64_t *s = r->s;
    uint64_t result = ib_rotl(s[1] * 5, 7) * 9;
    uint64_t t = s[1] << 17;
    s[2] ^= s[0];
    s[3] ^= s[1];
    s[1] ^= s[2];
    s[0] ^= s[3];
    s[2] ^= t;
    s[3] = ib_rotl(s[3], 45);
    return result;
}

/// Uniform in [0, n) (multiply-shift; the tiny bias does not matter here).
static inline uint32_t ib_below(ib_rng *r, uint32_t n) {
    return (uint32_t)(((ib_next(r) >> 32) * (uint64_t)n) >> 32);
}

/// Uniform in [lo, hi].
static inline int ib_range(ib_rng *r, int lo, int hi) {
    return lo + (int)ib_below(r, (uint32_t)(hi - lo + 1));
}

/// True with probability num/den.
static inline bool ib_chance(ib_rng *r, uint32_t num, uint32_t den) {
    return ib_below(r, den) < num;
}

#define IB_FNV_OFFSET 0xCBF29CE484222325ULL
#define IB_FNV_PRIME  0x00000100000001B3ULL

/// FNV-1a over the eight bytes of `v`, little-endian order.
static inline uint64_t ib_mix(uint64_t h, uint64_t v) {
    for (int i = 0; i < 8; i++) {
        h ^= (v >> (8 * i)) & 0xFF;
        h *= IB_FNV_PRIME;
    }
    return h;
}

/// FNV-1a over a byte string.
static uint64_t ib_mix_bytes(uint64_t h, const void *p, size_t n) {
    const unsigned char *b = (const unsigned char *)p;
    for (size_t i = 0; i < n; i++) {
        h ^= b[i];
        h *= IB_FNV_PRIME;
    }
    return h;
}

static void ib_result(cb_bench_result *out, uint64_t checksum, double value,
                      double work, const char *unit) {
    out->checksum = checksum;
    out->value = value;
    out->work = work;
    out->unit = unit;
}

static inline int ib_size(int size) {
    return size < 1 ? 1 : (size > 3 ? 3 : size);
}

/// Growable int array (append-only scratch lists).
typedef struct { int *a; int n, cap; } ib_ivec;

static bool ib_ivec_push(ib_ivec *v, int x) {
    if (v->n == v->cap) {
        int nc = v->cap ? v->cap * 2 : 16;
        int *na = (int *)realloc(v->a, (size_t)nc * sizeof(int));
        if (!na) return false;
        v->a = na;
        v->cap = nc;
    }
    v->a[v->n++] = x;
    return true;
}

// ── othello: bitboard Reversi search and exact endgame solving ─────────

#define OTH_INF 30000
#define OTH_WIN 20000
#define OTH_SHALLOW 6

typedef struct {
    uint64_t p, o;      // the position: side to move, opponent
    int16_t lo, hi;     // value bounds
    uint8_t move;       // best move found (64 = none)
    uint8_t depth;      // search depth the bounds hold for
} oth_tte;

typedef struct {
    oth_tte *tt;
    uint64_t mask;
    uint64_t nodes;
} oth_ctx;

static inline int oth_pc(uint64_t x) { return __builtin_popcountll(x); }

static inline uint64_t oth_e(uint64_t x)  { return (x << 1) & 0xFEFEFEFEFEFEFEFEULL; }
static inline uint64_t oth_w(uint64_t x)  { return (x >> 1) & 0x7F7F7F7F7F7F7F7FULL; }
static inline uint64_t oth_s(uint64_t x)  { return x << 8; }
static inline uint64_t oth_n(uint64_t x)  { return x >> 8; }
static inline uint64_t oth_se(uint64_t x) { return (x << 9) & 0xFEFEFEFEFEFEFEFEULL; }
static inline uint64_t oth_sw(uint64_t x) { return (x << 7) & 0x7F7F7F7F7F7F7F7FULL; }
static inline uint64_t oth_ne(uint64_t x) { return (x >> 7) & 0xFEFEFEFEFEFEFEFEULL; }
static inline uint64_t oth_nw(uint64_t x) { return (x >> 9) & 0x7F7F7F7F7F7F7F7FULL; }

// Kogge-Stone-style flood along one direction: opponent runs that start
// next to one of our discs; the square past the run is a legal move.
#define OTH_SPREAD(SH)                                                       \
    do {                                                                     \
        uint64_t t_ = SH(P) & O;                                             \
        t_ |= SH(t_) & O; t_ |= SH(t_) & O; t_ |= SH(t_) & O;                \
        t_ |= SH(t_) & O; t_ |= SH(t_) & O;                                  \
        m |= SH(t_);                                                         \
    } while (0)

static uint64_t oth_moves(uint64_t P, uint64_t O) {
    uint64_t m = 0;
    OTH_SPREAD(oth_e);  OTH_SPREAD(oth_w);
    OTH_SPREAD(oth_s);  OTH_SPREAD(oth_n);
    OTH_SPREAD(oth_se); OTH_SPREAD(oth_sw);
    OTH_SPREAD(oth_ne); OTH_SPREAD(oth_nw);
    return m & ~(P | O);
}

#define OTH_RAY(SH)                                                          \
    do {                                                                     \
        uint64_t f_ = 0, x_ = SH(b);                                         \
        while (x_ & O) { f_ |= x_; x_ = SH(x_); }                            \
        if (x_ & P) flips |= f_;                                             \
    } while (0)

/// The opponent discs a move on `sq` turns over.
static uint64_t oth_flips(uint64_t P, uint64_t O, int sq) {
    uint64_t b = 1ULL << sq, flips = 0;
    OTH_RAY(oth_e);  OTH_RAY(oth_w);
    OTH_RAY(oth_s);  OTH_RAY(oth_n);
    OTH_RAY(oth_se); OTH_RAY(oth_sw);
    OTH_RAY(oth_ne); OTH_RAY(oth_nw);
    return flips;
}

static inline uint64_t oth_hash(uint64_t P, uint64_t O) {
    uint64_t h = P * 0x9E3779B97F4A7C15ULL ^ ib_rotl(O * 0xC2B2AE3D27D4EB4FULL, 31);
    return h ^ (h >> 29);
}

/// Final disc difference; empty squares go to the winner.
static int oth_final(uint64_t P, uint64_t O, int empties) {
    int d = oth_pc(P) - oth_pc(O);
    if (d > 0) d += empties;
    else if (d < 0) d -= empties;
    return d;
}

// Square classes of the evaluation: corners, C, X, A and B squares.
static const uint64_t oth_wmask[5] = {
    0x8100000000000081ULL, 0x4281000000008142ULL, 0x0042000000004200ULL,
    0x2400810000810024ULL, 0x1800008181000018ULL,
};
static const int oth_wval[5] = { 100, -20, -50, 10, 5 };

static int oth_eval(uint64_t P, uint64_t O) {
    int s = 0;
    for (int k = 0; k < 5; k++)
        s += oth_wval[k] * (oth_pc(P & oth_wmask[k]) - oth_pc(O & oth_wmask[k]));
    // Corners already taken make the X and C squares next to them safe.
    uint64_t occ = (P | O) & 0x8100000000000081ULL;
    if (occ) {
        uint64_t safe = 0;
        if (occ & 0x1ULL) safe |= 0x0000000000000302ULL;
        if (occ & 0x80ULL) safe |= 0x000000000000C040ULL;
        if (occ & 0x0100000000000000ULL) safe |= 0x0203000000000000ULL;
        if (occ & 0x8000000000000000ULL) safe |= 0x40C0000000000000ULL;
        s += 30 * (oth_pc(P & safe & 0x0042000000004200ULL) - oth_pc(O & safe & 0x0042000000004200ULL));
        s += 15 * (oth_pc(P & safe & 0x4281000000008142ULL) - oth_pc(O & safe & 0x4281000000008142ULL));
    }
    s += 6 * (oth_pc(oth_moves(P, O)) - oth_pc(oth_moves(O, P)));
    return s;
}

/// Store a fail-soft result in the transposition table (always replace).
static void oth_store(oth_tte *e, uint64_t P, uint64_t O, int best, int alpha,
                      int beta, int move, int depth) {
    if (e->p != P || e->o != O || e->depth != depth) {
        e->p = P; e->o = O; e->lo = -OTH_INF; e->hi = OTH_INF; e->depth = (uint8_t)depth;
    }
    if (best <= alpha) { if (best < e->hi) e->hi = (int16_t)best; }
    else if (best >= beta) { if (best > e->lo) e->lo = (int16_t)best; }
    else { e->lo = e->hi = (int16_t)best; }
    e->move = (uint8_t)move;
}

/// Exact endgame solver: negascout over every remaining move, fastest-first
/// ordering (fewest replies for the opponent), transposition table above
/// the last OTH_SHALLOW empties. Returns the final disc difference.
static int oth_solve(oth_ctx *c, uint64_t P, uint64_t O, int alpha, int beta,
                     int empties, bool passed, int *bm) {
    c->nodes++;
    if (empties == 0) return oth_pc(P) - oth_pc(O);
    if (empties == 1 && !bm) {
        int sq = __builtin_ctzll(~(P | O));
        uint64_t f = oth_flips(P, O, sq);
        if (f) return oth_pc(P) - oth_pc(O) + 2 * oth_pc(f) + 1;
        f = oth_flips(O, P, sq);
        if (f) return oth_pc(P) - oth_pc(O) - 2 * oth_pc(f) - 1;
        return oth_final(P, O, 1);
    }
    uint64_t moves = oth_moves(P, O);
    if (!moves) {
        if (passed) return oth_final(P, O, empties);
        if (bm) *bm = 64;
        return -oth_solve(c, O, P, -beta, -alpha, empties, true, NULL);
    }
    if (empties <= OTH_SHALLOW && !bm) {
        int best = -OTH_INF;
        while (moves) {
            int sq = __builtin_ctzll(moves);
            moves &= moves - 1;
            uint64_t f = oth_flips(P, O, sq);
            int v = -oth_solve(c, O & ~f, P | f | (1ULL << sq), -beta, -alpha,
                               empties - 1, false, NULL);
            if (v > best) {
                best = v;
                if (v > alpha) { alpha = v; if (alpha >= beta) break; }
            }
        }
        return best;
    }
    oth_tte *e = &c->tt[oth_hash(P, O) & c->mask];
    int hmove = 64;
    if (e->p == P && e->o == O && e->depth == 0xFF) {
        if (!bm) {
            if (e->lo == e->hi) return e->lo;
            if (e->lo >= beta) return e->lo;
            if (e->hi <= alpha) return e->hi;
            if (e->lo > alpha) alpha = e->lo;
            if (e->hi < beta) beta = e->hi;
        }
        hmove = e->move;
    }
    int sqs[32], keys[32], n = 0;
    uint64_t fl[32];
    while (moves) {
        int sq = __builtin_ctzll(moves);
        moves &= moves - 1;
        uint64_t f = oth_flips(P, O, sq);
        uint64_t np = P | f | (1ULL << sq), no = O & ~f;
        int k;
        if (sq == hmove) k = -1000;
        else {
            k = 16 * oth_pc(oth_moves(no, np));
            if ((1ULL << sq) & 0x8100000000000081ULL) k -= 20;
        }
        int i = n++;
        while (i > 0 && keys[i - 1] > k) {
            keys[i] = keys[i - 1]; sqs[i] = sqs[i - 1]; fl[i] = fl[i - 1];
            i--;
        }
        keys[i] = k; sqs[i] = sq; fl[i] = f;
    }
    int a0 = alpha, best = -OTH_INF, bmove = sqs[0];
    for (int i = 0; i < n; i++) {
        uint64_t np = P | fl[i] | (1ULL << sqs[i]), no = O & ~fl[i];
        int v;
        if (i == 0) {
            v = -oth_solve(c, no, np, -beta, -alpha, empties - 1, false, NULL);
        } else {
            v = -oth_solve(c, no, np, -alpha - 1, -alpha, empties - 1, false, NULL);
            if (v > alpha && v < beta)
                v = -oth_solve(c, no, np, -beta, -v, empties - 1, false, NULL);
        }
        if (v > best) {
            best = v; bmove = sqs[i];
            if (v > alpha) { alpha = v; if (alpha >= beta) break; }
        }
    }
    oth_store(e, P, O, best, a0, beta, bmove, 0xFF);
    if (bm) *bm = bmove;
    return best;
}

/// Midgame negascout to a fixed depth with the static evaluation.
static int oth_search(oth_ctx *c, uint64_t P, uint64_t O, int alpha, int beta,
                      int depth, bool passed, int *bm) {
    c->nodes++;
    if (depth == 0) return oth_eval(P, O);
    uint64_t moves = oth_moves(P, O);
    if (!moves) {
        if (passed) {
            int d = oth_pc(P) - oth_pc(O);
            return d > 0 ? OTH_WIN + d : (d < 0 ? -OTH_WIN + d : 0);
        }
        if (bm) *bm = 64;
        return -oth_search(c, O, P, -beta, -alpha, depth, true, NULL);
    }
    oth_tte *e = &c->tt[oth_hash(P, O) & c->mask];
    int hmove = 64;
    if (e->p == P && e->o == O) {
        if (!bm && e->depth >= depth) {
            if (e->lo == e->hi) return e->lo;
            if (e->lo >= beta) return e->lo;
            if (e->hi <= alpha) return e->hi;
            if (e->lo > alpha) alpha = e->lo;
            if (e->hi < beta) beta = e->hi;
        }
        hmove = e->move;
    }
    int sqs[32], keys[32], n = 0;
    uint64_t fl[32];
    while (moves) {
        int sq = __builtin_ctzll(moves);
        moves &= moves - 1;
        uint64_t f = oth_flips(P, O, sq);
        int k;
        if (sq == hmove) k = -100000;
        else if (depth >= 3) k = oth_eval(O & ~f, P | f | (1ULL << sq));
        else {
            k = 0;
            for (int w = 0; w < 5; w++)
                if ((1ULL << sq) & oth_wmask[w]) k = -oth_wval[w];
        }
        int i = n++;
        while (i > 0 && keys[i - 1] > k) {
            keys[i] = keys[i - 1]; sqs[i] = sqs[i - 1]; fl[i] = fl[i - 1];
            i--;
        }
        keys[i] = k; sqs[i] = sq; fl[i] = f;
    }
    int a0 = alpha, best = -OTH_INF, bmove = sqs[0];
    for (int i = 0; i < n; i++) {
        uint64_t np = P | fl[i] | (1ULL << sqs[i]), no = O & ~fl[i];
        int v;
        if (i == 0) {
            v = -oth_search(c, no, np, -beta, -alpha, depth - 1, false, NULL);
        } else {
            v = -oth_search(c, no, np, -alpha - 1, -alpha, depth - 1, false, NULL);
            if (v > alpha && v < beta)
                v = -oth_search(c, no, np, -beta, -v, depth - 1, false, NULL);
        }
        if (v > best) {
            best = v; bmove = sqs[i];
            if (v > alpha) { alpha = v; if (alpha >= beta) break; }
        }
    }
    oth_store(e, P, O, best, a0, beta, bmove, depth);
    if (bm) *bm = bmove;
    return best;
}

/// Plays from the opening to a position with `empties` empty squares:
/// mostly the best move by a 1-ply evaluation, sometimes a random one,
/// so the positions are varied but not absurd. Returns false if the game
/// ended first.
static bool oth_make_position(ib_rng *r, int empties, uint64_t *pp, uint64_t *po) {
    uint64_t P = 0x0000000810000000ULL, O = 0x0000001008000000ULL;
    while (64 - oth_pc(P | O) > empties) {
        uint64_t moves = oth_moves(P, O);
        if (!moves) {
            if (!oth_moves(O, P)) return false;
            uint64_t t = P; P = O; O = t;
            continue;
        }
        int n = oth_pc(moves), sq = -1;
        if (ib_chance(r, 1, 3)) {
            int k = (int)ib_below(r, (uint32_t)n);
            uint64_t m = moves;
            while (k--) m &= m - 1;
            sq = __builtin_ctzll(m);
        } else {
            int bestv = INT_MIN;
            for (uint64_t m = moves; m; m &= m - 1) {
                int s = __builtin_ctzll(m);
                uint64_t f = oth_flips(P, O, s);
                int v = -oth_eval(O & ~f, P | f | (1ULL << s)) + (int)ib_below(r, 8);
                if (v > bestv) { bestv = v; sq = s; }
            }
        }
        uint64_t f = oth_flips(P, O, sq);
        uint64_t np = P | f | (1ULL << sq), no = O & ~f;
        P = no; O = np;
    }
    *pp = P; *po = O;
    return true;
}

/// Othello (Reversi) on 64-bit bitboards, the class of ntest/Zebra/Edax:
/// shift-and-mask move generation, an exact negascout endgame solver with
/// fastest-first ordering and a transposition table, and a midgame
/// iterative-deepening negascout with a positional + mobility evaluation.
/// Positions come from semi-random self-play with a fixed seed. Size 1
/// searches three midgames to depth 9 and solves six 16-empty endgames;
/// size 2 goes to depth 10 and 18 empties; size 3 to depth 11 and 19
/// empties. The checksum covers every score, best move and node count.
int cbk_othello(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int n_mid_t[4] = { 0, 3, 3, 4 };
    static const int mid_depth_t[4] = { 0, 9, 10, 11 };
    static const int n_end_t[4] = { 0, 6, 7, 8 };
    static const int end_empties_t[4] = { 0, 16, 18, 19 };
    static const int tt_bits_t[4] = { 0, 18, 20, 21 };
    oth_ctx c;
    c.mask = (1ULL << tt_bits_t[size]) - 1;
    c.nodes = 0;
    c.tt = (oth_tte *)calloc((size_t)c.mask + 1, sizeof(oth_tte));
    if (!c.tt) return 1;
    ib_rng r;
    ib_seed(&r, 0x07E1105EEDULL + (uint64_t)size);
    uint64_t h = IB_FNV_OFFSET;
    int64_t score_sum = 0;
    for (int i = 0; i < n_mid_t[size]; i++) {
        uint64_t P, O;
        while (!oth_make_position(&r, 36, &P, &O)) {}
        memset(c.tt, 0, ((size_t)c.mask + 1) * sizeof(oth_tte));
        int v = 0, bm = 64;
        for (int d = 1; d <= mid_depth_t[size]; d++)
            v = oth_search(&c, P, O, -OTH_INF, OTH_INF, d, false, &bm);
        h = ib_mix(h, P); h = ib_mix(h, O);
        h = ib_mix(h, (uint64_t)(int64_t)v); h = ib_mix(h, (uint64_t)bm);
        h = ib_mix(h, c.nodes);
        score_sum += v;
    }
    for (int i = 0; i < n_end_t[size]; i++) {
        uint64_t P, O;
        while (!oth_make_position(&r, end_empties_t[size], &P, &O)) {}
        memset(c.tt, 0, ((size_t)c.mask + 1) * sizeof(oth_tte));
        int bm = 64;
        int v = oth_solve(&c, P, O, -64, 64, end_empties_t[size], false, &bm);
        h = ib_mix(h, P); h = ib_mix(h, O);
        h = ib_mix(h, (uint64_t)(int64_t)v); h = ib_mix(h, (uint64_t)bm);
        h = ib_mix(h, c.nodes);
        score_sum += v;
    }
    free(c.tt);
    ib_result(out, h, (double)score_sum, (double)c.nodes, "nodes");
    return 0;
}

// ── sql: an in-memory SQLite order database ─────────────────────────────

static int sql_exec(sqlite3 *db, const char *s) {
    return sqlite3_exec(db, s, NULL, NULL, NULL) == SQLITE_OK ? 0 : 1;
}

/// Folds one result column into the digest by its type. Floats are
/// rounded to 1/1000 first so the digest does not depend on the last bit.
static uint64_t sql_fold(sqlite3_stmt *st, int c, uint64_t h) {
    switch (sqlite3_column_type(st, c)) {
    case SQLITE_INTEGER:
        return ib_mix(h ^ 1, (uint64_t)sqlite3_column_int64(st, c));
    case SQLITE_FLOAT: {
        double d = sqlite3_column_double(st, c);
        return ib_mix(h ^ 2, (uint64_t)(int64_t)floor(d * 1000.0 + 0.5));
    }
    case SQLITE_TEXT: {
        const unsigned char *t = sqlite3_column_text(st, c);
        int n = sqlite3_column_bytes(st, c);
        return ib_mix_bytes(h ^ 3, t, (size_t)n);
    }
    case SQLITE_NULL:
        return ib_mix(h, 0x4E554C4CULL);
    default: {
        const void *b = sqlite3_column_blob(st, c);
        int n = sqlite3_column_bytes(st, c);
        return ib_mix_bytes(h ^ 4, b, (size_t)n);
    }
    }
}

typedef struct { uint64_t h, rows; } sql_acc;

/// Steps a prepared statement to the end, folding every row into `acc`.
static int sql_drain(sqlite3_stmt *st, sql_acc *acc) {
    int rc;
    while ((rc = sqlite3_step(st)) == SQLITE_ROW) {
        int nc = sqlite3_column_count(st);
        for (int c = 0; c < nc; c++) acc->h = sql_fold(st, c, acc->h);
        acc->rows++;
    }
    return rc == SQLITE_DONE ? 0 : 1;
}

static int sql_query(sqlite3 *db, const char *q, sql_acc *acc) {
    sqlite3_stmt *st = NULL;
    if (sqlite3_prepare_v2(db, q, -1, &st, NULL) != SQLITE_OK) return 1;
    int rc = sql_drain(st, acc);
    sqlite3_finalize(st);
    acc->h = ib_mix(acc->h, acc->rows);
    return rc;
}

/// Runs a statement that changes rows and folds the change count in.
static int sql_change(sqlite3 *db, const char *q, sql_acc *acc) {
    if (sql_exec(db, q)) return 1;
    acc->h = ib_mix(acc->h, (uint64_t)sqlite3_changes(db));
    return 0;
}

static const char *const sql_syl[16] = {
    "ka", "lo", "mi", "ra", "ten", "shi", "po", "vu",
    "nel", "dra", "qui", "zo", "bel", "tor", "an", "esh",
};
static const char *const sql_seg[5] = { "RETAIL", "WHOLESALE", "ONLINE", "GOV", "EDU" };

static void sql_name(ib_rng *r, char *buf, int nsyl) {
    buf[0] = 0;
    for (int i = 0; i < nsyl; i++) strcat(buf, sql_syl[ib_below(r, 16)]);
}

/// Picks a skewed key in [1, n]: a fifth of the keys get half the picks.
static int64_t sql_skew(ib_rng *r, int n) {
    if (ib_chance(r, 1, 2)) return 1 + (int64_t)ib_below(r, (uint32_t)(n / 5 > 0 ? n / 5 : 1));
    return 1 + (int64_t)ib_below(r, (uint32_t)n);
}

static int sql_load(sqlite3 *db, ib_rng *r, int ncust, int nprod, int nord,
                    int32_t *price, uint64_t *rows) {
    sqlite3_stmt *st = NULL, *it = NULL;
    char name[64];
    int rc = 1;
    if (sql_exec(db,
            "CREATE TABLE customer(id INTEGER PRIMARY KEY, name TEXT NOT NULL,"
            " region INTEGER NOT NULL, segment TEXT NOT NULL, credit INTEGER NOT NULL);"
            "CREATE TABLE product(id INTEGER PRIMARY KEY, category INTEGER NOT NULL,"
            " name TEXT NOT NULL, price INTEGER NOT NULL);"
            "CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,"
            " day INTEGER NOT NULL, status INTEGER NOT NULL);"
            "CREATE TABLE item(order_id INTEGER NOT NULL, line INTEGER NOT NULL,"
            " product_id INTEGER NOT NULL, qty INTEGER NOT NULL, price INTEGER NOT NULL,"
            " PRIMARY KEY(order_id, line)) WITHOUT ROWID;"))
        return 1;

    // Customers.
    if (sql_exec(db, "BEGIN")) return 1;
    if (sqlite3_prepare_v2(db, "INSERT INTO customer VALUES(?1,?2,?3,?4,?5)", -1, &st, NULL)) goto fail;
    for (int i = 1; i <= ncust; i++) {
        sql_name(r, name, 2 + (int)ib_below(r, 2));
        sqlite3_bind_int64(st, 1, i);
        sqlite3_bind_text(st, 2, name, -1, SQLITE_TRANSIENT);
        sqlite3_bind_int64(st, 3, ib_below(r, 12));
        sqlite3_bind_text(st, 4, sql_seg[ib_below(r, 5)], -1, SQLITE_STATIC);
        sqlite3_bind_int64(st, 5, ib_below(r, 100001));
        if (sqlite3_step(st) != SQLITE_DONE) goto fail;
        sqlite3_reset(st);
        (*rows)++;
    }
    sqlite3_finalize(st); st = NULL;
    if (sql_exec(db, "COMMIT")) return 1;

    // Products.
    if (sql_exec(db, "BEGIN")) return 1;
    if (sqlite3_prepare_v2(db, "INSERT INTO product VALUES(?1,?2,?3,?4)", -1, &st, NULL)) goto fail;
    for (int i = 1; i <= nprod; i++) {
        sql_name(r, name, 3);
        int32_t p = 100 + (int32_t)ib_below(r, 900);
        if (ib_chance(r, 1, 4)) p *= 10 + (int32_t)ib_below(r, 90);
        price[i] = p;
        sqlite3_bind_int64(st, 1, i);
        sqlite3_bind_int64(st, 2, ib_below(r, 40));
        sqlite3_bind_text(st, 3, name, -1, SQLITE_TRANSIENT);
        sqlite3_bind_int64(st, 4, p);
        if (sqlite3_step(st) != SQLITE_DONE) goto fail;
        sqlite3_reset(st);
        (*rows)++;
    }
    sqlite3_finalize(st); st = NULL;
    if (sql_exec(db, "COMMIT")) return 1;

    // Orders and their line items, committed every 4096 orders.
    if (sqlite3_prepare_v2(db, "INSERT INTO orders VALUES(?1,?2,?3,?4)", -1, &st, NULL)) goto fail;
    if (sqlite3_prepare_v2(db, "INSERT INTO item VALUES(?1,?2,?3,?4,?5)", -1, &it, NULL)) goto fail;
    for (int i = 1; i <= nord; i++) {
        if ((i & 4095) == 1 && sql_exec(db, "BEGIN")) goto fail;
        sqlite3_bind_int64(st, 1, i);
        sqlite3_bind_int64(st, 2, sql_skew(r, ncust));
        sqlite3_bind_int64(st, 3, ib_below(r, 730));
        sqlite3_bind_int64(st, 4, ib_chance(r, 1, 10) ? 3 : ib_below(r, 3));
        if (sqlite3_step(st) != SQLITE_DONE) goto fail;
        sqlite3_reset(st);
        (*rows)++;
        int lines = 1 + (int)ib_below(r, 7);
        for (int l = 1; l <= lines; l++) {
            int64_t pid = sql_skew(r, nprod);
            sqlite3_bind_int64(it, 1, i);
            sqlite3_bind_int64(it, 2, l);
            sqlite3_bind_int64(it, 3, pid);
            sqlite3_bind_int64(it, 4, 1 + ib_below(r, 10));
            sqlite3_bind_int64(it, 5, price[pid]);
            if (sqlite3_step(it) != SQLITE_DONE) goto fail;
            sqlite3_reset(it);
            (*rows)++;
        }
        if (((i & 4095) == 0 || i == nord) && sql_exec(db, "COMMIT")) goto fail;
    }
    rc = 0;
fail:
    sqlite3_finalize(it);
    sqlite3_finalize(st);
    return rc;
}

/// The report queries: joins, grouping, ordering with LIMIT, a correlated
/// subquery, text matching. Every ORDER BY is total, so row order is fixed.
static int sql_reports(sqlite3 *db, sql_acc *acc) {
    static const char *const q[] = {
        // Revenue by region and segment (three-way join, GROUP BY).
        "SELECT c.region, c.segment, COUNT(DISTINCT o.id), SUM(i.qty * i.price)"
        " FROM customer c JOIN orders o ON o.customer_id = c.id"
        " JOIN item i ON i.order_id = o.id WHERE o.status <> 3"
        " GROUP BY c.region, c.segment ORDER BY c.region, c.segment",
        // Top spenders (aggregate, ORDER BY ... LIMIT).
        "SELECT c.id, c.name, SUM(i.qty * i.price) AS spend"
        " FROM customer c JOIN orders o ON o.customer_id = c.id"
        " JOIN item i ON i.order_id = o.id"
        " GROUP BY c.id ORDER BY spend DESC, c.id LIMIT 25",
        // Products priced above their category's average (correlated).
        "SELECT p.category, COUNT(*), SUM(p.price) FROM product p"
        " WHERE p.price > (SELECT AVG(p2.price) FROM product p2 WHERE p2.category = p.category)"
        " GROUP BY p.category ORDER BY p.category",
        // Customers who spent more than their credit (correlated, per row).
        "SELECT COUNT(*), SUM(c.id), MAX(c.credit) FROM customer c"
        " WHERE c.credit < (SELECT SUM(i.qty * i.price) FROM orders o"
        " JOIN item i ON i.order_id = o.id WHERE o.customer_id = c.id)",
        // Best-selling products per month (GROUP BY on an expression, HAVING).
        "SELECT o.day / 30 AS month, i.product_id, SUM(i.qty) AS units"
        " FROM orders o JOIN item i ON i.order_id = o.id"
        " GROUP BY month, i.product_id HAVING units > 40"
        " ORDER BY month, units DESC, i.product_id LIMIT 300",
        // Name prefixes (text functions, LIKE).
        "SELECT substr(name, 1, 3) AS pre, COUNT(*), MAX(credit), MIN(id) FROM customer"
        " WHERE name LIKE 'ka%' OR name LIKE '%esh' OR segment = 'GOV'"
        " GROUP BY pre ORDER BY pre",
        // Order-size distribution (subquery in FROM).
        ("SELECT n, COUNT(*), SUM(total) FROM (SELECT order_id, COUNT(*) AS n,"
         " SUM(qty * price) AS total FROM item GROUP BY order_id) GROUP BY n ORDER BY n"),
    };
    for (size_t k = 0; k < sizeof q / sizeof q[0]; k++)
        if (sql_query(db, q[k], acc)) return 1;
    return 0;
}

/// SQLite on an in-memory database, the class of SPEC's sqlite workload:
/// builds a four-table order schema (customers, products, orders, line
/// items in a WITHOUT ROWID table), bulk-inserts generated rows through
/// prepared statements inside transactions, builds secondary indexes,
/// runs a report suite (joins, GROUP BY, ORDER BY…LIMIT, correlated
/// subqueries, LIKE), thousands of indexed point lookups, UPDATEs (one
/// correlated) and a DELETE, then the reports again. Size 1 is 6k
/// customers and 16k orders (~80k rows); size 2 is 5× that; size 3 is
/// 14× (~1.1M rows, ~120 MB of database). The checksum folds every result
/// row and every change count.
int cbk_sql(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int ncust_t[4] = { 0, 6000, 30000, 80000 };
    static const int nprod_t[4] = { 0, 1000, 4000, 8000 };
    static const int nord_t[4] = { 0, 16000, 80000, 220000 };
    static const int nlook_t[4] = { 0, 2000, 8000, 20000 };
    int ncust = ncust_t[size], nprod = nprod_t[size], nord = nord_t[size];
    int32_t *price = (int32_t *)calloc((size_t)nprod + 1, sizeof(int32_t));
    if (!price) return 1;
    sqlite3 *db = NULL;
    if (sqlite3_open_v2(":memory:", &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE |
                        SQLITE_OPEN_NOMUTEX, NULL) != SQLITE_OK) {
        sqlite3_close(db);
        free(price);
        return 2;
    }
    int rc = 3;
    sqlite3_stmt *a = NULL, *b = NULL;
    ib_rng r;
    ib_seed(&r, 0x5C1173ULL + (uint64_t)size);
    sql_acc acc = { IB_FNV_OFFSET, 0 };
    uint64_t inserted = 0;
    if (sql_exec(db, "PRAGMA journal_mode=MEMORY; PRAGMA temp_store=MEMORY;")) goto done;
    if (sql_load(db, &r, ncust, nprod, nord, price, &inserted)) goto done;
    if (sql_exec(db,
            "CREATE INDEX orders_cust ON orders(customer_id, day);"
            "CREATE INDEX item_prod ON item(product_id);"
            "CREATE INDEX customer_region ON customer(region, credit);"
            "CREATE INDEX product_cat ON product(category, price);"
            "ANALYZE;"))
        goto done;
    if (sql_reports(db, &acc)) goto done;

    // OLTP-style point lookups: a customer's latest orders, then each
    // order's total.
    if (sqlite3_prepare_v2(db, "SELECT id, day, status FROM orders WHERE customer_id = ?1"
                           " ORDER BY day DESC, id DESC LIMIT 3", -1, &a, NULL)) goto done;
    if (sqlite3_prepare_v2(db, "SELECT SUM(qty * price), COUNT(*) FROM item"
                           " WHERE order_id = ?1", -1, &b, NULL)) goto done;
    for (int k = 0; k < nlook_t[size]; k++) {
        sqlite3_bind_int64(a, 1, sql_skew(&r, ncust));
        int s;
        while ((s = sqlite3_step(a)) == SQLITE_ROW) {
            for (int c = 0; c < 3; c++) acc.h = sql_fold(a, c, acc.h);
            acc.rows++;
            sqlite3_bind_int64(b, 1, sqlite3_column_int64(a, 0));
            if (sql_drain(b, &acc)) goto done;
            sqlite3_reset(b);
        }
        if (s != SQLITE_DONE) goto done;
        sqlite3_reset(a);
    }

    // Price changes, re-pricing of recent items (correlated UPDATE),
    // cancellations and a purge, then the reports again.
    if (sql_exec(db, "BEGIN")) goto done;
    if (sql_change(db, "UPDATE product SET price = price + price / 20 WHERE category % 3 = 0", &acc)) goto done;
    if (sql_change(db, "UPDATE item SET price = (SELECT p.price FROM product p WHERE p.id = item.product_id)"
                   " WHERE order_id IN (SELECT id FROM orders WHERE day >= 700)", &acc)) goto done;
    if (sql_change(db, "UPDATE orders SET status = 3 WHERE day % 17 = 0 AND customer_id % 5 = 1", &acc)) goto done;
    if (sql_change(db, "DELETE FROM item WHERE qty = 1 AND product_id % 11 = 0", &acc)) goto done;
    if (sql_exec(db, "COMMIT")) goto done;
    if (sql_reports(db, &acc)) goto done;
    rc = 0;
done:
    sqlite3_finalize(a);
    sqlite3_finalize(b);
    sqlite3_close(db);
    free(price);
    if (rc == 0)
        ib_result(out, acc.h, (double)acc.rows, (double)(inserted + acc.rows), "rows");
    return rc;
}

// ── lint: tokenizer, CFG builder and dataflow checker for C-like code ──

// Source text buffer.
typedef struct { char *s; size_t n, cap; bool oom; } lint_buf;

static void lb_put(lint_buf *b, const char *s, size_t len) {
    if (b->oom) return;
    if (b->n + len + 1 > b->cap) {
        size_t nc = b->cap ? b->cap * 2 : 65536;
        while (nc < b->n + len + 1) nc *= 2;
        char *ns = (char *)realloc(b->s, nc);
        if (!ns) { b->oom = true; return; }
        b->s = ns;
        b->cap = nc;
    }
    memcpy(b->s + b->n, s, len);
    b->n += len;
    b->s[b->n] = 0;
}

static void lb_str(lint_buf *b, const char *s) { lb_put(b, s, strlen(s)); }

static void lb_num(lint_buf *b, unsigned v) {
    char t[12];
    int n = 0;
    do { t[11 - n++] = (char)('0' + v % 10); v /= 10; } while (v);
    lb_put(b, t + 12 - n, (size_t)n);
}

// ---- The generator: random but well-formed C-like functions ----

#define LINT_MAXI 20
#define LINT_MAXP 8

typedef struct {
    ib_rng *r;
    lint_buf *b;
    int ni, np;                       // names in scope
    char in[LINT_MAXI][12], pn[LINT_MAXP][12];
    int budget;
} lint_gen;

static const char *const lint_ipre[12] = {
    "count", "idx", "len", "tmp", "sum", "val", "acc", "pos", "res", "off", "lim", "step",
};
static const char *const lint_ppre[6] = { "ptr", "buf", "node", "cur", "head", "tail" };
static const char *const lint_ops[6] = { " + ", " - ", " * ", " / ", " ^ ", " % " };
static const char *const lint_rel[6] = { " < ", " > ", " <= ", " >= ", " == ", " != " };

static void lg_name(char *dst, const char *pre, int k) {
    size_t n = strlen(pre);
    memcpy(dst, pre, n);
    dst[n++] = '_';
    if (k >= 10) dst[n++] = (char)('0' + k / 10);
    dst[n++] = (char)('0' + k % 10);
    dst[n] = 0;
}

static void lg_indent(lint_gen *g, int d) {
    for (int i = 0; i < d; i++) lb_put(g->b, "    ", 4);
}

static void lg_ivar(lint_gen *g) { lb_str(g->b, g->in[ib_below(g->r, (uint32_t)g->ni)]); }
static void lg_pvar(lint_gen *g) { lb_str(g->b, g->pn[ib_below(g->r, (uint32_t)g->np)]); }

static void lg_expr(lint_gen *g, int d) {
    uint32_t c = ib_below(g->r, d > 0 ? 11 : 6);
    switch (c) {
    case 3: lb_num(g->b, ib_below(g->r, 1000)); break;
    case 4:
        if (g->np) { lb_put(g->b, "*", 1); lg_pvar(g); } else lg_ivar(g);
        break;
    case 6: case 7: case 8:
        lb_put(g->b, "(", 1);
        lg_expr(g, d - 1);
        lb_str(g->b, lint_ops[ib_below(g->r, 6)]);
        lg_expr(g, d - 1);
        lb_put(g->b, ")", 1);
        break;
    case 9:
        lb_str(g->b, "mix(");
        lg_expr(g, d - 1);
        lb_str(g->b, ", ");
        lg_expr(g, d - 1);
        lb_put(g->b, ")", 1);
        break;
    case 10:
        lb_put(g->b, "-(", 2);
        lg_expr(g, d - 1);
        lb_put(g->b, ")", 1);
        break;
    default: lg_ivar(g); break;
    }
}

static void lg_cond(lint_gen *g, int d) {
    uint32_t c = ib_below(g->r, 10);
    if (c < 4 && g->np) {
        switch (ib_below(g->r, 4)) {
        case 0: lg_pvar(g); break;
        case 1: lb_put(g->b, "!", 1); lg_pvar(g); break;
        case 2: lg_pvar(g); lb_str(g->b, " != 0"); break;
        default: lg_pvar(g); lb_str(g->b, " == 0"); break;
        }
    } else {
        lg_expr(g, 1);
        lb_str(g->b, lint_rel[ib_below(g->r, 6)]);
        lg_expr(g, 1);
    }
    if (d == 0 && ib_chance(g->r, 1, 4)) {
        lb_str(g->b, ib_chance(g->r, 1, 2) ? " && " : " || ");
        lg_cond(g, 1);
    }
}

static void lg_stmt(lint_gen *g, int depth, bool *ret);

static void lg_block(lint_gen *g, int depth, int n) {
    for (int i = 0; i < n && g->budget > 0; i++) {
        bool ret = false;
        lg_stmt(g, depth, &ret);
        if (ret) {
            if (ib_chance(g->r, 1, 4) && g->budget > 0) lg_stmt(g, depth, &ret);
            break;
        }
    }
}

static void lg_stmt(lint_gen *g, int depth, bool *ret) {
    ib_rng *r = g->r;
    g->budget--;
    if (ib_chance(r, 1, 25)) {
        lg_indent(g, depth);
        lb_str(g->b, ib_chance(r, 1, 2) ? "/* check the bounds first */\n" : "// keep the old value\n");
    }
    lg_indent(g, depth);
    uint32_t c = ib_below(r, 100);
    if (c >= 28 && c < 40 && g->np) {
        lg_pvar(g);
        switch (ib_below(r, 5)) {
        case 0: lb_str(g->b, " = 0;\n"); break;
        case 1: lb_str(g->b, " = &"); lg_ivar(g); lb_str(g->b, ";\n"); break;
        case 2: lb_str(g->b, " = "); lg_pvar(g); lb_str(g->b, ";\n"); break;
        default: lb_str(g->b, " = alloc("); lg_expr(g, 1); lb_str(g->b, ");\n"); break;
        }
    } else if (c >= 40 && c < 50 && g->np) {
        lb_put(g->b, "*", 1);
        lg_pvar(g);
        lb_str(g->b, " = ");
        lg_expr(g, 2);
        lb_str(g->b, ";\n");
    } else if (c >= 50 && c < 66 && depth < 4) {
        lb_str(g->b, "if (");
        lg_cond(g, 0);
        lb_str(g->b, ") {\n");
        lg_block(g, depth + 1, 1 + (int)ib_below(r, 3));
        lg_indent(g, depth);
        if (ib_chance(r, 2, 5)) {
            lb_str(g->b, "} else {\n");
            lg_block(g, depth + 1, 1 + (int)ib_below(r, 3));
            lg_indent(g, depth);
        }
        lb_str(g->b, "}\n");
    } else if (c >= 66 && c < 73 && depth < 4) {
        lb_str(g->b, "while (");
        lg_cond(g, 0);
        lb_str(g->b, ") {\n");
        lg_block(g, depth + 1, 1 + (int)ib_below(r, 4));
        lg_indent(g, depth);
        lb_str(g->b, "}\n");
    } else if (c >= 73 && c < 86) {
        lb_str(g->b, "use(");
        lg_expr(g, 2);
        lb_str(g->b, ", ");
        lg_expr(g, 1);
        lb_str(g->b, ");\n");
    } else if (c >= 86 && c < 89 && depth > 1) {
        lb_str(g->b, "return ");
        lg_expr(g, 1);
        lb_str(g->b, ";\n");
        *ret = true;
    } else {
        lg_ivar(g);
        switch (ib_below(r, 6)) {
        case 0: lb_str(g->b, "++;\n"); break;
        case 1: lb_str(g->b, " += "); lg_expr(g, 2); lb_str(g->b, ";\n"); break;
        default: lb_str(g->b, " = "); lg_expr(g, 2); lb_str(g->b, ";\n"); break;
        }
    }
}

static void lg_function(lint_gen *g, unsigned index) {
    ib_rng *r = g->r;
    lint_buf *b = g->b;
    g->ni = g->np = 0;
    lb_str(b, "int fn");
    lb_num(b, index);
    lb_put(b, "(", 1);
    int nip = 1 + (int)ib_below(r, 3), npp = (int)ib_below(r, 2);
    for (int i = 0; i < nip; i++) {
        lg_name(g->in[g->ni], "arg", i);
        if (i) lb_str(b, ", ");
        lb_str(b, "int ");
        lb_str(b, g->in[g->ni++]);
    }
    for (int i = 0; i < npp; i++) {
        lg_name(g->pn[g->np], "src", i);
        lb_str(b, ", int *");
        lb_str(b, g->pn[g->np++]);
    }
    lb_str(b, ")\n{\n");
    int nil = 3 + (int)ib_below(r, LINT_MAXI - 6), npl = 1 + (int)ib_below(r, LINT_MAXP - 2);
    for (int i = 0; i < nil; i++) {
        char nm[12];
        lg_name(nm, lint_ipre[i % 12], i);
        lb_str(b, "    int ");
        lb_str(b, nm);
        if (ib_chance(r, 1, 2)) { lb_str(b, " = "); lg_expr(g, 1); }
        lb_str(b, ";\n");
        memcpy(g->in[g->ni++], nm, sizeof nm);
    }
    for (int i = 0; i < npl; i++) {
        char nm[12];
        lg_name(nm, lint_ppre[i % 6], i);
        lb_str(b, "    int *");
        lb_str(b, nm);
        if (ib_chance(r, 1, 3)) lb_str(b, " = 0");
        lb_str(b, ";\n");
        memcpy(g->pn[g->np++], nm, sizeof nm);
    }
    g->budget = 30 + (int)ib_below(r, 90);
    while (g->budget > 0) lg_block(g, 1, g->budget);
    lb_str(b, "    return ");
    lg_expr(g, 2);
    lb_str(b, ";\n}\n\n");
}

// ---- Tokens ----

enum {
    TK_EOF, TK_ID, TK_NUM, TK_INT, TK_IF, TK_ELSE, TK_WHILE, TK_RETURN,
    TK_LP, TK_RP, TK_LB, TK_RB, TK_SEMI, TK_COMMA, TK_ASSIGN, TK_PLUS,
    TK_MINUS, TK_STAR, TK_SLASH, TK_PERC, TK_CARET, TK_AMP, TK_LT, TK_GT,
    TK_LE, TK_GE, TK_EQ, TK_NE, TK_NOT, TK_ANDAND, TK_OROR, TK_INC, TK_DEC,
    TK_PLUSEQ, TK_MINUSEQ,
};

typedef struct { uint8_t k; int32_t v, line; } lint_tok;

// CFG node kinds and pointer-assignment kinds.
enum { LN_ENTRY, LN_EXIT, LN_NOP, LN_ASSIGN, LN_STORE, LN_BRANCH, LN_RETURN, LN_CALL };
enum { LP_NONE, LP_NULL, LP_ADDR, LP_COPY, LP_ALLOC, LP_OTHER };
// Finding kinds.
enum { LF_UNINIT = 1, LF_MAYUNINIT, LF_NULLDEREF, LF_MAYNULL, LF_DEADSTORE, LF_UNREACH };

typedef struct {
    uint8_t kind, pkind;
    int8_t pol;            // branch: 1 if the true edge means `test` is non-null
    int16_t def, src, test;
    int32_t line;
    int32_t succ[2];
    int32_t use_off, use_n, der_off, der_n;
} lint_node;

#define LINT_MAXV 64

typedef struct {
    // Source and tokens of the current file.
    lint_buf src;
    lint_tok *tok;
    int ntok, tcap, pos;
    // Identifier interning: open addressing on (hash, text).
    struct lint_ient { uint64_t h; int32_t off, len, id; } *itab;
    int icap, nid;
    int32_t *idoff, *idlen, *sym;
    int idcap;
    // The function being analysed.
    int nvars, exit_node;
    uint8_t vptr[LINT_MAXV], vparam[LINT_MAXV], vesc[LINT_MAXV];
    int8_t pidx[LINT_MAXV];
    int32_t vid[LINT_MAXV];
    lint_node *node;
    int nnode, ncap;
    ib_ivec uses, ders;
    // Analysis scratch, grown on demand.
    int32_t *poff, *plist, *rpo, *stk, *defid;
    uint8_t *reach;
    int scap;
    uint64_t *rd, *vdefs;      // reaching-definition OUT sets, per-var def sets
    size_t rdcap, vdcap;
    uint32_t *nin, *nout0, *nout1;
    uint64_t *lin, *lout, *luse, *ldef;
    bool err, oom;
    // Results.
    uint64_t h, findings, tokens, nodes_total;
    uint64_t counts[8];
} lint_ctx;

static int lint_intern(lint_ctx *c, const char *s, int32_t off, int32_t len) {
    uint64_t h = ib_mix_bytes(IB_FNV_OFFSET, s + off, (size_t)len);
    int mask = c->icap - 1, i = (int)(h & (uint64_t)mask);
    while (c->itab[i].id >= 0) {
        struct lint_ient *e = &c->itab[i];
        if (e->h == h && e->len == len && memcmp(s + e->off, s + off, (size_t)len) == 0) return e->id;
        i = (i + 1) & mask;
    }
    if (c->nid >= c->idcap || 2 * (c->nid + 1) > c->icap) { c->oom = true; return -1; }
    int id = c->nid++;
    c->itab[i].h = h; c->itab[i].off = off; c->itab[i].len = len; c->itab[i].id = id;
    c->idoff[id] = off; c->idlen[id] = len; c->sym[id] = -1;
    return id;
}

static bool lint_push_tok(lint_ctx *c, int k, int32_t v, int32_t line) {
    if (c->ntok == c->tcap) {
        int nc = c->tcap ? c->tcap * 2 : 65536;
        lint_tok *nt = (lint_tok *)realloc(c->tok, (size_t)nc * sizeof(lint_tok));
        if (!nt) { c->oom = true; return false; }
        c->tok = nt;
        c->tcap = nc;
    }
    c->tok[c->ntok].k = (uint8_t)k;
    c->tok[c->ntok].v = v;
    c->tok[c->ntok].line = line;
    c->ntok++;
    return true;
}

static bool lint_isal(char ch) { return (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || ch == '_'; }
static bool lint_isdig(char ch) { return ch >= '0' && ch <= '9'; }

/// Splits the file into tokens, interning identifiers; skips comments.
static bool lint_lex(lint_ctx *c) {
    const char *s = c->src.s;
    size_t n = c->src.n, i = 0;
    int32_t line = 1;
    c->ntok = 0;
    c->nid = 0;
    for (int k = 0; k < c->icap; k++) c->itab[k].id = -1;
    while (i < n) {
        char ch = s[i];
        if (ch == '\n') { line++; i++; continue; }
        if (ch == ' ' || ch == '\t' || ch == '\r') { i++; continue; }
        if (ch == '/' && i + 1 < n && s[i + 1] == '/') {
            while (i < n && s[i] != '\n') i++;
            continue;
        }
        if (ch == '/' && i + 1 < n && s[i + 1] == '*') {
            i += 2;
            while (i + 1 < n && !(s[i] == '*' && s[i + 1] == '/')) { if (s[i] == '\n') line++; i++; }
            i += 2;
            continue;
        }
        if (lint_isal(ch)) {
            size_t j = i + 1;
            while (j < n && (lint_isal(s[j]) || lint_isdig(s[j]))) j++;
            size_t len = j - i;
            int k = TK_ID;
            if (len == 3 && memcmp(s + i, "int", 3) == 0) k = TK_INT;
            else if (len == 2 && memcmp(s + i, "if", 2) == 0) k = TK_IF;
            else if (len == 4 && memcmp(s + i, "else", 4) == 0) k = TK_ELSE;
            else if (len == 5 && memcmp(s + i, "while", 5) == 0) k = TK_WHILE;
            else if (len == 6 && memcmp(s + i, "return", 6) == 0) k = TK_RETURN;
            int32_t v = 0;
            if (k == TK_ID) {
                v = lint_intern(c, s, (int32_t)i, (int32_t)len);
                if (v < 0) return false;
            }
            if (!lint_push_tok(c, k, v, line)) return false;
            i = j;
            continue;
        }
        if (lint_isdig(ch)) {
            int32_t v = 0;
            while (i < n && lint_isdig(s[i])) v = v * 10 + (s[i++] - '0');
            if (!lint_push_tok(c, TK_NUM, v, line)) return false;
            continue;
        }
        char d = i + 1 < n ? s[i + 1] : 0;
        int k = -1, w = 1;
        switch (ch) {
        case '(': k = TK_LP; break;
        case ')': k = TK_RP; break;
        case '{': k = TK_LB; break;
        case '}': k = TK_RB; break;
        case ';': k = TK_SEMI; break;
        case ',': k = TK_COMMA; break;
        case '*': k = TK_STAR; break;
        case '/': k = TK_SLASH; break;
        case '%': k = TK_PERC; break;
        case '^': k = TK_CARET; break;
        case '=': if (d == '=') { k = TK_EQ; w = 2; } else k = TK_ASSIGN; break;
        case '!': if (d == '=') { k = TK_NE; w = 2; } else k = TK_NOT; break;
        case '<': if (d == '=') { k = TK_LE; w = 2; } else k = TK_LT; break;
        case '>': if (d == '=') { k = TK_GE; w = 2; } else k = TK_GT; break;
        case '&': if (d == '&') { k = TK_ANDAND; w = 2; } else k = TK_AMP; break;
        case '|': if (d == '|') { k = TK_OROR; w = 2; } break;
        case '+':
            if (d == '+') { k = TK_INC; w = 2; }
            else if (d == '=') { k = TK_PLUSEQ; w = 2; }
            else k = TK_PLUS;
            break;
        case '-':
            if (d == '-') { k = TK_DEC; w = 2; }
            else if (d == '=') { k = TK_MINUSEQ; w = 2; }
            else k = TK_MINUS;
            break;
        default: break;
        }
        if (k < 0) return false;
        if (!lint_push_tok(c, k, 0, line)) return false;
        i += (size_t)w;
    }
    for (int k = 0; k < 4; k++)
        if (!lint_push_tok(c, TK_EOF, 0, line)) return false;
    return true;
}

// ---- Parser and CFG construction ----

static int lint_new_node(lint_ctx *c, int kind, int line) {
    if (c->nnode == c->ncap) {
        int nc = c->ncap ? c->ncap * 2 : 1024;
        lint_node *nn = (lint_node *)realloc(c->node, (size_t)nc * sizeof(lint_node));
        if (!nn) { c->oom = c->err = true; return 0; }
        c->node = nn;
        c->ncap = nc;
    }
    lint_node *n = &c->node[c->nnode];
    memset(n, 0, sizeof *n);
    n->kind = (uint8_t)kind;
    n->def = n->src = n->test = -1;
    n->line = line;
    n->succ[0] = n->succ[1] = -1;
    n->use_off = c->uses.n;
    n->der_off = c->ders.n;
    return c->nnode++;
}

/// Closes the use/deref lists of node `n` that were collected since
/// `uoff`/`doff`.
static void lint_close(lint_ctx *c, int n, int uoff, int doff) {
    c->node[n].use_off = uoff;
    c->node[n].use_n = c->uses.n - uoff;
    c->node[n].der_off = doff;
    c->node[n].der_n = c->ders.n - doff;
}

static void lint_link(lint_ctx *c, int from, int to) {
    if (from >= 0 && !c->err) c->node[from].succ[0] = to;
}

static int lint_nop(lint_ctx *c, int line) { return lint_new_node(c, LN_NOP, line); }

static inline int lint_peek(lint_ctx *c) { return c->tok[c->pos].k; }

static bool lint_accept(lint_ctx *c, int k) {
    if (c->tok[c->pos].k == k) { c->pos++; return true; }
    return false;
}

static void lint_expect(lint_ctx *c, int k) {
    if (!lint_accept(c, k)) c->err = true;
}

static int lint_var(lint_ctx *c, int32_t id) { return id >= 0 && id < c->nid ? c->sym[id] : -1; }

static void lint_use(lint_ctx *c, int v) {
    if (!ib_ivec_push(&c->uses, v)) c->oom = c->err = true;
}

static void lint_der(lint_ctx *c, int v) {
    if (!ib_ivec_push(&c->ders, v)) c->oom = c->err = true;
}

static void lint_expr(lint_ctx *c);

static void lint_unary(lint_ctx *c) {
    if (c->err) return;
    lint_tok *t = &c->tok[c->pos];
    switch (t->k) {
    case TK_MINUS:
    case TK_NOT:
        c->pos++;
        lint_unary(c);
        return;
    case TK_STAR: {
        if (t[1].k != TK_ID) { c->err = true; return; }
        int v = lint_var(c, t[1].v);
        c->pos += 2;
        if (v >= 0) { lint_use(c, v); if (c->vptr[v]) lint_der(c, v); }
        return;
    }
    case TK_AMP: {
        if (t[1].k != TK_ID) { c->err = true; return; }
        int v = lint_var(c, t[1].v);
        c->pos += 2;
        if (v >= 0) c->vesc[v] = 1;
        return;
    }
    case TK_LP:
        c->pos++;
        lint_expr(c);
        lint_expect(c, TK_RP);
        return;
    case TK_NUM:
        c->pos++;
        return;
    case TK_ID: {
        int v = lint_var(c, t->v);
        c->pos++;
        if (lint_accept(c, TK_LP)) {
            if (!lint_accept(c, TK_RP)) {
                do lint_expr(c); while (!c->err && lint_accept(c, TK_COMMA));
                lint_expect(c, TK_RP);
            }
        } else if (v >= 0) {
            lint_use(c, v);
        }
        return;
    }
    default:
        c->err = true;
        return;
    }
}

static bool lint_binop(int k) {
    return (k >= TK_PLUS && k <= TK_NE);
}

static void lint_expr(lint_ctx *c) {
    lint_unary(c);
    while (!c->err && lint_binop(lint_peek(c))) {
        c->pos++;
        lint_unary(c);
    }
}

static bool lint_condend(int k) { return k == TK_RP || k == TK_ANDAND || k == TK_OROR; }

/// One comparison of a condition, as a branch node to T/F. Recognises
/// null tests (`p`, `!p`, `p != 0`, `p == 0`) for the pointer analysis.
static int lint_atom(lint_ctx *c, int T, int F) {
    int uoff = c->uses.n, doff = c->ders.n;
    lint_tok *t = &c->tok[c->pos];
    int test = -1, pol = 0, v;
    if (t[0].k == TK_ID && (v = lint_var(c, t[0].v)) >= 0 && c->vptr[v] && lint_condend(t[1].k)) {
        test = v; pol = 1;
    } else if (t[0].k == TK_NOT && t[1].k == TK_ID && (v = lint_var(c, t[1].v)) >= 0 &&
               c->vptr[v] && lint_condend(t[2].k)) {
        test = v; pol = 0;
    } else if (t[0].k == TK_ID && (v = lint_var(c, t[0].v)) >= 0 && c->vptr[v] &&
               (t[1].k == TK_NE || t[1].k == TK_EQ) && t[2].k == TK_NUM && t[2].v == 0 &&
               lint_condend(t[3].k)) {
        test = v; pol = t[1].k == TK_NE;
    }
    int line = t->line;
    lint_expr(c);
    int n = lint_new_node(c, LN_BRANCH, line);
    if (c->err) return n;
    lint_close(c, n, uoff, doff);
    c->node[n].test = (int16_t)test;
    c->node[n].pol = (int8_t)pol;
    c->node[n].succ[0] = T;
    c->node[n].succ[1] = F;
    return n;
}

static void lint_and(lint_ctx *c, int cur, int T, int F) {
    for (;;) {
        int mid = lint_nop(c, c->tok[c->pos].line);
        int b = lint_atom(c, mid, F);
        lint_link(c, cur, b);
        if (c->err) return;
        if (lint_accept(c, TK_ANDAND)) { cur = mid; continue; }
        lint_link(c, mid, T);
        return;
    }
}

static void lint_or(lint_ctx *c, int cur, int T, int F) {
    for (;;) {
        int mid = lint_nop(c, c->tok[c->pos].line);
        lint_and(c, cur, T, mid);
        if (c->err) return;
        if (lint_accept(c, TK_OROR)) { cur = mid; continue; }
        lint_link(c, mid, F);
        return;
    }
}

/// Right-hand side of a pointer assignment.
static int lint_prhs(lint_ctx *c, int *src) {
    lint_tok *t = &c->tok[c->pos];
    int v;
    if (t[0].k == TK_NUM && t[0].v == 0 && t[1].k == TK_SEMI) { c->pos++; return LP_NULL; }
    if (t[0].k == TK_AMP && t[1].k == TK_ID && t[2].k == TK_SEMI) {
        v = lint_var(c, t[1].v);
        if (v >= 0) c->vesc[v] = 1;
        c->pos += 2;
        return LP_ADDR;
    }
    if (t[0].k == TK_ID && t[1].k == TK_SEMI && (v = lint_var(c, t[0].v)) >= 0 && c->vptr[v]) {
        *src = v;
        lint_use(c, v);
        c->pos++;
        return LP_COPY;
    }
    if (t[0].k == TK_ID && t[1].k == TK_LP && c->idlen[t[0].v] == 5 &&
        memcmp(c->src.s + c->idoff[t[0].v], "alloc", 5) == 0) {
        lint_expr(c);
        return LP_ALLOC;
    }
    lint_expr(c);
    return LP_OTHER;
}

/// `name = …;` for a variable `v` (the name is already consumed).
static int lint_assign_rhs(lint_ctx *c, int cur, int v, int line, int uoff, int doff) {
    int src = -1, pk = LP_NONE;
    if (c->vptr[v]) pk = lint_prhs(c, &src);
    else lint_expr(c);
    int n = lint_new_node(c, LN_ASSIGN, line);
    if (c->err) return -1;
    lint_close(c, n, uoff, doff);
    c->node[n].def = (int16_t)v;
    c->node[n].pkind = (uint8_t)pk;
    c->node[n].src = (int16_t)src;
    lint_link(c, cur, n);
    return n;
}

static int lint_new_var(lint_ctx *c, int32_t id, bool isptr, bool param) {
    if (c->nvars >= LINT_MAXV || id < 0) { c->err = true; return -1; }
    int v = c->nvars++;
    c->vptr[v] = isptr;
    c->vparam[v] = param;
    c->vesc[v] = 0;
    c->vid[v] = id;
    c->sym[id] = v;
    return v;
}

static int lint_stmt(lint_ctx *c, int cur);

static int lint_block(lint_ctx *c, int cur) {
    while (!c->err && lint_peek(c) != TK_RB && lint_peek(c) != TK_EOF) cur = lint_stmt(c, cur);
    lint_expect(c, TK_RB);
    return cur;
}

/// Parses one statement, adding its nodes after `cur`; returns the node
/// control leaves from, or -1 if it cannot fall through.
static int lint_stmt(lint_ctx *c, int cur) {
    if (c->err) return cur;
    lint_tok *t = &c->tok[c->pos];
    int line = t->line, uoff = c->uses.n, doff = c->ders.n;
    switch (t->k) {
    case TK_LB:
        c->pos++;
        return lint_block(c, cur);
    case TK_SEMI:
        c->pos++;
        return cur;
    case TK_IF: {
        c->pos++;
        lint_expect(c, TK_LP);
        int T = lint_nop(c, line), F = lint_nop(c, line);
        lint_or(c, cur, T, F);
        lint_expect(c, TK_RP);
        int et = lint_stmt(c, T), ee = F;
        if (lint_accept(c, TK_ELSE)) ee = lint_stmt(c, F);
        int J = lint_nop(c, line);
        lint_link(c, et, J);
        lint_link(c, ee, J);
        return J;
    }
    case TK_WHILE: {
        c->pos++;
        lint_expect(c, TK_LP);
        int H = lint_nop(c, line);
        lint_link(c, cur, H);
        int T = lint_nop(c, line), F = lint_nop(c, line);
        lint_or(c, H, T, F);
        lint_expect(c, TK_RP);
        int eb = lint_stmt(c, T);
        lint_link(c, eb, H);
        return F;
    }
    case TK_RETURN: {
        c->pos++;
        if (lint_peek(c) != TK_SEMI) lint_expr(c);
        lint_expect(c, TK_SEMI);
        int n = lint_new_node(c, LN_RETURN, line);
        if (c->err) return -1;
        lint_close(c, n, uoff, doff);
        lint_link(c, cur, n);
        lint_link(c, n, c->exit_node);
        return -1;
    }
    case TK_INT: {
        c->pos++;
        bool isptr = lint_accept(c, TK_STAR);
        if (lint_peek(c) != TK_ID) { c->err = true; return cur; }
        int v = lint_new_var(c, c->tok[c->pos].v, isptr, false);
        c->pos++;
        if (v < 0) return cur;
        if (lint_accept(c, TK_ASSIGN)) {
            int n = lint_assign_rhs(c, cur, v, line, uoff, doff);
            if (n >= 0) cur = n;
        }
        lint_expect(c, TK_SEMI);
        return cur;
    }
    case TK_STAR: {
        if (t[1].k != TK_ID) { c->err = true; return cur; }
        int v = lint_var(c, t[1].v);
        c->pos += 2;
        if (v >= 0) { lint_use(c, v); if (c->vptr[v]) lint_der(c, v); }
        lint_expect(c, TK_ASSIGN);
        lint_expr(c);
        lint_expect(c, TK_SEMI);
        int n = lint_new_node(c, LN_STORE, line);
        if (c->err) return cur;
        lint_close(c, n, uoff, doff);
        lint_link(c, cur, n);
        return n;
    }
    case TK_ID: {
        int v = lint_var(c, t->v);
        c->pos++;
        int n;
        if (lint_accept(c, TK_LP)) {
            if (!lint_accept(c, TK_RP)) {
                do lint_expr(c); while (!c->err && lint_accept(c, TK_COMMA));
                lint_expect(c, TK_RP);
            }
            n = lint_new_node(c, LN_CALL, line);
            if (c->err) return cur;
            lint_close(c, n, uoff, doff);
            lint_link(c, cur, n);
        } else {
            if (v < 0) { c->err = true; return cur; }
            if (lint_accept(c, TK_ASSIGN)) {
                n = lint_assign_rhs(c, cur, v, line, uoff, doff);
            } else if (lint_accept(c, TK_INC) || lint_accept(c, TK_DEC)) {
                lint_use(c, v);
                n = lint_new_node(c, LN_ASSIGN, line);
                if (c->err) return cur;
                lint_close(c, n, uoff, doff);
                c->node[n].def = (int16_t)v;
                c->node[n].pkind = c->vptr[v] ? LP_OTHER : LP_NONE;
                lint_link(c, cur, n);
            } else if (lint_accept(c, TK_PLUSEQ) || lint_accept(c, TK_MINUSEQ)) {
                lint_use(c, v);
                lint_expr(c);
                n = lint_new_node(c, LN_ASSIGN, line);
                if (c->err) return cur;
                lint_close(c, n, uoff, doff);
                c->node[n].def = (int16_t)v;
                c->node[n].pkind = c->vptr[v] ? LP_OTHER : LP_NONE;
                lint_link(c, cur, n);
            } else {
                c->err = true;
                return cur;
            }
            if (n < 0) return cur;
        }
        lint_expect(c, TK_SEMI);
        return n;
    }
    default:
        c->err = true;
        return cur;
    }
}

static bool lint_grow_scratch(lint_ctx *c) {
    int n = c->nnode;
    if (n + 1 > c->scap) {
        int nc = c->scap ? c->scap : 1024;
        while (nc < n + 1) nc *= 2;
        int32_t **ip[] = { &c->poff, &c->plist, &c->rpo, &c->stk, &c->defid };
        for (size_t k = 0; k < sizeof ip / sizeof ip[0]; k++) {
            int32_t *p = (int32_t *)realloc(*ip[k], (size_t)(2 * nc + 2) * sizeof(int32_t));
            if (!p) return false;
            *ip[k] = p;
        }
        uint8_t *rp = (uint8_t *)realloc(c->reach, (size_t)nc);
        if (!rp) return false;
        c->reach = rp;
        uint32_t **up[] = { &c->nin, &c->nout0, &c->nout1 };
        for (size_t k = 0; k < 3; k++) {
            uint32_t *p = (uint32_t *)realloc(*up[k], (size_t)nc * sizeof(uint32_t));
            if (!p) return false;
            *up[k] = p;
        }
        uint64_t **lp[] = { &c->lin, &c->lout, &c->luse, &c->ldef };
        for (size_t k = 0; k < 4; k++) {
            uint64_t *p = (uint64_t *)realloc(*lp[k], (size_t)nc * sizeof(uint64_t));
            if (!p) return false;
            *lp[k] = p;
        }
        c->scap = nc;
    }
    return true;
}

static void lint_report(lint_ctx *c, int fidx, int line, int kind, int var) {
    c->findings++;
    c->counts[kind]++;
    c->h = ib_mix(c->h, ((uint64_t)(uint32_t)fidx << 32) | ((uint64_t)(uint32_t)line << 8) | (uint64_t)kind);
    c->h = ib_mix(c->h, (uint64_t)(int64_t)var);
}

static inline uint32_t lint_pget(uint32_t s, int p) { return (s >> (2 * p)) & 3u; }
static inline uint32_t lint_pset(uint32_t s, int p, uint32_t v) {
    return (s & ~(3u << (2 * p))) | (v << (2 * p));
}

/// The null-pointer transfer function of one node: state in, the states
/// out of its true (o0) and false (o1) edges.
static void lint_ntransfer(lint_ctx *c, const lint_node *n, uint32_t s, uint32_t *o0, uint32_t *o1) {
    for (int k = 0; k < n->der_n; k++) {
        int p = c->pidx[c->ders.a[n->der_off + k]];
        if (p >= 0) s = lint_pset(s, p, 2);
    }
    if (n->def >= 0 && c->vptr[n->def]) {
        int p = c->pidx[n->def];
        uint32_t v = 3;
        switch (n->pkind) {
        case LP_NULL: v = 1; break;
        case LP_ADDR: v = 2; break;
        case LP_COPY: v = n->src >= 0 ? lint_pget(s, c->pidx[n->src]) : 3; break;
        default: v = 3; break;
        }
        s = lint_pset(s, p, v);
    }
    *o0 = *o1 = s;
    if (n->kind == LN_BRANCH && n->test >= 0) {
        int p = c->pidx[n->test];
        uint32_t cur = lint_pget(s, p);
        *o0 = lint_pset(s, p, cur & (n->pol ? 2u : 1u));
        *o1 = lint_pset(s, p, cur & (n->pol ? 1u : 2u));
    }
}

/// Runs the three dataflow analyses over the CFG of function `fidx` and
/// reports what they find.
static bool lint_analyze(lint_ctx *c, int fidx) {
    int N = c->nnode, V = c->nvars;
    if (!lint_grow_scratch(c)) return false;
    lint_node *nd = c->node;
    c->nodes_total += (uint64_t)N;

    // Predecessor lists (CSR); entries are pred*2 + edge slot.
    memset(c->poff, 0, (size_t)(N + 1) * sizeof(int32_t));
    for (int i = 0; i < N; i++)
        for (int s = 0; s < 2; s++)
            if (nd[i].succ[s] >= 0) c->poff[nd[i].succ[s] + 1]++;
    for (int i = 0; i < N; i++) c->poff[i + 1] += c->poff[i];
    for (int i = 0; i < N; i++) c->defid[i] = c->poff[i];
    for (int i = 0; i < N; i++)
        for (int s = 0; s < 2; s++)
            if (nd[i].succ[s] >= 0) c->plist[c->defid[nd[i].succ[s]]++] = 2 * i + s;

    // Reverse postorder of the reachable nodes (iterative DFS).
    memset(c->reach, 0, (size_t)N);
    int nr = 0, sp = 0;
    c->stk[sp++] = 0; c->stk[sp++] = 0;
    c->reach[0] = 1;
    while (sp) {
        int v = c->stk[sp - 2], k = c->stk[sp - 1];
        if (k < 2) {
            c->stk[sp - 1] = k + 1;
            int w = nd[v].succ[k];
            if (w >= 0 && !c->reach[w]) {
                c->reach[w] = 1;
                c->stk[sp++] = w; c->stk[sp++] = 0;
            }
        } else {
            c->rpo[nr++] = v;
            sp -= 2;
        }
    }
    for (int i = 0; i < nr / 2; i++) {
        int t = c->rpo[i]; c->rpo[i] = c->rpo[nr - 1 - i]; c->rpo[nr - 1 - i] = t;
    }

    // Unreachable statements.
    for (int i = 0; i < N; i++)
        if (!c->reach[i] && nd[i].kind != LN_NOP && nd[i].kind != LN_EXIT)
            lint_report(c, fidx, nd[i].line, LF_UNREACH, -1);

    // 1. Reaching definitions. Defs 0..V-1 are the entry definitions
    // (parameter values, or "uninitialised" for locals); then one per
    // assigning node.
    int D = V;
    for (int i = 0; i < N; i++) c->defid[i] = nd[i].def >= 0 ? D++ : -1;
    int W = (D + 63) / 64;
    size_t need = (size_t)N * (size_t)W;
    if (need > c->rdcap) {
        uint64_t *p = (uint64_t *)realloc(c->rd, need * sizeof(uint64_t));
        if (!p) return false;
        c->rd = p;
        c->rdcap = need;
    }
    size_t vneed = (size_t)(V + 1) * (size_t)W;
    if (vneed > c->vdcap) {
        uint64_t *p = (uint64_t *)realloc(c->vdefs, vneed * sizeof(uint64_t));
        if (!p) return false;
        c->vdefs = p;
        c->vdcap = vneed;
    }
    uint64_t *rd = c->rd, *vd = c->vdefs, *tmp = c->vdefs + (size_t)V * (size_t)W;
    memset(rd, 0, need * sizeof(uint64_t));
    memset(vd, 0, vneed * sizeof(uint64_t));
    for (int v = 0; v < V; v++) vd[(size_t)v * W + v / 64] |= 1ULL << (v % 64);
    for (int i = 0; i < N; i++)
        if (c->defid[i] >= 0) {
            int v = nd[i].def, d = c->defid[i];
            vd[(size_t)v * W + d / 64] |= 1ULL << (d % 64);
        }
    for (int v = 0; v < V; v++) rd[v / 64] |= 1ULL << (v % 64);   // OUT(entry)
    for (bool changed = true; changed;) {
        changed = false;
        for (int k = 1; k < nr; k++) {
            int i = c->rpo[k];
            memset(tmp, 0, (size_t)W * sizeof(uint64_t));
            for (int e = c->poff[i]; e < c->poff[i + 1]; e++) {
                const uint64_t *po = rd + (size_t)(c->plist[e] >> 1) * W;
                for (int w = 0; w < W; w++) tmp[w] |= po[w];
            }
            if (c->defid[i] >= 0) {
                const uint64_t *kill = vd + (size_t)nd[i].def * W;
                for (int w = 0; w < W; w++) tmp[w] &= ~kill[w];
                tmp[c->defid[i] / 64] |= 1ULL << (c->defid[i] % 64);
            }
            uint64_t *out = rd + (size_t)i * W;
            if (memcmp(out, tmp, (size_t)W * sizeof(uint64_t)) != 0) {
                memcpy(out, tmp, (size_t)W * sizeof(uint64_t));
                changed = true;
            }
        }
    }
    // Uses reached by an entry "uninitialised" definition.
    for (int k = 1; k < nr; k++) {
        int i = c->rpo[k];
        if (nd[i].use_n == 0) continue;
        memset(tmp, 0, (size_t)W * sizeof(uint64_t));
        for (int e = c->poff[i]; e < c->poff[i + 1]; e++) {
            const uint64_t *po = rd + (size_t)(c->plist[e] >> 1) * W;
            for (int w = 0; w < W; w++) tmp[w] |= po[w];
        }
        uint64_t seen = 0;
        for (int u = 0; u < nd[i].use_n; u++) {
            int v = c->uses.a[nd[i].use_off + u];
            if (c->vparam[v] || c->vesc[v] || (seen >> v & 1)) continue;
            seen |= 1ULL << v;
            if (!(tmp[v / 64] >> (v % 64) & 1)) continue;
            bool other = false;
            const uint64_t *dv = vd + (size_t)v * W;
            for (int w = 0; w < W; w++) {
                uint64_t m = tmp[w] & dv[w];
                if (w == v / 64) m &= ~(1ULL << (v % 64));
                if (m) { other = true; break; }
            }
            lint_report(c, fidx, nd[i].line, other ? LF_MAYUNINIT : LF_UNINIT, v);
        }
    }

    // 2. Null-pointer states: two bits per pointer (may be null, may be
    // non-null), refined along the edges of null tests.
    int np = 0;
    for (int v = 0; v < V; v++) c->pidx[v] = (int8_t)(c->vptr[v] ? np++ : -1);
    if (np > 0) {
        uint32_t entry = 0;
        for (int v = 0; v < V; v++)
            if (c->vptr[v] && c->vparam[v]) entry = lint_pset(entry, c->pidx[v], 2);
        for (int i = 0; i < N; i++) c->nin[i] = c->nout0[i] = c->nout1[i] = 0;
        c->nout0[0] = c->nout1[0] = entry;
        for (bool changed = true; changed;) {
            changed = false;
            for (int k = 1; k < nr; k++) {
                int i = c->rpo[k];
                uint32_t s = 0;
                for (int e = c->poff[i]; e < c->poff[i + 1]; e++) {
                    int pe = c->plist[e];
                    s |= (pe & 1) ? c->nout1[pe >> 1] : c->nout0[pe >> 1];
                }
                c->nin[i] = s;
                uint32_t o0, o1;
                lint_ntransfer(c, &nd[i], s, &o0, &o1);
                if (o0 != c->nout0[i] || o1 != c->nout1[i]) {
                    c->nout0[i] = o0; c->nout1[i] = o1;
                    changed = true;
                }
            }
        }
        for (int k = 1; k < nr; k++) {
            int i = c->rpo[k];
            uint32_t s = c->nin[i], done = 0;
            for (int d = 0; d < nd[i].der_n; d++) {
                int v = c->ders.a[nd[i].der_off + d], p = c->pidx[v];
                if (p < 0 || (done >> p & 1)) continue;
                done |= 1u << p;
                uint32_t st = lint_pget(s, p);
                if (st & 1) lint_report(c, fidx, nd[i].line, st == 1 ? LF_NULLDEREF : LF_MAYNULL, v);
            }
        }
    }

    // 3. Liveness, backwards, for stores nothing reads.
    for (int i = 0; i < N; i++) {
        uint64_t u = 0;
        for (int k = 0; k < nd[i].use_n; k++) u |= 1ULL << c->uses.a[nd[i].use_off + k];
        c->luse[i] = u;
        c->ldef[i] = nd[i].def >= 0 ? 1ULL << nd[i].def : 0;
        c->lin[i] = c->lout[i] = 0;
    }
    for (bool changed = true; changed;) {
        changed = false;
        for (int k = nr - 1; k >= 0; k--) {
            int i = c->rpo[k];
            uint64_t o = 0;
            if (nd[i].succ[0] >= 0) o |= c->lin[nd[i].succ[0]];
            if (nd[i].succ[1] >= 0) o |= c->lin[nd[i].succ[1]];
            uint64_t in = c->luse[i] | (o & ~c->ldef[i]);
            if (o != c->lout[i] || in != c->lin[i]) {
                c->lout[i] = o; c->lin[i] = in;
                changed = true;
            }
        }
    }
    for (int k = 0; k < nr; k++) {
        int i = c->rpo[k], v = nd[i].def;
        if (v >= 0 && !c->vesc[v] && !(c->lout[i] >> v & 1))
            lint_report(c, fidx, nd[i].line, LF_DEADSTORE, v);
    }
    return true;
}

/// Parses one function at the current token and analyses it.
static bool lint_function(lint_ctx *c, int fidx) {
    c->nvars = 0;
    c->nnode = 0;
    c->uses.n = c->ders.n = 0;
    c->err = false;
    lint_expect(c, TK_INT);
    lint_expect(c, TK_ID);
    lint_expect(c, TK_LP);
    int entry = lint_new_node(c, LN_ENTRY, c->tok[c->pos].line);
    c->exit_node = lint_new_node(c, LN_EXIT, c->tok[c->pos].line);
    (void)entry;
    if (!lint_accept(c, TK_RP)) {
        do {
            lint_expect(c, TK_INT);
            bool isptr = lint_accept(c, TK_STAR);
            if (lint_peek(c) != TK_ID) { c->err = true; break; }
            lint_new_var(c, c->tok[c->pos].v, isptr, true);
            c->pos++;
        } while (!c->err && lint_accept(c, TK_COMMA));
        lint_expect(c, TK_RP);
    }
    lint_expect(c, TK_LB);
    int end = lint_block(c, 0);
    lint_link(c, end, c->exit_node);
    for (int v = 0; v < c->nvars; v++) c->sym[c->vid[v]] = -1;
    if (c->err) return false;
    return lint_analyze(c, fidx);
}

static void lint_free(lint_ctx *c) {
    free(c->src.s); free(c->tok); free(c->itab);
    free(c->idoff); free(c->idlen); free(c->sym);
    free(c->node); free(c->uses.a); free(c->ders.a);
    free(c->poff); free(c->plist); free(c->rpo); free(c->stk); free(c->defid);
    free(c->reach); free(c->rd); free(c->vdefs);
    free(c->nin); free(c->nout0); free(c->nout1);
    free(c->lin); free(c->lout); free(c->luse); free(c->ldef);
}

/// A static analyser, the class of cppcheck: generates C-like source files
/// (functions with int and pointer locals, if/else, while, &&/||,
/// address-of, alloc() that may return null, early returns, comments),
/// tokenises them with identifier interning, parses each function into a
/// statement-level control-flow graph, and runs three dataflow analyses:
/// reaching definitions (uses of uninitialised variables), a null-pointer
/// state analysis refined along null-test edges (null and possibly-null
/// dereferences), and liveness (assignments nothing reads); unreachable
/// statements are reported too. Size 1 analyses 40 files of 200
/// functions (~6M tokens); size 2 170 files; size 3 720 files. The
/// checksum covers every finding (function, line, kind, variable).
int cbk_lint(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int nfiles_t[4] = { 0, 40, 170, 720 };
    const int per_file = 200;
    lint_ctx *c = (lint_ctx *)calloc(1, sizeof(lint_ctx));
    if (!c) return 1;
    c->icap = 1 << 14;
    c->idcap = c->icap / 2;
    c->itab = (struct lint_ient *)malloc((size_t)c->icap * sizeof(struct lint_ient));
    c->idoff = (int32_t *)malloc((size_t)c->idcap * sizeof(int32_t));
    c->idlen = (int32_t *)malloc((size_t)c->idcap * sizeof(int32_t));
    c->sym = (int32_t *)malloc((size_t)c->idcap * sizeof(int32_t));
    int rc = 1;
    if (!c->itab || !c->idoff || !c->idlen || !c->sym) goto done;
    c->h = IB_FNV_OFFSET;
    ib_rng r;
    ib_seed(&r, 0x11A7C0DEULL + (uint64_t)size);
    lint_gen g;
    memset(&g, 0, sizeof g);
    g.r = &r;
    g.b = &c->src;
    int fidx = 0;
    for (int f = 0; f < nfiles_t[size]; f++) {
        c->src.n = 0;
        lb_str(&c->src, "/* generated translation unit */\n");
        for (int k = 0; k < per_file; k++) lg_function(&g, (unsigned)(fidx + k));
        if (c->src.oom) goto done;
        rc = 2;
        if (!lint_lex(c)) goto done;
        c->tokens += (uint64_t)c->ntok;
        c->pos = 0;
        while (lint_peek(c) != TK_EOF) {
            if (!lint_function(c, fidx++)) goto done;
        }
        rc = 1;
    }
    for (int k = 1; k < 8; k++) c->h = ib_mix(c->h, c->counts[k]);
    ib_result(out, c->h, (double)c->findings, (double)c->tokens, "tokens");
    rc = 0;
done:
    lint_free(c);
    free(c);
    return rc;
}

// ── sat: a CDCL solver ──────────────────────────────────────────────────

// A CNF in DIMACS style: literals ±(var+1), each clause ended by 0.
typedef struct { int nv, nc; int *lits; size_t n, cap; bool oom; } sat_cnf;

static void sat_cnf_lit(sat_cnf *f, int lit) {
    if (f->oom) return;
    if (f->n == f->cap) {
        size_t nc = f->cap ? f->cap * 2 : 4096;
        int *p = (int *)realloc(f->lits, nc * sizeof(int));
        if (!p) { f->oom = true; return; }
        f->lits = p;
        f->cap = nc;
    }
    f->lits[f->n++] = lit;
    if (lit == 0) f->nc++;
}

typedef struct { int cref, blocker; } sat_w;
typedef struct { sat_w *a; int n, cap; } sat_wl;

// Clause arena layout: [size][flags][lits…]; flags = learnt | deleted<<1 | lbd<<2.
typedef struct {
    int nv;
    int *ar;
    size_t an, acap;
    sat_wl *watch;          // watch[x]: clauses watching ¬x, visited when x becomes true
    int8_t *lv;             // per literal: 1 true, -1 false, 0 unassigned
    int *level, *reason, *trail, *tlim, *heap, *hpos, *out, *tc, *lstamp;
    uint64_t *act, inc;
    uint8_t *phase, *seen;
    int tn, qhead, nlev, hn, outn, stamp;
    int *learnts;
    int nl, lcap;
    uint64_t conflicts, props, decisions;
    bool oom;
} sat_s;

static inline bool sat_before(const sat_s *s, int a, int b) {
    return s->act[a] > s->act[b] || (s->act[a] == s->act[b] && a < b);
}

static void sat_heap_up(sat_s *s, int i) {
    int v = s->heap[i];
    while (i > 0) {
        int p = (i - 1) >> 1;
        if (!sat_before(s, v, s->heap[p])) break;
        s->heap[i] = s->heap[p];
        s->hpos[s->heap[i]] = i;
        i = p;
    }
    s->heap[i] = v;
    s->hpos[v] = i;
}

static void sat_heap_down(sat_s *s, int i) {
    int v = s->heap[i];
    for (;;) {
        int l = 2 * i + 1;
        if (l >= s->hn) break;
        int c = (l + 1 < s->hn && sat_before(s, s->heap[l + 1], s->heap[l])) ? l + 1 : l;
        if (!sat_before(s, s->heap[c], v)) break;
        s->heap[i] = s->heap[c];
        s->hpos[s->heap[i]] = i;
        i = c;
    }
    s->heap[i] = v;
    s->hpos[v] = i;
}

static void sat_heap_insert(sat_s *s, int v) {
    if (s->hpos[v] >= 0) return;
    s->heap[s->hn] = v;
    s->hpos[v] = s->hn;
    sat_heap_up(s, s->hn++);
}

static int sat_heap_pop(sat_s *s) {
    int v = s->heap[0];
    s->hpos[v] = -1;
    if (--s->hn > 0) {
        s->heap[0] = s->heap[s->hn];
        s->hpos[s->heap[0]] = 0;
        sat_heap_down(s, 0);
    }
    return v;
}

/// VSIDS bump with integer activities: the increment grows by 1/19 per
/// conflict (decay 0.95), and everything is rescaled before overflow.
static void sat_bump(sat_s *s, int v) {
    s->act[v] += s->inc;
    if (s->act[v] > (1ULL << 60)) {
        for (int i = 0; i < s->nv; i++) s->act[i] >>= 30;
        s->inc = (s->inc >> 30) + 1;
        for (int i = s->hn / 2 - 1; i >= 0; i--) sat_heap_down(s, i);
    }
    if (s->hpos[v] >= 0) sat_heap_up(s, s->hpos[v]);
}

static void sat_decay(sat_s *s) {
    s->inc += s->inc / 19;
    if (s->inc > (1ULL << 59)) {
        for (int i = 0; i < s->nv; i++) s->act[i] >>= 30;
        s->inc >>= 30;
        for (int i = s->hn / 2 - 1; i >= 0; i--) sat_heap_down(s, i);
    }
}

static void sat_watch_push(sat_s *s, int lit, int cref, int blocker) {
    sat_wl *w = &s->watch[lit];
    if (w->n == w->cap) {
        int nc = w->cap ? w->cap * 2 : 8;
        sat_w *p = (sat_w *)realloc(w->a, (size_t)nc * sizeof(sat_w));
        if (!p) { s->oom = true; return; }
        w->a = p;
        w->cap = nc;
    }
    w->a[w->n].cref = cref;
    w->a[w->n].blocker = blocker;
    w->n++;
}

static int sat_alloc(sat_s *s, const int *lits, int n, bool learnt, int lbd) {
    if (s->an + (size_t)n + 2 > s->acap) {
        size_t nc = s->acap ? s->acap * 2 : 65536;
        while (nc < s->an + (size_t)n + 2) nc *= 2;
        int *p = (int *)realloc(s->ar, nc * sizeof(int));
        if (!p) { s->oom = true; return -1; }
        s->ar = p;
        s->acap = nc;
    }
    int cr = (int)s->an;
    s->ar[cr] = n;
    s->ar[cr + 1] = (learnt ? 1 : 0) | (lbd << 2);
    memcpy(s->ar + cr + 2, lits, (size_t)n * sizeof(int));
    s->an += (size_t)n + 2;
    return cr;
}

static void sat_attach(sat_s *s, int cr) {
    int *L = s->ar + cr + 2;
    sat_watch_push(s, L[0] ^ 1, cr, L[1]);
    sat_watch_push(s, L[1] ^ 1, cr, L[0]);
}

static inline void sat_assign(sat_s *s, int lit, int reason) {
    int v = lit >> 1;
    s->lv[lit] = 1;
    s->lv[lit ^ 1] = -1;
    s->level[v] = s->nlev;
    s->reason[v] = reason;
    s->trail[s->tn++] = lit;
}

/// Two-watched-literal unit propagation with blockers. Returns the
/// conflicting clause or -1.
static int sat_propagate(sat_s *s) {
    while (s->qhead < s->tn) {
        int p = s->trail[s->qhead++], fl = p ^ 1;
        sat_wl *ws = &s->watch[p];
        sat_w *i = ws->a, *j = ws->a, *end = ws->a + ws->n;
        int confl = -1;
        s->props++;
        while (i < end) {
            int blk = i->blocker;
            if (s->lv[blk] == 1) { *j++ = *i++; continue; }
            int cr = i->cref;
            int *c = s->ar + cr, sz = c[0], *L = c + 2;
            if (L[0] == fl) { L[0] = L[1]; L[1] = fl; }
            i++;
            int first = L[0];
            if (first != blk && s->lv[first] == 1) {
                j->cref = cr; j->blocker = first; j++;
                continue;
            }
            int k = 2;
            for (; k < sz; k++)
                if (s->lv[L[k]] != -1) break;
            if (k < sz) {
                L[1] = L[k];
                L[k] = fl;
                sat_watch_push(s, L[1] ^ 1, cr, first);
                continue;
            }
            j->cref = cr; j->blocker = first; j++;
            if (s->lv[first] == -1) {
                confl = cr;
                s->qhead = s->tn;
                while (i < end) *j++ = *i++;
            } else {
                sat_assign(s, first, cr);
            }
        }
        ws->n = (int)(j - ws->a);
        if (confl >= 0) return confl;
    }
    return -1;
}

static void sat_cancel(sat_s *s, int lvl) {
    if (s->nlev <= lvl) return;
    for (int c = s->tn - 1; c >= s->tlim[lvl]; c--) {
        int lit = s->trail[c], v = lit >> 1;
        s->lv[lit] = s->lv[lit ^ 1] = 0;
        s->reason[v] = -1;
        s->phase[v] = (uint8_t)!(lit & 1);
        sat_heap_insert(s, v);
    }
    s->tn = s->qhead = s->tlim[lvl];
    s->nlev = lvl;
}

/// First-UIP conflict analysis with basic clause minimisation; leaves the
/// learnt clause in out[0..outn) with the asserting literal first.
static void sat_analyze(sat_s *s, int confl, int *bt, int *lbd) {
    int pathc = 0, p = -1, idx = s->tn - 1;
    s->outn = 1;
    do {
        int *c = s->ar + confl, sz = c[0], *L = c + 2;
        for (int k = (p == -1 ? 0 : 1); k < sz; k++) {
            int q = L[k], v = q >> 1;
            if (!s->seen[v] && s->level[v] > 0) {
                sat_bump(s, v);
                s->seen[v] = 1;
                if (s->level[v] >= s->nlev) pathc++;
                else s->out[s->outn++] = q;
            }
        }
        while (!s->seen[s->trail[idx] >> 1]) idx--;
        p = s->trail[idx--];
        confl = s->reason[p >> 1];
        s->seen[p >> 1] = 0;
        pathc--;
    } while (pathc > 0);
    s->out[0] = p ^ 1;
    // Drop literals implied by others already in the clause.
    int n0 = s->outn, j = 1;
    memcpy(s->tc, s->out, (size_t)n0 * sizeof(int));
    for (int i = 1; i < n0; i++) {
        int v = s->out[i] >> 1, r = s->reason[v];
        bool keep = r < 0;
        if (!keep) {
            int *c = s->ar + r, sz = c[0];
            for (int k = 1; k < sz; k++) {
                int u = c[2 + k] >> 1;
                if (!s->seen[u] && s->level[u] > 0) { keep = true; break; }
            }
        }
        if (keep) s->out[j++] = s->out[i];
    }
    s->outn = j;
    for (int i = 1; i < n0; i++) s->seen[s->tc[i] >> 1] = 0;
    // Backjump level: the highest level among the rest, moved to out[1].
    int b = 0;
    if (s->outn > 1) {
        int mi = 1;
        for (int i = 2; i < s->outn; i++)
            if (s->level[s->out[i] >> 1] > s->level[s->out[mi] >> 1]) mi = i;
        int t = s->out[1]; s->out[1] = s->out[mi]; s->out[mi] = t;
        b = s->level[s->out[1] >> 1];
    }
    *bt = b;
    s->stamp++;
    int n = 0;
    for (int i = 0; i < s->outn; i++) {
        int l = s->level[s->out[i] >> 1];
        if (s->lstamp[l] != s->stamp) { s->lstamp[l] = s->stamp; n++; }
    }
    *lbd = n;
}

static int sat_key_cmp(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return x < y ? -1 : (x > y ? 1 : 0);
}

/// At level 0: deletes the worse half of the learnt clauses (by LBD, then
/// size), drops satisfied clauses and false literals, compacts the arena
/// and rebuilds every watch list. Returns false on a level-0 conflict.
static bool sat_reduce(sat_s *s, bool drop_learnts) {
    if (drop_learnts && s->nl > 0) {
        uint64_t *keys = (uint64_t *)malloc((size_t)s->nl * sizeof(uint64_t));
        if (!keys) { s->oom = true; return true; }
        for (int i = 0; i < s->nl; i++) {
            int cr = s->learnts[i];
            uint64_t lbd = (uint64_t)(s->ar[cr + 1] >> 2), sz = (uint64_t)s->ar[cr];
            if (sz > 0xFFFF) sz = 0xFFFF;
            keys[i] = lbd << 48 | sz << 32 | (uint64_t)(uint32_t)cr;
        }
        qsort(keys, (size_t)s->nl, sizeof(uint64_t), sat_key_cmp);
        for (int i = s->nl / 2; i < s->nl; i++) {
            int cr = (int)(uint32_t)keys[i];
            if ((s->ar[cr + 1] >> 2) > 2) s->ar[cr + 1] |= 2;
        }
        free(keys);
    }
    for (int i = 0; i < s->nv; i++) s->reason[i] = -1;
    size_t w = 0, pos = 0;
    s->nl = 0;
    bool ok = true;
    while (pos < s->an) {
        int sz = s->ar[pos], fl = s->ar[pos + 1];
        size_t next = pos + 2 + (size_t)sz;
        if (!(fl & 2)) {
            int *L = s->ar + pos + 2, n = 0;
            bool sat = false;
            for (int k = 0; k < sz; k++) {
                int8_t v = s->lv[L[k]];
                if (v == 1) { sat = true; break; }
                if (v == 0) L[n++] = L[k];
            }
            if (!sat) {
                if (n == 0) ok = false;
                else if (n == 1) sat_assign(s, L[0], -1);
                else {
                    s->ar[w] = n;
                    s->ar[w + 1] = fl;
                    memmove(s->ar + w + 2, L, (size_t)n * sizeof(int));
                    if (fl & 1) s->learnts[s->nl++] = (int)w;
                    w += 2 + (size_t)n;
                }
            }
        }
        pos = next;
    }
    s->an = w;
    for (int i = 0; i < 2 * s->nv; i++) s->watch[i].n = 0;
    for (size_t p = 0; p < s->an; p += 2 + (size_t)s->ar[p]) sat_attach(s, (int)p);
    if (!ok) return false;
    return sat_propagate(s) < 0;
}

static uint64_t sat_luby(uint64_t i) {
    // The i-th element (0-based) of 1,1,2,1,1,2,4,1,1,2,1,1,2,4,8,…
    uint64_t size = 1, seq = 0;
    while (size < i + 1) { seq++; size = 2 * size + 1; }
    while (size - 1 != i) {
        size = (size - 1) >> 1;
        seq--;
        if (i >= size) i -= size;
    }
    return 1ULL << seq;
}

static void sat_free(sat_s *s) {
    if (s->watch)
        for (int i = 0; i < 2 * s->nv; i++) free(s->watch[i].a);
    free(s->watch); free(s->ar); free(s->lv); free(s->level); free(s->reason);
    free(s->trail); free(s->tlim); free(s->heap); free(s->hpos); free(s->out);
    free(s->tc); free(s->lstamp); free(s->act); free(s->phase); free(s->seen);
    free(s->learnts);
}

/// Solves `f`: 1 satisfiable (model in `model`), -1 unsatisfiable, 0 out
/// of conflict budget, -2 out of memory.
static int sat_solve(const sat_cnf *f, uint64_t budget, uint8_t *model, sat_s *s) {
    memset(s, 0, sizeof *s);
    int nv = f->nv;
    s->nv = nv;
    s->watch = (sat_wl *)calloc((size_t)2 * nv, sizeof(sat_wl));
    s->lv = (int8_t *)calloc((size_t)2 * nv, 1);
    s->level = (int *)calloc((size_t)nv, sizeof(int));
    s->reason = (int *)malloc((size_t)nv * sizeof(int));
    s->trail = (int *)malloc((size_t)nv * sizeof(int));
    s->tlim = (int *)malloc((size_t)(nv + 1) * sizeof(int));
    s->heap = (int *)malloc((size_t)nv * sizeof(int));
    s->hpos = (int *)malloc((size_t)nv * sizeof(int));
    s->out = (int *)malloc((size_t)(nv + 1) * sizeof(int));
    s->tc = (int *)malloc((size_t)(nv + 1) * sizeof(int));
    s->lstamp = (int *)calloc((size_t)nv + 1, sizeof(int));
    s->act = (uint64_t *)calloc((size_t)nv, sizeof(uint64_t));
    s->phase = (uint8_t *)calloc((size_t)nv, 1);
    s->seen = (uint8_t *)calloc((size_t)nv, 1);
    s->lcap = 1024;
    s->learnts = (int *)malloc((size_t)s->lcap * sizeof(int));
    if (!s->watch || !s->lv || !s->level || !s->reason || !s->trail || !s->tlim ||
        !s->heap || !s->hpos || !s->out || !s->tc || !s->lstamp || !s->act ||
        !s->phase || !s->seen || !s->learnts)
        return -2;
    s->inc = 1 << 20;
    for (int v = 0; v < nv; v++) { s->reason[v] = -1; s->hpos[v] = -1; }
    for (int v = 0; v < nv; v++) sat_heap_insert(s, v);

    // Load the clauses: drop duplicate literals and tautologies, assign
    // units at level 0.
    bool unsat = false;
    size_t i = 0;
    while (i < f->n) {
        int n = 0;
        bool taut = false;
        for (; f->lits[i] != 0; i++) {
            int x = f->lits[i], lit = 2 * (abs(x) - 1) + (x < 0);
            if (s->seen[lit >> 1]) {
                for (int k = 0; k < n; k++) if (s->out[k] == (lit ^ 1)) taut = true;
                bool dup = false;
                for (int k = 0; k < n; k++) if (s->out[k] == lit) dup = true;
                if (dup) continue;
            }
            s->seen[lit >> 1] = 1;
            s->out[n++] = lit;
        }
        i++;
        for (int k = 0; k < n; k++) s->seen[s->out[k] >> 1] = 0;
        if (taut) continue;
        if (n == 0) { unsat = true; continue; }
        if (n == 1) {
            if (s->lv[s->out[0]] == -1) unsat = true;
            else if (s->lv[s->out[0]] == 0) sat_assign(s, s->out[0], -1);
            continue;
        }
        int cr = sat_alloc(s, s->out, n, false, 0);
        if (cr < 0) return -2;
        sat_attach(s, cr);
    }
    if (unsat || sat_propagate(s) >= 0) return -1;

    uint64_t restarts = 0, left = 100 * sat_luby(0);
    int max_learnts = 2000 + f->nc / 3, simp_tn = -1;
    for (;;) {
        if (s->oom) return -2;
        int confl = sat_propagate(s);
        if (confl >= 0) {
            s->conflicts++;
            if (s->nlev == 0) return -1;
            int bt, lbd;
            sat_analyze(s, confl, &bt, &lbd);
            sat_cancel(s, bt);
            if (s->outn == 1) {
                sat_assign(s, s->out[0], -1);
            } else {
                int cr = sat_alloc(s, s->out, s->outn, true, lbd);
                if (cr < 0) return -2;
                if (s->nl == s->lcap) {
                    int *p = (int *)realloc(s->learnts, (size_t)s->lcap * 2 * sizeof(int));
                    if (!p) return -2;
                    s->learnts = p;
                    s->lcap *= 2;
                }
                s->learnts[s->nl++] = cr;
                sat_attach(s, cr);
                sat_assign(s, s->out[0], cr);
            }
            sat_decay(s);
            if (s->conflicts >= budget) return 0;
            if (--left == 0) {
                sat_cancel(s, 0);
                left = 100 * sat_luby(++restarts);
                bool drop = s->nl >= max_learnts;
                if (drop) max_learnts += max_learnts / 10;
                if ((drop || s->tn != simp_tn) && !sat_reduce(s, drop)) return -1;
                simp_tn = s->tn;
            }
        } else {
            int v = -1;
            while (s->hn > 0) {
                int x = sat_heap_pop(s);
                if (s->lv[2 * x] == 0) { v = x; break; }
            }
            if (v < 0) {
                for (int k = 0; k < nv; k++) model[k] = s->lv[2 * k] == 1;
                return 1;
            }
            s->decisions++;
            s->tlim[s->nlev++] = s->tn;
            sat_assign(s, 2 * v + (s->phase[v] ? 0 : 1), -1);
        }
    }
}

static bool sat_check_model(const sat_cnf *f, const uint8_t *model) {
    size_t i = 0;
    while (i < f->n) {
        bool ok = false;
        for (; f->lits[i] != 0; i++) {
            int x = f->lits[i];
            if ((x > 0) == (model[abs(x) - 1] != 0)) ok = true;
        }
        i++;
        if (!ok) return false;
    }
    return true;
}

static void sat_gen_random(sat_cnf *f, ib_rng *r, int n, int m) {
    f->nv = n;
    for (int c = 0; c < m; c++) {
        int v[3];
        for (int k = 0; k < 3; k++) {
            bool dup;
            do {
                v[k] = (int)ib_below(r, (uint32_t)n);
                dup = false;
                for (int q = 0; q < k; q++) if (v[q] == v[k]) dup = true;
            } while (dup);
            sat_cnf_lit(f, ib_chance(r, 1, 2) ? v[k] + 1 : -(v[k] + 1));
        }
        sat_cnf_lit(f, 0);
    }
}

/// Pigeonhole: `holes`+1 pigeons into `holes` holes (unsatisfiable).
static void sat_gen_php(sat_cnf *f, int holes) {
    int p = holes + 1;
    f->nv = p * holes;
    for (int i = 0; i < p; i++) {
        for (int j = 0; j < holes; j++) sat_cnf_lit(f, i * holes + j + 1);
        sat_cnf_lit(f, 0);
    }
    for (int j = 0; j < holes; j++)
        for (int a = 0; a < p; a++)
            for (int b = a + 1; b < p; b++) {
                sat_cnf_lit(f, -(a * holes + j + 1));
                sat_cnf_lit(f, -(b * holes + j + 1));
                sat_cnf_lit(f, 0);
            }
}

/// k-colouring of a random graph with n vertices and m edges.
static void sat_gen_colour(sat_cnf *f, ib_rng *r, int n, int m, int k) {
    f->nv = n * k;
    for (int v = 0; v < n; v++) {
        for (int c = 0; c < k; c++) sat_cnf_lit(f, v * k + c + 1);
        sat_cnf_lit(f, 0);
        for (int a = 0; a < k; a++)
            for (int b = a + 1; b < k; b++) {
                sat_cnf_lit(f, -(v * k + a + 1));
                sat_cnf_lit(f, -(v * k + b + 1));
                sat_cnf_lit(f, 0);
            }
    }
    for (int e = 0; e < m; e++) {
        int a = (int)ib_below(r, (uint32_t)n), b = (int)ib_below(r, (uint32_t)n);
        if (a == b) continue;
        for (int c = 0; c < k; c++) {
            sat_cnf_lit(f, -(a * k + c + 1));
            sat_cnf_lit(f, -(b * k + c + 1));
            sat_cnf_lit(f, 0);
        }
    }
}

/// A CDCL SAT solver, the class of the logic-synthesis and formal-
/// verification engines (abc, MiniSat-style): two watched literals with
/// blockers, first-UIP learning with clause minimisation, integer VSIDS
/// on a binary heap, phase saving, Luby restarts and LBD-based learnt-
/// clause deletion with arena compaction. Instances: random 3-SAT at the
/// phase transition (clause/variable ratio 4.26), a pigeonhole formula
/// and random-graph 3- and 4-colouring near their thresholds. Every model
/// is checked against the original clauses. Size 1 is 8 random instances
/// of ~170 variables, PHP(8,7) and 4 colourings; size 2 is 11 random
/// instances of ~200 variables, PHP(9,8) and 6 colourings; size 3 is 24
/// of ~220, PHP(9,8) and 8 colourings. The checksum covers each answer,
/// model and conflict/decision/propagation count.
int cbk_sat(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int nrand_t[4] = { 0, 8, 11, 24 };
    static const int rvars_t[4] = { 0, 165, 195, 210 };
    static const int php_t[4] = { 0, 7, 8, 8 };
    static const int ncol_t[4] = { 0, 4, 6, 8 };
    static const int cv3_t[4] = { 0, 400, 500, 550 };
    static const int cv4_t[4] = { 0, 150, 200, 250 };
    ib_rng r;
    ib_seed(&r, 0x5A7C0DEULL + (uint64_t)size);
    uint64_t h = IB_FNV_OFFSET, work = 0;
    int nsat = 0, total = nrand_t[size] + 1 + ncol_t[size];
    sat_s *s = (sat_s *)malloc(sizeof(sat_s));
    if (!s) return 1;
    for (int inst = 0; inst < total; inst++) {
        sat_cnf f;
        memset(&f, 0, sizeof f);
        if (inst < nrand_t[size]) {
            int n = rvars_t[size] + 5 * (inst % 4);
            sat_gen_random(&f, &r, n, n * 426 / 100);
        } else if (inst == nrand_t[size]) {
            sat_gen_php(&f, php_t[size]);
        } else if (inst & 1) {
            int n = cv3_t[size];
            sat_gen_colour(&f, &r, n, n * 220 / 100, 3);
        } else {
            int n = cv4_t[size];
            sat_gen_colour(&f, &r, n, n * 410 / 100, 4);
        }
        uint8_t *model = f.oom ? NULL : (uint8_t *)calloc((size_t)f.nv, 1);
        if (!model) { free(f.lits); free(s); return 1; }
        int res = sat_solve(&f, 2000000, model, s);
        bool good = res != -2 && (res != 1 || sat_check_model(&f, model));
        h = ib_mix(h, (uint64_t)(int64_t)res);
        h = ib_mix(h, s->conflicts);
        h = ib_mix(h, s->decisions);
        h = ib_mix(h, s->props);
        if (res == 1) {
            nsat++;
            h = ib_mix_bytes(h, model, (size_t)f.nv);
        }
        work += s->props;
        sat_free(s);
        free(model);
        free(f.lits);
        if (!good) { free(s); return 2; }
    }
    free(s);
    ib_result(out, h, (double)nsat, (double)work, "propagations");
    return 0;
}

// ── placeroute: annealing placement and negotiated-congestion routing ──

/// e^-x for x >= 0 from plain IEEE arithmetic (no libm), so annealing
/// decisions are identical wherever the code runs.
static double ib_exp_neg(double x) {
    if (x > 700.0) return 0.0;
    int n = (int)(x * 1.4426950408889634);
    double r = x - (double)n * 0.6931471805599453;   // in [0, ln 2) (+ rounding)
    double t = 1.0, s = 1.0;
    for (int k = 1; k <= 14; k++) {
        t *= -r / (double)k;
        s += t;
    }
    return ldexp(s, -n);
}

typedef struct {
    int W, H, ncell, nnet;
    int *noff, *npin;        // net -> pin cells (CSR)
    int *coff, *cnet;        // cell -> nets (CSR)
    int *pos, *at;           // cell -> site, site -> cell or -1
    int *ncost;              // per-net half-perimeter wirelength
    int *stamp, st;
    int *aff, *affc;         // nets touched by the current move, their new costs
    int64_t cost;
} pr_ctx;

static int pr_hpwl(const pr_ctx *p, int n) {
    int b = p->noff[n], e = p->noff[n + 1];
    if (e - b < 2) return 0;
    int s = p->pos[p->npin[b]];
    int x0 = s % p->W, x1 = x0, y0 = s / p->W, y1 = y0;
    for (int k = b + 1; k < e; k++) {
        s = p->pos[p->npin[k]];
        int x = s % p->W, y = s / p->W;
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
    }
    return (x1 - x0) + (y1 - y0);
}

/// Proposes swapping cell `a` into site `t` (with whatever is there);
/// returns the cost change and leaves the swap applied.
static int pr_try(pr_ctx *p, int a, int t, int *naff) {
    int sa = p->pos[a], b = p->at[t];
    p->pos[a] = t;
    if (b >= 0) p->pos[b] = sa;
    p->st++;
    int delta = 0, n = 0;
    for (int pass = 0; pass < 2; pass++) {
        int c = pass ? b : a;
        if (c < 0) continue;
        for (int k = p->coff[c]; k < p->coff[c + 1]; k++) {
            int net = p->cnet[k];
            if (p->stamp[net] == p->st) continue;
            p->stamp[net] = p->st;
            int nc = pr_hpwl(p, net);
            p->aff[n] = net;
            p->affc[n] = nc;
            n++;
            delta += nc - p->ncost[net];
        }
    }
    *naff = n;
    return delta;
}

static void pr_commit(pr_ctx *p, int a, int t, int sa, int naff, int delta) {
    int b = p->at[t];
    p->at[t] = a;
    p->at[sa] = b;
    for (int k = 0; k < naff; k++) p->ncost[p->aff[k]] = p->affc[k];
    p->cost += delta;
}

static void pr_undo(pr_ctx *p, int a, int t, int sa) {
    int b = p->at[t];
    p->pos[a] = sa;
    if (b >= 0) p->pos[b] = t;
}

/// One move: a random cell to a random site within `rl` of it.
static bool pr_move(pr_ctx *p, ib_rng *r, int rl, double T, int *delta_out) {
    int a = (int)ib_below(r, (uint32_t)p->ncell), sa = p->pos[a];
    int x = sa % p->W, y = sa / p->W;
    int xl = x - rl < 0 ? 0 : x - rl, xh = x + rl >= p->W ? p->W - 1 : x + rl;
    int yl = y - rl < 0 ? 0 : y - rl, yh = y + rl >= p->H ? p->H - 1 : y + rl;
    int t = (yl + (int)ib_below(r, (uint32_t)(yh - yl + 1))) * p->W +
            xl + (int)ib_below(r, (uint32_t)(xh - xl + 1));
    if (t == sa) { *delta_out = 0; return false; }
    int naff, d = pr_try(p, a, t, &naff);
    bool ok = d <= 0;
    if (!ok && T > 0) {
        double u = (double)(ib_next(r) >> 11) * (1.0 / 9007199254740992.0);
        ok = u < ib_exp_neg((double)d / T);
    }
    if (ok) pr_commit(p, a, t, sa, naff, d);
    else pr_undo(p, a, t, sa);
    *delta_out = ok ? d : 0;
    return ok;
}

static int pr_icbrt(int n) {
    int c = 1;
    while ((int64_t)(c + 1) * (c + 1) * (c + 1) <= n) c++;
    return c;
}

// Routing state.
typedef struct {
    int W, H, NE, HE, cap;
    int *occ, *hist;
    int64_t pres;
    uint64_t *heap;
    int hn, hcap;
    int64_t *dist;
    int *prev, *vst, *tst, vstamp, tstamp;     // prev: edge into a node
    int **nedge, *nedge_n, *nedge_cap;         // per-net routed edges
    uint64_t expansions;
    bool oom;
} pr_route;

static inline int pr_edge(const pr_route *g, int a, int b) {
    // a, b adjacent sites
    int lo = a < b ? a : b, hi = a < b ? b : a;
    if (hi - lo == 1) return (lo / g->W) * (g->W - 1) + lo % g->W;
    return g->HE + lo;
}

static inline int64_t pr_ecost(const pr_route *g, int e) {
    int over = g->occ[e] + 1 - g->cap;
    int64_t c = 16 + 8 * (int64_t)g->hist[e];
    if (over > 0) c *= 1 + g->pres * over;
    return c;
}

static void pr_hpush(pr_route *g, uint64_t key) {
    if (g->hn == g->hcap) {
        int nc = g->hcap ? 2 * g->hcap : 1024;
        uint64_t *p = (uint64_t *)realloc(g->heap, (size_t)nc * sizeof(uint64_t));
        if (!p) { g->oom = true; return; }
        g->heap = p;
        g->hcap = nc;
    }
    int i = g->hn++;
    while (i > 0) {
        int q = (i - 1) >> 1;
        if (g->heap[q] <= key) break;
        g->heap[i] = g->heap[q];
        i = q;
    }
    g->heap[i] = key;
}

static uint64_t pr_hpop(pr_route *g) {
    uint64_t top = g->heap[0], last = g->heap[--g->hn];
    int i = 0;
    for (;;) {
        int l = 2 * i + 1;
        if (l >= g->hn) break;
        int c = (l + 1 < g->hn && g->heap[l + 1] < g->heap[l]) ? l + 1 : l;
        if (g->heap[c] >= last) break;
        g->heap[i] = g->heap[c];
        i = c;
    }
    if (g->hn > 0) g->heap[i] = last;
    return top;
}

static bool pr_add_edge(pr_route *g, int net, int e) {
    if (g->nedge_n[net] == g->nedge_cap[net]) {
        int nc = g->nedge_cap[net] ? 2 * g->nedge_cap[net] : 8;
        int *p = (int *)realloc(g->nedge[net], (size_t)nc * sizeof(int));
        if (!p) { g->oom = true; return false; }
        g->nedge[net] = p;
        g->nedge_cap[net] = nc;
    }
    g->nedge[net][g->nedge_n[net]++] = e;
    g->occ[e]++;
    return true;
}

/// Routes one net as a Steiner-ish tree: A* from the whole tree built so
/// far to each sink in turn (nearest first), under congestion costs.
static bool pr_route_net(pr_route *g, const pr_ctx *p, int net, int *tree, int *sinks) {
    int b = p->noff[net], e = p->noff[net + 1];
    if (e - b < 2) return true;
    int W = g->W, nt = 0, ns = 0;
    int src = p->pos[p->npin[b]], sx = src % W, sy = src / W;
    g->tstamp++;
    g->tst[src] = g->tstamp;
    tree[nt++] = src;
    for (int k = b + 1; k < e; k++) {
        int s = p->pos[p->npin[k]];
        int d = abs(s % W - sx) + abs(s / W - sy);
        int i = ns++;
        while (i > 0) {
            int q = sinks[i - 1];
            int dq = abs(q % W - sx) + abs(q / W - sy);
            if (dq < d || (dq == d && q < s)) break;
            sinks[i] = q;
            i--;
        }
        sinks[i] = s;
    }
    for (int k = 0; k < ns; k++) {
        int t = sinks[k];
        if (g->tst[t] == g->tstamp) continue;
        int tx = t % W, ty = t / W;
        g->vstamp++;
        g->hn = 0;
        for (int i = 0; i < nt; i++) {
            int v = tree[i];
            g->vst[v] = g->vstamp;
            g->dist[v] = 0;
            g->prev[v] = -1;
            int64_t hcost = 16 * (int64_t)(abs(v % W - tx) + abs(v / W - ty));
            pr_hpush(g, (uint64_t)hcost << 24 | (uint64_t)v);
        }
        bool found = false;
        while (g->hn > 0 && !g->oom) {
            uint64_t key = pr_hpop(g);
            int v = (int)(key & 0xFFFFFF);
            int64_t f = (int64_t)(key >> 24);
            int vx = v % W, vy = v / W;
            int64_t hv = 16 * (int64_t)(abs(vx - tx) + abs(vy - ty));
            if (f - hv > g->dist[v]) continue;          // stale entry
            g->expansions++;
            if (v == t) { found = true; break; }
            int nb[4], nn = 0;
            if (vx > 0) nb[nn++] = v - 1;
            if (vx + 1 < W) nb[nn++] = v + 1;
            if (vy > 0) nb[nn++] = v - W;
            if (vy + 1 < g->H) nb[nn++] = v + W;
            for (int q = 0; q < nn; q++) {
                int w = nb[q], ed = pr_edge(g, v, w);
                int64_t nd = g->dist[v] + pr_ecost(g, ed);
                if (g->vst[w] != g->vstamp || nd < g->dist[w]) {
                    g->vst[w] = g->vstamp;
                    g->dist[w] = nd;
                    g->prev[w] = ed;
                    int64_t hw = 16 * (int64_t)(abs(w % W - tx) + abs(w / W - ty));
                    pr_hpush(g, (uint64_t)(nd + hw) << 24 | (uint64_t)w);
                }
            }
        }
        if (!found) return false;
        // Walk back to the tree, claiming the edges.
        int v = t;
        while (g->tst[v] != g->tstamp) {
            int ed = g->prev[v];
            g->tst[v] = g->tstamp;
            tree[nt++] = v;
            if (!pr_add_edge(g, net, ed)) return false;
            int a, c;
            if (ed < g->HE) { a = (ed / (W - 1)) * W + ed % (W - 1); c = a + 1; }
            else { a = ed - g->HE; c = a + W; }
            v = (v == a) ? c : a;
        }
    }
    return true;
}

static void pr_ripup(pr_route *g, int net) {
    for (int k = 0; k < g->nedge_n[net]; k++) g->occ[g->nedge[net][k]]--;
    g->nedge_n[net] = 0;
}

static int64_t pr_overflow(const pr_route *g) {
    int64_t o = 0;
    for (int e = 0; e < g->NE; e++)
        if (g->occ[e] > g->cap) o += g->occ[e] - g->cap;
    return o;
}

/// FPGA-style place and route, the class of VPR: a generated netlist
/// (each cell drives one net with 1–8 sinks, mostly near it in a hidden
/// reference layout) is placed on a W×H grid by simulated annealing
/// (VPR's schedule: temperature from the initial cost spread, cooling by
/// acceptance rate, a shrinking move window, half-perimeter wirelength
/// cost, incremental net updates), then routed on the grid graph with
/// A* maze routing per net and PathFinder negotiated congestion (present
/// and history costs; every pass rips up and reroutes every net until no
/// edge is over its capacity, which is set at ~1.8× the average demand).
/// Size 1 is a 36×36 grid (1.1k cells); size 2 70×70; size 3 112×112. The
/// checksum covers the annealing trajectory, the final placement cost,
/// every routed net length and the overflow after each routing pass.
int cbk_placeroute(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int side_t[4] = { 0, 36, 70, 112 };
    static const int inner_t[4] = { 0, 2, 2, 2 };
    int W = side_t[size], H = W, nsite = W * H;
    pr_ctx p;
    pr_route g;
    memset(&p, 0, sizeof p);
    memset(&g, 0, sizeof g);
    p.W = W; p.H = H;
    p.ncell = nsite * 85 / 100;
    p.nnet = p.ncell;
    int ncell = p.ncell, nnet = p.nnet, rc = 1;
    int maxpins = nnet * 9;
    int *hidden_at = (int *)malloc((size_t)nsite * sizeof(int));
    int *hidden = (int *)malloc((size_t)ncell * sizeof(int));
    int *tree = (int *)malloc((size_t)nsite * sizeof(int));
    int *sinks = (int *)malloc(16 * sizeof(int));
    p.noff = (int *)malloc((size_t)(nnet + 1) * sizeof(int));
    p.npin = (int *)malloc((size_t)maxpins * sizeof(int));
    p.coff = (int *)calloc((size_t)ncell + 1, sizeof(int));
    p.cnet = (int *)malloc((size_t)maxpins * sizeof(int));
    p.pos = (int *)malloc((size_t)ncell * sizeof(int));
    p.at = (int *)malloc((size_t)nsite * sizeof(int));
    p.ncost = (int *)malloc((size_t)nnet * sizeof(int));
    p.stamp = (int *)calloc((size_t)nnet, sizeof(int));
    p.aff = (int *)malloc((size_t)nnet * sizeof(int));
    p.affc = (int *)malloc((size_t)nnet * sizeof(int));
    g.W = W; g.H = H;
    g.HE = (W - 1) * H;
    g.NE = g.HE + W * (H - 1);
    g.occ = (int *)calloc((size_t)g.NE, sizeof(int));
    g.hist = (int *)calloc((size_t)g.NE, sizeof(int));
    g.dist = (int64_t *)malloc((size_t)nsite * sizeof(int64_t));
    g.prev = (int *)malloc((size_t)nsite * sizeof(int));
    g.vst = (int *)calloc((size_t)nsite, sizeof(int));
    g.tst = (int *)calloc((size_t)nsite, sizeof(int));
    g.nedge = (int **)calloc((size_t)nnet, sizeof(int *));
    g.nedge_n = (int *)calloc((size_t)nnet, sizeof(int));
    g.nedge_cap = (int *)calloc((size_t)nnet, sizeof(int));
    ib_rng r;
    ib_seed(&r, 0x9CA7E5ULL + (uint64_t)size);
    uint64_t h = IB_FNV_OFFSET, moves = 0;
    if (!hidden_at || !hidden || !tree || !sinks || !p.noff || !p.npin || !p.coff ||
        !p.cnet || !p.pos || !p.at || !p.ncost || !p.stamp || !p.aff || !p.affc ||
        !g.occ || !g.hist || !g.dist || !g.prev || !g.vst || !g.tst || !g.nedge ||
        !g.nedge_n || !g.nedge_cap)
        goto done;

    // The netlist: a hidden reference layout gives it locality.
    for (int s = 0; s < nsite; s++) hidden_at[s] = s;
    for (int s = nsite - 1; s > 0; s--) {
        int j = (int)ib_below(&r, (uint32_t)s + 1), t = hidden_at[s];
        hidden_at[s] = hidden_at[j]; hidden_at[j] = t;
    }
    for (int s = 0; s < nsite; s++) {
        int c = hidden_at[s];
        hidden_at[s] = c < ncell ? c : -1;
        if (c < ncell) hidden[c] = s;
    }
    int npins = 0;
    for (int n = 0; n < nnet; n++) {
        p.noff[n] = npins;
        p.npin[npins++] = n;            // cell n drives net n
        uint32_t u = ib_below(&r, 100);
        int fan = u < 40 ? 1 : u < 65 ? 2 : u < 80 ? 3 : u < 90 ? 4 : 5 + (int)ib_below(&r, 4);
        int hs = hidden[n], hx = hs % W, hy = hs / W;
        for (int f = 0; f < fan; f++) {
            for (int tries = 0; tries < 12; tries++) {
                int s;
                if (ib_chance(&r, 1, 12)) s = (int)ib_below(&r, (uint32_t)nsite);
                else {
                    int x = hx + ib_range(&r, -3, 3), y = hy + ib_range(&r, -3, 3);
                    if (x < 0 || x >= W || y < 0 || y >= H) continue;
                    s = y * W + x;
                }
                int c = hidden_at[s];
                if (c < 0) continue;
                bool dup = false;
                for (int k = p.noff[n]; k < npins; k++) if (p.npin[k] == c) dup = true;
                if (dup) continue;
                p.npin[npins++] = c;
                break;
            }
        }
    }
    p.noff[nnet] = npins;
    for (int k = 0; k < npins; k++) p.coff[p.npin[k] + 1]++;
    for (int c = 0; c < ncell; c++) p.coff[c + 1] += p.coff[c];
    {
        int *fill = hidden;   // reuse as a cursor array
        for (int c = 0; c < ncell; c++) fill[c] = p.coff[c];
        for (int n = 0; n < nnet; n++)
            for (int k = p.noff[n]; k < p.noff[n + 1]; k++) p.cnet[fill[p.npin[k]]++] = n;
    }

    // Random initial placement.
    for (int s = 0; s < nsite; s++) p.at[s] = s < ncell ? s : -1;
    for (int s = nsite - 1; s > 0; s--) {
        int j = (int)ib_below(&r, (uint32_t)s + 1), t = p.at[s];
        p.at[s] = p.at[j]; p.at[j] = t;
    }
    for (int s = 0; s < nsite; s++) if (p.at[s] >= 0) p.pos[p.at[s]] = s;
    for (int n = 0; n < nnet; n++) { p.ncost[n] = pr_hpwl(&p, n); p.cost += p.ncost[n]; }

    // Annealing. Starting temperature: 20 × the spread of the cost over
    // a burst of accepted random moves.
    double sum = 0, sum2 = 0;
    for (int k = 0; k < ncell; k++) {
        int d;
        pr_move(&p, &r, W, 1e300, &d);
        sum += (double)p.cost;
        sum2 += (double)p.cost * (double)p.cost;
    }
    moves += (uint64_t)ncell;
    double mean = sum / ncell, var = sum2 / ncell - mean * mean;
    double T = 20.0 * sqrt(var > 0 ? var : 1.0), rlim = W;
    int per_T = inner_t[size] * ncell * pr_icbrt(ncell) / 2;
    for (int step = 0; step < 400; step++) {
        int acc = 0, d;
        for (int k = 0; k < per_T; k++) acc += pr_move(&p, &r, (int)rlim, T, &d);
        moves += (uint64_t)per_T;
        double rate = (double)acc / per_T;
        T *= rate > 0.96 ? 0.5 : rate > 0.8 ? 0.9 : rate > 0.15 ? 0.95 : 0.8;
        rlim *= 1.0 - 0.44 + rate;
        if (rlim < 1) rlim = 1;
        if (rlim > W) rlim = W;
        h = ib_mix(h, (uint64_t)p.cost);
        if (T < 0.005 * (double)p.cost / nnet) break;
    }
    for (int k = 0; k < per_T; k++) { int d; pr_move(&p, &r, 1, 0.0, &d); }   // quench
    moves += (uint64_t)per_T;
    int64_t check = 0;
    for (int n = 0; n < nnet; n++) check += pr_hpwl(&p, n);
    if (check != p.cost) { rc = 3; goto done; }
    h = ib_mix(h, (uint64_t)p.cost);

    // Routing with negotiated congestion.
    // Channel width: about 1.8× the average demand the placement implies,
    // tight enough that the first pass overflows and negotiation is needed.
    g.cap = 1 + (int)(p.cost * 9 / ((int64_t)g.NE * 5));
    g.pres = 1;
    int64_t over = 0;
    int iter;
    for (iter = 0; iter < 40; iter++) {
        for (int n = 0; n < nnet; n++) {
            pr_ripup(&g, n);
            if (!pr_route_net(&g, &p, n, tree, sinks)) { rc = g.oom ? 1 : 4; goto done; }
        }
        over = pr_overflow(&g);
        h = ib_mix(h, (uint64_t)over);
        if (over == 0) break;
        for (int e = 0; e < g.NE; e++)
            if (g.occ[e] > g.cap) g.hist[e] += g.occ[e] - g.cap;
        g.pres = g.pres * 2 > 1000 ? 1000 : g.pres * 2;
    }
    int64_t wl = 0;
    for (int n = 0; n < nnet; n++) {
        wl += g.nedge_n[n];
        h = ib_mix(h, (uint64_t)g.nedge_n[n]);
    }
    h = ib_mix(h, (uint64_t)iter);
    h = ib_mix(h, (uint64_t)wl);
    ib_result(out, h, (double)wl, (double)(moves + g.expansions), "moves+expansions");
    rc = 0;
done:
    if (g.nedge)
        for (int n = 0; n < nnet; n++) free(g.nedge[n]);
    free(hidden_at); free(hidden); free(tree); free(sinks);
    free(p.noff); free(p.npin); free(p.coff); free(p.cnet); free(p.pos); free(p.at);
    free(p.ncost); free(p.stamp); free(p.aff); free(p.affc);
    free(g.occ); free(g.hist); free(g.dist); free(g.prev); free(g.vst); free(g.tst);
    free(g.nedge); free(g.nedge_n); free(g.nedge_cap); free(g.heap);
    return rc;
}

// ── archsim: an out-of-order core model with TAGE and two cache levels ─

enum {
    AS_ADD, AS_SUB, AS_ADDI, AS_AND, AS_ANDI, AS_XOR, AS_SHLI, AS_SHRI, AS_MUL,
    AS_LD, AS_ST, AS_BEQ, AS_BNE, AS_BLT, AS_JMP, AS_HALT,
};

typedef struct { uint8_t op, rd, rs1, rs2; int32_t imm; } as_insn;

// Set-associative cache with LRU by access stamps and dirty bits.
typedef struct {
    uint64_t *tag;          // line address + 1 (0 = invalid)
    uint64_t *stamp;
    uint8_t *dirty;
    int sets, ways;
    uint64_t hits, misses, writebacks;
} as_cache;

static bool as_cache_init(as_cache *c, int sets, int ways) {
    memset(c, 0, sizeof *c);
    c->sets = sets;
    c->ways = ways;
    c->tag = (uint64_t *)calloc((size_t)sets * ways, sizeof(uint64_t));
    c->stamp = (uint64_t *)calloc((size_t)sets * ways, sizeof(uint64_t));
    c->dirty = (uint8_t *)calloc((size_t)sets * ways, 1);
    return c->tag && c->stamp && c->dirty;
}

static void as_cache_free(as_cache *c) {
    free(c->tag); free(c->stamp); free(c->dirty);
}

/// Looks up `line`; on a miss installs it, evicting the LRU way. Returns
/// true on a hit; `*victim` gets the evicted dirty line + 1 (or 0).
static bool as_cache_access(as_cache *c, uint64_t line, uint64_t now, bool write,
                            uint64_t *victim) {
    size_t base = (size_t)(line & (uint64_t)(c->sets - 1)) * c->ways;
    uint64_t key = line + 1;
    *victim = 0;
    for (int w = 0; w < c->ways; w++) {
        if (c->tag[base + w] == key) {
            c->stamp[base + w] = now;
            if (write) c->dirty[base + w] = 1;
            c->hits++;
            return true;
        }
    }
    c->misses++;
    size_t v = base;
    for (int w = 0; w < c->ways; w++) {
        if (c->tag[base + w] == 0) { v = base + w; break; }
        if (c->stamp[base + w] < c->stamp[v]) v = base + w;
    }
    if (c->tag[v] && c->dirty[v]) { *victim = c->tag[v]; c->writebacks++; }
    c->tag[v] = key;
    c->stamp[v] = now;
    c->dirty[v] = write;
    return false;
}

// TAGE-lite: a bimodal base and four tagged tables on geometric history
// lengths, with folded-history indexing.
#define AS_TG 4
#define AS_TG_BITS 10
#define AS_TAG_BITS 9
#define AS_HBUF 256
static const int as_hlen[AS_TG] = { 5, 15, 44, 130 };

typedef struct { uint16_t tag; int8_t ctr; uint8_t u; } as_tge;

typedef struct {
    uint8_t bim[4096];
    as_tge t[AS_TG][1 << AS_TG_BITS];
    uint8_t hist[AS_HBUF];
    int hptr;
    uint32_t fi[AS_TG], ft1[AS_TG], ft2[AS_TG];
    int idx[AS_TG], tg[AS_TG], provider, alt;
    bool pred, altpred;
    uint64_t updates;
} as_tage;

static void as_fold(uint32_t *comp, int clen, int hlen, int newbit, int oldbit) {
    uint32_t c = (*comp << 1) | (uint32_t)newbit;
    c ^= (uint32_t)oldbit << (hlen % clen);
    c ^= c >> clen;
    *comp = c & ((1u << clen) - 1);
}

static bool as_tage_predict(as_tage *p, uint32_t pc) {
    p->provider = p->alt = -1;
    for (int i = 0; i < AS_TG; i++) {
        p->idx[i] = (int)((pc ^ (pc >> (AS_TG_BITS - i)) ^ p->fi[i]) & ((1u << AS_TG_BITS) - 1));
        p->tg[i] = (int)((pc ^ p->ft1[i] ^ (p->ft2[i] << 1)) & ((1u << AS_TAG_BITS) - 1));
    }
    for (int i = AS_TG - 1; i >= 0; i--) {
        if (p->t[i][p->idx[i]].tag == p->tg[i]) {
            if (p->provider < 0) p->provider = i;
            else { p->alt = i; break; }
        }
    }
    bool base = p->bim[pc & 4095] >= 2;
    p->altpred = p->alt >= 0 ? p->t[p->alt][p->idx[p->alt]].ctr >= 0 : base;
    p->pred = p->provider >= 0 ? p->t[p->provider][p->idx[p->provider]].ctr >= 0 : base;
    return p->pred;
}

static void as_tage_update(as_tage *p, uint32_t pc, bool taken) {
    int prov = p->provider;
    if (prov >= 0) {
        as_tge *e = &p->t[prov][p->idx[prov]];
        if (p->pred != p->altpred) {
            if (p->pred == taken) { if (e->u < 3) e->u++; }
            else if (e->u > 0) e->u--;
        }
        if (taken) { if (e->ctr < 3) e->ctr++; }
        else if (e->ctr > -4) e->ctr--;
    } else {
        uint8_t *b = &p->bim[pc & 4095];
        if (taken) { if (*b < 3) (*b)++; }
        else if (*b > 0) (*b)--;
    }
    if (p->pred != taken && prov < AS_TG - 1) {
        bool done = false;
        for (int j = prov + 1; j < AS_TG; j++) {
            as_tge *e = &p->t[j][p->idx[j]];
            if (e->u == 0) {
                e->tag = (uint16_t)p->tg[j];
                e->ctr = taken ? 0 : -1;
                done = true;
                break;
            }
        }
        if (!done)
            for (int j = prov + 1; j < AS_TG; j++)
                if (p->t[j][p->idx[j]].u > 0) p->t[j][p->idx[j]].u--;
    }
    if ((++p->updates & ((1u << 18) - 1)) == 0)
        for (int i = 0; i < AS_TG; i++)
            for (int k = 0; k < (1 << AS_TG_BITS); k++) p->t[i][k].u >>= 1;
    // Push the outcome into the global history and the folded copies.
    p->hptr = (p->hptr + 1) & (AS_HBUF - 1);
    p->hist[p->hptr] = taken;
    for (int i = 0; i < AS_TG; i++) {
        int old = p->hist[(p->hptr - as_hlen[i]) & (AS_HBUF - 1)];
        as_fold(&p->fi[i], AS_TG_BITS, as_hlen[i], taken, old);
        as_fold(&p->ft1[i], AS_TAG_BITS, as_hlen[i], taken, old);
        as_fold(&p->ft2[i], AS_TAG_BITS - 1, as_hlen[i], taken, old);
    }
}

// The core's timing state.
#define AS_ROB 192
#define AS_CAL 16384
#define AS_FETCH 4
#define AS_COMMIT 4
#define AS_FRONT 5
#define AS_REDIRECT 3
enum { AS_FU_ALU, AS_FU_MEM, AS_FU_MUL, AS_FU_BR, AS_NFU };
static const int as_fu_ports[AS_NFU] = { 4, 2, 1, 2 };

typedef struct {
    as_insn code[256];
    int ncode;
    int64_t *mem;
    uint64_t memmask;
    int64_t reg[32];
    uint64_t ready[32];
    uint64_t rob[AS_ROB];
    uint64_t cal_tag[AS_NFU][AS_CAL];
    uint8_t cal_cnt[AS_NFU][AS_CAL];
    struct { uint64_t last; int64_t stride; int conf; } pf[64];
    as_cache l1, l2;
    as_tage tage;
    uint64_t fetch, last_commit, now;
    int fetch_n, commit_n;
    uint64_t insts, branches, mispredicts, prefetches;
} as_core;

static int as_emit(as_core *c, int op, int rd, int rs1, int rs2, int32_t imm) {
    as_insn *i = &c->code[c->ncode];
    i->op = (uint8_t)op; i->rd = (uint8_t)rd; i->rs1 = (uint8_t)rs1; i->rs2 = (uint8_t)rs2;
    i->imm = imm;
    return c->ncode++;
}

static uint64_t as_issue(as_core *c, int fu, uint64_t t) {
    for (;; t++) {
        size_t s = (size_t)(t & (AS_CAL - 1));
        if (c->cal_tag[fu][s] != t) { c->cal_tag[fu][s] = t; c->cal_cnt[fu][s] = 0; }
        if (c->cal_cnt[fu][s] < as_fu_ports[fu]) { c->cal_cnt[fu][s]++; return t; }
    }
}

/// A data access through L1 and L2; returns the load-to-use latency.
static int as_mem_access(as_core *c, uint64_t word, bool write) {
    uint64_t line = word >> 3, victim;
    c->now++;
    if (as_cache_access(&c->l1, line, c->now, write, &victim)) return 4;
    if (victim) { uint64_t v2; as_cache_access(&c->l2, victim - 1, c->now, true, &v2); }
    if (as_cache_access(&c->l2, line, c->now, false, &victim)) return 16;
    return 176;
}

static void as_prefetch(as_core *c, uint32_t pc, uint64_t word) {
    int k = (int)(pc & 63);
    int64_t d = (int64_t)(word - c->pf[k].last);
    if (d == c->pf[k].stride && d != 0) { if (c->pf[k].conf < 3) c->pf[k].conf++; }
    else { c->pf[k].stride = d; c->pf[k].conf = 0; }
    c->pf[k].last = word;
    if (c->pf[k].conf >= 2) {
        uint64_t target = (word + (uint64_t)(4 * c->pf[k].stride)) & c->memmask, victim;
        // Prefetch fills go through both levels and count as accesses.
        c->now++;
        c->prefetches++;
        as_cache_access(&c->l2, target >> 3, c->now, false, &victim);
        as_cache_access(&c->l1, target >> 3, c->now, false, &victim);
        if (victim) { uint64_t v2; as_cache_access(&c->l2, victim - 1, c->now, true, &v2); }
    }
}

/// Runs the program functionally and times every instruction on the
/// out-of-order model. Returns false if it overran `limit`.
static bool as_run(as_core *c, uint64_t limit) {
    int pc = 0;
    int64_t *R = c->reg;
    while (c->insts < limit) {
        const as_insn *in = &c->code[pc];
        int next = pc + 1, fu = AS_FU_ALU, lat = 1;
        bool isbr = false, taken = false;
        uint64_t a = 0;
        switch (in->op) {
        case AS_ADD:  R[in->rd] = (int64_t)((uint64_t)R[in->rs1] + (uint64_t)R[in->rs2]); break;
        case AS_SUB:  R[in->rd] = (int64_t)((uint64_t)R[in->rs1] - (uint64_t)R[in->rs2]); break;
        case AS_ADDI: R[in->rd] = (int64_t)((uint64_t)R[in->rs1] + (uint64_t)(int64_t)in->imm); break;
        case AS_AND:  R[in->rd] = R[in->rs1] & R[in->rs2]; break;
        case AS_ANDI: R[in->rd] = R[in->rs1] & in->imm; break;
        case AS_XOR:  R[in->rd] = R[in->rs1] ^ R[in->rs2]; break;
        case AS_SHLI: R[in->rd] = (int64_t)((uint64_t)R[in->rs1] << (in->imm & 63)); break;
        case AS_SHRI: R[in->rd] = (int64_t)((uint64_t)R[in->rs1] >> (in->imm & 63)); break;
        case AS_MUL:
            R[in->rd] = (int64_t)((uint64_t)R[in->rs1] * (uint64_t)R[in->rs2]);
            fu = AS_FU_MUL; lat = 3;
            break;
        case AS_LD:
            a = ((uint64_t)R[in->rs1] + (uint64_t)(int64_t)in->imm) & c->memmask;
            R[in->rd] = c->mem[a];
            fu = AS_FU_MEM;
            lat = as_mem_access(c, a, false);
            as_prefetch(c, (uint32_t)pc, a);
            break;
        case AS_ST:
            a = ((uint64_t)R[in->rs1] + (uint64_t)(int64_t)in->imm) & c->memmask;
            c->mem[a] = R[in->rs2];
            fu = AS_FU_MEM;
            as_mem_access(c, a, true);
            break;
        case AS_BEQ: isbr = true; taken = R[in->rs1] == R[in->rs2]; break;
        case AS_BNE: isbr = true; taken = R[in->rs1] != R[in->rs2]; break;
        case AS_BLT: isbr = true; taken = R[in->rs1] < R[in->rs2]; break;
        case AS_JMP: next = in->imm; fu = AS_FU_BR; break;
        case AS_HALT: return true;
        default: return false;
        }
        R[0] = 0;
        if (isbr) { fu = AS_FU_BR; if (taken) next = in->imm; }

        // Timing: fetch, dispatch into the ROB, issue when operands and a
        // port are ready, complete, commit in order.
        if (c->fetch_n >= AS_FETCH) { c->fetch++; c->fetch_n = 0; }
        c->fetch_n++;
        uint64_t disp = c->fetch + AS_FRONT, robfree = c->rob[c->insts % AS_ROB] + 1;
        if (robfree > disp) { c->fetch = robfree - AS_FRONT; disp = robfree; }
        uint64_t rdy = disp + 1;
        if (c->ready[in->rs1] > rdy) rdy = c->ready[in->rs1];
        if ((in->op <= AS_XOR && in->op != AS_ADDI && in->op != AS_ANDI) || in->op == AS_MUL ||
            in->op == AS_ST || isbr)
            if (c->ready[in->rs2] > rdy) rdy = c->ready[in->rs2];
        uint64_t issue = as_issue(c, fu, rdy), done = issue + (uint64_t)lat;
        if (in->rd && in->op != AS_ST && !isbr && in->op != AS_JMP) c->ready[in->rd] = done;
        uint64_t cm = done + 1;
        if (cm < c->last_commit) cm = c->last_commit;
        if (cm == c->last_commit) {
            if (c->commit_n >= AS_COMMIT) { cm++; c->commit_n = 0; }
        } else {
            c->commit_n = 0;
        }
        c->commit_n++;
        c->last_commit = cm;
        c->rob[c->insts % AS_ROB] = cm;
        if (isbr) {
            c->branches++;
            bool pred = as_tage_predict(&c->tage, (uint32_t)pc);
            as_tage_update(&c->tage, (uint32_t)pc, taken);
            if (pred != taken) {
                c->mispredicts++;
                if (c->fetch < done + AS_REDIRECT) c->fetch = done + AS_REDIRECT;
                c->fetch_n = 0;
            } else if (taken) {
                c->fetch_n = AS_FETCH;           // a taken branch ends the fetch group
            }
        } else if (in->op == AS_JMP) {
            c->fetch_n = AS_FETCH;
        }
        c->insts++;
        pc = next;
    }
    return false;
}

/// Computer-architecture simulation, the class of gem5: a synthetic
/// program (a branchy array reduction, a pointer chase through a random
/// linked list, a column walk over a matrix, hash-table probing with
/// stores, a multiply chain with periodic branches, a strided update)
/// runs on a functional model of a small RISC ISA, and every dynamic
/// instruction is timed on an out-of-order core: 4-wide fetch with
/// redirect on mispredict, a 192-entry ROB, an issue calendar per port
/// class, in-order 4-wide commit; a TAGE-lite branch predictor (bimodal +
/// four tagged tables, histories 5–130); a 32 KB 8-way L1D and 1 MB
/// 16-way L2 with LRU, write-back/write-allocate, and a per-PC stride
/// prefetcher. Size 1 simulates ~13M instructions over 8 MB of simulated
/// memory; size 2 ~62M over 16 MB; size 3 ~280M over 32 MB. The checksum
/// covers cycles, instructions, cache hits/misses/write-backs, branch
/// mispredicts, prefetches and the final register file.
int cbk_archsim(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int membits_t[4] = { 0, 20, 21, 22 };
    static const int outer_t[4] = { 0, 175, 800, 3600 };
    as_core *c = (as_core *)calloc(1, sizeof(as_core));
    if (!c) return 1;
    uint64_t memw = 1ULL << membits_t[size];
    c->mem = (int64_t *)malloc(memw * sizeof(int64_t));
    if (!c->mem || !as_cache_init(&c->l1, 64, 8) || !as_cache_init(&c->l2, 1024, 16)) {
        as_cache_free(&c->l1); as_cache_free(&c->l2);
        free(c->mem); free(c);
        return 1;
    }
    c->memmask = memw - 1;
    ib_rng r;
    ib_seed(&r, 0xA5C51AULL + (uint64_t)size);

    // Memory layout (word addresses).
    const int32_t NA = 4096, MR = 64, MC = 512, CC = 8;
    const int32_t NB = 2000, ND = 2000, NE = 1000, NF = 256;
    const int32_t A_BASE = 0, M_BASE = NA;
    const int32_t T_BASE = M_BASE + MR * MC;
    const int32_t NT = (int32_t)(memw / 8);
    const int32_t L_BASE = T_BASE + NT;
    const int32_t NL = (int32_t)((memw - (uint64_t)L_BASE) / 2);
    for (uint64_t i = 0; i < memw; i++) c->mem[i] = (int64_t)(ib_next(&r) >> 1);
    for (int32_t i = 0; i < NA; i++) {
        int64_t v = (int64_t)(ib_next(&r) >> 8) & ~1LL;
        if ((i % 5 == 0) != ib_chance(&r, 1, 10)) v |= 1;
        c->mem[A_BASE + i] = v;
    }
    for (int32_t i = 0; i < NT; i++) c->mem[T_BASE + i] = (int64_t)(ib_next(&r) >> 40) - (1LL << 23);
    {
        // A random cyclic order of the list nodes (Sattolo's shuffle).
        int32_t *perm = (int32_t *)malloc((size_t)NL * sizeof(int32_t));
        if (!perm) {
            as_cache_free(&c->l1); as_cache_free(&c->l2);
            free(c->mem); free(c);
            return 1;
        }
        for (int32_t i = 0; i < NL; i++) perm[i] = i;
        for (int32_t i = NL - 1; i > 0; i--) {
            int32_t j = (int32_t)ib_below(&r, (uint32_t)i), t = perm[i];
            perm[i] = perm[j]; perm[j] = t;
        }
        for (int32_t i = 0; i < NL; i++) c->mem[L_BASE + 2 * i] = L_BASE + 2 * perm[i];
        free(perm);
    }

    // The program.
    as_emit(c, AS_ADDI, 1, 0, 0, outer_t[size]);
    as_emit(c, AS_ADDI, 8, 0, 0, L_BASE);
    as_emit(c, AS_ADDI, 22, 0, 0, 0x5BD1E995);
    as_emit(c, AS_ADDI, 23, 0, 0, 0);
    as_emit(c, AS_ADDI, 24, 0, 0, 7);
    int top = c->ncode;
    // A: branchy reduction over an array.
    as_emit(c, AS_ADDI, 2, 0, 0, A_BASE);
    as_emit(c, AS_ADDI, 3, 0, 0, NA);
    int la = as_emit(c, AS_LD, 4, 2, 0, 0);
    as_emit(c, AS_ANDI, 5, 4, 0, 1);
    int la_br = as_emit(c, AS_BEQ, 0, 5, 0, 0);
    as_emit(c, AS_ADD, 6, 6, 4, 0);
    int la_j = as_emit(c, AS_JMP, 0, 0, 0, 0);
    int la_else = as_emit(c, AS_XOR, 6, 6, 4, 0);
    as_emit(c, AS_SHRI, 5, 4, 0, 3);
    as_emit(c, AS_ADD, 6, 6, 5, 0);
    int la_next = as_emit(c, AS_ADDI, 2, 2, 0, 1);
    as_emit(c, AS_ADDI, 3, 3, 0, -1);
    as_emit(c, AS_BNE, 0, 3, 0, la);
    c->code[la_br].imm = la_else;
    c->code[la_j].imm = la_next;
    // B: pointer chase.
    as_emit(c, AS_ADDI, 10, 0, 0, NB);
    int lb = as_emit(c, AS_LD, 8, 8, 0, 0);
    as_emit(c, AS_LD, 9, 8, 0, 1);
    as_emit(c, AS_ADD, 7, 7, 9, 0);
    as_emit(c, AS_ADDI, 10, 10, 0, -1);
    as_emit(c, AS_BNE, 0, 10, 0, lb);
    // C: column walk (stride MC words), continuing where it left off.
    as_emit(c, AS_ANDI, 11, 11, 0, MC - 1);
    as_emit(c, AS_ADDI, 21, 0, 0, CC);
    int lco = as_emit(c, AS_ADDI, 13, 11, 0, M_BASE);
    as_emit(c, AS_ADDI, 12, 0, 0, MR);
    int lc = as_emit(c, AS_LD, 14, 13, 0, 0);
    as_emit(c, AS_ADD, 20, 20, 14, 0);
    as_emit(c, AS_ADDI, 13, 13, 0, MC);
    as_emit(c, AS_ADDI, 12, 12, 0, -1);
    as_emit(c, AS_BNE, 0, 12, 0, lc);
    as_emit(c, AS_ADDI, 11, 11, 0, 1);
    as_emit(c, AS_ADDI, 21, 21, 0, -1);
    as_emit(c, AS_BNE, 0, 21, 0, lco);
    // D: hash probing with conditional stores.
    as_emit(c, AS_ADDI, 16, 0, 0, ND);
    int ld = as_emit(c, AS_MUL, 15, 15, 22, 0);
    as_emit(c, AS_ADD, 15, 15, 16, 0);
    as_emit(c, AS_SHRI, 17, 15, 0, 13);
    as_emit(c, AS_ANDI, 17, 17, 0, NT - 1);
    as_emit(c, AS_ADDI, 17, 17, 0, T_BASE);
    as_emit(c, AS_LD, 18, 17, 0, 0);
    int ld_br = as_emit(c, AS_BLT, 0, 18, 23, 0);
    as_emit(c, AS_ADDI, 19, 19, 0, 1);
    as_emit(c, AS_ST, 0, 17, 16, 0);
    int ld_skip = as_emit(c, AS_ADDI, 16, 16, 0, -1);
    as_emit(c, AS_BNE, 0, 16, 0, ld);
    c->code[ld_br].imm = ld_skip;
    // E: multiply-add chain with a periodic branch.
    as_emit(c, AS_ADDI, 25, 0, 0, NE);
    int le = as_emit(c, AS_SHLI, 26, 24, 0, 1);
    as_emit(c, AS_ADD, 24, 24, 26, 0);
    as_emit(c, AS_ADD, 24, 24, 25, 0);
    as_emit(c, AS_ANDI, 26, 25, 0, 7);
    int le_br = as_emit(c, AS_BNE, 0, 26, 0, 0);
    as_emit(c, AS_XOR, 27, 27, 24, 0);
    int le_skip = as_emit(c, AS_ADDI, 25, 25, 0, -1);
    as_emit(c, AS_BNE, 0, 25, 0, le);
    c->code[le_br].imm = le_skip;
    // F: strided read-modify-write, one line per iteration.
    as_emit(c, AS_ADDI, 28, 0, 0, A_BASE);
    as_emit(c, AS_ADDI, 29, 0, 0, NF);
    int lf = as_emit(c, AS_LD, 30, 28, 0, 0);
    as_emit(c, AS_ADDI, 30, 30, 0, 3);
    as_emit(c, AS_ST, 0, 28, 30, 0);
    as_emit(c, AS_ADDI, 28, 28, 0, 8);
    as_emit(c, AS_ADDI, 29, 29, 0, -1);
    as_emit(c, AS_BNE, 0, 29, 0, lf);
    // Outer loop.
    as_emit(c, AS_ADDI, 1, 1, 0, -1);
    as_emit(c, AS_BNE, 0, 1, 0, top);
    as_emit(c, AS_HALT, 0, 0, 0, 0);

    bool ok = as_run(c, 2000000000ULL);
    uint64_t h = IB_FNV_OFFSET;
    uint64_t cycles = c->last_commit;
    h = ib_mix(h, cycles);
    h = ib_mix(h, c->insts);
    h = ib_mix(h, c->l1.hits); h = ib_mix(h, c->l1.misses); h = ib_mix(h, c->l1.writebacks);
    h = ib_mix(h, c->l2.hits); h = ib_mix(h, c->l2.misses); h = ib_mix(h, c->l2.writebacks);
    h = ib_mix(h, c->branches); h = ib_mix(h, c->mispredicts); h = ib_mix(h, c->prefetches);
    for (int i = 0; i < 32; i++) h = ib_mix(h, (uint64_t)c->reg[i]);
    double insts = (double)c->insts;
    as_cache_free(&c->l1);
    as_cache_free(&c->l2);
    free(c->mem);
    free(c);
    if (!ok) return 2;
    ib_result(out, h, (double)cycles, insts, "instructions");
    return 0;
}

// ── ntt: RNS number-theoretic transforms and a toy RLWE scheme ─────────

typedef unsigned __int128 nt_u128;
typedef __int128 nt_i128;

static inline uint64_t nt_mulhi(uint64_t a, uint64_t b) {
    return (uint64_t)(((nt_u128)a * b) >> 64);
}

static uint64_t nt_mulmod(uint64_t a, uint64_t b, uint64_t p) {
    return (uint64_t)(((nt_u128)a * b) % p);
}

static uint64_t nt_powmod(uint64_t a, uint64_t e, uint64_t p) {
    uint64_t r = 1 % p;
    a %= p;
    while (e) {
        if (e & 1) r = nt_mulmod(r, a, p);
        a = nt_mulmod(a, a, p);
        e >>= 1;
    }
    return r;
}

/// Deterministic Miller–Rabin for 64-bit n (the first 12 prime bases).
static bool nt_is_prime(uint64_t n) {
    static const uint64_t bases[12] = { 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37 };
    if (n < 2) return false;
    for (int i = 0; i < 12; i++) {
        if (n == bases[i]) return true;
        if (n % bases[i] == 0) return false;
    }
    uint64_t d = n - 1;
    int s = 0;
    while (!(d & 1)) { d >>= 1; s++; }
    for (int i = 0; i < 12; i++) {
        uint64_t x = nt_powmod(bases[i], d, n);
        if (x == 1 || x == n - 1) continue;
        bool comp = true;
        for (int k = 1; k < s; k++) {
            x = nt_mulmod(x, x, n);
            if (x == n - 1) { comp = false; break; }
        }
        if (comp) return false;
    }
    return true;
}

typedef struct {
    uint64_t p, pinv, r2;            // modulus, -p^-1 mod 2^64, 2^128 mod p
    uint64_t *psi, *psis, *ipsi, *ipsis;   // bit-reversed twiddles + Shoup companions
    uint64_t ninv, ninvs;
} nt_prime;

/// x·w mod p in [0, 2p) with Shoup's precomputed quotient ws.
static inline uint64_t nt_shoup(uint64_t x, uint64_t w, uint64_t ws, uint64_t p) {
    return x * w - nt_mulhi(x, ws) * p;
}

static inline uint64_t nt_shoup_pre(uint64_t w, uint64_t p) {
    return (uint64_t)(((nt_u128)w << 64) / p);
}

/// Montgomery product a·b·2^-64 mod p.
static inline uint64_t nt_mont(uint64_t a, uint64_t b, uint64_t p, uint64_t pinv) {
    nt_u128 t = (nt_u128)a * b;
    uint64_t m = (uint64_t)t * pinv;
    uint64_t r = (uint64_t)((t + (nt_u128)m * p) >> 64);
    return r >= p ? r - p : r;
}

/// a·b mod p for operands in normal form (two Montgomery steps).
static inline uint64_t nt_mul(uint64_t a, uint64_t b, const nt_prime *P) {
    return nt_mont(nt_mont(a, b, P->p, P->pinv), P->r2, P->p, P->pinv);
}

static bool nt_prime_init(nt_prime *P, uint64_t p, int n, int logn) {
    memset(P, 0, sizeof *P);
    P->p = p;
    uint64_t inv = p;
    for (int i = 0; i < 6; i++) inv *= 2 - p * inv;
    P->pinv = (uint64_t)0 - inv;
    uint64_t rmod = ((uint64_t)0 - p) % p;            // 2^64 mod p
    P->r2 = nt_mulmod(rmod, rmod, p);
    // A primitive 2n-th root of unity: g^((p-1)/2n) with order exactly 2n.
    uint64_t psi = 0;
    for (uint64_t g = 2; g < 1000; g++) {
        uint64_t w = nt_powmod(g, (p - 1) / (2 * (uint64_t)n), p);
        if (nt_powmod(w, (uint64_t)n, p) == p - 1) { psi = w; break; }
    }
    if (!psi) return false;
    uint64_t ipsi = nt_powmod(psi, p - 2, p);
    P->psi = (uint64_t *)malloc((size_t)n * sizeof(uint64_t));
    P->psis = (uint64_t *)malloc((size_t)n * sizeof(uint64_t));
    P->ipsi = (uint64_t *)malloc((size_t)n * sizeof(uint64_t));
    P->ipsis = (uint64_t *)malloc((size_t)n * sizeof(uint64_t));
    if (!P->psi || !P->psis || !P->ipsi || !P->ipsis) return false;
    uint64_t w = 1, iw = 1;
    for (int k = 0; k < n; k++) {
        int rv = 0;
        for (int b = 0; b < logn; b++) rv |= ((k >> b) & 1) << (logn - 1 - b);
        P->psi[rv] = w;
        P->ipsi[rv] = iw;
        w = nt_mulmod(w, psi, p);
        iw = nt_mulmod(iw, ipsi, p);
    }
    for (int k = 0; k < n; k++) {
        P->psis[k] = nt_shoup_pre(P->psi[k], p);
        P->ipsis[k] = nt_shoup_pre(P->ipsi[k], p);
    }
    P->ninv = nt_powmod((uint64_t)n, p - 2, p);
    P->ninvs = nt_shoup_pre(P->ninv, p);
    return true;
}

static void nt_prime_free(nt_prime *P) {
    free(P->psi); free(P->psis); free(P->ipsi); free(P->ipsis);
}

/// Forward negacyclic NTT (Cooley–Tukey, Harvey's lazy butterflies):
/// standard order in, bit-reversed out, values reduced to [0, p).
static void nt_forward(uint64_t *a, int n, const nt_prime *P) {
    uint64_t p = P->p, p2 = 2 * p;
    int t = n;
    for (int m = 1; m < n; m <<= 1) {
        t >>= 1;
        for (int i = 0; i < m; i++) {
            uint64_t w = P->psi[m + i], ws = P->psis[m + i];
            uint64_t *x = a + 2 * i * t, *y = x + t;
            for (int j = 0; j < t; j++) {
                uint64_t u = x[j];
                if (u >= p2) u -= p2;
                uint64_t v = nt_shoup(y[j], w, ws, p);
                x[j] = u + v;
                y[j] = u - v + p2;
            }
        }
    }
    for (int j = 0; j < n; j++) {
        uint64_t u = a[j];
        if (u >= p2) u -= p2;
        if (u >= p) u -= p;
        a[j] = u;
    }
}

/// Inverse negacyclic NTT (Gentleman–Sande): bit-reversed in, standard
/// order out, scaled by n^-1, values in [0, p).
static void nt_inverse(uint64_t *a, int n, const nt_prime *P) {
    uint64_t p = P->p, p2 = 2 * p;
    int t = 1;
    for (int m = n; m > 1; m >>= 1) {
        int h = m >> 1;
        for (int i = 0; i < h; i++) {
            uint64_t w = P->ipsi[h + i], ws = P->ipsis[h + i];
            uint64_t *x = a + 2 * i * t, *y = x + t;
            for (int j = 0; j < t; j++) {
                uint64_t u = x[j], v = y[j];
                uint64_t s = u + v;
                if (s >= p2) s -= p2;
                x[j] = s;
                y[j] = nt_shoup(u - v + p2, w, ws, p);
            }
        }
        t <<= 1;
    }
    for (int j = 0; j < n; j++) {
        uint64_t u = nt_shoup(a[j], P->ninv, P->ninvs, p);
        a[j] = u >= p ? u - p : u;
    }
}

typedef struct {
    int n, logn, L;
    uint64_t t;
    nt_prime P[8];
    uint64_t bfly;
} nt_ctx;

/// Small signed coefficients into every RNS residue, then NTT.
static void nt_lift_small(nt_ctx *c, const int64_t *x, uint64_t *out, bool ntt) {
    for (int l = 0; l < c->L; l++) {
        uint64_t p = c->P[l].p, *o = out + (size_t)l * c->n;
        for (int i = 0; i < c->n; i++) {
            int64_t v = x[i];
            o[i] = v >= 0 ? (uint64_t)v % p : p - ((uint64_t)(-v) % p);
            if (o[i] == p) o[i] = 0;
        }
        if (ntt) { nt_forward(o, c->n, &c->P[l]); c->bfly += (uint64_t)c->n / 2 * c->logn; }
    }
}

static void nt_sample_ternary(ib_rng *r, int64_t *x, int n) {
    for (int i = 0; i < n; i++) x[i] = (int64_t)ib_below(r, 3) - 1;
}

static void nt_sample_cbd(ib_rng *r, int64_t *x, int n) {
    for (int i = 0; i < n; i++) {
        uint64_t b = ib_next(r);
        x[i] = (int64_t)__builtin_popcountll(b & 0xF) - (int64_t)__builtin_popcountll((b >> 4) & 0xF);
    }
}

/// Decrypts the NTT-domain ciphertext (c0, c1[, c2]) with the NTT-domain
/// key s (and s² when c2 is given): inverse NTT of c0 + c1·s + c2·s², CRT
/// on the first two primes to the centred value, checked against every
/// other residue, reduced mod t. Returns false on any inconsistency.
static bool nt_decrypt(nt_ctx *c, const uint64_t *c0, const uint64_t *c1, const uint64_t *c2,
                       const uint64_t *s, const uint64_t *s2, uint64_t *tmp, int64_t *m) {
    int n = c->n;
    for (int l = 0; l < c->L; l++) {
        const nt_prime *P = &c->P[l];
        size_t o = (size_t)l * n;
        for (int i = 0; i < n; i++) {
            uint64_t v = c0[o + i] + nt_mul(c1[o + i], s[o + i], P);
            if (v >= P->p) v -= P->p;
            if (c2) {
                v += nt_mul(c2[o + i], s2[o + i], P);
                if (v >= P->p) v -= P->p;
            }
            tmp[o + i] = v;
        }
        nt_inverse(tmp + o, n, P);
        c->bfly += (uint64_t)n / 2 * c->logn;
    }
    uint64_t q1 = c->P[0].p, q2 = c->P[1].p;
    uint64_t q1inv = nt_powmod(q1 % q2, q2 - 2, q2);
    nt_u128 Q = (nt_u128)q1 * q2;
    for (int i = 0; i < n; i++) {
        uint64_t r1 = tmp[i], r2 = tmp[(size_t)n + i];
        uint64_t d = r2 >= r1 % q2 ? r2 - r1 % q2 : r2 + q2 - r1 % q2;
        nt_u128 x = (nt_u128)r1 + (nt_u128)q1 * nt_mulmod(d, q1inv, q2);
        nt_i128 v = x > Q / 2 ? (nt_i128)x - (nt_i128)Q : (nt_i128)x;
        for (int l = 2; l < c->L; l++) {
            nt_i128 ql = (nt_i128)c->P[l].p, rv = v % ql;
            if (rv < 0) rv += ql;
            if ((uint64_t)rv != tmp[(size_t)l * n + i]) return false;
        }
        nt_i128 mt = v % (nt_i128)c->t;
        if (mt < 0) mt += (nt_i128)c->t;
        m[i] = (int64_t)mt;
    }
    return true;
}

/// Homomorphic-encryption arithmetic, the class of SEAL: negacyclic
/// number-theoretic transforms over 60-bit NTT-friendly primes (found by
/// Miller–Rabin) with Harvey's lazy butterflies and Shoup multiplication,
/// Montgomery products, an RNS polynomial ring with several primes, and a
/// toy BGV-style RLWE scheme: key generation, encryption of two random
/// plaintexts (t = 65537), ciphertext multiplication, decryption via CRT
/// on two primes cross-checked against every other residue, and a check
/// of the decrypted product against a schoolbook negacyclic product. Then
/// rounds of NTT → multiply by a key → inverse NTT → twist by x across all
/// primes. Size 1 is n = 4096 with 4 primes and 1000 rounds; size 2
/// n = 8192 with 6 primes and 1900 rounds; size 3 n = 16384 with 8 primes
/// and 2900 rounds. The checksum covers the decrypted product and every
/// residue of the final polynomial.
int cbk_ntt(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int logn_t[4] = { 0, 12, 13, 14 };
    static const int L_t[4] = { 0, 4, 6, 8 };
    static const int rounds_t[4] = { 0, 1000, 1900, 2900 };
    nt_ctx *c = (nt_ctx *)calloc(1, sizeof(nt_ctx));
    if (!c) return 1;
    c->logn = logn_t[size];
    c->n = 1 << c->logn;
    c->L = L_t[size];
    c->t = 65537;
    int n = c->n, L = c->L, rc = 1;
    size_t NL = (size_t)n * L;
    enum { S, S2, A, PK0, U, C0, C1, D0, D1, D2, D0B, D1B, TMP, ACC, KEY, NPOLY };
    uint64_t *poly[NPOLY] = { 0 };
    int64_t *sm = (int64_t *)malloc((size_t)n * sizeof(int64_t));
    int64_t *m1 = (int64_t *)malloc((size_t)n * sizeof(int64_t));
    int64_t *m2 = (int64_t *)malloc((size_t)n * sizeof(int64_t));
    int64_t *e = (int64_t *)malloc((size_t)n * sizeof(int64_t));
    int64_t *dec = (int64_t *)malloc((size_t)n * sizeof(int64_t));
    bool okalloc = sm && m1 && m2 && e && dec;
    for (int k = 0; k < NPOLY; k++) {
        poly[k] = (uint64_t *)malloc(NL * sizeof(uint64_t));
        if (!poly[k]) okalloc = false;
    }
    ib_rng r;
    ib_seed(&r, 0x5EA1C0DEULL + (uint64_t)size);
    uint64_t h = IB_FNV_OFFSET;
    if (!okalloc) goto done;

    // NTT-friendly primes p ≡ 1 (mod 2^16), just below 2^60.
    {
        int found = 0;
        for (uint64_t k = (1ULL << 44) - 1; found < L && k > 0; k--) {
            uint64_t p = (k << 16) + 1;
            if (!nt_is_prime(p)) continue;
            if (!nt_prime_init(&c->P[found], p, n, c->logn)) goto done;
            found++;
        }
        if (found < L) goto done;
    }
    rc = 2;

    // Keys: s ternary, a uniform (sampled straight into the NTT domain),
    // pk0 = -(a·s) + t·e.
    nt_sample_ternary(&r, sm, n);
    nt_lift_small(c, sm, poly[S], true);
    for (int l = 0; l < L; l++) {
        size_t o = (size_t)l * n;
        const nt_prime *P = &c->P[l];
        for (int i = 0; i < n; i++) {
            poly[S2][o + i] = nt_mul(poly[S][o + i], poly[S][o + i], P);
            poly[A][o + i] = nt_mulhi(ib_next(&r), P->p);
        }
    }
    nt_sample_cbd(&r, e, n);
    for (int i = 0; i < n; i++) e[i] *= (int64_t)c->t;
    nt_lift_small(c, e, poly[TMP], true);
    for (size_t k = 0; k < NL; k++) {
        const nt_prime *P = &c->P[k / n];
        uint64_t as = nt_mul(poly[A][k], poly[S][k], P);
        uint64_t v = poly[TMP][k] + (P->p - as);
        poly[PK0][k] = v >= P->p ? v - P->p : v;
    }

    // Two encryptions: c0 = pk0·u + t·e1 + m, c1 = a·u + t·e2.
    for (int which = 0; which < 2; which++) {
        int64_t *m = which ? m2 : m1;
        uint64_t *c0 = poly[which ? D0B : C0], *c1 = poly[which ? D1B : C1];
        for (int i = 0; i < n; i++) m[i] = (int64_t)ib_below(&r, (uint32_t)c->t);
        nt_sample_ternary(&r, sm, n);
        nt_lift_small(c, sm, poly[U], true);
        nt_sample_cbd(&r, e, n);
        for (int i = 0; i < n; i++) e[i] = e[i] * (int64_t)c->t + m[i];
        nt_lift_small(c, e, poly[TMP], true);
        for (size_t k = 0; k < NL; k++) {
            const nt_prime *P = &c->P[k / n];
            uint64_t v = nt_mul(poly[PK0][k], poly[U][k], P) + poly[TMP][k];
            c0[k] = v >= P->p ? v - P->p : v;
        }
        nt_sample_cbd(&r, e, n);
        for (int i = 0; i < n; i++) e[i] *= (int64_t)c->t;
        nt_lift_small(c, e, poly[TMP], true);
        for (size_t k = 0; k < NL; k++) {
            const nt_prime *P = &c->P[k / n];
            uint64_t v = nt_mul(poly[A][k], poly[U][k], P) + poly[TMP][k];
            c1[k] = v >= P->p ? v - P->p : v;
        }
        if (!nt_decrypt(c, c0, c1, NULL, poly[S], NULL, poly[TMP], dec)) goto done;
        for (int i = 0; i < n; i++) if (dec[i] != m[i]) goto done;
    }

    // Multiply: (c0, c1)·(c0', c1') = (c0c0', c0c1' + c1c0', c1c1').
    for (size_t k = 0; k < NL; k++) {
        const nt_prime *P = &c->P[k / n];
        uint64_t a0 = poly[C0][k], a1 = poly[C1][k], b0 = poly[D0B][k], b1 = poly[D1B][k];
        poly[D0][k] = nt_mul(a0, b0, P);
        uint64_t x = nt_mul(a0, b1, P) + nt_mul(a1, b0, P);
        poly[D1][k] = x >= P->p ? x - P->p : x;
        poly[D2][k] = nt_mul(a1, b1, P);
    }
    if (!nt_decrypt(c, poly[D0], poly[D1], poly[D2], poly[S], poly[S2], poly[TMP], dec)) goto done;
    // Schoolbook negacyclic m1·m2 mod t for the check.
    for (int i = 0; i < n; i++) {
        int64_t acc = 0;
        for (int j = 0; j <= i; j++) acc += m1[j] * m2[i - j];
        for (int j = i + 1; j < n; j++) acc -= m1[j] * m2[n + i - j];
        int64_t v = acc % (int64_t)c->t;
        if (v < 0) v += (int64_t)c->t;
        if (v != dec[i]) goto done;
        h = ib_mix(h, (uint64_t)v);
    }

    // Bulk rounds over all primes: acc ← INTT(NTT(acc) ⊙ key) · x.
    for (size_t k = 0; k < NL; k++) {
        const nt_prime *P = &c->P[k / n];
        poly[ACC][k] = nt_mulhi(ib_next(&r), P->p);
        // keys stored in Montgomery form: one Montgomery step per product
        poly[KEY][k] = nt_mont(nt_mulhi(ib_next(&r), P->p), P->r2, P->p, P->pinv);
    }
    for (int round = 0; round < rounds_t[size]; round++) {
        for (int l = 0; l < L; l++) {
            const nt_prime *P = &c->P[l];
            uint64_t *a = poly[ACC] + (size_t)l * n, *kk = poly[KEY] + (size_t)l * n;
            nt_forward(a, n, P);
            for (int i = 0; i < n; i++) a[i] = nt_mont(a[i], kk[i], P->p, P->pinv);
            nt_inverse(a, n, P);
            uint64_t last = a[n - 1];
            memmove(a + 1, a, (size_t)(n - 1) * sizeof(uint64_t));
            a[0] = last ? P->p - last : 0;
            c->bfly += (uint64_t)n * c->logn;
        }
    }
    for (size_t k = 0; k < NL; k++) h = ib_mix(h, poly[ACC][k]);
    for (int l = 0; l < L; l++) h = ib_mix(h, c->P[l].p);
    ib_result(out, h, (double)dec[0] + (double)dec[n - 1], (double)c->bfly, "butterflies");
    rc = 0;
done:
    for (int l = 0; l < 8; l++) nt_prime_free(&c->P[l]);
    for (int k = 0; k < NPOLY; k++) free(poly[k]);
    free(sm); free(m1); free(m2); free(e); free(dec);
    free(c);
    return rc;
}

// ── bfs: graph500-style Kronecker graph traversal ───────────────────────

typedef struct {
    uint32_t nv;
    uint32_t *off;          // CSR offsets, nv + 1
    uint32_t *adj;          // neighbours
} bfs_graph;

/// Edge `e` of the R-MAT/Kronecker generator (A, B, C, D = .57, .19, .19,
/// .05), counter-based so the two CSR passes see the same edges.
static void bfs_edge(uint64_t seed, uint64_t e, int scale, uint32_t *u, uint32_t *v) {
    uint64_t x = seed ^ (e * 0xD1B54A32D192ED03ULL), r = 0;
    uint32_t a = 0, b = 0;
    for (int bit = 0; bit < scale; bit++) {
        if ((bit & 3) == 0) r = ib_splitmix(&x);
        uint32_t q = (uint32_t)(r & 0xFFFF);
        r >>= 16;
        uint32_t ub = q >= 49807, vb = (q >= 37356 && q < 49807) || q >= 62259;
        a |= ub << bit;
        b |= vb << bit;
    }
    *u = a;
    *v = b;
}

/// Plain level-synchronous top-down BFS; fills `hist` with the number of
/// vertices per level and returns the number of levels.
static int bfs_topdown(const bfs_graph *g, uint32_t root, int32_t *parent, uint32_t *q,
                       uint64_t *hist, int maxlev, uint64_t *scanned) {
    for (uint32_t i = 0; i < g->nv; i++) parent[i] = -1;
    parent[root] = (int32_t)root;
    q[0] = root;
    uint32_t lo = 0, hi = 1, tail = 1;
    int lev = 0;
    while (lo < hi) {
        if (lev < maxlev) hist[lev] = hi - lo;
        for (uint32_t i = lo; i < hi; i++) {
            uint32_t v = q[i];
            for (uint32_t k = g->off[v]; k < g->off[v + 1]; k++) {
                uint32_t w = g->adj[k];
                if (parent[w] < 0) { parent[w] = (int32_t)v; q[tail++] = w; }
            }
            *scanned += g->off[v + 1] - g->off[v];
        }
        lo = hi;
        hi = tail;
        lev++;
    }
    return lev;
}

/// Direction-optimising BFS (Beamer et al.): top-down while the frontier
/// is small, bottom-up (unvisited vertices look for a parent in the
/// frontier bitmap) once the frontier's edges outweigh the unexplored
/// ones by alpha = 14, back to top-down below n/24 frontier vertices.
static void bfs_diropt(const bfs_graph *g, uint32_t root, int32_t *parent, uint32_t *q,
                       uint32_t *q2, uint64_t *bm, uint64_t *bm2, uint64_t total_deg,
                       uint64_t *scanned, int *bu_steps) {
    uint32_t nv = g->nv;
    size_t words = (nv + 63) / 64;
    for (uint32_t i = 0; i < nv; i++) parent[i] = -1;
    parent[root] = (int32_t)root;
    uint64_t mu = total_deg - (g->off[root + 1] - g->off[root]);
    uint32_t nq = 1;
    q[0] = root;
    bool bottom_up = false;
    uint32_t nf = 1;
    while (nf > 0) {
        if (!bottom_up) {
            uint64_t mf = 0;
            for (uint32_t i = 0; i < nq; i++) mf += g->off[q[i] + 1] - g->off[q[i]];
            if (mf > mu / 14) {
                memset(bm, 0, words * sizeof(uint64_t));
                for (uint32_t i = 0; i < nq; i++) bm[q[i] >> 6] |= 1ULL << (q[i] & 63);
                bottom_up = true;
            }
        } else if (nf < nv / 24) {
            nq = 0;
            for (size_t w = 0; w < words; w++)
                for (uint64_t b = bm[w]; b; b &= b - 1)
                    q[nq++] = (uint32_t)(w * 64 + (size_t)__builtin_ctzll(b));
            bottom_up = false;
        }
        uint64_t newdeg = 0;
        if (!bottom_up) {
            uint32_t n2 = 0;
            for (uint32_t i = 0; i < nq; i++) {
                uint32_t v = q[i];
                for (uint32_t k = g->off[v]; k < g->off[v + 1]; k++) {
                    uint32_t w = g->adj[k];
                    if (parent[w] < 0) {
                        parent[w] = (int32_t)v;
                        q2[n2++] = w;
                        newdeg += g->off[w + 1] - g->off[w];
                    }
                }
                *scanned += g->off[v + 1] - g->off[v];
            }
            uint32_t *t = q; q = q2; q2 = t;
            nq = n2;
            nf = n2;
        } else {
            (*bu_steps)++;
            memset(bm2, 0, words * sizeof(uint64_t));
            uint32_t n2 = 0;
            for (uint32_t v = 0; v < nv; v++) {
                if (parent[v] >= 0) continue;
                for (uint32_t k = g->off[v]; k < g->off[v + 1]; k++) {
                    uint32_t w = g->adj[k];
                    (*scanned)++;
                    if (bm[w >> 6] >> (w & 63) & 1) {
                        parent[v] = (int32_t)w;
                        bm2[v >> 6] |= 1ULL << (v & 63);
                        n2++;
                        newdeg += g->off[v + 1] - g->off[v];
                        break;
                    }
                }
            }
            uint64_t *t = bm; bm = bm2; bm2 = t;
            nf = n2;
        }
        mu -= newdeg;
    }
}

/// graph500-style validation of a BFS tree: levels from the parent
/// chains (no cycles), every tree edge is a graph edge one level apart,
/// every graph edge joins vertices at most one level apart, and both
/// ends of every edge are either both reached or both not.
static bool bfs_validate(const bfs_graph *g, uint32_t root, const int32_t *parent,
                         int32_t *level, uint32_t *stack, uint64_t *hist, int maxlev) {
    uint32_t nv = g->nv;
    if (parent[root] != (int32_t)root) return false;
    for (uint32_t i = 0; i < nv; i++) level[i] = -1;
    level[root] = 0;
    for (uint32_t v = 0; v < nv; v++) {
        if (parent[v] < 0 || level[v] >= 0) continue;
        uint32_t sp = 0, u = v;
        while (level[u] < 0) {
            if (sp >= nv) return false;                  // a cycle
            stack[sp++] = u;
            u = (uint32_t)parent[u];
            if (parent[u] < 0) return false;
        }
        int32_t l = level[u];
        while (sp) level[stack[--sp]] = ++l;
    }
    for (int i = 0; i < maxlev; i++) hist[i] = 0;
    for (uint32_t v = 0; v < nv; v++) {
        if (level[v] < 0) continue;
        if (level[v] < maxlev) hist[level[v]]++;
        if (v != root) {
            uint32_t pv = (uint32_t)parent[v];
            if (level[v] != level[pv] + 1) return false;
            bool found = false;
            for (uint32_t k = g->off[v]; k < g->off[v + 1]; k++)
                if (g->adj[k] == pv) { found = true; break; }
            if (!found) return false;
        }
        for (uint32_t k = g->off[v]; k < g->off[v + 1]; k++) {
            uint32_t w = g->adj[k];
            if (level[w] < 0) return false;
            int d = level[v] - level[w];
            if (d > 1 || d < -1) return false;
        }
    }
    return true;
}

/// Graph analytics, the class of graph500: a Kronecker (R-MAT) graph
/// with graph500's parameters (A/B/C = .57/.19/.19, edge factor 16,
/// vertex labels permuted) is generated twice from a counter-based
/// generator to build an undirected CSR without storing the edge list;
/// then BFS runs from random roots, each with direction-optimising BFS
/// (top-down / bottom-up switching) and plain top-down BFS, and every
/// tree is validated graph500-style. Size 1 is scale 17 (131k vertices,
/// 2M edges) with 8 roots; size 2 scale 19 with 8 roots; size 3 scale 20
/// with 24 roots. The checksum covers each root's reached-vertex count,
/// traversed edges and level histogram (identical for both BFS kinds).
int cbk_bfs(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int scale_t[4] = { 0, 17, 19, 20 };
    static const int roots_t[4] = { 0, 8, 8, 24 };
    enum { MAXLEV = 64 };
    int scale = scale_t[size];
    uint32_t nv = 1u << scale;
    uint64_t ne = 16ULL * nv, seed = 0x6A09E667F3BCC908ULL + (uint64_t)size;
    size_t words = (nv + 63) / 64;
    bfs_graph g = { nv, NULL, NULL };
    uint32_t *perm = (uint32_t *)malloc((size_t)nv * sizeof(uint32_t));
    uint32_t *cur = (uint32_t *)malloc((size_t)nv * sizeof(uint32_t));
    uint32_t *q2 = (uint32_t *)malloc((size_t)nv * sizeof(uint32_t));
    int32_t *parent = (int32_t *)malloc((size_t)nv * sizeof(int32_t));
    int32_t *level = (int32_t *)malloc((size_t)nv * sizeof(int32_t));
    uint64_t *bm = (uint64_t *)malloc(words * sizeof(uint64_t));
    uint64_t *bm2 = (uint64_t *)malloc(words * sizeof(uint64_t));
    g.off = (uint32_t *)calloc((size_t)nv + 1, sizeof(uint32_t));
    int rc = 1;
    if (!perm || !cur || !q2 || !parent || !level || !bm || !bm2 || !g.off) goto done;
    ib_rng r;
    ib_seed(&r, seed);
    for (uint32_t i = 0; i < nv; i++) perm[i] = i;
    for (uint32_t i = nv - 1; i > 0; i--) {
        uint32_t j = ib_below(&r, i + 1), t = perm[i];
        perm[i] = perm[j]; perm[j] = t;
    }
    // Pass 1: degrees. Pass 2: fill.
    for (uint64_t e = 0; e < ne; e++) {
        uint32_t u, v;
        bfs_edge(seed, e, scale, &u, &v);
        if (u == v) continue;
        g.off[perm[u] + 1]++;
        g.off[perm[v] + 1]++;
    }
    for (uint32_t i = 0; i < nv; i++) g.off[i + 1] += g.off[i];
    g.adj = (uint32_t *)malloc((size_t)g.off[nv] * sizeof(uint32_t));
    if (!g.adj) goto done;
    memcpy(cur, g.off, (size_t)nv * sizeof(uint32_t));
    for (uint64_t e = 0; e < ne; e++) {
        uint32_t u, v;
        bfs_edge(seed, e, scale, &u, &v);
        if (u == v) continue;
        u = perm[u];
        v = perm[v];
        g.adj[cur[u]++] = v;
        g.adj[cur[v]++] = u;
    }
    uint64_t total_deg = g.off[nv], h = IB_FNV_OFFSET, teps_edges = 0, scanned = 0;
    uint64_t hist[MAXLEV], hist2[MAXLEV];
    int bu = 0;
    rc = 2;
    for (int k = 0; k < roots_t[size]; k++) {
        uint32_t root;
        do root = ib_below(&r, nv); while (g.off[root + 1] == g.off[root]);
        bfs_diropt(&g, root, parent, cur, q2, bm, bm2, total_deg, &scanned, &bu);
        if (!bfs_validate(&g, root, parent, level, q2, hist, MAXLEV)) goto done;
        uint64_t reached = 0, edges = 0;
        for (uint32_t v = 0; v < nv; v++)
            if (parent[v] >= 0) { reached++; edges += g.off[v + 1] - g.off[v]; }
        memset(hist2, 0, sizeof hist2);
        int levs = bfs_topdown(&g, root, parent, cur, hist2, MAXLEV, &scanned);
        if (memcmp(hist, hist2, sizeof hist) != 0) goto done;
        h = ib_mix(h, root);
        h = ib_mix(h, reached);
        h = ib_mix(h, edges / 2);
        h = ib_mix(h, (uint64_t)levs);
        for (int i = 0; i < levs && i < MAXLEV; i++) h = ib_mix(h, hist[i]);
        teps_edges += edges / 2;
    }
    h = ib_mix(h, total_deg);
    h = ib_mix(h, (uint64_t)bu);
    ib_result(out, h, (double)teps_edges, (double)scanned, "edges");
    rc = 0;
done:
    free(perm); free(cur); free(q2); free(parent); free(level); free(bm); free(bm2);
    free(g.off); free(g.adj);
    return rc;
}

// ── align: seed-and-extend protein search with banded Smith–Waterman ───

// Residue order: A R N D C Q E G H I L K M F P S T W Y V.
static const int8_t al_b62[20][20] = {
    { 4, -1, -2, -2,  0, -1, -1,  0, -2, -1, -1, -1, -1, -2, -1,  1,  0, -3, -2,  0 },
    {-1,  5,  0, -2, -3,  1,  0, -2,  0, -3, -2,  2, -1, -3, -2, -1, -1, -3, -2, -3 },
    {-2,  0,  6,  1, -3,  0,  0,  0,  1, -3, -3,  0, -2, -3, -2,  1,  0, -4, -2, -3 },
    {-2, -2,  1,  6, -3,  0,  2, -1, -1, -3, -4, -1, -3, -3, -1,  0, -1, -4, -3, -3 },
    { 0, -3, -3, -3,  9, -3, -4, -3, -3, -1, -1, -3, -1, -2, -3, -1, -1, -2, -2, -1 },
    {-1,  1,  0,  0, -3,  5,  2, -2,  0, -3, -2,  1,  0, -3, -1,  0, -1, -2, -1, -2 },
    {-1,  0,  0,  2, -4,  2,  5, -2,  0, -3, -3,  1, -2, -3, -1,  0, -1, -3, -2, -2 },
    { 0, -2,  0, -1, -3, -2, -2,  6, -2, -4, -4, -2, -3, -3, -2,  0, -2, -2, -3, -3 },
    {-2,  0,  1, -1, -3,  0,  0, -2,  8, -3, -3, -1, -2, -1, -2, -1, -2, -2,  2, -3 },
    {-1, -3, -3, -3, -1, -3, -3, -4, -3,  4,  2, -3,  1,  0, -3, -2, -1, -3, -1,  3 },
    {-1, -2, -3, -4, -1, -2, -3, -4, -3,  2,  4, -2,  2,  0, -3, -2, -1, -2, -1,  1 },
    {-1,  2,  0, -1, -3,  1,  1, -2, -1, -3, -2,  5, -1, -3, -1,  0, -1, -3, -2, -2 },
    {-1, -1, -2, -3, -1,  0, -2, -3, -2,  1,  2, -1,  5,  0, -2, -1, -1, -1, -1,  1 },
    {-2, -3, -3, -3, -2, -3, -3, -3, -1,  0,  0, -3,  0,  6, -4, -2, -2,  1,  3, -1 },
    {-1, -2, -2, -1, -3, -1, -1, -2, -2, -3, -3, -1, -2, -4,  7, -1, -1, -4, -3, -2 },
    { 1, -1,  1,  0, -1,  0,  0,  0, -1, -2, -2,  0, -1, -2, -1,  4,  1, -3, -2, -2 },
    { 0, -1,  0, -1, -1, -1, -1, -2, -2, -1, -1, -1, -1, -2, -1,  1,  5, -2, -2,  0 },
    {-3, -3, -4, -4, -2, -2, -3, -2, -2, -3, -2, -3, -1,  1, -4, -3, -2, 11,  2, -3 },
    {-2, -2, -2, -3, -2, -1, -2, -3,  2, -1, -1, -2, -1,  3, -3, -2, -2,  2,  7, -1 },
    { 0, -3, -3, -3, -1, -2, -2, -3, -3,  3,  1, -2,  1, -1, -2, -2,  0, -3, -1,  4 },
};

// Background frequencies (per mille) for generating sequences.
static const uint16_t al_freq[20] = {
    78, 51, 43, 53, 19, 43, 63, 74, 22, 51, 90, 57, 22, 39, 52, 71, 58, 13, 32, 69,
};

// An 11-letter reduced alphabet for seeding:
// {KREDQN} {C} {G} {H} {ILV} {M} {F} {Y} {W} {P} {STA}.
static const uint8_t al_red[20] = { 10, 0, 0, 0, 1, 0, 0, 2, 3, 4, 4, 0, 5, 6, 9, 10, 10, 8, 7, 4 };

// Spaced seed 111011010…: weight 6 over a span of 8.
static const int al_shape[6] = { 0, 1, 2, 4, 5, 7 };
#define AL_SPAN 8
#define AL_NBUCKET 1771561      /* 11^6 */
#define AL_GAPO 12              /* first gap position: open 11 + extend 1 */
#define AL_GAPE 1
#define AL_BAND 20
#define AL_XDROP 18
#define AL_UNGAP 32
#define AL_TOPK 24
#define AL_HASH 16384

static uint8_t al_residue(ib_rng *r) {
    uint32_t x = ib_below(r, 1000), acc = 0;
    for (int k = 0; k < 20; k++) {
        acc += al_freq[k];
        if (x < acc) return (uint8_t)k;
    }
    return 19;
}

/// Writes a mutated copy of src (substitutions at `sub` per mille, plus
/// short insertions and deletions) to dst; returns its length.
static int al_mutate(ib_rng *r, const uint8_t *src, int n, uint8_t *dst, int cap, int sub) {
    int m = 0;
    for (int i = 0; i < n && m < cap; i++) {
        uint32_t x = ib_below(r, 1000);
        if (x < (uint32_t)sub) dst[m++] = al_residue(r);
        else if (x < (uint32_t)sub + 12) continue;
        else if (x < (uint32_t)sub + 24) {
            int ins = 1 + (int)ib_below(r, 3);
            for (int k = 0; k < ins && m < cap; k++) dst[m++] = al_residue(r);
            if (m < cap) dst[m++] = src[i];
        } else dst[m++] = src[i];
    }
    return m;
}

static inline int al_key(const uint8_t *s) {
    int k = 0;
    for (int j = 5; j >= 0; j--) k = k * 11 + al_red[s[al_shape[j]]];
    return k;
}

/// Banded local alignment (Gotoh, affine gaps) of q against s around
/// diagonal `diag` (s index - q index). Returns the best score.
static int al_banded_sw(const uint8_t *q, int m, const uint8_t *s, int n, int diag,
                        int *H, int *E, uint64_t *cells) {
    const int W = 2 * AL_BAND + 1, NEG = -1000000;
    int best = 0;
    for (int k = 0; k < W; k++) { H[k] = 0; E[k] = NEG; }
    // H/E hold row i-1 indexed by band offset k: column j = i + diag - BAND + k.
    for (int i = 0; i < m; i++) {
        int F = NEG, hleft = 0;
        int jbase = i + diag - AL_BAND;
        const int8_t *row = al_b62[q[i]];
        int prevdiag = H[0];   // H[i-1][j-1] for k = 0 is H_prev[0]
        for (int k = 0; k < W; k++) {
            int j = jbase + k;
            int hdiag = prevdiag;                     // H(i-1, j-1)
            int hup = k + 1 < W ? H[k + 1] : 0;       // H(i-1, j)
            int eup = k + 1 < W ? E[k + 1] : NEG;
            prevdiag = k + 1 < W ? H[k + 1] : 0;
            if (j < 0 || j >= n) { H[k] = 0; E[k] = NEG; hleft = 0; F = NEG; continue; }
            int e = hup - AL_GAPO > eup - AL_GAPE ? hup - AL_GAPO : eup - AL_GAPE;
            F = hleft - AL_GAPO > F - AL_GAPE ? hleft - AL_GAPO : F - AL_GAPE;
            int h = hdiag + row[s[j]];
            if (e > h) h = e;
            if (F > h) h = F;
            if (h < 0) h = 0;
            H[k] = h;
            E[k] = e;
            hleft = h;
            if (h > best) best = h;
        }
        *cells += (uint64_t)W;
    }
    return best;
}

typedef struct { uint32_t stamp, subj; int32_t diag, ext; } al_slot;

/// Protein sequence search, the class of DIAMOND/BLASTP: generates a
/// protein database with families (mutated copies of ancestor sequences
/// with substitutions and indels) plus random sequences, indexes it by a
/// spaced seed (weight 6, span 8) over an 11-letter reduced alphabet,
/// then for each query looks up its seeds, extends hits without gaps
/// (BLOSUM62, X-drop) once per diagonal, and aligns the best-scoring
/// subjects with banded Smith–Waterman (BLOSUM62, gap open 11, extend 1,
/// band ±20). Size 1 is 1500 database sequences (~450k residues) and 150
/// queries; size 2 4000 and 350; size 3 10000 and 450. The checksum
/// covers every gapped score and each query's best hit.
int cbk_align(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int ndb_t[4] = { 0, 1500, 4000, 10000 };
    static const int nq_t[4] = { 0, 150, 350, 450 };
    static const int nfam_t[4] = { 0, 120, 300, 700 };
    int ndb = ndb_t[size], nq = nq_t[size], nfam = nfam_t[size];
    const int maxlen = 520;
    ib_rng r;
    ib_seed(&r, 0xA11C0DEULL + (uint64_t)size);
    int rc = 1;
    uint8_t *fam = (uint8_t *)malloc((size_t)nfam * maxlen);
    int *famlen = (int *)malloc((size_t)nfam * sizeof(int));
    size_t dbcap = (size_t)ndb * maxlen;
    uint8_t *db = (uint8_t *)malloc(dbcap);
    uint32_t *dstart = (uint32_t *)malloc(((size_t)ndb + 1) * sizeof(uint32_t));
    uint32_t *dsid = (uint32_t *)malloc(dbcap * sizeof(uint32_t));
    uint32_t *boff = (uint32_t *)calloc((size_t)AL_NBUCKET + 1, sizeof(uint32_t));
    uint32_t *bpos = NULL;
    uint8_t *q = (uint8_t *)malloc((size_t)maxlen);
    al_slot *ht = (al_slot *)calloc(AL_HASH, sizeof(al_slot));
    uint32_t *cstamp = (uint32_t *)calloc((size_t)ndb, sizeof(uint32_t));
    int32_t *cscore = (int32_t *)malloc((size_t)ndb * sizeof(int32_t));
    int32_t *cdiag = (int32_t *)malloc((size_t)ndb * sizeof(int32_t));
    int32_t *clist = (int32_t *)malloc((size_t)ndb * sizeof(int32_t));
    int *H = (int *)malloc((2 * AL_BAND + 1) * sizeof(int));
    int *E = (int *)malloc((2 * AL_BAND + 1) * sizeof(int));
    if (!fam || !famlen || !db || !dstart || !dsid || !boff || !q || !ht || !cstamp ||
        !cscore || !cdiag || !clist || !H || !E)
        goto done;

    for (int f = 0; f < nfam; f++) {
        famlen[f] = 150 + (int)ib_below(&r, 300);
        for (int i = 0; i < famlen[f]; i++) fam[(size_t)f * maxlen + i] = al_residue(&r);
    }
    size_t D = 0;
    for (int s = 0; s < ndb; s++) {
        dstart[s] = (uint32_t)D;
        int len;
        if (ib_chance(&r, 3, 5)) {
            int f = (int)ib_below(&r, (uint32_t)nfam);
            len = al_mutate(&r, fam + (size_t)f * maxlen, famlen[f], db + D, maxlen,
                            100 + (int)ib_below(&r, 400));
        } else {
            len = 100 + (int)ib_below(&r, 400);
            for (int i = 0; i < len; i++) db[D + i] = al_residue(&r);
        }
        for (int i = 0; i < len; i++) dsid[D + i] = (uint32_t)s;
        D += (size_t)len;
    }
    dstart[ndb] = (uint32_t)D;

    // Seed index (counting sort into buckets).
    for (int s = 0; s < ndb; s++)
        for (uint32_t p = dstart[s]; p + AL_SPAN <= dstart[s + 1]; p++) boff[al_key(db + p) + 1]++;
    for (int k = 0; k < AL_NBUCKET; k++) boff[k + 1] += boff[k];
    bpos = (uint32_t *)malloc((size_t)boff[AL_NBUCKET] * sizeof(uint32_t) + 1);
    if (!bpos) goto done;
    for (int s = 0; s < ndb; s++)
        for (uint32_t p = dstart[s]; p + AL_SPAN <= dstart[s + 1]; p++) {
            int k = al_key(db + p);
            bpos[boff[k]++] = p;
        }
    for (int k = AL_NBUCKET; k > 0; k--) boff[k] = boff[k - 1];
    boff[0] = 0;

    uint64_t h = IB_FNV_OFFSET, cells = 0, extensions = 0;
    int64_t total_best = 0;
    uint32_t stamp = 0;
    for (int qi = 0; qi < nq; qi++) {
        int m;
        if (ib_chance(&r, 7, 10)) {
            int f = (int)ib_below(&r, (uint32_t)nfam);
            m = al_mutate(&r, fam + (size_t)f * maxlen, famlen[f], q, maxlen,
                          100 + (int)ib_below(&r, 450));
        } else {
            m = 100 + (int)ib_below(&r, 400);
            for (int i = 0; i < m; i++) q[i] = al_residue(&r);
        }
        stamp++;
        int ncand = 0, nslots = 0;
        for (int i = 0; i + AL_SPAN <= m; i++) {
            int key = al_key(q + i);
            for (uint32_t b = boff[key]; b < boff[key + 1]; b++) {
                uint32_t p = bpos[b], s = dsid[p];
                int32_t sp = (int32_t)(p - dstart[s]), diag = sp - i;
                // Diagonals already extended past this seed are skipped. The
                // table is never filled beyond 3/4, so probing terminates.
                uint32_t slot = (s * 2654435761u ^ (uint32_t)diag * 40503u) & (AL_HASH - 1);
                while (ht[slot].stamp == stamp && !(ht[slot].subj == s && ht[slot].diag == diag))
                    slot = (slot + 1) & (AL_HASH - 1);
                bool known = ht[slot].stamp == stamp;
                if (known && ht[slot].ext >= i) continue;
                // Ungapped X-drop extension along the diagonal.
                const uint8_t *sq = db + dstart[s];
                int slen = (int)(dstart[s + 1] - dstart[s]), sc = 0;
                for (int k = 0; k < AL_SPAN; k++) sc += al_b62[q[i + k]][sq[sp + k]];
                int run = 0, bestr = 0, qend = i + AL_SPAN - 1;
                for (int qq = i + AL_SPAN, ss = sp + AL_SPAN; qq < m && ss < slen; qq++, ss++) {
                    run += al_b62[q[qq]][sq[ss]];
                    if (run > bestr) { bestr = run; qend = qq; }
                    else if (bestr - run > AL_XDROP) break;
                }
                run = 0;
                int bestl = 0;
                for (int qq = i - 1, ss = sp - 1; qq >= 0 && ss >= 0; qq--, ss--) {
                    run += al_b62[q[qq]][sq[ss]];
                    if (run > bestl) bestl = run;
                    else if (bestl - run > AL_XDROP) break;
                }
                extensions++;
                if (!known && nslots < AL_HASH * 3 / 4) {
                    nslots++;
                    ht[slot].stamp = stamp;
                    ht[slot].subj = s;
                    ht[slot].diag = diag;
                    known = true;
                }
                if (known) ht[slot].ext = qend;
                int score = sc + bestr + bestl;
                if (score < AL_UNGAP) continue;
                if (cstamp[s] != stamp) {
                    cstamp[s] = stamp;
                    cscore[s] = score;
                    cdiag[s] = diag;
                    clist[ncand++] = (int32_t)s;
                } else if (score > cscore[s]) {
                    cscore[s] = score;
                    cdiag[s] = diag;
                }
            }
        }
        // Top candidates by ungapped score (ties: lower subject id).
        for (int a = 1; a < ncand; a++) {
            int32_t x = clist[a];
            int b = a;
            while (b > 0 && (cscore[clist[b - 1]] < cscore[x] ||
                             (cscore[clist[b - 1]] == cscore[x] && clist[b - 1] > x))) {
                clist[b] = clist[b - 1];
                b--;
            }
            clist[b] = x;
        }
        int bests = -1, bestsc = 0;
        int lim = ncand < AL_TOPK ? ncand : AL_TOPK;
        for (int c = 0; c < lim; c++) {
            int32_t s = clist[c];
            int sc = al_banded_sw(q, m, db + dstart[s], (int)(dstart[s + 1] - dstart[s]),
                                  cdiag[s], H, E, &cells);
            h = ib_mix(h, ((uint64_t)(uint32_t)s << 32) | (uint32_t)sc);
            if (sc > bestsc) { bestsc = sc; bests = s; }
        }
        h = ib_mix(h, ((uint64_t)(uint32_t)qi << 40) | ((uint64_t)(uint32_t)ncand << 20) |
                          (uint32_t)(bests + 1));
        h = ib_mix(h, (uint64_t)bestsc);
        total_best += bestsc;
    }
    h = ib_mix(h, extensions);
    ib_result(out, h, (double)total_best, (double)cells, "cells");
    rc = 0;
done:
    free(fam); free(famlen); free(db); free(dstart); free(dsid); free(boff); free(bpos);
    free(q); free(ht); free(cstamp); free(cscore); free(cdiag); free(clist); free(H); free(E);
    return rc;
}

// ── csp: a finite-domain constraint solver ──────────────────────────────

enum { CC_ALLDIFF, CC_LINLE, CC_NEQ, CC_DISJ, CC_MACHINE };
enum { CS_FIRSTFAIL, CS_SCHED };

/// A domain: bounds, plus a value bitset for "small" variables (0..63).
typedef struct { int32_t lo, hi; uint64_t bits; } csp_dom;
typedef struct { int type, n, first, c; } csp_con;
typedef struct { int var; csp_dom old; } csp_te;
typedef struct { int mark, var; int32_t val; uint8_t right; } csp_cp;

typedef struct {
    int nv, nc;
    csp_dom *dom;
    uint8_t *small;
    int *hint;                  // scheduling: the disjunction a boolean decides
    ib_ivec cvars, ccoef;
    csp_con *con;
    int ccap;
    int *voff, *vlist;          // variable -> constraints
    int *queue;
    uint8_t *inq;
    int qh, qn;
    csp_te *trail;
    int tn, tcap;
    csp_cp *cps;
    int ncp, cpcap;
    uint64_t nodes, props;
    bool oom;
} csp_s;

static bool csp_init(csp_s *s, int nv) {
    memset(s, 0, sizeof *s);
    s->nv = nv;
    s->dom = (csp_dom *)calloc((size_t)nv, sizeof(csp_dom));
    s->small = (uint8_t *)calloc((size_t)nv, 1);
    s->hint = (int *)malloc((size_t)nv * sizeof(int));
    if (!s->dom || !s->small || !s->hint) return false;
    for (int i = 0; i < nv; i++) s->hint[i] = -1;
    return true;
}

static void csp_free(csp_s *s) {
    free(s->dom); free(s->small); free(s->hint); free(s->cvars.a); free(s->ccoef.a);
    free(s->con); free(s->voff); free(s->vlist); free(s->queue); free(s->inq);
    free(s->trail); free(s->cps);
}

static void csp_small(csp_s *s, int v, int lo, int hi) {
    s->small[v] = 1;
    s->dom[v].lo = lo;
    s->dom[v].hi = hi;
    s->dom[v].bits = (hi >= 63 ? ~0ULL : ((1ULL << (hi + 1)) - 1)) & ~((1ULL << lo) - 1);
}

static void csp_big(csp_s *s, int v, int lo, int hi) {
    s->small[v] = 0;
    s->dom[v].lo = lo;
    s->dom[v].hi = hi;
    s->dom[v].bits = 0;
}

static int csp_post(csp_s *s, int type, int n, const int *vars, const int *coef, int c) {
    if (s->nc == s->ccap) {
        int nc = s->ccap ? 2 * s->ccap : 64;
        csp_con *p = (csp_con *)realloc(s->con, (size_t)nc * sizeof(csp_con));
        if (!p) { s->oom = true; return -1; }
        s->con = p;
        s->ccap = nc;
    }
    csp_con *k = &s->con[s->nc];
    k->type = type; k->n = n; k->first = s->cvars.n; k->c = c;
    for (int i = 0; i < n; i++) {
        if (!ib_ivec_push(&s->cvars, vars[i]) || !ib_ivec_push(&s->ccoef, coef ? coef[i] : 0)) {
            s->oom = true;
            return -1;
        }
    }
    return s->nc++;
}

/// Builds the variable→constraint lists and the propagation queue.
static bool csp_finish(csp_s *s) {
    s->voff = (int *)calloc((size_t)s->nv + 1, sizeof(int));
    s->vlist = (int *)malloc(((size_t)s->cvars.n + 1) * sizeof(int));
    s->queue = (int *)malloc(((size_t)s->nc + 1) * sizeof(int));
    s->inq = (uint8_t *)calloc((size_t)s->nc + 1, 1);
    if (s->oom || !s->voff || !s->vlist || !s->queue || !s->inq) return false;
    for (int k = 0; k < s->nc; k++)
        for (int i = 0; i < s->con[k].n; i++) s->voff[s->cvars.a[s->con[k].first + i] + 1]++;
    for (int v = 0; v < s->nv; v++) s->voff[v + 1] += s->voff[v];
    int *fill = (int *)malloc((size_t)s->nv * sizeof(int));
    if (!fill) return false;
    memcpy(fill, s->voff, (size_t)s->nv * sizeof(int));
    for (int k = 0; k < s->nc; k++)
        for (int i = 0; i < s->con[k].n; i++) s->vlist[fill[s->cvars.a[s->con[k].first + i]]++] = k;
    free(fill);
    return true;
}

static void csp_enqueue_var(csp_s *s, int v) {
    for (int k = s->voff[v]; k < s->voff[v + 1]; k++) {
        int c = s->vlist[k];
        if (!s->inq[c]) {
            s->inq[c] = 1;
            s->queue[(s->qh + s->qn++) % (s->nc + 1)] = c;
        }
    }
}

static void csp_save(csp_s *s, int v) {
    if (s->tn == s->tcap) {
        int nc = s->tcap ? 2 * s->tcap : 1024;
        csp_te *p = (csp_te *)realloc(s->trail, (size_t)nc * sizeof(csp_te));
        if (!p) { s->oom = true; return; }
        s->trail = p;
        s->tcap = nc;
    }
    s->trail[s->tn].var = v;
    s->trail[s->tn].old = s->dom[v];
    s->tn++;
}

static void csp_undo(csp_s *s, int mark) {
    while (s->tn > mark) {
        s->tn--;
        s->dom[s->trail[s->tn].var] = s->trail[s->tn].old;
    }
}

static bool csp_set_lo(csp_s *s, int v, int64_t lo) {
    csp_dom *d = &s->dom[v];
    if (lo <= d->lo) return true;
    if (lo > d->hi) return false;
    csp_save(s, v);
    if (s->small[v]) {
        d->bits &= ~((1ULL << lo) - 1);
        d->lo = __builtin_ctzll(d->bits);
    } else {
        d->lo = (int32_t)lo;
    }
    csp_enqueue_var(s, v);
    return true;
}

static bool csp_set_hi(csp_s *s, int v, int64_t hi) {
    csp_dom *d = &s->dom[v];
    if (hi >= d->hi) return true;
    if (hi < d->lo) return false;
    csp_save(s, v);
    if (s->small[v]) {
        d->bits &= hi >= 63 ? ~0ULL : ((1ULL << (hi + 1)) - 1);
        d->hi = 63 - __builtin_clzll(d->bits);
    } else {
        d->hi = (int32_t)hi;
    }
    csp_enqueue_var(s, v);
    return true;
}

static bool csp_remove(csp_s *s, int v, int64_t val) {
    csp_dom *d = &s->dom[v];
    if (val < d->lo || val > d->hi) return true;
    if (!s->small[v]) {
        if (val == d->lo) return csp_set_lo(s, v, val + 1);
        if (val == d->hi) return csp_set_hi(s, v, val - 1);
        return true;                       // holes are not represented
    }
    if (!(d->bits >> val & 1)) return true;
    if (d->lo == d->hi) return false;
    csp_save(s, v);
    d->bits &= ~(1ULL << val);
    d->lo = __builtin_ctzll(d->bits);
    d->hi = 63 - __builtin_clzll(d->bits);
    csp_enqueue_var(s, v);
    return true;
}

static inline bool csp_fixed(const csp_s *s, int v) { return s->dom[v].lo == s->dom[v].hi; }

static int64_t csp_floordiv(int64_t a, int64_t b) {
    int64_t q = a / b;
    if (a % b != 0 && ((a < 0) != (b < 0))) q--;
    return q;
}

static int64_t csp_ceildiv(int64_t a, int64_t b) {
    int64_t q = a / b;
    if (a % b != 0 && ((a < 0) == (b < 0))) q++;
    return q;
}

static bool csp_propagate_con(csp_s *s, int k) {
    const csp_con *c = &s->con[k];
    const int *x = s->cvars.a + c->first, *a = s->ccoef.a + c->first;
    s->props++;
    switch (c->type) {
    case CC_ALLDIFF: {
        // Fixed values leave every other domain; then a pigeonhole check
        // on the union of the open domains (values shifted by offsets).
        for (int i = 0; i < c->n; i++) {
            if (!csp_fixed(s, x[i])) continue;
            int w = s->dom[x[i]].lo + a[i];
            for (int j = 0; j < c->n; j++)
                if (j != i && !csp_remove(s, x[j], w - a[j])) return false;
        }
        unsigned __int128 uni = 0;
        int open = 0;
        for (int i = 0; i < c->n; i++) {
            if (csp_fixed(s, x[i])) continue;
            uni |= (unsigned __int128)s->dom[x[i]].bits << a[i];
            open++;
        }
        int cnt = __builtin_popcountll((uint64_t)uni) + __builtin_popcountll((uint64_t)(uni >> 64));
        return cnt >= open;
    }
    case CC_LINLE: {
        int64_t minsum = 0;
        for (int i = 0; i < c->n; i++)
            minsum += a[i] > 0 ? (int64_t)a[i] * s->dom[x[i]].lo : (int64_t)a[i] * s->dom[x[i]].hi;
        if (minsum > c->c) return false;
        for (int i = 0; i < c->n; i++) {
            int64_t mine = a[i] > 0 ? (int64_t)a[i] * s->dom[x[i]].lo : (int64_t)a[i] * s->dom[x[i]].hi;
            int64_t slack = (int64_t)c->c - (minsum - mine);
            if (a[i] > 0) { if (!csp_set_hi(s, x[i], csp_floordiv(slack, a[i]))) return false; }
            else if (a[i] < 0) { if (!csp_set_lo(s, x[i], csp_ceildiv(slack, a[i]))) return false; }
        }
        return true;
    }
    case CC_NEQ:
        if (csp_fixed(s, x[1]) && !csp_remove(s, x[0], (int64_t)s->dom[x[1]].lo + c->c)) return false;
        if (csp_fixed(s, x[0]) && !csp_remove(s, x[1], (int64_t)s->dom[x[0]].lo - c->c)) return false;
        return true;
    case CC_DISJ: {
        // x + dx <= y  (b = 1)   or   y + dy <= x  (b = 0)
        int X = x[0], Y = x[1], B = x[2], dx = a[0], dy = a[1];
        if (csp_fixed(s, B)) {
            if (s->dom[B].lo == 1)
                return csp_set_lo(s, Y, (int64_t)s->dom[X].lo + dx) &&
                       csp_set_hi(s, X, (int64_t)s->dom[Y].hi - dx);
            return csp_set_lo(s, X, (int64_t)s->dom[Y].lo + dy) &&
                   csp_set_hi(s, Y, (int64_t)s->dom[X].hi - dy);
        }
        bool can1 = s->dom[X].lo + dx <= s->dom[Y].hi, can2 = s->dom[Y].lo + dy <= s->dom[X].hi;
        if (!can1 && !can2) return false;
        if (!can1) return csp_set_hi(s, B, 0);
        if (!can2) return csp_set_lo(s, B, 1);
        return true;
    }
    case CC_MACHINE: {
        // The tasks on one machine need their summed durations between the
        // earliest start and the latest end; that bounds the makespan.
        int64_t minlo = INT64_MAX, maxend = INT64_MIN, sum = 0;
        int M = x[c->n - 1];
        for (int i = 0; i < c->n - 1; i++) {
            if (s->dom[x[i]].lo < minlo) minlo = s->dom[x[i]].lo;
            if ((int64_t)s->dom[x[i]].hi + a[i] > maxend) maxend = (int64_t)s->dom[x[i]].hi + a[i];
            sum += a[i];
        }
        if (minlo + sum > maxend) return false;
        return csp_set_lo(s, M, minlo + sum);
    }
    default:
        return false;
    }
}

static void csp_clearq(csp_s *s) {
    while (s->qn > 0) {
        s->inq[s->queue[s->qh]] = 0;
        s->qh = (s->qh + 1) % (s->nc + 1);
        s->qn--;
    }
}

static bool csp_propagate(csp_s *s) {
    while (s->qn > 0) {
        int k = s->queue[s->qh];
        s->qh = (s->qh + 1) % (s->nc + 1);
        s->qn--;
        s->inq[k] = 0;
        if (s->oom || !csp_propagate_con(s, k)) {
            csp_clearq(s);
            return false;
        }
    }
    return true;
}

static int csp_select(const csp_s *s, const int *dec, int ndec, int strat) {
    int best = -1;
    int64_t bsize = INT64_MAX;
    for (int i = 0; i < ndec; i++) {
        int v = dec[i];
        if (csp_fixed(s, v)) continue;
        if (strat == CS_SCHED) return v;
        int64_t sz = s->small[v] ? __builtin_popcountll(s->dom[v].bits)
                                 : (int64_t)s->dom[v].hi - s->dom[v].lo + 1;
        if (sz < bsize) { bsize = sz; best = v; }
    }
    return best;
}

static int32_t csp_value(const csp_s *s, int v, int strat) {
    if (strat == CS_SCHED && s->hint[v] >= 0) {
        const csp_con *c = &s->con[s->hint[v]];
        int X = s->cvars.a[c->first], Y = s->cvars.a[c->first + 1];
        return (int64_t)s->dom[X].lo + s->dom[X].hi <= (int64_t)s->dom[Y].lo + s->dom[Y].hi ? 1 : 0;
    }
    return s->dom[v].lo;
}

typedef void (*csp_onsol)(csp_s *s, void *ctx);

/// Depth-first search with binary branching (x = v | x != v) and an
/// explicit choice-point stack. With `obj` >= 0 it is branch and bound:
/// every solution tightens obj < best. Stops after `limit` solutions.
static uint64_t csp_search(csp_s *s, const int *dec, int ndec, int strat, int obj,
                           uint64_t limit, csp_onsol onsol, void *ctx) {
    uint64_t sols = 0;
    int64_t best = INT64_MAX;
    for (int k = 0; k < s->nc; k++) {
        s->inq[k] = 1;
        s->queue[(s->qh + s->qn++) % (s->nc + 1)] = k;
    }
    bool ok = csp_propagate(s);
    s->ncp = 0;
    for (;;) {
        if (ok) {
            int v = csp_select(s, dec, ndec, strat);
            if (v < 0) {
                sols++;
                if (obj >= 0) best = s->dom[obj].lo;
                if (onsol) onsol(s, ctx);
                if (sols >= limit) return sols;
                ok = false;
                continue;
            }
            if (s->ncp == s->cpcap) {
                int nc = s->cpcap ? 2 * s->cpcap : 256;
                csp_cp *p = (csp_cp *)realloc(s->cps, (size_t)nc * sizeof(csp_cp));
                if (!p) { s->oom = true; return sols; }
                s->cps = p;
                s->cpcap = nc;
            }
            int32_t val = csp_value(s, v, strat);
            csp_cp *cp = &s->cps[s->ncp++];
            cp->mark = s->tn; cp->var = v; cp->val = val; cp->right = 0;
            s->nodes++;
            ok = csp_set_lo(s, v, val) && csp_set_hi(s, v, val) && csp_propagate(s);
            if (!ok) csp_clearq(s);
        } else {
            // Backtrack to the newest choice point still on its left branch.
            while (s->ncp > 0 && s->cps[s->ncp - 1].right) {
                csp_undo(s, s->cps[s->ncp - 1].mark);
                s->ncp--;
            }
            if (s->ncp == 0) return sols;
            csp_cp *cp = &s->cps[s->ncp - 1];
            csp_undo(s, cp->mark);
            cp->right = 1;
            s->nodes++;
            ok = csp_remove(s, cp->var, cp->val);
            if (ok && obj >= 0 && best != INT64_MAX) ok = csp_set_hi(s, obj, best - 1);
            ok = ok && csp_propagate(s);
            if (!ok) csp_clearq(s);
        }
    }
}

// ---- Models ----

typedef struct { uint64_t h; int n; const int *vars; } csp_hashctx;

static void csp_hash_sol(csp_s *s, void *ctx) {
    csp_hashctx *hc = (csp_hashctx *)ctx;
    for (int i = 0; i < hc->n; i++) hc->h = ib_mix(hc->h, (uint64_t)s->dom[hc->vars[i]].lo);
}

/// Counts the n-queens solutions with three all-different constraints.
static int csp_queens(int n, uint64_t *count, uint64_t *nodes, uint64_t *props) {
    csp_s s;
    if (!csp_init(&s, n)) { csp_free(&s); return 1; }
    int vars[64], off[64];
    for (int i = 0; i < n; i++) { csp_small(&s, i, 0, n - 1); vars[i] = i; }
    for (int i = 0; i < n; i++) off[i] = 0;
    csp_post(&s, CC_ALLDIFF, n, vars, off, 0);
    for (int i = 0; i < n; i++) off[i] = i;
    csp_post(&s, CC_ALLDIFF, n, vars, off, 0);
    for (int i = 0; i < n; i++) off[i] = n - i;
    csp_post(&s, CC_ALLDIFF, n, vars, off, 0);
    if (!csp_finish(&s)) { csp_free(&s); return 1; }
    *count = csp_search(&s, vars, n, CS_FIRSTFAIL, -1, UINT64_MAX, NULL, NULL);
    *nodes += s.nodes;
    *props += s.props;
    bool oom = s.oom;
    csp_free(&s);
    return oom ? 1 : 0;
}

/// Chromatic number of a random graph: k-colourability for k = 2, 3, …
/// until a colouring exists (vertex 0 fixed to colour 0). Returns the
/// colouring's hash in *h.
static int csp_colour(ib_rng *r, int n, int m, int *chi, uint64_t *h, uint64_t *nodes,
                      uint64_t *props) {
    int *eu = (int *)malloc((size_t)m * sizeof(int)), *ev = (int *)malloc((size_t)m * sizeof(int));
    int *deg = (int *)calloc((size_t)n, sizeof(int)), *ord = (int *)malloc((size_t)n * sizeof(int));
    int *lab = (int *)malloc((size_t)n * sizeof(int));
    int rc = 1;
    if (!eu || !ev || !deg || !ord || !lab) goto out;
    int ne = 0;
    for (int e = 0; e < m; e++) {
        int a = (int)ib_below(r, (uint32_t)n), b = (int)ib_below(r, (uint32_t)n);
        if (a == b) continue;
        eu[ne] = a; ev[ne] = b; ne++;
        deg[a]++; deg[b]++;
    }
    // Relabel by decreasing degree so first-fail ties go to busy vertices.
    for (int i = 0; i < n; i++) ord[i] = i;
    for (int i = 1; i < n; i++) {
        int x = ord[i], j = i;
        while (j > 0 && (deg[ord[j - 1]] < deg[x] || (deg[ord[j - 1]] == deg[x] && ord[j - 1] > x))) {
            ord[j] = ord[j - 1];
            j--;
        }
        ord[j] = x;
    }
    for (int i = 0; i < n; i++) lab[ord[i]] = i;
    for (int k = 2; k <= 64; k++) {
        csp_s s;
        if (!csp_init(&s, n)) { csp_free(&s); goto out; }
        int dv[2], *vars = ord;      // ord reused as the decision list 0..n-1
        for (int i = 0; i < n; i++) { csp_small(&s, i, 0, k - 1); vars[i] = i; }
        csp_small(&s, 0, 0, 0);
        for (int e = 0; e < ne; e++) {
            dv[0] = lab[eu[e]]; dv[1] = lab[ev[e]];
            csp_post(&s, CC_NEQ, 2, dv, NULL, 0);
        }
        if (!csp_finish(&s)) { csp_free(&s); goto out; }
        csp_hashctx hc = { IB_FNV_OFFSET, n, vars };
        uint64_t sols = csp_search(&s, vars, n, CS_FIRSTFAIL, -1, 1, csp_hash_sol, &hc);
        *nodes += s.nodes;
        *props += s.props;
        bool oom = s.oom;
        csp_free(&s);
        if (oom) goto out;
        if (sols) { *chi = k; *h = hc.h; rc = 0; break; }
    }
out:
    free(eu); free(ev); free(deg); free(ord); free(lab);
    return rc;
}

typedef struct { int nt; int32_t *best; } csp_jspctx;

static void csp_jsp_sol(csp_s *s, void *ctx) {
    csp_jspctx *j = (csp_jspctx *)ctx;
    for (int i = 0; i < j->nt; i++) j->best[i] = s->dom[i].lo;
}

/// Job-shop scheduling, minimising the makespan by branch and bound over
/// the order of each pair of tasks sharing a machine.
static int csp_jobshop(ib_rng *r, int J, int K, int *makespan, uint64_t *h, uint64_t *nodes,
                       uint64_t *props) {
    int nt = J * K, npair = K * J * (J - 1) / 2;
    int nvar = nt + 1 + npair, M = nt, rc = 1;
    int *mach = (int *)malloc((size_t)nt * sizeof(int)), *dur = (int *)malloc((size_t)nt * sizeof(int));
    int32_t *best = (int32_t *)malloc((size_t)nt * sizeof(int32_t));
    int *dec = (int *)malloc((size_t)npair * sizeof(int));
    int *tv = (int *)malloc((size_t)(J + 1) * sizeof(int)), *td = (int *)malloc((size_t)(J + 1) * sizeof(int));
    csp_s s;
    bool inited = false;
    if (!mach || !dur || !best || !dec || !tv || !td) goto out;
    int horizon = 0;
    for (int j = 0; j < J; j++) {
        int perm[16];
        for (int k = 0; k < K; k++) perm[k] = k;
        for (int k = K - 1; k > 0; k--) {
            int q = (int)ib_below(r, (uint32_t)k + 1), t = perm[k];
            perm[k] = perm[q]; perm[q] = t;
        }
        for (int k = 0; k < K; k++) {
            mach[j * K + k] = perm[k];
            dur[j * K + k] = 1 + (int)ib_below(r, 9);
            horizon += dur[j * K + k];
        }
    }
    inited = true;
    if (!csp_init(&s, nvar)) goto out;
    for (int t = 0; t < nt; t++) csp_big(&s, t, 0, horizon);
    csp_big(&s, M, 0, horizon);
    int vv[3], cc[3];
    for (int j = 0; j < J; j++) {
        for (int k = 0; k + 1 < K; k++) {
            vv[0] = j * K + k; vv[1] = j * K + k + 1;
            cc[0] = 1; cc[1] = -1;
            csp_post(&s, CC_LINLE, 2, vv, cc, -dur[j * K + k]);
        }
        vv[0] = j * K + K - 1; vv[1] = M;
        cc[0] = 1; cc[1] = -1;
        csp_post(&s, CC_LINLE, 2, vv, cc, -dur[j * K + K - 1]);
    }
    int b = nt + 1, nd = 0;
    for (int mc = 0; mc < K; mc++) {
        int n = 0;
        for (int t = 0; t < nt; t++)
            if (mach[t] == mc) { tv[n] = t; td[n] = dur[t]; n++; }
        for (int i = 0; i < n; i++)
            for (int q = i + 1; q < n; q++) {
                csp_small(&s, b, 0, 1);
                vv[0] = tv[i]; vv[1] = tv[q]; vv[2] = b;
                cc[0] = td[i]; cc[1] = td[q]; cc[2] = 0;
                s.hint[b] = csp_post(&s, CC_DISJ, 3, vv, cc, 0);
                dec[nd++] = b++;
            }
        tv[n] = M; td[n] = 0;
        csp_post(&s, CC_MACHINE, n + 1, tv, td, 0);
    }
    if (!csp_finish(&s)) goto out;
    csp_jspctx jc = { nt, best };
    uint64_t sols = csp_search(&s, dec, nd, CS_SCHED, M, UINT64_MAX, csp_jsp_sol, &jc);
    *nodes += s.nodes;
    *props += s.props;
    if (s.oom || sols == 0) goto out;
    // Check the best schedule: job order, machine exclusivity, makespan.
    int ms = 0;
    for (int t = 0; t < nt; t++) if (best[t] + dur[t] > ms) ms = best[t] + dur[t];
    for (int j = 0; j < J; j++)
        for (int k = 0; k + 1 < K; k++)
            if (best[j * K + k] + dur[j * K + k] > best[j * K + k + 1]) goto out;
    for (int t = 0; t < nt; t++)
        for (int u = t + 1; u < nt; u++)
            if (mach[t] == mach[u] && best[t] < best[u] + dur[u] && best[u] < best[t] + dur[t]) goto out;
    *makespan = ms;
    for (int t = 0; t < nt; t++) *h = ib_mix(*h, (uint64_t)best[t]);
    rc = 0;
out:
    if (inited) csp_free(&s);
    free(mach); free(dur); free(best); free(dec); free(tv); free(td);
    return rc;
}

/// 4×4 magic squares (all-different, linear sums of 34): the first
/// `limit` solutions.
static int csp_magic(uint64_t limit, uint64_t *count, uint64_t *h, uint64_t *nodes, uint64_t *props) {
    csp_s s;
    if (!csp_init(&s, 16)) { csp_free(&s); return 1; }
    int vars[16], off[16] = { 0 }, one[4] = { 1, 1, 1, 1 }, mone[4] = { -1, -1, -1, -1 }, v4[4];
    for (int i = 0; i < 16; i++) { csp_small(&s, i, 1, 16); vars[i] = i; }
    csp_post(&s, CC_ALLDIFF, 16, vars, off, 0);
    for (int line = 0; line < 10; line++) {
        for (int k = 0; k < 4; k++) {
            if (line < 4) v4[k] = line * 4 + k;
            else if (line < 8) v4[k] = k * 4 + (line - 4);
            else if (line == 8) v4[k] = k * 5;
            else v4[k] = k * 3 + 3;
        }
        csp_post(&s, CC_LINLE, 4, v4, one, 34);
        csp_post(&s, CC_LINLE, 4, v4, mone, -34);
    }
    if (!csp_finish(&s)) { csp_free(&s); return 1; }
    csp_hashctx hc = { *h, 16, vars };
    *count = csp_search(&s, vars, 16, CS_FIRSTFAIL, -1, limit, csp_hash_sol, &hc);
    *h = hc.h;
    *nodes += s.nodes;
    *props += s.props;
    bool oom = s.oom;
    csp_free(&s);
    return oom ? 1 : 0;
}

/// Constraint programming, the class of MiniZinc with a CP backend: a
/// finite-domain solver (bitset domains for small variables, bounds for
/// large ones, a trail, a propagation queue to fixpoint) with all-
/// different (value elimination + pigeonhole), linear inequalities
/// (bounds reasoning), disequalities, reified disjunctive task pairs and
/// a per-machine energy bound, searched depth-first with first-fail
/// binary branching or branch and bound. Instances: counting n-queens,
/// chromatic numbers of random graphs (average degree 14), 4×4 magic
/// squares, and makespan-optimal job-shop schedules (each one checked).
/// Size 1 counts 10-queens, colours four 60-vertex graphs, solves three
/// 6×6 job shops and enumerates 1500 magic squares; size 2 is 12-queens,
/// 65-vertex graphs, four 7×6 job shops, 3000 squares; size 3 is
/// 13-queens, eight 70-vertex graphs, ten 6×6 job shops and all 7040
/// squares. The checksum covers every count, chromatic number, colouring,
/// schedule and the node count.
int cbk_csp(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int queens_t[4] = { 0, 10, 12, 13 };
    static const int ngraph_t[4] = { 0, 4, 4, 8 };
    static const int gn_t[4] = { 0, 60, 65, 70 };
    static const int jsp_t[4][2] = { { 0, 0 }, { 6, 6 }, { 7, 6 }, { 6, 6 } };
    static const int njsp_t[4] = { 0, 3, 4, 10 };
    static const uint64_t magic_t[4] = { 0, 1500, 3000, UINT64_MAX };
    ib_rng r;
    ib_seed(&r, 0xC5B0C5B0ULL + (uint64_t)size);
    uint64_t h = IB_FNV_OFFSET, nodes = 0, props = 0, cnt = 0;
    double value = 0;
    if (csp_queens(queens_t[size], &cnt, &nodes, &props)) return 1;
    h = ib_mix(h, cnt);
    value += (double)cnt;
    for (int g = 0; g < ngraph_t[size]; g++) {
        int n = gn_t[size], chi = 0;
        uint64_t ch = 0;
        if (csp_colour(&r, n, n * 7, &chi, &ch, &nodes, &props)) return 2;
        h = ib_mix(h, (uint64_t)chi);
        h = ib_mix(h, ch);
        value += chi;
    }
    for (int k = 0; k < njsp_t[size]; k++) {
        int ms = 0;
        if (csp_jobshop(&r, jsp_t[size][0], jsp_t[size][1], &ms, &h, &nodes, &props)) return 3;
        h = ib_mix(h, (uint64_t)ms);
        value += ms;
    }
    uint64_t mh = IB_FNV_OFFSET;
    if (csp_magic(magic_t[size], &cnt, &mh, &nodes, &props)) return 4;
    h = ib_mix(h, cnt);
    h = ib_mix(h, mh);
    h = ib_mix(h, nodes);
    ib_result(out, h, value, (double)nodes, "nodes");
    return 0;
}

// ── flac: LPC + Rice lossless audio codec with a verifying decoder ─────

#define FL_BLOCK 4096
#define FL_MAXORDER 12
#define FL_PREC 14
#define FL_MAXPORDER 6
#define FL_MAXRICE 14

typedef struct { uint8_t *buf; size_t n, cap; uint64_t acc; int bits; bool oom; } fl_bw;

static void fl_byte(fl_bw *w, uint8_t b) {
    if (w->n == w->cap) {
        size_t nc = w->cap ? w->cap * 2 : 65536;
        uint8_t *p = (uint8_t *)realloc(w->buf, nc);
        if (!p) { w->oom = true; return; }
        w->buf = p;
        w->cap = nc;
    }
    w->buf[w->n++] = b;
}

static void fl_put(fl_bw *w, uint32_t v, int nb) {
    if (nb == 0) return;
    w->acc = (w->acc << nb) | (nb == 32 ? v : (v & ((1u << nb) - 1)));
    w->bits += nb;
    while (w->bits >= 8) {
        w->bits -= 8;
        fl_byte(w, (uint8_t)(w->acc >> w->bits));
    }
}

static void fl_align(fl_bw *w) {
    if (w->bits) fl_put(w, 0, 8 - w->bits);
}

static void fl_rice(fl_bw *w, uint32_t u, int k) {
    uint32_t q = u >> k;
    while (q >= 32) { fl_put(w, 0, 32); q -= 32; }
    fl_put(w, 1, (int)q + 1);
    fl_put(w, u, k);
}

typedef struct { const uint8_t *buf; size_t n, pos; uint64_t acc; int bits; bool over; } fl_br;

static uint32_t fl_get(fl_br *r, int nb) {
    if (nb == 0) return 0;
    while (r->bits < nb) {
        uint8_t b = 0;
        if (r->pos < r->n) b = r->buf[r->pos++];
        else r->over = true;
        r->acc = (r->acc << 8) | b;
        r->bits += 8;
    }
    r->bits -= nb;
    return (uint32_t)(r->acc >> r->bits) & (nb == 32 ? 0xFFFFFFFFu : ((1u << nb) - 1));
}

static int32_t fl_gets(fl_br *r, int nb) {
    uint32_t v = fl_get(r, nb);
    if (v >> (nb - 1)) v |= ~0u << (nb - 1) << 1;
    return (int32_t)v;
}

static uint32_t fl_get_rice(fl_br *r, int k) {
    uint32_t q = 0;
    while (fl_get(r, 1) == 0) {
        if (r->over) return 0;
        q++;
    }
    return (q << k) | fl_get(r, k);
}

static uint16_t fl_crc16(const uint8_t *p, size_t n) {
    uint16_t crc = 0;
    for (size_t i = 0; i < n; i++) {
        crc ^= (uint16_t)(p[i] << 8);
        for (int b = 0; b < 8; b++)
            crc = (uint16_t)((crc & 0x8000) ? (crc << 1) ^ 0x8005 : crc << 1);
    }
    return crc;
}

static inline uint32_t fl_zig(int32_t e) { return ((uint32_t)e << 1) ^ (uint32_t)(e >> 31); }
static inline int32_t fl_unzig(uint32_t u) { return (int32_t)(u >> 1) ^ -(int32_t)(u & 1); }

// A subframe plan: how one channel of one block is coded.
enum { FL_CONST, FL_VERB, FL_FIXED, FL_LPC };
typedef struct {
    int type, order, shift, porder;
    int32_t coef[FL_MAXORDER];
    int rice[1 << FL_MAXPORDER];
    uint64_t bits;
} fl_plan;

/// Residual of a plan (samples order..n-1). False if any residual does
/// not fit the coder's 31-bit range.
static bool fl_residual(const int32_t *x, int n, const fl_plan *p, int32_t *e) {
    int o = p->order;
    for (int i = o; i < n; i++) {
        int64_t pred;
        if (p->type == FL_FIXED) {
            switch (o) {
            case 0: pred = 0; break;
            case 1: pred = x[i - 1]; break;
            case 2: pred = 2 * (int64_t)x[i - 1] - x[i - 2]; break;
            case 3: pred = 3 * (int64_t)x[i - 1] - 3 * (int64_t)x[i - 2] + x[i - 3]; break;
            default:
                pred = 4 * (int64_t)x[i - 1] - 6 * (int64_t)x[i - 2] + 4 * (int64_t)x[i - 3] - x[i - 4];
                break;
            }
        } else {
            int64_t s = 0;
            for (int j = 0; j < o; j++) s += (int64_t)p->coef[j] * x[i - 1 - j];
            pred = s >> p->shift;
        }
        int64_t r = (int64_t)x[i] - pred;
        if (r > (1 << 29) || r < -(1 << 29)) return false;
        e[i] = (int32_t)r;
    }
    return true;
}

/// Picks the Rice partition order and per-partition parameters for the
/// residual; returns the estimated bit count (FLAC-style estimate).
static uint64_t fl_partition(const int32_t *e, int n, int order, fl_plan *p) {
    uint64_t sums[1 << FL_MAXPORDER];
    int maxp = 0;
    while (maxp < FL_MAXPORDER && (n >> (maxp + 1)) > order && ((n >> (maxp + 1)) << (maxp + 1)) == n) maxp++;
    int parts = 1 << maxp, plen = n >> maxp;
    for (int k = 0; k < parts; k++) {
        uint64_t s = 0;
        int lo = k == 0 ? order : k * plen, hi = (k + 1) * plen;
        for (int i = lo; i < hi; i++) s += fl_zig(e[i]);
        sums[k] = s;
    }
    uint64_t best = UINT64_MAX;
    for (int po = maxp; po >= 0; po--) {
        int np = 1 << po, len = n >> po;
        uint64_t total = 4;
        int ks[1 << FL_MAXPORDER];
        for (int k = 0; k < np; k++) {
            uint64_t cnt = (uint64_t)(len - (k == 0 ? order : 0)), s = sums[k], bb = UINT64_MAX;
            int bk = 0;
            for (int r = 0; r <= FL_MAXRICE; r++) {
                uint64_t b = cnt * (uint64_t)(r + 1) + (s >> r);
                if (b < bb) { bb = b; bk = r; }
            }
            ks[k] = bk;
            total += 4 + bb;
        }
        if (total < best) {
            best = total;
            p->porder = po;
            memcpy(p->rice, ks, (size_t)np * sizeof(int));
        }
        if (po > 0)
            for (int k = 0; k < np / 2; k++) sums[k] = sums[2 * k] + sums[2 * k + 1];
    }
    return best;
}

/// Finds the cheapest coding of one channel signal: constant, verbatim,
/// fixed polynomial predictors 0–4, or quantised LPC of every order 1–12
/// from Levinson–Durbin on the Welch-windowed autocorrelation.
static void fl_analyse(const int32_t *x, int n, int bps, fl_plan *best, int32_t *e,
                       double *xw, uint64_t *lpc_tries) {
    best->type = FL_VERB;
    best->order = 0;
    best->bits = 2 + (uint64_t)n * bps;
    bool constant = true;
    for (int i = 1; i < n && constant; i++) constant = x[i] == x[0];
    if (constant) { best->type = FL_CONST; best->bits = 2 + (uint64_t)bps; return; }
    fl_plan p;
    for (int o = 0; o <= 4 && o < n; o++) {
        p.type = FL_FIXED;
        p.order = o;
        if (!fl_residual(x, n, &p, e)) continue;
        p.bits = 2 + 3 + (uint64_t)o * bps + fl_partition(e, n, o, &p);
        if (p.bits < best->bits) *best = p;
    }
    // Windowed autocorrelation.
    double autoc[FL_MAXORDER + 1];
    double half = (n - 1) / 2.0, den = (n + 1) / 2.0;
    for (int i = 0; i < n; i++) {
        double t = (i - half) / den;
        xw[i] = (double)x[i] * (1.0 - t * t);
    }
    for (int l = 0; l <= FL_MAXORDER; l++) {
        double s = 0;
        for (int i = l; i < n; i++) s += xw[i] * xw[i - l];
        autoc[l] = s;
    }
    if (autoc[0] <= 0) return;
    // Levinson–Durbin: predictor a[1..i] for every order i.
    double a[FL_MAXORDER + 1] = { 0 }, na[FL_MAXORDER + 1], lpc[FL_MAXORDER + 1][FL_MAXORDER + 1];
    double err = autoc[0];
    int maxo = 0;
    for (int i = 1; i <= FL_MAXORDER; i++) {
        double acc = autoc[i];
        for (int j = 1; j < i; j++) acc -= a[j] * autoc[i - j];
        double k = acc / err;
        na[i] = k;
        for (int j = 1; j < i; j++) na[j] = a[j] - k * a[i - j];
        for (int j = 1; j <= i; j++) { a[j] = na[j]; lpc[i][j] = na[j]; }
        err *= 1.0 - k * k;
        maxo = i;
        if (!(err > 0)) break;
    }
    for (int o = 1; o <= maxo && o < n; o++) {
        double cmax = 0;
        for (int j = 1; j <= o; j++) if (fabs(lpc[o][j]) > cmax) cmax = fabs(lpc[o][j]);
        if (!(cmax > 0)) continue;
        int ex;
        frexp(cmax, &ex);
        int shift = (FL_PREC - 1) - ex;
        if (shift < 0) continue;
        if (shift > 15) shift = 15;
        double carry = 0;
        p.type = FL_LPC;
        p.order = o;
        p.shift = shift;
        for (int j = 0; j < o; j++) {
            double v = ldexp(lpc[o][j + 1], shift) + carry;
            double q = floor(v + 0.5);
            if (q > (1 << (FL_PREC - 1)) - 1) q = (1 << (FL_PREC - 1)) - 1;
            if (q < -(1 << (FL_PREC - 1))) q = -(1 << (FL_PREC - 1));
            p.coef[j] = (int32_t)q;
            carry = v - q;
        }
        (*lpc_tries)++;
        if (!fl_residual(x, n, &p, e)) continue;
        p.bits = 2 + 4 + 4 + 5 + (uint64_t)o * (FL_PREC + bps) + fl_partition(e, n, o, &p);
        if (p.bits < best->bits) *best = p;
    }
}

static void fl_write_sub(fl_bw *w, const int32_t *x, int n, int bps, fl_plan *p, int32_t *e) {
    fl_put(w, (uint32_t)p->type, 2);
    if (p->type == FL_CONST) { fl_put(w, (uint32_t)x[0], bps); return; }
    if (p->type == FL_VERB) {
        for (int i = 0; i < n; i++) fl_put(w, (uint32_t)x[i], bps);
        return;
    }
    if (p->type == FL_FIXED) {
        fl_put(w, (uint32_t)p->order, 3);
    } else {
        fl_put(w, (uint32_t)(p->order - 1), 4);
        fl_put(w, FL_PREC - 1, 4);
        fl_put(w, (uint32_t)p->shift, 5);
        for (int j = 0; j < p->order; j++) fl_put(w, (uint32_t)p->coef[j], FL_PREC);
    }
    for (int i = 0; i < p->order; i++) fl_put(w, (uint32_t)x[i], bps);
    fl_residual(x, n, p, e);
    fl_put(w, (uint32_t)p->porder, 4);
    int np = 1 << p->porder, len = n >> p->porder;
    for (int k = 0; k < np; k++) {
        int r = p->rice[k];
        fl_put(w, (uint32_t)r, 4);
        int lo = k == 0 ? p->order : k * len, hi = (k + 1) * len;
        for (int i = lo; i < hi; i++) fl_rice(w, fl_zig(e[i]), r);
    }
}

static bool fl_read_sub(fl_br *r, int32_t *x, int n, int bps) {
    int type = (int)fl_get(r, 2);
    if (type == FL_CONST) {
        int32_t v = fl_gets(r, bps);
        for (int i = 0; i < n; i++) x[i] = v;
        return !r->over;
    }
    if (type == FL_VERB) {
        for (int i = 0; i < n; i++) x[i] = fl_gets(r, bps);
        return !r->over;
    }
    fl_plan p;
    p.type = type;
    if (type == FL_FIXED) {
        p.order = (int)fl_get(r, 3);
        if (p.order > 4) return false;
    } else {
        p.order = (int)fl_get(r, 4) + 1;
        int prec = (int)fl_get(r, 4) + 1;
        p.shift = (int)fl_get(r, 5);
        for (int j = 0; j < p.order; j++) p.coef[j] = fl_gets(r, prec);
    }
    if (p.order > n) return false;
    for (int i = 0; i < p.order; i++) x[i] = fl_gets(r, bps);
    int po = (int)fl_get(r, 4);
    if (po > FL_MAXPORDER) return false;
    int np = 1 << po, len = n >> po;
    for (int k = 0; k < np; k++) {
        int rk = (int)fl_get(r, 4);
        int lo = k == 0 ? p.order : k * len, hi = (k + 1) * len;
        for (int i = lo; i < hi; i++) {
            int32_t res = fl_unzig(fl_get_rice(r, rk));
            int64_t pred;
            if (type == FL_FIXED) {
                switch (p.order) {
                case 0: pred = 0; break;
                case 1: pred = x[i - 1]; break;
                case 2: pred = 2 * (int64_t)x[i - 1] - x[i - 2]; break;
                case 3: pred = 3 * (int64_t)x[i - 1] - 3 * (int64_t)x[i - 2] + x[i - 3]; break;
                default:
                    pred = 4 * (int64_t)x[i - 1] - 6 * (int64_t)x[i - 2] + 4 * (int64_t)x[i - 3] - x[i - 4];
                    break;
                }
            } else {
                int64_t s = 0;
                for (int j = 0; j < p.order; j++) s += (int64_t)p.coef[j] * x[i - 1 - j];
                pred = s >> p.shift;
            }
            x[i] = (int32_t)(pred + res);
        }
        if (r->over) return false;
    }
    return true;
}

// Integer synthesis: "magic circle" oscillators (area-preserving, so
// bounded forever) with decaying envelopes, plus low-passed noise.
typedef struct { int64_t x, y, eps, env, decay; int pan, left; } fl_voice;
typedef struct { fl_voice v[3]; int64_t lp; } fl_synth;

static void fl_note(ib_rng *r, fl_voice *v) {
    v->eps = 400 + (int64_t)ib_below(r, 8600);
    v->x = 9000 + (int64_t)ib_below(r, 6000);
    v->y = 0;
    v->env = 65536;
    v->decay = 65500 + (int64_t)ib_below(r, 34);
    v->pan = (int)ib_below(r, 257);
    v->left = 4000 + (int)ib_below(r, 12000);
}

static void fl_synth_block(ib_rng *r, fl_synth *s, int32_t *L, int32_t *R, int n) {
    for (int i = 0; i < n; i++) {
        int64_t sl = 0, sr = 0;
        for (int k = 0; k < 3; k++) {
            fl_voice *v = &s->v[k];
            if (--v->left <= 0) fl_note(r, v);
            v->x -= (v->eps * v->y) >> 15;
            v->y += (v->eps * v->x) >> 15;
            v->env = (v->env * v->decay) >> 16;
            int64_t a = (v->y * v->env) >> 17;
            sl += (a * (256 - v->pan)) >> 8;
            sr += (a * v->pan) >> 8;
        }
        int64_t white = (int64_t)(ib_next(r) >> 52) - 2048;
        s->lp += (white - s->lp) >> 3;
        sl += s->lp >> 2;
        sr += (s->lp + (white >> 4)) >> 2;
        L[i] = (int32_t)(sl > 32767 ? 32767 : (sl < -32768 ? -32768 : sl));
        R[i] = (int32_t)(sr > 32767 ? 32767 : (sr < -32768 ? -32768 : sr));
    }
}

/// Lossless audio compression, the class of FLAC: synthetic 16-bit audio
/// (decaying oscillator notes plus filtered noise, in stereo pairs) is
/// coded in 4096-sample frames: per pair the best of left/right,
/// left/side, right/side and mid/side; per channel the cheapest of
/// constant, verbatim, fixed predictors 0–4 and quantised LPC of every
/// order 1–12 (Welch window, autocorrelation and Levinson–Durbin in
/// double, 14-bit coefficients with error feedback); residuals Rice-coded
/// with a searched partition order. Each frame carries a CRC-16 and is
/// decoded at once and compared bit for bit. Size 1 is 2 channels × ~16 s
/// at 44.1 kHz; size 2 4 channels × ~44 s; size 3 6 channels × ~130 s.
/// The checksum covers the whole bitstream and the decoded samples.
int cbk_flac(int size, cb_bench_result *out) {
    size = ib_size(size);
    static const int pairs_t[4] = { 0, 1, 2, 3 };
    static const int frames_t[4] = { 0, 170, 470, 1400 };
    int pairs = pairs_t[size], nch = 2 * pairs, nframes = frames_t[size];
    int32_t *pcm = (int32_t *)malloc((size_t)nch * FL_BLOCK * sizeof(int32_t));
    int32_t *cand = (int32_t *)malloc((size_t)4 * FL_BLOCK * sizeof(int32_t));
    int32_t *dec = (int32_t *)malloc((size_t)2 * FL_BLOCK * sizeof(int32_t));
    int32_t *e = (int32_t *)malloc((size_t)FL_BLOCK * sizeof(int32_t));
    double *xw = (double *)malloc((size_t)FL_BLOCK * sizeof(double));
    fl_synth *syn = (fl_synth *)calloc((size_t)pairs, sizeof(fl_synth));
    fl_bw w;
    memset(&w, 0, sizeof w);
    int rc = 1;
    if (!pcm || !cand || !dec || !e || !xw || !syn) goto done;
    ib_rng r;
    ib_seed(&r, 0xF1ACULL + (uint64_t)size);
    for (int p = 0; p < pairs; p++)
        for (int k = 0; k < 3; k++) fl_note(&r, &syn[p].v[k]);
    uint64_t hs = IB_FNV_OFFSET, hd = IB_FNV_OFFSET, total = 0, tries = 0;
    rc = 2;
    for (int f = 0; f < nframes; f++) {
        int n = FL_BLOCK;
        for (int p = 0; p < pairs; p++)
            fl_synth_block(&r, &syn[p], pcm + (size_t)(2 * p) * n, pcm + (size_t)(2 * p + 1) * n, n);
        w.n = 0;
        w.bits = 0;
        fl_put(&w, 0xFFF8, 16);
        fl_put(&w, (uint32_t)f, 32);
        fl_put(&w, (uint32_t)n, 16);
        for (int p = 0; p < pairs; p++) {
            const int32_t *L = pcm + (size_t)(2 * p) * n, *R = L + n;
            int32_t *M = cand + 2 * n, *S = cand + 3 * n;
            for (int i = 0; i < n; i++) { M[i] = (L[i] + R[i]) >> 1; S[i] = L[i] - R[i]; }
            fl_plan pl, pr, pm, ps;
            fl_analyse(L, n, 16, &pl, e, xw, &tries);
            fl_analyse(R, n, 16, &pr, e, xw, &tries);
            fl_analyse(M, n, 16, &pm, e, xw, &tries);
            fl_analyse(S, n, 17, &ps, e, xw, &tries);
            uint64_t c[4] = { pl.bits + pr.bits, pl.bits + ps.bits, pr.bits + ps.bits, pm.bits + ps.bits };
            int mode = 0;
            for (int k = 1; k < 4; k++) if (c[k] < c[mode]) mode = k;
            fl_put(&w, (uint32_t)mode, 2);
            switch (mode) {
            case 0: fl_write_sub(&w, L, n, 16, &pl, e); fl_write_sub(&w, R, n, 16, &pr, e); break;
            case 1: fl_write_sub(&w, L, n, 16, &pl, e); fl_write_sub(&w, S, n, 17, &ps, e); break;
            case 2: fl_write_sub(&w, R, n, 16, &pr, e); fl_write_sub(&w, S, n, 17, &ps, e); break;
            default: fl_write_sub(&w, M, n, 16, &pm, e); fl_write_sub(&w, S, n, 17, &ps, e); break;
            }
        }
        fl_align(&w);
        uint16_t crc = fl_crc16(w.buf, w.n);
        fl_put(&w, crc, 16);
        if (w.oom) { rc = 1; goto done; }
        hs = ib_mix_bytes(hs, w.buf, w.n);
        total += w.n;

        // Decode the frame and compare with the input.
        fl_br br = { w.buf, w.n, 0, 0, 0, false };
        if (fl_crc16(w.buf, w.n - 2) != (uint16_t)(w.buf[w.n - 2] << 8 | w.buf[w.n - 1])) goto done;
        if (fl_get(&br, 16) != 0xFFF8 || fl_get(&br, 32) != (uint32_t)f) goto done;
        int dn = (int)fl_get(&br, 16);
        if (dn != n) goto done;
        for (int p = 0; p < pairs; p++) {
            int mode = (int)fl_get(&br, 2);
            int32_t *A = dec, *B = dec + n;
            if (!fl_read_sub(&br, A, n, 16)) goto done;
            if (!fl_read_sub(&br, B, n, mode == 0 ? 16 : 17)) goto done;
            const int32_t *L = pcm + (size_t)(2 * p) * n, *R = L + n;
            for (int i = 0; i < n; i++) {
                int32_t l, rr;
                switch (mode) {
                case 0: l = A[i]; rr = B[i]; break;
                case 1: l = A[i]; rr = A[i] - B[i]; break;
                case 2: rr = A[i]; l = A[i] + B[i]; break;
                default: {
                    int32_t mid = (int32_t)((uint32_t)A[i] << 1) | (B[i] & 1);
                    l = (mid + B[i]) >> 1;
                    rr = (mid - B[i]) >> 1;
                    break;
                }
                }
                if (l != L[i] || rr != R[i]) goto done;
                hd = ib_mix(hd, (uint64_t)(uint32_t)l << 32 | (uint32_t)rr);
            }
        }
    }
    hs = ib_mix(hs, total);
    hs = ib_mix(hs, hd);
    hs = ib_mix(hs, tries);
    ib_result(out, hs, (double)total, (double)nframes * FL_BLOCK * nch, "samples");
    rc = 0;
done:
    free(pcm); free(cand); free(dec); free(e); free(xw); free(syn); free(w.buf);
    return rc;
}
