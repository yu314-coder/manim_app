//
//  cb_bench_fp_b.c — the newer floating-point workloads of `spec`: texture
//  compression, colour management, mesh generation, flight dynamics, a
//  spiking neural network, transformer inference, smoothed particle
//  hydrodynamics and compressible hydrodynamics.
//
//  Each is a small but real program of its kind, written from scratch for
//  CodeBench; none of it comes from SPEC or any other suite. Every one is
//  reentrant (all state lives on the heap or on the caller's stack, and the
//  only statics are const tables) and deterministic: inputs come from a
//  xoshiro256** generator with a fixed seed and every sum is taken in a
//  fixed order, so the answer is the same at every optimisation level and
//  on every core.
//

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cb_bench.h"

#if defined(__aarch64__)
#include <arm_neon.h>
#endif

// Every floating-point operation in this file is rounded on its own: no
// multiply-add is fused unless the code asks for it (the matrix kernel
// does, explicitly). With contraction left to the compiler, -O0 fuses a
// reduction's a*b+c that the -Os vectorizer splits, and the answers part
// at the ninth digit; chaotic workloads (the spiking network, SPH) would
// part completely. This way the answers are the same at every
// optimisation level.
#pragma STDC FP_CONTRACT OFF

// ── Shared: random numbers, digests, noise ──────────────────────────────

/// xoshiro256** seeded through splitmix64: the same stream on every
/// machine, and private to the call that owns it.
typedef struct {
    uint64_t s[4];
} fb_rng;

static uint64_t fb_splitmix(uint64_t *x) {
    uint64_t z = (*x += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

static void fb_seed(fb_rng *r, uint64_t seed) {
    uint64_t x = seed;
    for (int i = 0; i < 4; i++) r->s[i] = fb_splitmix(&x);
}

static inline uint64_t fb_rotl(uint64_t x, int k) {
    return (x << k) | (x >> (64 - k));
}

static inline uint64_t fb_next(fb_rng *r) {
    uint64_t *s = r->s;
    uint64_t out = fb_rotl(s[1] * 5, 7) * 9;
    uint64_t t = s[1] << 17;
    s[2] ^= s[0];
    s[3] ^= s[1];
    s[1] ^= s[2];
    s[0] ^= s[3];
    s[2] ^= t;
    s[3] = fb_rotl(s[3], 45);
    return out;
}

/// Uniform in [0, 1), 53 random bits.
static inline double fb_u01(fb_rng *r) {
    return (double)(fb_next(r) >> 11) * 0x1.0p-53;
}

static inline double fb_range(fb_rng *r, double lo, double hi) {
    return lo + (hi - lo) * fb_u01(r);
}

/// Uniform integer in [0, n).
static inline uint32_t fb_below(fb_rng *r, uint32_t n) {
    return (uint32_t)(((fb_next(r) >> 32) * (uint64_t)n) >> 32);
}

/// Folds one word into a running 64-bit digest.
static inline uint64_t fb_digest(uint64_t h, uint64_t v) {
    h ^= v + 0x9E3779B97F4A7C15ull + (h << 6) + (h >> 2);
    h *= 0xFF51AFD7ED558CCDull;
    return h ^ (h >> 32);
}

static inline double fb_clamp(double v, double lo, double hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static inline uint32_t fb_hash3(uint32_t x, uint32_t y, uint32_t z) {
    uint32_t h = x * 0x8DA6B343u ^ y * 0xD8163841u ^ z * 0xCB1AB31Fu;
    h ^= h >> 16;
    h *= 0x7FEB352Du;
    h ^= h >> 15;
    h *= 0x846CA68Bu;
    h ^= h >> 16;
    return h;
}

/// Smooth value noise in [0, 1): a hashed lattice, interpolated bilinearly
/// with a smoothstep fade.
static double fb_noise(double x, double y, uint32_t seed) {
    double fx = floor(x), fy = floor(y);
    uint32_t ix = (uint32_t)(int32_t)fx, iy = (uint32_t)(int32_t)fy;
    double tx = x - fx, ty = y - fy;
    tx = tx * tx * (3.0 - 2.0 * tx);
    ty = ty * ty * (3.0 - 2.0 * ty);
    const double k = 1.0 / 4294967296.0;
    double a = fb_hash3(ix, iy, seed) * k, b = fb_hash3(ix + 1, iy, seed) * k;
    double c = fb_hash3(ix, iy + 1, seed) * k, d = fb_hash3(ix + 1, iy + 1, seed) * k;
    return a + (b - a) * tx + (c - a) * ty + (a - b - c + d) * tx * ty;
}

/// Fractal sum of `octaves` noise layers, normalised to [0, 1).
static double fb_fbm(double x, double y, int octaves, uint32_t seed) {
    double sum = 0, amp = 0.5, norm = 0;
    for (int o = 0; o < octaves; o++) {
        sum += amp * fb_noise(x, y, seed + 977u * (uint32_t)o);
        norm += amp;
        x = x * 2.03 + 17.1;
        y = y * 2.03 + 5.3;
        amp *= 0.5;
    }
    return sum / norm;
}

/// Grows a heap array to hold at least `need` elements (1.5x steps).
static int fb_grow(void **p, int *cap, int need, size_t elem) {
    if (need <= *cap) return 0;
    int nc = *cap > 0 ? *cap : 64;
    while (nc < need) nc += nc / 2 + 16;
    void *q = realloc(*p, (size_t)nc * elem);
    if (q == NULL) return 1;
    *p = q;
    *cap = nc;
    return 0;
}

// ── astc: texture block compression ─────────────────────────────────────

#define AS_MAXT 36  // texels in the largest block (6x6)
#define AS_NPAT 32  // partition patterns per partition count
#define AS_KEEP 2   // patterns per partition count that get a full encode

/// One block mode: partitions, weight levels, endpoint levels. Each table
/// holds three modes per partition count, sized to roughly 128 bits a block.
typedef struct {
    uint16_t parts, wlev, elev;
} as_mode;

static const as_mode kAsModes4[9] = {
    {1, 16, 64}, {1, 8, 256}, {1, 12, 128},
    {2, 4, 32},  {2, 3, 48},  {2, 6, 16},
    {3, 3, 16},  {3, 4, 10},  {3, 2, 24},
};
static const as_mode kAsModes6[9] = {
    {1, 4, 128}, {1, 3, 256}, {1, 5, 40},
    {2, 2, 64},  {2, 3, 24},  {2, 4, 12},
    {3, 2, 16},  {3, 2, 10},  {3, 3, 6},
};

typedef struct {
    int bw, bh, n;
    const as_mode *modes;
    uint8_t pat[2][AS_NPAT][AS_MAXT];  // [parts - 2][pattern][texel]
} as_ctx;

/// Partition patterns, generated like a hardware format's seed table: each
/// pattern is an anisotropic Voronoi split of the block around random
/// sites, every partition at least two texels, no two patterns alike.
static void as_make_patterns(as_ctx *cx) {
    fb_rng r;
    fb_seed(&r, 0xA57CB10Cull + (uint64_t)cx->bw);
    int n = cx->n;
    for (int pc = 2; pc <= 3; pc++) {
        uint8_t(*pat)[AS_MAXT] = cx->pat[pc - 2];
        for (int s = 0; s < AS_NPAT; s++) {
            for (;;) {
                double sx[3], sy[3], an[3];
                for (int k = 0; k < pc; k++) {
                    sx[k] = fb_u01(&r) * cx->bw;
                    sy[k] = fb_u01(&r) * cx->bh;
                    an[k] = 0.4 + 1.2 * fb_u01(&r);
                }
                int cnt[3] = {0, 0, 0};
                for (int t = 0; t < n; t++) {
                    double x = (t % cx->bw) + 0.5, y = (t / cx->bw) + 0.5;
                    int best = 0;
                    double bd = 0;
                    for (int k = 0; k < pc; k++) {
                        double dx = x - sx[k], dy = y - sy[k];
                        double d = dx * dx * an[k] + dy * dy / an[k];
                        if (k == 0 || d < bd) {
                            bd = d;
                            best = k;
                        }
                    }
                    pat[s][t] = (uint8_t)best;
                    cnt[best]++;
                }
                int ok = 1;
                for (int k = 0; k < pc; k++)
                    if (cnt[k] < 2) ok = 0;
                for (int q = 0; q < s && ok; q++)
                    if (memcmp(pat[q], pat[s], (size_t)n) == 0) ok = 0;
                if (ok) break;
            }
        }
    }
}

static inline int as_q_ep(double v, int levels) {
    double t = floor(v * (double)(levels - 1) / 255.0 + 0.5);
    if (t < 0) t = 0;
    if (t > levels - 1) t = levels - 1;
    return (int)t;
}

static inline int as_unq_ep(int q, int levels) {
    return (q * 255 + (levels - 1) / 2) / (levels - 1);
}

static inline int as_unq_w(int w, int levels) {
    return (w * 64 + (levels - 1) / 2) / (levels - 1);
}

static inline uint32_t as_texel_err(const int *c, const int *q0, const int *q1, int wv) {
    uint32_t e = 0;
    for (int ch = 0; ch < 4; ch++) {
        int v = (q0[ch] * (64 - wv) + q1[ch] * wv + 32) >> 6;
        int d = v - c[ch];
        e += (uint32_t)(d * d);
    }
    return e;
}

/// Principal axis of a texel subset by power iteration on its RGBA
/// covariance; the endpoints are the extreme projections onto it.
static void as_pca(const int (*c)[4], const uint8_t *idx, int m, double *e0, double *e1) {
    int64_t s[4] = {0, 0, 0, 0}, ss[4][4];
    memset(ss, 0, sizeof ss);
    for (int k = 0; k < m; k++) {
        const int *px = c[idx[k]];
        for (int i = 0; i < 4; i++) {
            s[i] += px[i];
            for (int j = i; j < 4; j++) ss[i][j] += px[i] * px[j];
        }
    }
    double mean[4], cov[4][4];
    double mm = (double)m * (double)m;
    for (int i = 0; i < 4; i++) mean[i] = (double)s[i] / (double)m;
    for (int i = 0; i < 4; i++)
        for (int j = i; j < 4; j++) {
            double v = (double)(ss[i][j] * m - s[i] * s[j]) / mm;
            cov[i][j] = v;
            cov[j][i] = v;
        }
    int b = 0;
    for (int i = 1; i < 4; i++)
        if (cov[i][i] > cov[b][b]) b = i;
    double v[4];
    for (int i = 0; i < 4; i++) v[i] = cov[b][b] > 0 ? cov[b][i] : 0.5;
    for (int it = 0; it < 8; it++) {
        double w[4], mx = 0;
        for (int i = 0; i < 4; i++) {
            w[i] = cov[i][0] * v[0] + cov[i][1] * v[1] + cov[i][2] * v[2] + cov[i][3] * v[3];
            if (fabs(w[i]) > mx) mx = fabs(w[i]);
        }
        if (mx <= 0) break;
        for (int i = 0; i < 4; i++) v[i] = w[i] / mx;
    }
    double len = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + v[3] * v[3]);
    for (int i = 0; i < 4; i++) v[i] /= len;
    double tmin = 0, tmax = 0;
    for (int k = 0; k < m; k++) {
        const int *px = c[idx[k]];
        double t = (px[0] - mean[0]) * v[0] + (px[1] - mean[1]) * v[1] +
                   (px[2] - mean[2]) * v[2] + (px[3] - mean[3]) * v[3];
        if (k == 0 || t < tmin) tmin = t;
        if (k == 0 || t > tmax) tmax = t;
    }
    for (int i = 0; i < 4; i++) {
        e0[i] = fb_clamp(mean[i] + tmin * v[i], 0, 255);
        e1[i] = fb_clamp(mean[i] + tmax * v[i], 0, 255);
    }
}

/// Encodes one subset at one quantisation: quantise the endpoints, pick
/// each texel's weight (projection, then the best of it and its two
/// neighbours by true decoded error), refit the endpoints by least squares
/// for those weights, and repeat twice. Writes the decoded texels.
static uint32_t as_fit_subset(const int (*c)[4], const uint8_t *idx, int m, int wlev, int elev,
                              const double *e0in, const double *e1in, uint8_t (*dec)[4]) {
    double e0[4], e1[4];
    int q0[4], q1[4];
    uint8_t w[AS_MAXT];
    uint32_t err = 0;
    memcpy(e0, e0in, sizeof e0);
    memcpy(e1, e1in, sizeof e1);
    for (int it = 0;; it++) {
        int d[4];
        int64_t dd = 0;
        for (int ch = 0; ch < 4; ch++) {
            q0[ch] = as_unq_ep(as_q_ep(e0[ch], elev), elev);
            q1[ch] = as_unq_ep(as_q_ep(e1[ch], elev), elev);
            d[ch] = q1[ch] - q0[ch];
            dd += d[ch] * d[ch];
        }
        err = 0;
        for (int k = 0; k < m; k++) {
            const int *px = c[idx[k]];
            int wi = 0;
            if (dd > 0) {
                int64_t dot = 0;
                for (int ch = 0; ch < 4; ch++) dot += (int64_t)(px[ch] - q0[ch]) * d[ch];
                int64_t num = 2 * dot * (wlev - 1) + dd;
                wi = num <= 0 ? 0 : (int)(num / (2 * dd));
                if (wi > wlev - 1) wi = wlev - 1;
            }
            int bw = wi;
            uint32_t be = as_texel_err(px, q0, q1, as_unq_w(wi, wlev));
            if (wi > 0) {
                uint32_t e = as_texel_err(px, q0, q1, as_unq_w(wi - 1, wlev));
                if (e < be) {
                    be = e;
                    bw = wi - 1;
                }
            }
            if (wi < wlev - 1) {
                uint32_t e = as_texel_err(px, q0, q1, as_unq_w(wi + 1, wlev));
                if (e < be) {
                    be = e;
                    bw = wi + 1;
                }
            }
            w[k] = (uint8_t)bw;
            err += be;
        }
        if (it == 2) break;
        // Least-squares endpoints for these weights (every term is exact).
        double a = 0, b = 0, cc = 0, r0[4] = {0, 0, 0, 0}, r1[4] = {0, 0, 0, 0};
        for (int k = 0; k < m; k++) {
            const int *px = c[idx[k]];
            double om = as_unq_w(w[k], wlev) / 64.0, im = 1.0 - om;
            a += im * im;
            b += im * om;
            cc += om * om;
            for (int ch = 0; ch < 4; ch++) {
                r0[ch] += im * px[ch];
                r1[ch] += om * px[ch];
            }
        }
        double det = a * cc - b * b;
        if (det < 1e-9) break;
        for (int ch = 0; ch < 4; ch++) {
            e0[ch] = fb_clamp((cc * r0[ch] - b * r1[ch]) / det, 0, 255);
            e1[ch] = fb_clamp((a * r1[ch] - b * r0[ch]) / det, 0, 255);
        }
    }
    for (int k = 0; k < m; k++) {
        int wv = as_unq_w(w[k], wlev);
        for (int ch = 0; ch < 4; ch++)
            dec[idx[k]][ch] = (uint8_t)((q0[ch] * (64 - wv) + q1[ch] * wv + 32) >> 6);
    }
    return err;
}

/// Integer k-means on the block's colours (exact arithmetic, so the
/// clustering never depends on rounding).
static void as_kmeans(const int (*c)[4], int n, int P, uint8_t *lab) {
    int seed[3] = {0, 0, 0};
    int lo = 0, hi = 0, slo = 1 << 30, shi = -1;
    for (int t = 0; t < n; t++) {
        int s = c[t][0] + c[t][1] + c[t][2] + c[t][3];
        if (s < slo) {
            slo = s;
            lo = t;
        }
        if (s > shi) {
            shi = s;
            hi = t;
        }
    }
    seed[0] = lo;
    seed[1] = hi;
    if (P == 3) {
        int64_t bestd = -1;
        for (int t = 0; t < n; t++) {
            int64_t d0 = 0, d1 = 0;
            for (int ch = 0; ch < 4; ch++) {
                int a = c[t][ch] - c[lo][ch], b = c[t][ch] - c[hi][ch];
                d0 += a * a;
                d1 += b * b;
            }
            int64_t d = d0 < d1 ? d0 : d1;
            if (d > bestd) {
                bestd = d;
                seed[2] = t;
            }
        }
    }
    int64_t sum[3][4], cnt[3];
    for (int k = 0; k < P; k++) {
        for (int ch = 0; ch < 4; ch++) sum[k][ch] = c[seed[k]][ch];
        cnt[k] = 1;
    }
    for (int it = 0; it < 4; it++) {
        for (int t = 0; t < n; t++) {
            int best = 0;
            int64_t bd = 0;
            for (int k = 0; k < P; k++) {
                int64_t d = 0;
                for (int ch = 0; ch < 4; ch++) {
                    int64_t e = (int64_t)c[t][ch] * cnt[k] - sum[k][ch];
                    d += e * e;
                }
                if (k == 0 || d * cnt[best] * cnt[best] < bd * cnt[k] * cnt[k]) {
                    best = k;
                    bd = d;
                }
            }
            lab[t] = (uint8_t)best;
        }
        int64_t ns[3][4], nc[3] = {0, 0, 0};
        memset(ns, 0, sizeof ns);
        for (int t = 0; t < n; t++) {
            nc[lab[t]]++;
            for (int ch = 0; ch < 4; ch++) ns[lab[t]][ch] += c[t][ch];
        }
        for (int k = 0; k < P; k++)
            if (nc[k] > 0) {
                cnt[k] = nc[k];
                memcpy(sum[k], ns[k], sizeof sum[k]);
            }
    }
}

/// The AS_KEEP patterns that best match a clustering, up to relabelling.
static void as_rank(const uint8_t (*pat)[AS_MAXT], int n, int P, const uint8_t *lab, int *keep) {
    static const uint8_t perm[6][3] = {{0, 1, 2}, {0, 2, 1}, {1, 0, 2}, {1, 2, 0}, {2, 0, 1}, {2, 1, 0}};
    int sc[AS_NPAT];
    for (int s = 0; s < AS_NPAT; s++) {
        int best = n;
        for (int q = 0; q < 6; q++) {
            if (P == 2 && q != 0 && q != 2) continue;
            int mism = 0;
            for (int t = 0; t < n; t++) mism += perm[q][pat[s][t]] != lab[t];
            if (mism < best) best = mism;
        }
        sc[s] = best;
    }
    for (int k = 0; k < AS_KEEP; k++) {
        int b = -1;
        for (int s = 0; s < AS_NPAT; s++)
            if (sc[s] >= 0 && (b < 0 || sc[s] < sc[b])) b = s;
        keep[k] = b;
        sc[b] = -1;
    }
}

/// Encodes one block: one partition, the best-matching two- and
/// three-partition patterns, each at three quantisations; keeps the
/// encoding with the lowest squared error.
static uint32_t as_encode_block(const as_ctx *cx, const int (*c)[4], uint8_t (*best)[4], uint32_t *choice) {
    static const uint8_t kZero[AS_MAXT] = {0};
    int n = cx->n;
    uint8_t lab[AS_MAXT];
    const uint8_t *cand[1 + 2 * AS_KEEP];
    int candP[1 + 2 * AS_KEEP], nc = 0;
    cand[nc] = kZero;
    candP[nc++] = 1;
    for (int P = 2; P <= 3; P++) {
        int keep[AS_KEEP];
        as_kmeans(c, n, P, lab);
        as_rank((const uint8_t(*)[AS_MAXT])cx->pat[P - 2], n, P, lab, keep);
        for (int k = 0; k < AS_KEEP; k++) {
            cand[nc] = cx->pat[P - 2][keep[k]];
            candP[nc++] = P;
        }
    }
    uint32_t bestErr = UINT32_MAX;
    uint8_t dec[AS_MAXT][4];
    for (int ci = 0; ci < nc && bestErr > 0; ci++) {
        int P = candP[ci];
        const uint8_t *pat = cand[ci];
        uint8_t idx[3][AS_MAXT];
        int m[3] = {0, 0, 0};
        for (int t = 0; t < n; t++) idx[pat[t]][m[pat[t]]++] = (uint8_t)t;
        double e0[3][4], e1[3][4];
        for (int p = 0; p < P; p++) as_pca(c, idx[p], m[p], e0[p], e1[p]);
        for (int mi = 0; mi < 9; mi++) {
            const as_mode *md = &cx->modes[mi];
            if (md->parts != P) continue;
            uint32_t err = 0;
            for (int p = 0; p < P; p++)
                err += as_fit_subset(c, idx[p], m[p], md->wlev, md->elev, e0[p], e1[p], dec);
            if (err < bestErr) {
                bestErr = err;
                memcpy(best, dec, (size_t)n * 4);
                *choice = (uint32_t)(ci * 16 + mi);
            }
        }
    }
    return bestErr;
}

/// Encodes the whole image in bs x bs blocks into `dec` (the decoded
/// image), then checks the decoded image against the source.
static int as_encode_image(const uint8_t *img, int W, int H, int bs, const as_mode *modes,
                           uint8_t *dec, uint64_t *errOut, uint64_t *digest) {
    as_ctx cx;
    cx.bw = cx.bh = bs;
    cx.n = bs * bs;
    cx.modes = modes;
    as_make_patterns(&cx);
    uint64_t err = 0, dg = *digest;
    int c[AS_MAXT][4];
    uint8_t best[AS_MAXT][4];
    for (int by = 0; by < H / bs; by++)
        for (int bx = 0; bx < W / bs; bx++) {
            for (int t = 0; t < cx.n; t++) {
                const uint8_t *p = img + ((size_t)(by * bs + t / bs) * W + (size_t)(bx * bs + t % bs)) * 4;
                for (int ch = 0; ch < 4; ch++) c[t][ch] = p[ch];
            }
            uint32_t choice = 0;
            err += as_encode_block(&cx, (const int(*)[4])c, best, &choice);
            dg = fb_digest(dg, choice);
            for (int t = 0; t < cx.n; t++) {
                uint8_t *p = dec + ((size_t)(by * bs + t / bs) * W + (size_t)(bx * bs + t % bs)) * 4;
                memcpy(p, best[t], 4);
            }
        }
    uint64_t e2 = 0;
    for (size_t i = 0; i < (size_t)W * H * 4; i++) {
        int d = (int)dec[i] - (int)img[i];
        e2 += (uint64_t)(d * d);
    }
    if (e2 != err) return 1;
    *errOut = err;
    *digest = dg;
    return 0;
}

/// A photo-like RGBA test image: a sky-to-ground gradient shaped by fractal
/// noise, soft-edged discs (some translucent) for hard edges and flat
/// regions, and per-pixel grain.
static void as_make_image(uint8_t *img, int W, int H) {
    fb_rng r;
    fb_seed(&r, 0xA57C1A6E5ull);
    enum { ND = 24 };
    double dx[ND], dy[ND], dr[ND], dc[ND][3], da[ND];
    for (int k = 0; k < ND; k++) {
        dx[k] = fb_u01(&r) * W;
        dy[k] = fb_u01(&r) * H;
        dr[k] = (0.02 + 0.08 * fb_u01(&r)) * W;
        for (int ch = 0; ch < 3; ch++) dc[k][ch] = 255.0 * fb_u01(&r);
        da[k] = fb_u01(&r) < 0.3 ? 0.5 : 1.0;
    }
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            double u = (x + 0.5) / W, v = (y + 0.5) / H;
            double n1 = fb_fbm(u * 6, v * 6, 5, 11);
            double n2 = fb_fbm(u * 20, v * 20, 3, 29);
            double col[3], alpha = 255;
            double horizon = 0.45 + 0.08 * (n1 - 0.5);
            if (v < horizon) {
                double s = v / horizon;
                col[0] = 60 + 140 * s + 30 * (n2 - 0.5);
                col[1] = 110 + 80 * s + 20 * (n2 - 0.5);
                col[2] = 200 - 20 * s + 20 * (n1 - 0.5);
            } else {
                col[0] = 70 + 110 * n1;
                col[1] = 70 + 80 * n2;
                col[2] = 30 + 50 * n1 * n2;
            }
            for (int k = 0; k < ND; k++) {
                double ex = x + 0.5 - dx[k], ey = y + 0.5 - dy[k];
                double rr = dr[k] + 1;
                if (ex * ex + ey * ey >= rr * rr) continue;
                double cov = fb_clamp(dr[k] - sqrt(ex * ex + ey * ey) + 0.5, 0, 1) * da[k];
                for (int ch = 0; ch < 3; ch++) col[ch] = col[ch] * (1 - cov) + dc[k][ch] * cov;
                if (da[k] < 1) alpha = alpha * (1 - 0.6 * cov);
            }
            double g = (double)(fb_hash3((uint32_t)x, (uint32_t)y, 7) & 15) - 7.5;
            uint8_t *p = img + ((size_t)y * W + x) * 4;
            for (int ch = 0; ch < 3; ch++) p[ch] = (uint8_t)floor(fb_clamp(col[ch] + g, 0, 255) + 0.5);
            p[3] = (uint8_t)floor(fb_clamp(alpha, 0, 255) + 0.5);
        }
}

/// Texture block compression in the style of ASTC and BC7 (the class of
/// astcenc): a photo-like RGBA image is encoded twice, in 4x4 blocks and in
/// 6x6 blocks. For each block the encoder clusters the colours, picks the
/// best-matching two- and three-partition patterns, finds each partition's
/// endpoints by power-iteration PCA on its colour covariance, then tries
/// three weight/endpoint quantisations per partition count with weight
/// search and least-squares endpoint refinement, keeping the encoding with
/// the lowest error. The decoded images are compared with the source.
/// `value` is the PSNR in dB over both encodings; `checksum` digests the
/// mode chosen for every block and the total squared errors. Sizes 1/2/3:
/// 480x360, 1152x864 and 2208x1656 images.
int cbk_astc(int size, cb_bench_result *out) {
    int W = size == 1 ? 480 : (size == 2 ? 1152 : 2208);
    int H = W / 4 * 3;
    uint8_t *img = malloc((size_t)W * H * 4);
    uint8_t *dec = malloc((size_t)W * H * 4);
    if (img == NULL || dec == NULL) {
        free(img);
        free(dec);
        return 1;
    }
    as_make_image(img, W, H);
    uint64_t err4 = 0, err6 = 0, digest = 0;
    int rc = as_encode_image(img, W, H, 4, kAsModes4, dec, &err4, &digest);
    if (rc == 0) rc = as_encode_image(img, W, H, 6, kAsModes6, dec, &err6, &digest);
    free(img);
    free(dec);
    if (rc != 0) return 2;
    double mse = (double)(err4 + err6) / (8.0 * W * H);
    out->value = 10.0 * log10(255.0 * 255.0 / mse);
    out->checksum = fb_digest(fb_digest(digest, err4), err6);
    out->work = 2.0 * W * H;
    out->unit = "texels";
    return 0;
}

// ── color: colour management for VFX ────────────────────────────────────

#define CM_LUT 33     // 3D LUT edge
#define CM_CHUNK 512  // pixels per pass through the op chain

typedef struct {
    double m[3][3];
} cm_m33;

static cm_m33 cm_mul(cm_m33 a, cm_m33 b) {
    cm_m33 c;
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            c.m[i][j] = a.m[i][0] * b.m[0][j] + a.m[i][1] * b.m[1][j] + a.m[i][2] * b.m[2][j];
    return c;
}

static cm_m33 cm_inv(cm_m33 a) {
    double (*m)[3] = a.m;
    cm_m33 r;
    r.m[0][0] = m[1][1] * m[2][2] - m[1][2] * m[2][1];
    r.m[0][1] = m[0][2] * m[2][1] - m[0][1] * m[2][2];
    r.m[0][2] = m[0][1] * m[1][2] - m[0][2] * m[1][1];
    r.m[1][0] = m[1][2] * m[2][0] - m[1][0] * m[2][2];
    r.m[1][1] = m[0][0] * m[2][2] - m[0][2] * m[2][0];
    r.m[1][2] = m[0][2] * m[1][0] - m[0][0] * m[1][2];
    r.m[2][0] = m[1][0] * m[2][1] - m[1][1] * m[2][0];
    r.m[2][1] = m[0][1] * m[2][0] - m[0][0] * m[2][1];
    r.m[2][2] = m[0][0] * m[1][1] - m[0][1] * m[1][0];
    double det = m[0][0] * r.m[0][0] + m[0][1] * r.m[1][0] + m[0][2] * r.m[2][0];
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) r.m[i][j] /= det;
    return r;
}

static void cm_xyz_of(double x, double y, double *v) {
    v[0] = x / y;
    v[1] = 1.0;
    v[2] = (1.0 - x - y) / y;
}

/// The normalised primary matrix (RGB to XYZ) of a colour space given its
/// primaries' and white point's xy chromaticities.
static cm_m33 cm_npm(const double *pr) {
    cm_m33 P;
    double w[3], v[3];
    for (int k = 0; k < 3; k++) {
        cm_xyz_of(pr[2 * k], pr[2 * k + 1], v);
        for (int i = 0; i < 3; i++) P.m[i][k] = v[i];
    }
    cm_xyz_of(pr[6], pr[7], w);
    cm_m33 Pi = cm_inv(P);
    for (int k = 0; k < 3; k++) {
        double s = Pi.m[k][0] * w[0] + Pi.m[k][1] * w[1] + Pi.m[k][2] * w[2];
        for (int i = 0; i < 3; i++) P.m[i][k] *= s;
    }
    return P;
}

/// Bradford chromatic adaptation between two white points (xy).
static cm_m33 cm_cat(const double *ws, const double *wd) {
    const cm_m33 B = {{{0.8951, 0.2664, -0.1614}, {-0.7502, 1.7135, 0.0367}, {0.0389, -0.0685, 1.0296}}};
    double s[3], d[3];
    cm_xyz_of(ws[0], ws[1], s);
    cm_xyz_of(wd[0], wd[1], d);
    cm_m33 D;
    memset(&D, 0, sizeof D);
    for (int i = 0; i < 3; i++) {
        double cs = B.m[i][0] * s[0] + B.m[i][1] * s[1] + B.m[i][2] * s[2];
        double cd = B.m[i][0] * d[0] + B.m[i][1] * d[1] + B.m[i][2] * d[2];
        D.m[i][i] = cd / cs;
    }
    return cm_mul(cm_inv(B), cm_mul(D, B));
}

static void cm_to_float(const cm_m33 *a, double gain, float *f) {
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) f[i * 3 + j] = (float)(a->m[i][j] * gain);
}

// A camera log curve (this suite's own): y = A log2(x + B) + C.
#define CM_LA 0.075
#define CM_LB 0.02
#define CM_LC 0.62

static double cm_cct_from_lin(double x) {
    return x <= 0.0078125 ? 10.5402377416545 * x + 0.0729055341958355 : (log2(x) + 9.72) / 17.52;
}

static double cm_lin_from_cct(double y) {
    if (y <= 0.155251141552511) return (y - 0.0729055341958355) / 10.5402377416545;
    return exp2(y * 17.52 - 9.72);
}

/// The creative look baked into the 3D LUT: hue-dependent saturation, a
/// contrast curve about mid grey, and a teal/orange split tone, all on
/// AP1 linear values; input and output are ACEScct-encoded.
static void cm_look(double *rgb) {
    double r = cm_lin_from_cct(rgb[0]), g = cm_lin_from_cct(rgb[1]), b = cm_lin_from_cct(rgb[2]);
    double Y = 0.2722287168 * r + 0.6740817658 * g + 0.0536895174 * b;
    double oa = r - 0.5 * (g + b), ob = 0.8660254037844386 * (g - b);
    double hue = atan2(ob, oa);
    double sat = 1.12 + 0.18 * cos(hue - 0.5);
    double Yc = Y > 1e-6 ? 0.18 * pow(Y / 0.18, 1.08) : Y;
    double k = Y > 1e-6 ? Yc / Y : 1.0;
    double ts = 1.0 / (1.0 + (Y / 0.05) * (Y / 0.05)), th = Y * Y / (Y * Y + 1.0);
    double o[3] = {(Yc + sat * (r - Y) * k) * (1.0 - 0.04 * ts + 0.05 * th),
                   (Yc + sat * (g - Y) * k) * (1.0 + 0.01 * ts + 0.01 * th),
                   (Yc + sat * (b - Y) * k) * (1.0 + 0.05 * ts - 0.06 * th)};
    for (int i = 0; i < 3; i++) rgb[i] = cm_cct_from_lin(o[i] > -0.0068 ? o[i] : -0.0068);
}

static void cm_build_lut(float *lut) {
    for (int ri = 0; ri < CM_LUT; ri++)
        for (int gi = 0; gi < CM_LUT; gi++)
            for (int bi = 0; bi < CM_LUT; bi++) {
                double v[3] = {ri / (CM_LUT - 1.0), gi / (CM_LUT - 1.0), bi / (CM_LUT - 1.0)};
                cm_look(v);
                float *o = lut + ((size_t)(ri * CM_LUT + gi) * CM_LUT + bi) * 3;
                for (int i = 0; i < 3; i++) o[i] = (float)v[i];
            }
}

/// A camera plate: scene-linear values in a wide camera gamut (sky, an HDR
/// sun, textured ground, saturated lights well outside Rec.709), stored as
/// the camera's log encoding the way plates arrive at a VFX facility.
static void cm_make_plate(float *img, int W, int H) {
    fb_rng r;
    fb_seed(&r, 0xC0102ACEull);
    enum { ND = 16 };
    double dx[ND], dy[ND], dr[ND], dc[ND][3];
    static const double kLights[4][3] = {{0.02, 1.6, 0.1}, {0.03, 0.05, 1.2}, {1.4, 0.05, 0.02}, {1.1, 0.9, 0.05}};
    for (int k = 0; k < ND; k++) {
        dx[k] = fb_u01(&r);
        dy[k] = 0.3 + 0.7 * fb_u01(&r);
        dr[k] = 0.01 + 0.05 * fb_u01(&r);
        double s = 0.3 + 3.0 * fb_u01(&r);
        for (int ch = 0; ch < 3; ch++) dc[k][ch] = kLights[k & 3][ch] * s;
    }
    double aspect = (double)H / W;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            double u = (x + 0.5) / W, v = (y + 0.5) / H;
            double n1 = fb_fbm(u * 8, v * 8 * aspect, 4, 101);
            double n2 = fb_noise(u * W / 3.0, v * H / 3.0, 202);
            double c[3];
            if (v < 0.5 + 0.06 * (n1 - 0.5)) {
                double s = 1.4 - v;
                double sun = 40.0 * exp(-((u - 0.72) * (u - 0.72) + (v - 0.18) * (v - 0.18)) / 0.0006);
                c[0] = 0.18 * s + sun;
                c[1] = 0.26 * s + 0.9 * sun;
                c[2] = 0.48 * s + 0.7 * sun;
            } else {
                c[0] = 0.06 + 0.08 * n1;
                c[1] = 0.05 + 0.05 * n1;
                c[2] = 0.03 + 0.02 * n2;
            }
            for (int k = 0; k < ND; k++) {
                double ex = u - dx[k], ey = (v - dy[k]) * aspect;
                double d2 = (ex * ex + ey * ey) / (dr[k] * dr[k]);
                if (d2 >= 4.0) continue;
                double w = d2 < 1.0 ? 1.0 : 1.0 - (d2 - 1.0) / 3.0;
                for (int ch = 0; ch < 3; ch++) c[ch] = c[ch] * (1 - w) + dc[k][ch] * w;
            }
            float *p = img + ((size_t)y * W + x) * 3;
            for (int ch = 0; ch < 3; ch++) {
                double lin = c[ch] * (0.97 + 0.06 * n2);
                p[ch] = (float)(CM_LA * log2(lin + CM_LB) + CM_LC);
            }
        }
}

// The op chain. Like an OCIO CPU processor, each op runs over a whole
// chunk of pixels before the next op starts.

static void cm_op_logdecode(float *px, int n) {
    const float k = (float)(1.0 / CM_LA), c = (float)CM_LC, b = (float)CM_LB;
    for (int i = 0; i < 3 * n; i++) px[i] = exp2f((px[i] - c) * k) - b;
}

static void cm_op_matrix(float *px, int n, const float *m) {
    for (int i = 0; i < n; i++) {
        float r = px[3 * i], g = px[3 * i + 1], b = px[3 * i + 2];
        px[3 * i] = m[0] * r + m[1] * g + m[2] * b;
        px[3 * i + 1] = m[3] * r + m[4] * g + m[5] * b;
        px[3 * i + 2] = m[6] * r + m[7] * g + m[8] * b;
    }
}

/// ASC CDL: slope, offset, power per channel, then saturation.
static void cm_op_cdl(float *px, int n, const float *slope, const float *offset, const float *power, float sat) {
    for (int i = 0; i < n; i++) {
        float *p = px + 3 * i;
        for (int ch = 0; ch < 3; ch++) {
            float v = p[ch] * slope[ch] + offset[ch];
            p[ch] = v > 0 ? powf(v, power[ch]) : 0.0f;
        }
        float luma = 0.2126f * p[0] + 0.7152f * p[1] + 0.0722f * p[2];
        for (int ch = 0; ch < 3; ch++) p[ch] = luma + sat * (p[ch] - luma);
    }
}

static void cm_op_to_cct(float *px, int n) {
    for (int i = 0; i < 3 * n; i++) {
        float x = px[i];
        px[i] = x <= 0.0078125f ? 10.5402377416545f * x + 0.0729055341958355f : (log2f(x) + 9.72f) / 17.52f;
    }
}

static void cm_op_from_cct(float *px, int n) {
    for (int i = 0; i < 3 * n; i++) {
        float y = px[i];
        px[i] = y <= 0.155251141552511f ? (y - 0.0729055341958355f) / 10.5402377416545f : exp2f(y * 17.52f - 9.72f);
    }
}

/// 3D LUT with tetrahedral interpolation: the unit cube cell around the
/// input is split into six tetrahedra along its main diagonal and the
/// output blends the four corners of the one holding the point.
static void cm_op_lut(float *px, int n, const float *lut) {
    const float scale = (float)(CM_LUT - 1);
    const int sr = CM_LUT * CM_LUT * 3, sg = CM_LUT * 3, sb = 3;
    for (int i = 0; i < n; i++) {
        float *p = px + 3 * i;
        float f[3];
        int ix[3];
        for (int ch = 0; ch < 3; ch++) {
            float v = p[ch] < 0 ? 0.0f : (p[ch] > 1 ? 1.0f : p[ch]);
            v *= scale;
            int k = (int)v;
            if (k > CM_LUT - 2) k = CM_LUT - 2;
            ix[ch] = k;
            f[ch] = v - (float)k;
        }
        const float *c000 = lut + ix[0] * sr + ix[1] * sg + ix[2] * sb;
        const float *c111 = c000 + sr + sg + sb;
        const float *ca, *cb;
        float fa, fb, fc;  // largest, middle, smallest fraction
        float fr = f[0], fg = f[1], fbl = f[2];
        if (fr > fg) {
            if (fg > fbl) {
                ca = c000 + sr; cb = c000 + sr + sg; fa = fr; fb = fg; fc = fbl;
            } else if (fr > fbl) {
                ca = c000 + sr; cb = c000 + sr + sb; fa = fr; fb = fbl; fc = fg;
            } else {
                ca = c000 + sb; cb = c000 + sr + sb; fa = fbl; fb = fr; fc = fg;
            }
        } else {
            if (fbl > fg) {
                ca = c000 + sb; cb = c000 + sg + sb; fa = fbl; fb = fg; fc = fr;
            } else if (fbl > fr) {
                ca = c000 + sg; cb = c000 + sg + sb; fa = fg; fb = fbl; fc = fr;
            } else {
                ca = c000 + sg; cb = c000 + sr + sg; fa = fg; fb = fr; fc = fbl;
            }
        }
        for (int ch = 0; ch < 3; ch++)
            p[ch] = c000[ch] + fa * (ca[ch] - c000[ch]) + fb * (cb[ch] - ca[ch]) + fc * (c111[ch] - cb[ch]);
    }
}

/// A filmic tone curve: a rational toe and shoulder, scene linear in,
/// display linear out, approaching 1 for very bright input.
static void cm_op_tonemap(float *px, int n) {
    const float a = 1.8f, b = 0.06f, c = 0.66f, d = 0.15f;
    for (int i = 0; i < 3 * n; i++) {
        float x = px[i];
        px[i] = x > 0 ? x * (a * x + b) / (x * (a * x + c) + d) : x * (b / d);
    }
}

/// Gamut mapping: each channel's distance from the achromatic axis is
/// compressed smoothly past a threshold so out-of-gamut (negative) values
/// land just inside the target gamut instead of clipping.
static void cm_op_gamut(float *px, int n) {
    const float thr = 0.8f, s = 0.2f;
    for (int i = 0; i < n; i++) {
        float *p = px + 3 * i;
        float ach = p[0] > p[1] ? p[0] : p[1];
        if (p[2] > ach) ach = p[2];
        if (ach <= 0) continue;
        for (int ch = 0; ch < 3; ch++) {
            float dist = (ach - p[ch]) / ach;
            if (dist > thr) {
                float e = (dist - thr) / s;
                dist = thr + s * e / sqrtf(1.0f + e * e);
                p[ch] = ach - dist * ach;
            }
        }
    }
}

static void cm_op_srgb(float *px, int n) {
    for (int i = 0; i < 3 * n; i++) {
        float x = px[i] < 0 ? 0.0f : (px[i] > 1 ? 1.0f : px[i]);
        px[i] = x <= 0.0031308f ? 12.92f * x : 1.055f * powf(x, 1.0f / 2.4f) - 0.055f;
    }
}

/// Colour management for VFX (the class of OpenColorIO): a log-encoded
/// camera plate goes through a grading pipeline for a sequence of frames:
/// log to linear, exposure and camera-to-ACES (AP0) and AP0-to-AP1
/// matrices built from primaries with Bradford adaptation, an ASC CDL
/// grade keyed per frame, a 33^3 3D LUT look applied in ACEScct with
/// tetrahedral interpolation, a filmic tone curve, AP1-to-Rec.709, gamut
/// compression and the sRGB encoding. `value` is meanR + 2 meanG + 4 meanB
/// of the display-referred output over all frames (weighted so a channel
/// swap shows). Sizes 1/2/3: a 960x540 plate for 6 frames, 1920x1080 for
/// 9 frames and 1920x1080 for 38 frames.
int cbk_color(int size, cb_bench_result *out) {
    int W = size == 1 ? 960 : 1920, H = size == 1 ? 540 : 1080;
    int frames = size == 1 ? 6 : (size == 2 ? 9 : 38);
    size_t npix = (size_t)W * H;
    float *plate = malloc(npix * 3 * sizeof(float));
    float *disp = malloc(npix * 3 * sizeof(float));
    float *lut = malloc((size_t)CM_LUT * CM_LUT * CM_LUT * 3 * sizeof(float));
    if (plate == NULL || disp == NULL || lut == NULL) {
        free(plate);
        free(disp);
        free(lut);
        return 1;
    }
    static const double kAP0[8] = {0.7347, 0.2653, 0.0, 1.0, 0.0001, -0.0770, 0.32168, 0.33767};
    static const double kAP1[8] = {0.713, 0.293, 0.165, 0.830, 0.128, 0.044, 0.32168, 0.33767};
    static const double k709[8] = {0.64, 0.33, 0.30, 0.60, 0.15, 0.06, 0.3127, 0.3290};
    static const double kCam[8] = {0.73, 0.28, 0.14, 0.86, 0.10, -0.03, 0.3127, 0.3290};
    cm_m33 camToAp0 = cm_mul(cm_inv(cm_npm(kAP0)), cm_mul(cm_cat(kCam + 6, kAP0 + 6), cm_npm(kCam)));
    cm_m33 ap0ToAp1 = cm_mul(cm_inv(cm_npm(kAP1)), cm_npm(kAP0));
    cm_m33 ap1To709 = cm_mul(cm_inv(cm_npm(k709)), cm_mul(cm_cat(kAP1 + 6, k709 + 6), cm_npm(kAP1)));
    float mA1[9], m709[9];
    cm_to_float(&ap0ToAp1, 1.0, mA1);
    cm_to_float(&ap1To709, 1.0, m709);
    cm_build_lut(lut);
    cm_make_plate(plate, W, H);

    double sum[3] = {0, 0, 0};
    for (int f = 0; f < frames; f++) {
        float mCam[9], slope[3], offset[3], power[3];
        cm_to_float(&camToAp0, exp2(0.3 * sin(0.7 * f)), mCam);
        slope[0] = (float)(1.05 + 0.03 * sin(f));
        slope[1] = 1.0f;
        slope[2] = (float)(0.97 - 0.02 * cos(f));
        offset[0] = 0.002f;
        offset[1] = 0.0f;
        offset[2] = (float)(-0.003 + 0.001 * sin(1.3 * f));
        power[0] = 0.95f;
        power[1] = (float)(1.0 + 0.02 * sin(0.5 * f));
        power[2] = 1.04f;
        float sat = (float)(1.1 - 0.05 * cos(0.9 * f));
        for (size_t p0 = 0; p0 < npix; p0 += CM_CHUNK) {
            int n = npix - p0 < CM_CHUNK ? (int)(npix - p0) : CM_CHUNK;
            float *px = disp + p0 * 3;
            memcpy(px, plate + p0 * 3, (size_t)n * 3 * sizeof(float));
            cm_op_logdecode(px, n);
            cm_op_matrix(px, n, mCam);
            cm_op_matrix(px, n, mA1);
            cm_op_cdl(px, n, slope, offset, power, sat);
            cm_op_to_cct(px, n);
            cm_op_lut(px, n, lut);
            cm_op_from_cct(px, n);
            cm_op_tonemap(px, n);
            cm_op_matrix(px, n, m709);
            cm_op_gamut(px, n);
            cm_op_srgb(px, n);
            double cs[3] = {0, 0, 0};
            for (int i = 0; i < n; i++)
                for (int ch = 0; ch < 3; ch++) cs[ch] += px[3 * i + ch];
            for (int ch = 0; ch < 3; ch++) sum[ch] += cs[ch];
        }
    }
    free(plate);
    free(disp);
    free(lut);
    double cnt = (double)npix * frames;
    out->value = sum[0] / cnt + 2.0 * sum[1] / cnt + 4.0 * sum[2] / cnt;
    out->checksum = 0;
    out->work = cnt;
    out->unit = "pixels";
    return 0;
}

// ── delaunay: mesh generation ───────────────────────────────────────────

// Every vertex lies on a grid of 2^-24 in the unit square. That makes the
// orientation test exact in double, and lets the in-circle test fall back
// to exact 128-bit integers when its double result is too close to call,
// so every combinatorial decision is exact on any compiler.
#define DL_G 16777216.0

typedef struct {
    int v[3];  // counter-clockwise
    int n[3];  // n[i]: the triangle across the edge opposite v[i], -1 on the hull
} dl_tri;

typedef struct {
    int a, b, out, oe, slot;
} dl_edge;

typedef struct {
    double *x, *y;
    int nv, capv;
    dl_tri *t;
    uint32_t *mark;
    int nt, capt;
    uint32_t stamp;
    int *stack, *cav;
    int capstack, capcav, ncav;
    dl_edge *bnd;
    int capbnd, nbnd;
    int hint;
} dl_mesh;

static inline double dl_orient(double ax, double ay, double bx, double by, double cx, double cy) {
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

/// > 0 when (px, py) is strictly inside the circumcircle of the
/// counter-clockwise triangle (a, b, c); a filtered, exact predicate.
static int dl_incircle(const double *x, const double *y, int a, int b, int c, double px, double py) {
    double adx = x[a] - px, ady = y[a] - py;
    double bdx = x[b] - px, bdy = y[b] - py;
    double cdx = x[c] - px, cdy = y[c] - py;
    double bc = bdx * cdy - cdx * bdy;
    double ca = cdx * ady - adx * cdy;
    double ab = adx * bdy - bdx * ady;
    double al = adx * adx + ady * ady;
    double bl = bdx * bdx + bdy * bdy;
    double cl = cdx * cdx + cdy * cdy;
    double det = al * bc + bl * ca + cl * ab;
    double eb = 1e-14 * (al * fabs(bc) + bl * fabs(ca) + cl * fabs(ab));
    if (det > eb) return 1;
    if (det < -eb) return -1;
    int64_t iax = (int64_t)(adx * DL_G), iay = (int64_t)(ady * DL_G);
    int64_t ibx = (int64_t)(bdx * DL_G), iby = (int64_t)(bdy * DL_G);
    int64_t icx = (int64_t)(cdx * DL_G), icy = (int64_t)(cdy * DL_G);
    int64_t ibc = ibx * icy - icx * iby, ica = icx * iay - iax * icy, iab = iax * iby - ibx * iay;
    int64_t ial = iax * iax + iay * iay, ibl = ibx * ibx + iby * iby, icl = icx * icx + icy * icy;
    __int128 d = (__int128)ial * ibc + (__int128)ibl * ica + (__int128)icl * iab;
    return d > 0 ? 1 : (d < 0 ? -1 : 0);
}

static int dl_reserve_v(dl_mesh *m, int need) {
    if (need <= m->capv) return 0;
    int cap = m->capv;
    if (fb_grow((void **)&m->x, &cap, need, sizeof(double))) return 1;
    cap = m->capv;
    if (fb_grow((void **)&m->y, &cap, need, sizeof(double))) return 1;
    m->capv = cap;
    return 0;
}

static int dl_reserve_t(dl_mesh *m, int need) {
    if (need <= m->capt) return 0;
    int cap = m->capt, old = m->capt;
    if (fb_grow((void **)&m->t, &cap, need, sizeof(dl_tri))) return 1;
    cap = m->capt;
    if (fb_grow((void **)&m->mark, &cap, need, sizeof(uint32_t))) return 1;
    memset(m->mark + old, 0, (size_t)(cap - old) * sizeof(uint32_t));
    m->capt = cap;
    return 0;
}

/// Walks from triangle t towards p by orientation tests (a visibility
/// walk, which terminates on a Delaunay triangulation). Returns the
/// triangle holding p, or the hull triangle where p leaves the domain with
/// *hull_edge set to the edge crossed; -1 if the walk does not end.
static int dl_locate(const dl_mesh *m, double px, double py, int t, int *hull_edge) {
    const double *x = m->x, *y = m->y;
    for (int k = 0; k <= m->nt + 16; k++) {
        const dl_tri *T = &m->t[t];
        int next = -2;
        for (int e = 0; e < 3; e++) {
            int i = (e + k) % 3;
            int a = T->v[(i + 1) % 3], b = T->v[(i + 2) % 3];
            if (dl_orient(x[a], y[a], x[b], y[b], px, py) < 0) {
                next = T->n[i];
                if (next < 0) {
                    *hull_edge = i;
                    return t;
                }
                break;
            }
        }
        if (next == -2) {
            *hull_edge = -1;
            return t;
        }
        t = next;
    }
    return -1;
}

/// The Bowyer–Watson cavity of p: the triangles whose circumcircles hold
/// it, grown from t0 across shared edges, and the cavity's boundary edges.
static int dl_cavity(dl_mesh *m, double px, double py, int t0) {
    uint32_t in = (m->stamp += 2), outm = in + 1;
    int sp = 0;
    m->ncav = 0;
    m->nbnd = 0;
    if (fb_grow((void **)&m->stack, &m->capstack, 1, sizeof(int))) return -1;
    m->stack[sp++] = t0;
    m->mark[t0] = in;
    while (sp > 0) {
        int c = m->stack[--sp];
        if (fb_grow((void **)&m->cav, &m->capcav, m->ncav + 1, sizeof(int))) return -1;
        m->cav[m->ncav++] = c;
        for (int i = 0; i < 3; i++) {
            int nb = m->t[c].n[i];
            if (nb >= 0) {
                uint32_t mk = m->mark[nb];
                if (mk == in) continue;
                if (mk != outm) {
                    const int *v = m->t[nb].v;
                    if (dl_incircle(m->x, m->y, v[0], v[1], v[2], px, py) > 0) {
                        m->mark[nb] = in;
                        if (fb_grow((void **)&m->stack, &m->capstack, sp + 1, sizeof(int))) return -1;
                        m->stack[sp++] = nb;
                        continue;
                    }
                    m->mark[nb] = outm;
                }
            }
            if (fb_grow((void **)&m->bnd, &m->capbnd, m->nbnd + 1, sizeof(dl_edge))) return -1;
            dl_edge *e = &m->bnd[m->nbnd++];
            e->a = m->t[c].v[(i + 1) % 3];
            e->b = m->t[c].v[(i + 2) % 3];
            e->out = nb;
            e->oe = -1;
            if (nb >= 0)
                for (int j = 0; j < 3; j++)
                    if (m->t[nb].n[j] == c) e->oe = j;
        }
    }
    return 0;
}

/// Replaces the cavity by a fan of triangles around the new vertex p. A
/// hull edge that p lies on is split instead of fanned. 0 on success,
/// -1 on an inconsistent cavity, -2 when out of memory.
static int dl_commit(dl_mesh *m, double px, double py) {
    int p = m->nv, nn = 0;
    for (int k = 0; k < m->nbnd; k++) {
        dl_edge *e = &m->bnd[k];
        double o = dl_orient(m->x[e->a], m->y[e->a], m->x[e->b], m->y[e->b], px, py);
        if (o > 0) {
            e->slot = 0;
            nn++;
        } else if (o == 0 && e->out < 0) {
            e->slot = -1;
        } else {
            return -1;
        }
    }
    if (nn < m->ncav) return -1;
    if (dl_reserve_v(m, p + 1) || dl_reserve_t(m, m->nt + nn - m->ncav)) return -2;
    m->x[p] = px;
    m->y[p] = py;
    m->nv = p + 1;
    int used = 0;
    for (int k = 0; k < m->nbnd; k++) {
        dl_edge *e = &m->bnd[k];
        if (e->slot < 0) continue;
        int s = used < m->ncav ? m->cav[used] : m->nt++;
        used++;
        e->slot = s;
        dl_tri *T = &m->t[s];
        T->v[0] = e->a;
        T->v[1] = e->b;
        T->v[2] = p;
        T->n[0] = T->n[1] = -1;
        T->n[2] = e->out;
        if (e->out >= 0) m->t[e->out].n[e->oe] = s;
    }
    for (int k = 0; k < m->nbnd; k++) {
        const dl_edge *e = &m->bnd[k];
        if (e->slot < 0) continue;
        dl_tri *T = &m->t[e->slot];
        for (int q = 0; q < m->nbnd; q++) {
            const dl_edge *f = &m->bnd[q];
            if (q == k || f->slot < 0) continue;
            if (f->a == e->b) T->n[0] = f->slot;
            if (f->b == e->a) T->n[1] = f->slot;
        }
        m->hint = e->slot;
    }
    return 0;
}

/// Inserts a point: 0 inserted, 1 skipped (a duplicate or outside), < 0 error.
static int dl_insert(dl_mesh *m, double px, double py) {
    int he, t = dl_locate(m, px, py, m->hint, &he);
    if (t < 0) return -1;
    if (he >= 0) return 1;
    for (int k = 0; k < 3; k++) {
        int v = m->t[t].v[k];
        if (m->x[v] == px && m->y[v] == py) return 1;
    }
    if (dl_cavity(m, px, py, t)) return -2;
    return dl_commit(m, px, py);
}

/// Splits hull edge i of triangle s at its grid midpoint (Ruppert's answer
/// to an encroached boundary segment).
static int dl_split_hull(dl_mesh *m, int s, int i) {
    int a = m->t[s].v[(i + 1) % 3], b = m->t[s].v[(i + 2) % 3];
    int64_t ax = (int64_t)(m->x[a] * DL_G), ay = (int64_t)(m->y[a] * DL_G);
    int64_t bx = (int64_t)(m->x[b] * DL_G), by = (int64_t)(m->y[b] * DL_G);
    int64_t len = (bx > ax ? bx - ax : ax - bx) + (by > ay ? by - ay : ay - by);
    if (len < 2) return 1;
    double px = (double)((ax + bx) / 2) / DL_G, py = (double)((ay + by) / 2) / DL_G;
    if (dl_cavity(m, px, py, s)) return -2;
    return dl_commit(m, px, py);
}

/// Ruppert's quality test, exactly: the smallest angle (the one opposite
/// the shortest edge) is under 20.7 degrees, i.e. sin^2 < 1/8. Triangles
/// whose shortest edge is under the size floor are left alone.
static int dl_bad(const dl_mesh *m, int t, int64_t minlen2) {
    const int *v = m->t[t].v;
    int64_t X[3], Y[3], L[3];
    for (int k = 0; k < 3; k++) {
        X[k] = (int64_t)(m->x[v[k]] * DL_G);
        Y[k] = (int64_t)(m->y[v[k]] * DL_G);
    }
    for (int k = 0; k < 3; k++) {
        int a = (k + 1) % 3, b = (k + 2) % 3;
        int64_t dx = X[b] - X[a], dy = Y[b] - Y[a];
        L[k] = dx * dx + dy * dy;
    }
    int k = 0;
    if (L[1] < L[k]) k = 1;
    if (L[2] < L[k]) k = 2;
    if (L[k] < minlen2) return 0;
    int a = (k + 1) % 3, b = (k + 2) % 3;
    int64_t ux = X[a] - X[k], uy = Y[a] - Y[k], wx = X[b] - X[k], wy = Y[b] - Y[k];
    int64_t cr = ux * wy - uy * wx;
    return (__int128)cr * cr * 8 < (__int128)L[b] * L[a];
}

/// Refines one bad triangle: inserts its circumcentre (snapped to the
/// grid), unless the centre is outside the domain or encroaches a boundary
/// segment of its cavity, in which case that segment is split instead.
static int dl_refine(dl_mesh *m, int t) {
    const int *v = m->t[t].v;
    double ax = m->x[v[0]], ay = m->y[v[0]];
    double bx = m->x[v[1]] - ax, by = m->y[v[1]] - ay;
    double cx = m->x[v[2]] - ax, cy = m->y[v[2]] - ay;
    double d = 2.0 * (bx * cy - by * cx);
    double b2 = bx * bx + by * by, c2 = cx * cx + cy * cy;
    double ux = ax + (cy * b2 - by * c2) / d, uy = ay + (bx * c2 - cx * b2) / d;
    double sx = floor(ux * DL_G + 0.5) / DL_G, sy = floor(uy * DL_G + 0.5) / DL_G;
    int he, lt = dl_locate(m, sx, sy, t, &he);
    if (lt < 0) return -1;
    if (he >= 0) return dl_split_hull(m, lt, he);
    for (int k = 0; k < 3; k++) {
        int w = m->t[lt].v[k];
        if (m->x[w] == sx && m->y[w] == sy) return 1;
    }
    if (dl_cavity(m, sx, sy, lt)) return -2;
    for (int c = 0; c < m->ncav; c++) {
        const dl_tri *T = &m->t[m->cav[c]];
        for (int i = 0; i < 3; i++) {
            if (T->n[i] >= 0) continue;
            int a = T->v[(i + 1) % 3], b = T->v[(i + 2) % 3];
            if ((m->x[a] - sx) * (m->x[b] - sx) + (m->y[a] - sy) * (m->y[b] - sy) <= 0)
                return dl_split_hull(m, m->cav[c], i);
        }
    }
    return dl_commit(m, sx, sy);
}

static uint64_t dl_hilbert(uint32_t x, uint32_t y) {
    const uint32_t n = 1u << 16;
    uint64_t d = 0;
    for (uint32_t s = n / 2; s > 0; s /= 2) {
        uint32_t rx = (x & s) > 0, ry = (y & s) > 0;
        d += (uint64_t)s * s * ((3 * rx) ^ ry);
        if (ry == 0) {
            if (rx == 1) {
                x = n - 1 - x;
                y = n - 1 - y;
            }
            uint32_t t = x;
            x = y;
            y = t;
        }
    }
    return d;
}

typedef struct {
    uint64_t key;
    int64_t X, Y;
} dl_pt;

static int dl_cmp(const void *a, const void *b) {
    uint64_t ka = ((const dl_pt *)a)->key, kb = ((const dl_pt *)b)->key;
    return ka < kb ? -1 : (ka > kb ? 1 : 0);
}

static void dl_put(dl_pt *p, int idx, double x, double y) {
    int64_t X = (int64_t)floor(x * DL_G + 0.5), Y = (int64_t)floor(y * DL_G + 0.5);
    if (X < 0) X = 0;
    if (X > (int64_t)DL_G) X = (int64_t)DL_G;
    if (Y < 0) Y = 0;
    if (Y > (int64_t)DL_G) Y = (int64_t)DL_G;
    uint32_t hx = (uint32_t)(X >> 8), hy = (uint32_t)(Y >> 8);
    if (hx > 65535) hx = 65535;
    if (hy > 65535) hy = 65535;
    p->X = X;
    p->Y = Y;
    p->key = (dl_hilbert(hx, hy) << 24) | (uint64_t)idx;
}

static void dl_free(dl_mesh *m) {
    free(m->x);
    free(m->y);
    free(m->t);
    free(m->mark);
    free(m->stack);
    free(m->cav);
    free(m->bnd);
}

typedef struct {
    double sumMin;
    long insertions, triangles;
    uint64_t digest;
} dl_stats;

/// Generates, triangulates and refines one mesh of n0 input points.
static int dl_mesh_one(int n0, uint64_t seed, dl_stats *st) {
    int nb = 2 * (int)sqrt((double)n0);
    int np = n0 + 4 * nb;
    dl_pt *pts = malloc((size_t)np * sizeof(dl_pt));
    int *bad = NULL, capbad = 0;
    dl_mesh m;
    memset(&m, 0, sizeof m);
    int rc = 0;
    if (pts == NULL || dl_reserve_v(&m, n0 * 2) || dl_reserve_t(&m, n0 * 4)) {
        rc = 1;
        goto done;
    }
    fb_rng r;
    fb_seed(&r, seed);
    double ccx[8], ccy[8], ccr[8];
    for (int k = 0; k < 8; k++) {
        ccx[k] = fb_range(&r, 0.15, 0.85);
        ccy[k] = fb_range(&r, 0.15, 0.85);
        ccr[k] = fb_range(&r, 0.02, 0.08);
    }
    double crad = fb_range(&r, 0.25, 0.4), sfreq = fb_range(&r, 6.0, 12.0);
    for (int i = 0; i < n0; i++) {
        double x, y, sel = fb_u01(&r);
        if (sel < 0.55) {
            x = fb_u01(&r);
            y = fb_u01(&r);
        } else if (sel < 0.80) {
            int k = (int)fb_below(&r, 8);
            x = ccx[k] + ccr[k] * (fb_u01(&r) + fb_u01(&r) - 1.0);
            y = ccy[k] + ccr[k] * (fb_u01(&r) + fb_u01(&r) - 1.0);
        } else if (sel < 0.92) {
            double a = 6.283185307179586 * fb_u01(&r), rr = crad + 1e-4 * (fb_u01(&r) - 0.5);
            x = 0.5 + rr * cos(a);
            y = 0.5 + rr * sin(a);
        } else {
            x = fb_u01(&r);
            y = 0.5 + 0.25 * sin(sfreq * x) + 1e-4 * (fb_u01(&r) - 0.5);
        }
        dl_put(&pts[i], i, fb_clamp(x, 1.0 / DL_G, 1.0 - 1.0 / DL_G), fb_clamp(y, 1.0 / DL_G, 1.0 - 1.0 / DL_G));
    }
    for (int s = 0; s < 4; s++)
        for (int k = 0; k < nb; k++) {
            double t = fb_u01(&r);
            int idx = n0 + s * nb + k;
            if (s == 0) dl_put(&pts[idx], idx, t, 0.0);
            else if (s == 1) dl_put(&pts[idx], idx, 1.0, t);
            else if (s == 2) dl_put(&pts[idx], idx, t, 1.0);
            else dl_put(&pts[idx], idx, 0.0, t);
        }
    qsort(pts, (size_t)np, sizeof(dl_pt), dl_cmp);

    // The square as two triangles over its corners.
    static const double kCx[4] = {0, 1, 1, 0}, kCy[4] = {0, 0, 1, 1};
    for (int k = 0; k < 4; k++) {
        m.x[k] = kCx[k];
        m.y[k] = kCy[k];
    }
    m.nv = 4;
    m.t[0] = (dl_tri){{0, 1, 2}, {-1, 1, -1}};
    m.t[1] = (dl_tri){{0, 2, 3}, {-1, -1, 0}};
    m.nt = 2;
    for (int i = 0; i < np; i++) {
        int e = dl_insert(&m, (double)pts[i].X / DL_G, (double)pts[i].Y / DL_G);
        if (e < 0) {
            rc = 2;
            goto done;
        }
        st->insertions += e == 0;
    }

    // Ruppert refinement rounds.
    const int64_t minlen2 = (int64_t)4096 * 4096;  // edges under 2^-12 are left alone
    for (int round = 0; round < 8; round++) {
        int nbad = 0;
        for (int t = 0; t < m.nt; t++) {
            if (!dl_bad(&m, t, minlen2)) continue;
            if (fb_grow((void **)&bad, &capbad, 4 * (nbad + 1), sizeof(int))) {
                rc = 1;
                goto done;
            }
            bad[4 * nbad] = t;
            memcpy(&bad[4 * nbad + 1], m.t[t].v, 3 * sizeof(int));
            nbad++;
        }
        if (nbad == 0) break;
        for (int k = 0; k < nbad; k++) {
            int t = bad[4 * k];
            if (memcmp(m.t[t].v, &bad[4 * k + 1], 3 * sizeof(int)) != 0) continue;
            int e = dl_refine(&m, t);
            if (e < 0) {
                rc = 3;
                goto done;
            }
            st->insertions += e == 0;
        }
    }

    // Statistics; the area must come to exactly the square's.
    double area2 = 0, sumMin = 0;
    int stillBad = 0;
    for (int t = 0; t < m.nt; t++) {
        const int *v = m.t[t].v;
        double X[3], Y[3], L[3];
        for (int k = 0; k < 3; k++) {
            X[k] = m.x[v[k]];
            Y[k] = m.y[v[k]];
        }
        area2 += dl_orient(X[0], Y[0], X[1], Y[1], X[2], Y[2]);
        for (int k = 0; k < 3; k++) {
            double dx = X[(k + 2) % 3] - X[(k + 1) % 3], dy = Y[(k + 2) % 3] - Y[(k + 1) % 3];
            L[k] = dx * dx + dy * dy;
        }
        int k = 0;
        if (L[1] < L[k]) k = 1;
        if (L[2] < L[k]) k = 2;
        double ux = X[(k + 1) % 3] - X[k], uy = Y[(k + 1) % 3] - Y[k];
        double wx = X[(k + 2) % 3] - X[k], wy = Y[(k + 2) % 3] - Y[k];
        sumMin += atan2(fabs(ux * wy - uy * wx), ux * wx + uy * wy) * (180.0 / 3.141592653589793);
        stillBad += dl_bad(&m, t, 0);
    }
    if (area2 != 2.0) {
        rc = 4;
        goto done;
    }
    st->sumMin += sumMin;
    st->digest = fb_digest(fb_digest(fb_digest(st->digest, (uint64_t)m.nt), (uint64_t)m.nv), (uint64_t)stillBad);
    st->triangles += m.nt;
done:
    free(bad);
    free(pts);
    dl_free(&m);
    return rc;
}

/// Mesh generation (the class of gmsh): 2D Delaunay triangulations of the
/// unit square built by Bowyer–Watson insertion with a visibility walk for
/// point location, over point clouds that mix uniform scatter, dense
/// clusters and points strung along a circle and a sine curve (the kind of
/// input a CAD boundary produces), inserted in Hilbert-curve order. Each
/// mesh then gets eight rounds of Ruppert refinement: every triangle with
/// an angle under 20.7 degrees gets its circumcentre inserted, or the
/// boundary segment that centre encroaches split. Predicates are exact
/// (grid coordinates, a filtered in-circle test with a 128-bit fallback),
/// so the meshes are the same on any machine. `value` is the mean of the
/// triangles' smallest angles in degrees; `checksum` digests each mesh's
/// triangle, vertex and remaining-bad counts (each mesh's area is checked
/// to be exactly 1). Sizes 1/2/3: 2 meshes of 100 000 input points, 6 of
/// 200 000, and 16 of 300 000.
int cbk_delaunay(int size, cb_bench_result *out) {
    int n0 = size == 1 ? 100000 : (size == 2 ? 200000 : 300000);
    int meshes = size == 1 ? 2 : (size == 2 ? 6 : 16);
    dl_stats st = {0, 0, 0, 0};
    for (int k = 0; k < meshes; k++) {
        int rc = dl_mesh_one(n0, 0xDE1A0E7ull + 0x1000ull * (uint64_t)k, &st);
        if (rc != 0) return rc;
    }
    out->value = st.sumMin / (double)st.triangles;
    out->checksum = st.digest;
    out->work = (double)st.insertions;
    out->unit = "insertions";
    return 0;
}

// ── flight: 6-DOF flight dynamics ───────────────────────────────────────

enum { FL_X, FL_Y, FL_Z, FL_U, FL_V, FL_W, FL_Q0, FL_Q1, FL_Q2, FL_Q3, FL_P, FL_Q, FL_R, FL_TH, FL_FUEL, FL_N };

// Aerodynamic tables (this suite's own data for a small jet). Angle of
// attack in degrees; coefficients clamp at the table ends, as JSBSim's do.
static const double kFlAlpha[12] = {-10, -5, 0, 4, 8, 12, 14, 16, 18, 20, 25, 30};
static const double kFlCL[12] = {-0.55, -0.15, 0.25, 0.62, 0.98, 1.30, 1.40, 1.45, 1.38, 1.25, 1.05, 0.95};
static const double kFlCm[12] = {0.10, 0.06, 0.02, -0.02, -0.06, -0.10, -0.115, -0.125, -0.13, -0.135, -0.16, -0.20};
static const double kFlMach[5] = {0.2, 0.4, 0.6, 0.75, 0.85};
static const double kFlCLMach[5] = {1.0, 1.05, 1.15, 1.28, 1.20};
static const double kFlCmdeMach[5] = {1.0, 1.0, 0.95, 0.85, 0.7};
static const double kFlCD[12][5] = {
    {0.0600, 0.0606, 0.0628, 0.0696, 0.0880}, {0.0320, 0.0323, 0.0340, 0.0399, 0.0572},
    {0.0240, 0.0242, 0.0257, 0.0314, 0.0484}, {0.0300, 0.0303, 0.0319, 0.0378, 0.0550},
    {0.0500, 0.0505, 0.0525, 0.0590, 0.0770}, {0.0850, 0.0859, 0.0886, 0.0961, 0.1155},
    {0.1100, 0.1111, 0.1143, 0.1226, 0.1430}, {0.1400, 0.1414, 0.1452, 0.1544, 0.1760},
    {0.1800, 0.1818, 0.1864, 0.1968, 0.2200}, {0.2300, 0.2323, 0.2379, 0.2498, 0.2750},
    {0.3600, 0.3636, 0.3718, 0.3876, 0.4180}, {0.5000, 0.5050, 0.5160, 0.5360, 0.5720},
};

typedef struct {
    double mdry, S, b, c, Ixx, Iyy, Izz, Ixz, Tmax, tsfc;
    double kcl, kcd, kcm;
    double de0, th0, theta0, amp;
} fl_ac;

static int fl_seg(const double *xs, int n, double x, double *f) {
    if (x <= xs[0]) {
        *f = 0;
        return 0;
    }
    if (x >= xs[n - 1]) {
        *f = 1;
        return n - 2;
    }
    int i = 0;
    while (x > xs[i + 1]) i++;
    *f = (x - xs[i]) / (xs[i + 1] - xs[i]);
    return i;
}

static double fl_interp1(const double *xs, const double *ys, int n, double x) {
    double f;
    int i = fl_seg(xs, n, x, &f);
    return ys[i] + f * (ys[i + 1] - ys[i]);
}

static double fl_cd(double adeg, double mach) {
    double fa, fm;
    int i = fl_seg(kFlAlpha, 12, adeg, &fa), j = fl_seg(kFlMach, 5, mach, &fm);
    double a = kFlCD[i][j] + fm * (kFlCD[i][j + 1] - kFlCD[i][j]);
    double b = kFlCD[i + 1][j] + fm * (kFlCD[i + 1][j + 1] - kFlCD[i + 1][j]);
    return a + fa * (b - a);
}

/// International Standard Atmosphere: troposphere and lower stratosphere.
static void fl_atmos(double h, double *rho, double *asnd) {
    double T, p;
    if (h < 11000.0) {
        T = 288.15 - 0.0065 * h;
        p = 101325.0 * pow(T / 288.15, 5.255877);
    } else {
        T = 216.65;
        p = 22632.06 * exp(-0.000157688 * (h - 11000.0));
    }
    *rho = p / (287.05287 * T);
    *asnd = sqrt(1.4 * 287.05287 * T);
}

static double fl_ramp(double t, double a, double b) {
    if (t <= a) return 0;
    if (t >= b) return 1;
    double x = (t - a) / (b - a);
    return x * x * (3 - 2 * x);
}

/// The flight-test script, a 60 s cycle flown through a simple autopilot
/// (pitch-attitude hold, bank-angle hold, yaw damper): a pull-up, a banked
/// turn and roll-out, a throttle chop with a descent, then full power in a
/// climb with open-loop elevator doublets on top.
static void fl_controls(const fl_ac *ac, double t, const double *s, double *ctl) {
    double tc = fmod(t, 60.0), A = ac->amp;
    double q0 = s[FL_Q0], q1 = s[FL_Q1], q2 = s[FL_Q2], q3 = s[FL_Q3];
    double phi = atan2(2 * (q0 * q1 + q2 * q3), 1 - 2 * (q1 * q1 + q2 * q2));
    double sth = fb_clamp(2 * (q0 * q2 - q3 * q1), -1.0, 1.0);
    double theta = asin(sth);
    double up = fl_ramp(tc, 4, 5) - fl_ramp(tc, 9, 12);
    double turn = fl_ramp(tc, 12, 14) - fl_ramp(tc, 24, 27);
    double idle = fl_ramp(tc, 32, 33) - fl_ramp(tc, 38, 40);
    double full = fl_ramp(tc, 44, 45) - fl_ramp(tc, 55, 57);
    double thetaCmd = ac->theta0 + A * (0.10 * up + 0.025 * turn - 0.05 * idle + 0.07 * full);
    double phiCmd = 0.5 * A * turn;
    double de = ac->de0 - 1.0 * (thetaCmd - theta) + 0.5 * s[FL_Q];
    if (tc > 46 && tc < 54) de += 0.015 * A * sin((tc - 46) * 1.5707963267948966);
    double da = 0.5 * (phiCmd - phi) - 0.3 * s[FL_P];
    double dr = 0.5 * s[FL_R] - 0.3 * (phiCmd - phi) * 0.1;
    double th = ac->th0 * (1 - idle) + 0.1 * idle;
    th += (1.0 - th) * full;
    ctl[0] = fb_clamp(de, -0.15, 0.15);
    ctl[1] = fb_clamp(da, -0.1, 0.1);
    ctl[2] = fb_clamp(dr, -0.1, 0.1);
    ctl[3] = th;
}

/// The equations of motion: body-axis forces and moments from the tables,
/// thrust lapsing with density, gravity through the attitude quaternion,
/// Euler's equations with the Ixz cross product, quaternion kinematics.
static void fl_deriv(const fl_ac *ac, double t, const double *s, double *ds) {
    double ctl[4];
    fl_controls(ac, t, s, ctl);
    double rho, asnd;
    fl_atmos(-s[FL_Z], &rho, &asnd);
    double u = s[FL_U], v = s[FL_V], w = s[FL_W];
    double p = s[FL_P], q = s[FL_Q], r = s[FL_R];
    double q0 = s[FL_Q0], q1 = s[FL_Q1], q2 = s[FL_Q2], q3 = s[FL_Q3];
    double V = sqrt(u * u + v * v + w * w), Vxz = sqrt(u * u + w * w);
    double alpha = atan2(w, u), beta = asin(v / V);
    double ca = u / Vxz, sa = w / Vxz;
    double mach = V / asnd, qbar = 0.5 * rho * V * V;
    double adeg = alpha * 57.29577951308232;
    double phat = p * ac->b / (2 * V), qhat = q * ac->c / (2 * V), rhat = r * ac->b / (2 * V);
    double de = ctl[0], da = ctl[1], dr = ctl[2];

    double CL = fl_interp1(kFlAlpha, kFlCL, 12, adeg) * fl_interp1(kFlMach, kFlCLMach, 5, mach) * ac->kcl +
                5.0 * qhat + 0.4 * de;
    double CD = fl_cd(adeg, mach) * ac->kcd;
    double CY = -0.6 * beta + 0.15 * dr;
    double Cl = -0.08 * beta - 0.45 * phat + 0.12 * rhat + 0.12 * da + 0.01 * dr;
    double Cm = fl_interp1(kFlAlpha, kFlCm, 12, adeg) * ac->kcm - 15.0 * qhat -
                1.2 * fl_interp1(kFlMach, kFlCmdeMach, 5, mach) * de;
    double Cn = 0.10 * beta - 0.03 * phat - 0.15 * rhat - 0.01 * da - 0.08 * dr;

    double qS = qbar * ac->S;
    double L = qS * CL, D = qS * CD, Y = qS * CY;
    double thrust = s[FL_TH] * ac->Tmax * pow(rho / 1.225, 0.7) * (1.0 + 0.15 * mach);
    double Fx = -D * u / V + L * sa + thrust;
    double Fy = -D * v / V + Y;
    double Fz = -D * w / V - L * ca;
    const double g = 9.80665;
    double gx = 2 * (q1 * q3 - q0 * q2) * g, gy = 2 * (q2 * q3 + q0 * q1) * g;
    double gz = (q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3) * g;
    double mass = ac->mdry + s[FL_FUEL];
    ds[FL_U] = Fx / mass + gx + r * v - q * w;
    ds[FL_V] = Fy / mass + gy + p * w - r * u;
    ds[FL_W] = Fz / mass + gz + q * u - p * v;

    double Lm = qS * ac->b * Cl, Mm = qS * ac->c * Cm, Nm = qS * ac->b * Cn;
    double hx = ac->Ixx * p - ac->Ixz * r, hy = ac->Iyy * q, hz = ac->Izz * r - ac->Ixz * p;
    double rx = Lm - (q * hz - r * hy), ry = Mm - (r * hx - p * hz), rz = Nm - (p * hy - q * hx);
    double det = ac->Ixx * ac->Izz - ac->Ixz * ac->Ixz;
    ds[FL_P] = (ac->Izz * rx + ac->Ixz * rz) / det;
    ds[FL_Q] = ry / ac->Iyy;
    ds[FL_R] = (ac->Ixz * rx + ac->Ixx * rz) / det;

    ds[FL_Q0] = 0.5 * (-q1 * p - q2 * q - q3 * r);
    ds[FL_Q1] = 0.5 * (q0 * p + q2 * r - q3 * q);
    ds[FL_Q2] = 0.5 * (q0 * q - q1 * r + q3 * p);
    ds[FL_Q3] = 0.5 * (q0 * r + q1 * q - q2 * p);

    ds[FL_X] = (q0 * q0 + q1 * q1 - q2 * q2 - q3 * q3) * u + 2 * (q1 * q2 - q0 * q3) * v + 2 * (q1 * q3 + q0 * q2) * w;
    ds[FL_Y] = 2 * (q1 * q2 + q0 * q3) * u + (q0 * q0 - q1 * q1 + q2 * q2 - q3 * q3) * v + 2 * (q2 * q3 - q0 * q1) * w;
    ds[FL_Z] = 2 * (q1 * q3 - q0 * q2) * u + 2 * (q2 * q3 + q0 * q1) * v + (q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3) * w;

    ds[FL_TH] = (ctl[3] - s[FL_TH]) / 1.2;
    ds[FL_FUEL] = s[FL_FUEL] > 0 ? -ac->tsfc * thrust : 0.0;
}

/// Trims an aircraft for level flight: angle of attack for the lift
/// needed (bisection on the table), elevator for zero pitching moment,
/// throttle for the drag.
static void fl_trim(fl_ac *ac, double h0, double V0, double psi, double fuel, double *s) {
    double rho, asnd;
    fl_atmos(h0, &rho, &asnd);
    double mach = V0 / asnd, qbar = 0.5 * rho * V0 * V0;
    double clreq = (ac->mdry + fuel) * 9.80665 / (qbar * ac->S);
    double fm = fl_interp1(kFlMach, kFlCLMach, 5, mach) * ac->kcl;
    double lo = -5, hi = 12;
    for (int i = 0; i < 60; i++) {
        double mid = 0.5 * (lo + hi);
        if (fl_interp1(kFlAlpha, kFlCL, 12, mid) * fm < clreq) lo = mid;
        else hi = mid;
    }
    double adeg = 0.5 * (lo + hi), alpha = adeg / 57.29577951308232;
    ac->theta0 = alpha;
    ac->de0 = fl_interp1(kFlAlpha, kFlCm, 12, adeg) * ac->kcm / (1.2 * fl_interp1(kFlMach, kFlCmdeMach, 5, mach));
    double drag = qbar * ac->S * fl_cd(adeg, mach) * ac->kcd;
    ac->th0 = fb_clamp(drag / (ac->Tmax * pow(rho / 1.225, 0.7) * (1.0 + 0.15 * mach)), 0.05, 1.0);
    memset(s, 0, FL_N * sizeof(double));
    s[FL_Z] = -h0;
    s[FL_U] = V0 * cos(alpha);
    s[FL_W] = V0 * sin(alpha);
    double ch = cos(0.5 * psi), sh = sin(0.5 * psi), ct = cos(0.5 * alpha), st = sin(0.5 * alpha);
    s[FL_Q0] = ch * ct;
    s[FL_Q1] = -sh * st;
    s[FL_Q2] = ch * st;
    s[FL_Q3] = sh * ct;
    s[FL_TH] = ac->th0;
    s[FL_FUEL] = fuel;
}

/// Flight dynamics (the class of JSBSim, as in flightdm): a population of
/// small jets, each a 6-DOF rigid body with a quaternion attitude,
/// aerodynamic coefficients interpolated from 1D and 2D tables in angle of
/// attack and Mach, damping and control derivatives, an ISA atmosphere and
/// a spool-lagged engine burning fuel. Each is trimmed for level flight,
/// then flies a repeating flight-test script (pull-up, banked turn,
/// throttle chop, elevator doublets) through a simple autopilot, integrated
/// with classic RK4 at 120 Hz. `value` sums each
/// aircraft's final altitude (m), airspeed (m/s), fuel left (kg) and
/// ground distance (km). Sizes 1/2/3: 48 aircraft for 140 s, 96 for
/// 420 s, and 192 for 900 s.
int cbk_flight(int size, cb_bench_result *out) {
    int nac = size == 1 ? 48 : (size == 2 ? 96 : 192);
    double tend = size == 1 ? 140.0 : (size == 2 ? 420.0 : 900.0);
    const double dt = 1.0 / 120.0;
    long steps = (long)(tend * 120.0 + 0.5);
    fb_rng r;
    fb_seed(&r, 0xF11647ull);
    double total = 0;
    for (int a = 0; a < nac; a++) {
        fl_ac ac;
        ac.mdry = 9000.0 * fb_range(&r, 0.85, 1.15);
        ac.S = 30.0 * fb_range(&r, 0.9, 1.1);
        ac.b = 12.0 * fb_range(&r, 0.95, 1.05);
        ac.c = ac.S / ac.b;
        ac.Ixx = 15000.0 * fb_range(&r, 0.9, 1.1);
        ac.Iyy = 60000.0 * fb_range(&r, 0.9, 1.1);
        ac.Izz = 70000.0 * fb_range(&r, 0.9, 1.1);
        ac.Ixz = 1500.0 * fb_range(&r, 0.5, 1.5);
        ac.Tmax = 60000.0 * fb_range(&r, 0.9, 1.2);
        ac.tsfc = 2.0e-5 * fb_range(&r, 0.9, 1.1);
        ac.kcl = fb_range(&r, 0.95, 1.05);
        ac.kcd = fb_range(&r, 0.95, 1.08);
        ac.kcm = fb_range(&r, 0.9, 1.1);
        ac.amp = fb_range(&r, 0.6, 1.3);
        double h0 = fb_range(&r, 2000, 9000), V0 = fb_range(&r, 150, 230);
        double psi = fb_range(&r, 0, 6.283185307179586), fuel = fb_range(&r, 2000, 4000);
        double s[FL_N], k1[FL_N], k2[FL_N], k3[FL_N], k4[FL_N], tmp[FL_N];
        fl_trim(&ac, h0, V0, psi, fuel, s);
        for (long n = 0; n < steps; n++) {
            double t = n * dt;
            fl_deriv(&ac, t, s, k1);
            for (int i = 0; i < FL_N; i++) tmp[i] = s[i] + 0.5 * dt * k1[i];
            fl_deriv(&ac, t + 0.5 * dt, tmp, k2);
            for (int i = 0; i < FL_N; i++) tmp[i] = s[i] + 0.5 * dt * k2[i];
            fl_deriv(&ac, t + 0.5 * dt, tmp, k3);
            for (int i = 0; i < FL_N; i++) tmp[i] = s[i] + dt * k3[i];
            fl_deriv(&ac, t + dt, tmp, k4);
            for (int i = 0; i < FL_N; i++) s[i] += dt / 6.0 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]);
            double qn = sqrt(s[FL_Q0] * s[FL_Q0] + s[FL_Q1] * s[FL_Q1] + s[FL_Q2] * s[FL_Q2] + s[FL_Q3] * s[FL_Q3]);
            for (int i = FL_Q0; i <= FL_Q3; i++) s[i] /= qn;
        }
        double V = sqrt(s[FL_U] * s[FL_U] + s[FL_V] * s[FL_V] + s[FL_W] * s[FL_W]);
        double dist = sqrt(s[FL_X] * s[FL_X] + s[FL_Y] * s[FL_Y]);
        double contrib = -s[FL_Z] + V + s[FL_FUEL] + 0.001 * dist;
        if (!isfinite(contrib)) return 2;
        total += contrib;
    }
    out->value = total;
    out->checksum = 0;
    out->work = (double)nac * (double)steps;
    out->unit = "RK4 steps";
    return 0;
}

// ── snn: spiking neural network ─────────────────────────────────────────

// A balanced network is chaotic: one spike moved by one step changes
// everything after it. So, beyond the file's no-contraction rule, this
// section calls no libm function in its arithmetic (sn_exp below is plain
// + - * /); the result is the same bit for bit on any IEEE-754 machine.

/// exp(x) from + - * / and ldexp only: reduction by ln 2, then a Taylor
/// series. Accurate to an ulp or two, and identical everywhere.
static double sn_exp(double x) {
    double k = floor(x * 1.4426950408889634 + 0.5);
    double r = x - k * 0.6931471805599453;
    double term = 1.0, sum = 1.0;
    for (int i = 1; i <= 20; i++) {
        term = term * r / i;
        sum = sum + term;
    }
    return ldexp(sum, (int)k);
}

#define SN_KMAX 24  // largest external spike count drawn in one step

/// Spiking neural network simulation (the class of NEST): a Brunel-style
/// balanced network of leaky integrate-and-fire neurons with exponential
/// post-synaptic currents (NEST's iaf_psc_exp, integrated exactly with
/// propagators), 80% excitatory and 20% inhibitory, each neuron receiving
/// 400 excitatory and 100 inhibitory synapses from random sources. The
/// connectivity is stored by source in compressed rows, each synapse with
/// its own delay (1-3 ms) into a ring buffer of future input; spikes are
/// delivered as events. External drive is Poisson input drawn per neuron
/// per 0.1 ms step. `value` is the mean membrane potential in mV over all
/// neurons and steps; `checksum` is the total spike count. Sizes 1/2/3:
/// 5 000 neurons for 0.5 s, 16 000 for 1 s, 32 000 for 2 s.
int cbk_snn(int size, cb_bench_result *out) {
    int N = size == 1 ? 5000 : (size == 2 ? 16000 : 32000);
    int steps = size == 1 ? 5000 : (size == 2 ? 10000 : 20000);
    const int NE = N * 4 / 5, NI = N - NE, CE = 400, CI = 100, D = 32;
    const double h = 0.1;                          // ms
    const double tauM = 20.0, tauS = 2.0, Cm = 250.0;  // ms, ms, pF
    const double theta = 20.0, vReset = 10.0, eL = -70.0;  // mV (V relative to rest)
    const int tRef = 20;                           // steps (2 ms)
    const double JE = 25.0, JI = -5.0 * JE;        // pA
    const double lambda = 0.7;                     // external spikes per step

    // Exact-integration propagators.
    double P22 = sn_exp(-h / tauM), P11 = sn_exp(-h / tauS);
    double P21 = tauM * tauS / (Cm * (tauS - tauM)) * (P11 - P22);

    // Poisson(lambda) inverse-CDF thresholds on 64-bit uniforms.
    uint64_t thr[SN_KMAX];
    {
        double pk = sn_exp(-lambda), cdf = 0.0;
        for (int k = 0; k < SN_KMAX; k++) {
            cdf = cdf + pk;
            pk = pk * lambda / (k + 1);
            thr[k] = cdf >= 1.0 ? UINT64_MAX : (uint64_t)(cdf * 18446744073709551616.0);
        }
    }

    uint32_t *start = calloc((size_t)N + 1, sizeof(uint32_t));
    uint32_t *fill = malloc((size_t)N * sizeof(uint32_t));
    uint32_t *syn = malloc((size_t)N * (CE + CI) * sizeof(uint32_t));
    double *V = malloc((size_t)N * sizeof(double));
    double *Ie = calloc((size_t)N, sizeof(double));
    double *Ii = calloc((size_t)N, sizeof(double));
    double *ringE = calloc((size_t)N * D, sizeof(double));
    double *ringI = calloc((size_t)N * D, sizeof(double));
    int *ref = calloc((size_t)N, sizeof(int));
    int *spk = malloc((size_t)N * sizeof(int));
    int rc = 0;
    if (!start || !fill || !syn || !V || !Ie || !Ii || !ringE || !ringI || !ref || !spk) {
        rc = 1;
        goto done;
    }

    // Fixed in-degree wiring, generated twice from the same seed: once to
    // count each source's synapses, once to fill the rows.
    for (int pass = 0; pass < 2; pass++) {
        fb_rng r;
        fb_seed(&r, 0x5A11ull);
        for (int tgt = 0; tgt < N; tgt++)
            for (int k = 0; k < CE + CI; k++) {
                uint32_t src = k < CE ? fb_below(&r, (uint32_t)NE) : (uint32_t)NE + fb_below(&r, (uint32_t)NI);
                if (src == (uint32_t)tgt) src = k < CE ? (src + 1) % (uint32_t)NE : (uint32_t)NE + (src - NE + 1) % (uint32_t)NI;
                uint32_t delay = 10 + fb_below(&r, 21);
                if (pass == 0) start[src + 1]++;
                else syn[fill[src]++] = (uint32_t)tgt | delay << 24;
            }
        if (pass == 0) {
            for (int i = 0; i < N; i++) start[i + 1] += start[i];
            memcpy(fill, start, (size_t)N * sizeof(uint32_t));
        }
    }

    fb_rng r;
    fb_seed(&r, 0x5A12ull);
    for (int i = 0; i < N; i++) V[i] = theta * fb_u01(&r);
    double sumV = 0.0;
    uint64_t spikes = 0;
    for (int step = 0; step < steps; step++) {
        int slot = step & (D - 1);
        double *re = ringE + (size_t)slot * N, *ri = ringI + (size_t)slot * N;
        int nsp = 0;
        double sv = 0.0;
        for (int i = 0; i < N; i++) {
            double v = V[i];
            if (ref[i] > 0) ref[i]--;
            else v = P22 * v + P21 * Ie[i] + P21 * Ii[i];
            uint64_t x = fb_next(&r);
            int k = 0;
            while (k < SN_KMAX && x >= thr[k]) k++;
            Ie[i] = P11 * Ie[i] + re[i] + k * JE;
            Ii[i] = P11 * Ii[i] + ri[i];
            re[i] = 0.0;
            ri[i] = 0.0;
            if (v >= theta) {
                v = vReset;
                ref[i] = tRef;
                spk[nsp++] = i;
            }
            V[i] = v;
            sv = sv + v;
        }
        sumV = sumV + sv;
        for (int s = 0; s < nsp; s++) {
            int src = spk[s];
            double w = src < NE ? JE : JI;
            double *ring = src < NE ? ringE : ringI;
            for (uint32_t k = start[src]; k < start[src + 1]; k++) {
                uint32_t e = syn[k];
                int at = (slot + (int)(e >> 24)) & (D - 1);
                ring[(size_t)at * N + (e & 0xFFFFFF)] += w;
            }
        }
        spikes += (uint64_t)nsp;
    }
    out->value = eL + sumV / ((double)N * steps);
    out->checksum = spikes;
    out->work = (double)N * steps;
    out->unit = "neuron updates";
done:
    free(start);
    free(fill);
    free(syn);
    free(V);
    free(Ie);
    free(Ii);
    free(ringE);
    free(ringI);
    free(ref);
    free(spk);
    return rc;
}

// ── transformer: neural machine translation inference ───────────────────

#define TF_D 256     // model width
#define TF_H 4       // attention heads
#define TF_DH 64     // head width
#define TF_FF 1024   // feed-forward width
#define TF_V 3000    // vocabulary
#define TF_NE 2      // encoder layers
#define TF_ND 2      // decoder layers
#define TF_B 8       // sentences decoded together
#define TF_MAXS 28   // longest source sentence
#define TF_MAXT 32   // longest translation
#define TF_BOS 1
#define TF_EOS 2
#define TF_KB 128    // matmul depth block

typedef struct {
    const float *wq, *bq, *wk, *bk, *wv, *bv, *wo, *bo;
} tf_att;

typedef struct {
    const float *ln1g, *ln1b, *ln2g, *ln2b, *ln3g, *ln3b;
    tf_att self, cross;
    const float *w1, *b1, *w2, *b2;
} tf_layer;

typedef struct {
    float *blob;
    const float *emb, *wout;
    tf_layer enc[TF_NE], dec[TF_ND];
    const float *encg, *encb, *decg, *decb;
    float pe[TF_MAXT + TF_MAXS][TF_D];
} tf_model;

static float *tf_take(float **cur, size_t n) {
    float *p = *cur;
    *cur += n;
    return p;
}

static const float *tf_rand(float **cur, size_t n, fb_rng *r, double base, double a) {
    float *p = tf_take(cur, n);
    for (size_t i = 0; i < n; i++) p[i] = (float)(base + (2.0 * fb_u01(r) - 1.0) * a);
    return p;
}

static void tf_init_att(tf_att *at, float **cur, fb_rng *r) {
    double a = sqrt(6.0 / (2 * TF_D));
    at->wq = tf_rand(cur, TF_D * TF_D, r, 0, a);
    at->bq = tf_rand(cur, TF_D, r, 0, 0.02);
    at->wk = tf_rand(cur, TF_D * TF_D, r, 0, a);
    at->bk = tf_rand(cur, TF_D, r, 0, 0.02);
    at->wv = tf_rand(cur, TF_D * TF_D, r, 0, a);
    at->bv = tf_rand(cur, TF_D, r, 0, 0.02);
    at->wo = tf_rand(cur, TF_D * TF_D, r, 0, a);
    at->bo = tf_rand(cur, TF_D, r, 0, 0.02);
}

static void tf_init_layer(tf_layer *L, int cross, float **cur, fb_rng *r) {
    double af = sqrt(6.0 / (TF_D + TF_FF));
    L->ln1g = tf_rand(cur, TF_D, r, 1.0, 0.05);
    L->ln1b = tf_rand(cur, TF_D, r, 0, 0.05);
    tf_init_att(&L->self, cur, r);
    L->ln2g = tf_rand(cur, TF_D, r, 1.0, 0.05);
    L->ln2b = tf_rand(cur, TF_D, r, 0, 0.05);
    if (cross) {
        tf_init_att(&L->cross, cur, r);
        L->ln3g = tf_rand(cur, TF_D, r, 1.0, 0.05);
        L->ln3b = tf_rand(cur, TF_D, r, 0, 0.05);
    }
    L->w1 = tf_rand(cur, (size_t)TF_D * TF_FF, r, 0, af);
    L->b1 = tf_rand(cur, TF_FF, r, 0, 0.02);
    L->w2 = tf_rand(cur, (size_t)TF_FF * TF_D, r, 0, af);
    L->b2 = tf_rand(cur, TF_D, r, 0, 0.02);
}

static size_t tf_model_floats(void) {
    size_t att = 4 * (size_t)TF_D * TF_D + 4 * TF_D;
    size_t ffn = 2 * (size_t)TF_D * TF_FF + TF_FF + TF_D;
    size_t enc = 4 * TF_D + att + ffn, dec = 6 * TF_D + 2 * att + ffn;
    return 2 * (size_t)TF_V * TF_D + TF_NE * enc + TF_ND * dec + 4 * TF_D;
}

/// Weights from the generator (Xavier-uniform) and sinusoidal position
/// encodings.
static int tf_init(tf_model *m) {
    m->blob = malloc(tf_model_floats() * sizeof(float));
    if (m->blob == NULL) return 1;
    fb_rng r;
    fb_seed(&r, 0x7F0A11ull);
    float *cur = m->blob;
    m->emb = tf_rand(&cur, (size_t)TF_V * TF_D, &r, 0, sqrt(6.0 / (TF_V + TF_D)));
    m->wout = tf_rand(&cur, (size_t)TF_D * TF_V, &r, 0, sqrt(6.0 / (TF_V + TF_D)));
    for (int l = 0; l < TF_NE; l++) tf_init_layer(&m->enc[l], 0, &cur, &r);
    for (int l = 0; l < TF_ND; l++) tf_init_layer(&m->dec[l], 1, &cur, &r);
    m->encg = tf_rand(&cur, TF_D, &r, 1.0, 0.05);
    m->encb = tf_rand(&cur, TF_D, &r, 0, 0.05);
    m->decg = tf_rand(&cur, TF_D, &r, 1.0, 0.05);
    m->decb = tf_rand(&cur, TF_D, &r, 0, 0.05);
    for (int p = 0; p < TF_MAXT + TF_MAXS; p++)
        for (int i = 0; i < TF_D / 2; i++) {
            double f = p / pow(10000.0, 2.0 * i / TF_D);
            m->pe[p][2 * i] = (float)sin(f);
            m->pe[p][2 * i + 1] = (float)cos(f);
        }
    return 0;
}

// Four-lane vectors with an explicitly fused multiply-add: NEON on arm64,
// fmaf lane by lane elsewhere (the same results either way).
#if defined(__aarch64__)
typedef float32x4_t tf_v4;
#define TF_LD(p) vld1q_f32(p)
#define TF_ST(p, v) vst1q_f32((p), (v))
#define TF_FMA(acc, x, b) vfmaq_n_f32((acc), (b), (x))
#else
typedef float tf_v4 __attribute__((vector_size(16)));
typedef float tf_v4u __attribute__((vector_size(16), aligned(4)));
#define TF_LD(p) (*(const tf_v4u *)(p))
#define TF_ST(p, v) (*(tf_v4u *)(p) = (v))
static inline tf_v4 tf_fma4(tf_v4 a, float x, tf_v4 b) {
    tf_v4 r;
    for (int i = 0; i < 4; i++) r[i] = fmaf(x, b[i], a[i]);
    return r;
}
#define TF_FMA(acc, x, b) tf_fma4((acc), (x), (b))
#endif

/// C = A B + bias (or C += A B + bias), A M x K, B K x N, row-major. A
/// register-blocked kernel: 4 rows x 16 columns of C stay in sixteen
/// 4-lane accumulators while k runs through a block of TF_KB, with B's
/// panel resident in L1. Each output's sum still runs over k in order, so
/// the blocking never changes the answer.
static void tf_matmul(const float *A, int M, int K, const float *B, int N, const float *bias, float *C, int acc) {
    for (int i = 0; i < M; i++) {
        float *c = C + (size_t)i * N;
        for (int j = 0; j < N; j++) c[j] = (acc ? c[j] : 0.0f) + (bias ? bias[j] : 0.0f);
    }
    int n16 = N & ~15;
    for (int j0 = 0; j0 < n16; j0 += 16)
        for (int k0 = 0; k0 < K; k0 += TF_KB) {
            int k1 = k0 + TF_KB < K ? k0 + TF_KB : K;
            int i = 0;
            for (; i + 4 <= M; i += 4) {
                float *c0 = C + (size_t)i * N + j0, *c1 = c0 + N, *c2 = c1 + N, *c3 = c2 + N;
                const float *a0 = A + (size_t)i * K, *a1 = a0 + K, *a2 = a1 + K, *a3 = a2 + K;
                tf_v4 s00 = TF_LD(c0), s01 = TF_LD(c0 + 4), s02 = TF_LD(c0 + 8), s03 = TF_LD(c0 + 12);
                tf_v4 s10 = TF_LD(c1), s11 = TF_LD(c1 + 4), s12 = TF_LD(c1 + 8), s13 = TF_LD(c1 + 12);
                tf_v4 s20 = TF_LD(c2), s21 = TF_LD(c2 + 4), s22 = TF_LD(c2 + 8), s23 = TF_LD(c2 + 12);
                tf_v4 s30 = TF_LD(c3), s31 = TF_LD(c3 + 4), s32 = TF_LD(c3 + 8), s33 = TF_LD(c3 + 12);
                for (int k = k0; k < k1; k++) {
                    const float *b = B + (size_t)k * N + j0;
                    tf_v4 b0 = TF_LD(b), b1 = TF_LD(b + 4), b2 = TF_LD(b + 8), b3 = TF_LD(b + 12);
                    float x = a0[k];
                    s00 = TF_FMA(s00, x, b0);
                    s01 = TF_FMA(s01, x, b1);
                    s02 = TF_FMA(s02, x, b2);
                    s03 = TF_FMA(s03, x, b3);
                    x = a1[k];
                    s10 = TF_FMA(s10, x, b0);
                    s11 = TF_FMA(s11, x, b1);
                    s12 = TF_FMA(s12, x, b2);
                    s13 = TF_FMA(s13, x, b3);
                    x = a2[k];
                    s20 = TF_FMA(s20, x, b0);
                    s21 = TF_FMA(s21, x, b1);
                    s22 = TF_FMA(s22, x, b2);
                    s23 = TF_FMA(s23, x, b3);
                    x = a3[k];
                    s30 = TF_FMA(s30, x, b0);
                    s31 = TF_FMA(s31, x, b1);
                    s32 = TF_FMA(s32, x, b2);
                    s33 = TF_FMA(s33, x, b3);
                }
                TF_ST(c0, s00); TF_ST(c0 + 4, s01); TF_ST(c0 + 8, s02); TF_ST(c0 + 12, s03);
                TF_ST(c1, s10); TF_ST(c1 + 4, s11); TF_ST(c1 + 8, s12); TF_ST(c1 + 12, s13);
                TF_ST(c2, s20); TF_ST(c2 + 4, s21); TF_ST(c2 + 8, s22); TF_ST(c2 + 12, s23);
                TF_ST(c3, s30); TF_ST(c3 + 4, s31); TF_ST(c3 + 8, s32); TF_ST(c3 + 12, s33);
            }
            for (; i < M; i++) {
                float *c0 = C + (size_t)i * N + j0;
                const float *a0 = A + (size_t)i * K;
                tf_v4 s00 = TF_LD(c0), s01 = TF_LD(c0 + 4), s02 = TF_LD(c0 + 8), s03 = TF_LD(c0 + 12);
                for (int k = k0; k < k1; k++) {
                    const float *b = B + (size_t)k * N + j0;
                    float x = a0[k];
                    s00 = TF_FMA(s00, x, TF_LD(b));
                    s01 = TF_FMA(s01, x, TF_LD(b + 4));
                    s02 = TF_FMA(s02, x, TF_LD(b + 8));
                    s03 = TF_FMA(s03, x, TF_LD(b + 12));
                }
                TF_ST(c0, s00); TF_ST(c0 + 4, s01); TF_ST(c0 + 8, s02); TF_ST(c0 + 12, s03);
            }
        }
    for (int i = 0; i < M; i++)  // columns past the last full panel
        for (int j = n16; j < N; j++) {
            float s = C[(size_t)i * N + j];
            for (int k = 0; k < K; k++) s = fmaf(A[(size_t)i * K + k], B[(size_t)k * N + j], s);
            C[(size_t)i * N + j] = s;
        }
}

static void tf_layernorm(const float *x, int M, const float *g, const float *b, float *y) {
    for (int i = 0; i < M; i++) {
        const float *xi = x + (size_t)i * TF_D;
        float *yi = y + (size_t)i * TF_D;
        float mean = 0, var = 0;
        for (int j = 0; j < TF_D; j++) mean += xi[j];
        mean /= TF_D;
        for (int j = 0; j < TF_D; j++) {
            float d = xi[j] - mean;
            var += d * d;
        }
        var /= TF_D;
        float inv = 1.0f / sqrtf(var + 1e-5f);
        for (int j = 0; j < TF_D; j++) yi[j] = (xi[j] - mean) * inv * g[j] + b[j];
    }
}

/// exp for floats from + - * / and ldexpf only (Cody–Waite reduction by
/// ln 2, then a degree-7 polynomial): within an ulp or two, and the same on
/// every machine, so a greedy argmax never flips on a libm difference.
static inline float tf_exp(float x) {
    if (x < -87.0f) return 0.0f;
    if (x > 88.0f) x = 88.0f;
    float k = floorf(x * 1.44269504f + 0.5f);
    float r = (x - k * 0.693145752f) - k * 1.42860677e-6f;
    float p = 1.0f + r * (1.0f + r * (0.5f + r * (1.0f / 6 + r * (1.0f / 24 + r * (1.0f / 120 + r * (1.0f / 720 + r * (1.0f / 5040)))))));
    return ldexpf(p, (int)k);
}

/// GELU, tanh form, with tanh(t) = 1 - 2 / (e^2t + 1).
static void tf_gelu(float *x, size_t n) {
    for (size_t i = 0; i < n; i++) {
        float v = x[i];
        float t = 0.7978845608f * (v + 0.044715f * v * v * v);
        float th = t > 9.0f ? 1.0f : 1.0f - 2.0f / (tf_exp(2.0f * t) + 1.0f);
        x[i] = 0.5f * v * (1.0f + th);
    }
}

/// One head's attention for one query over n keys/values (row stride ld).
static void tf_attend(const float *q, const float *K, const float *V, int ld, int n, float *sc, float *o) {
    const float scale = 0.125f;  // 1 / sqrt(TF_DH)
    float mx = -INFINITY;
    for (int j = 0; j < n; j++) {
        const float *k = K + (size_t)j * ld;
        float s = 0;
        for (int d = 0; d < TF_DH; d++) s += q[d] * k[d];
        s *= scale;
        sc[j] = s;
        if (s > mx) mx = s;
    }
    float sum = 0;
    for (int j = 0; j < n; j++) {
        sc[j] = tf_exp(sc[j] - mx);
        sum += sc[j];
    }
    float inv = 1.0f / sum;
    for (int d = 0; d < TF_DH; d++) o[d] = 0;
    for (int j = 0; j < n; j++) {
        const float *v = V + (size_t)j * ld;
        float p = sc[j] * inv;
        for (int d = 0; d < TF_DH; d++) o[d] += p * v[d];
    }
}

typedef struct {
    float *X, *Hn, *Q, *K, *V, *A, *F, *logits;
    float *kc[TF_ND], *vc[TF_ND], *km[TF_ND], *vm[TF_ND];
    float sc[TF_MAXS * TF_B + TF_MAXT];
} tf_work;

/// Translates one batch of TF_B sentences greedily; adds the summed
/// negative log-likelihood of the chosen tokens and a digest of them.
static void tf_batch(const tf_model *m, tf_work *w, fb_rng *r, double *nll, uint64_t *dg, long *tokens) {
    int len[TF_B], off[TF_B + 1], src[TF_B * TF_MAXS];
    off[0] = 0;
    for (int b = 0; b < TF_B; b++) {
        len[b] = 12 + (int)fb_below(r, TF_MAXS - 12 + 1);
        for (int i = 0; i < len[b]; i++) src[off[b] + i] = i == len[b] - 1 ? TF_EOS : 3 + (int)fb_below(r, TF_V - 3);
        off[b + 1] = off[b] + len[b];
    }
    int nt = off[TF_B];
    const float esc = 16.0f;  // sqrt(TF_D)

    // Encoder over all source tokens of the batch at once.
    for (int b = 0; b < TF_B; b++)
        for (int i = 0; i < len[b]; i++) {
            float *x = w->X + (size_t)(off[b] + i) * TF_D;
            const float *e = m->emb + (size_t)src[off[b] + i] * TF_D;
            for (int j = 0; j < TF_D; j++) x[j] = e[j] * esc + m->pe[i][j];
        }
    for (int l = 0; l < TF_NE; l++) {
        const tf_layer *L = &m->enc[l];
        tf_layernorm(w->X, nt, L->ln1g, L->ln1b, w->Hn);
        tf_matmul(w->Hn, nt, TF_D, L->self.wq, TF_D, L->self.bq, w->Q, 0);
        tf_matmul(w->Hn, nt, TF_D, L->self.wk, TF_D, L->self.bk, w->K, 0);
        tf_matmul(w->Hn, nt, TF_D, L->self.wv, TF_D, L->self.bv, w->V, 0);
        for (int b = 0; b < TF_B; b++)
            for (int hd = 0; hd < TF_H; hd++)
                for (int i = 0; i < len[b]; i++) {
                    size_t row = (size_t)(off[b] + i) * TF_D + hd * TF_DH;
                    size_t base = (size_t)off[b] * TF_D + hd * TF_DH;
                    tf_attend(w->Q + row, w->K + base, w->V + base, TF_D, len[b], w->sc, w->A + row);
                }
        tf_matmul(w->A, nt, TF_D, L->self.wo, TF_D, L->self.bo, w->X, 1);
        tf_layernorm(w->X, nt, L->ln2g, L->ln2b, w->Hn);
        tf_matmul(w->Hn, nt, TF_D, L->w1, TF_FF, L->b1, w->F, 0);
        tf_gelu(w->F, (size_t)nt * TF_FF);
        tf_matmul(w->F, nt, TF_FF, L->w2, TF_D, L->b2, w->X, 1);
    }
    tf_layernorm(w->X, nt, m->encg, m->encb, w->Hn);
    for (int l = 0; l < TF_ND; l++) {
        tf_matmul(w->Hn, nt, TF_D, m->dec[l].cross.wk, TF_D, m->dec[l].cross.bk, w->km[l], 0);
        tf_matmul(w->Hn, nt, TF_D, m->dec[l].cross.wv, TF_D, m->dec[l].cross.bv, w->vm[l], 0);
    }

    // Greedy decoding with a key/value cache.
    int tok[TF_B], done[TF_B], tmax[TF_B], ndone = 0;
    for (int b = 0; b < TF_B; b++) {
        tok[b] = TF_BOS;
        done[b] = 0;
        tmax[b] = len[b] + 4 < TF_MAXT ? len[b] + 4 : TF_MAXT;
    }
    for (int t = 0; t < TF_MAXT && ndone < TF_B; t++) {
        for (int b = 0; b < TF_B; b++) {
            float *x = w->X + (size_t)b * TF_D;
            const float *e = m->emb + (size_t)tok[b] * TF_D;
            for (int j = 0; j < TF_D; j++) x[j] = e[j] * esc + m->pe[t][j];
        }
        for (int l = 0; l < TF_ND; l++) {
            const tf_layer *L = &m->dec[l];
            tf_layernorm(w->X, TF_B, L->ln1g, L->ln1b, w->Hn);
            tf_matmul(w->Hn, TF_B, TF_D, L->self.wq, TF_D, L->self.bq, w->Q, 0);
            tf_matmul(w->Hn, TF_B, TF_D, L->self.wk, TF_D, L->self.bk, w->K, 0);
            tf_matmul(w->Hn, TF_B, TF_D, L->self.wv, TF_D, L->self.bv, w->V, 0);
            for (int b = 0; b < TF_B; b++) {
                float *kc = w->kc[l] + (size_t)b * TF_MAXT * TF_D, *vc = w->vc[l] + (size_t)b * TF_MAXT * TF_D;
                memcpy(kc + (size_t)t * TF_D, w->K + (size_t)b * TF_D, TF_D * sizeof(float));
                memcpy(vc + (size_t)t * TF_D, w->V + (size_t)b * TF_D, TF_D * sizeof(float));
                for (int hd = 0; hd < TF_H; hd++)
                    tf_attend(w->Q + (size_t)b * TF_D + hd * TF_DH, kc + hd * TF_DH, vc + hd * TF_DH, TF_D, t + 1,
                              w->sc, w->A + (size_t)b * TF_D + hd * TF_DH);
            }
            tf_matmul(w->A, TF_B, TF_D, L->self.wo, TF_D, L->self.bo, w->X, 1);
            tf_layernorm(w->X, TF_B, L->ln2g, L->ln2b, w->Hn);
            tf_matmul(w->Hn, TF_B, TF_D, L->cross.wq, TF_D, L->cross.bq, w->Q, 0);
            for (int b = 0; b < TF_B; b++)
                for (int hd = 0; hd < TF_H; hd++) {
                    size_t base = (size_t)off[b] * TF_D + hd * TF_DH;
                    tf_attend(w->Q + (size_t)b * TF_D + hd * TF_DH, w->km[l] + base, w->vm[l] + base, TF_D, len[b],
                              w->sc, w->A + (size_t)b * TF_D + hd * TF_DH);
                }
            tf_matmul(w->A, TF_B, TF_D, L->cross.wo, TF_D, L->cross.bo, w->X, 1);
            tf_layernorm(w->X, TF_B, L->ln3g, L->ln3b, w->Hn);
            tf_matmul(w->Hn, TF_B, TF_D, L->w1, TF_FF, L->b1, w->F, 0);
            tf_gelu(w->F, (size_t)TF_B * TF_FF);
            tf_matmul(w->F, TF_B, TF_FF, L->w2, TF_D, L->b2, w->X, 1);
        }
        tf_layernorm(w->X, TF_B, m->decg, m->decb, w->Hn);
        tf_matmul(w->Hn, TF_B, TF_D, m->wout, TF_V, NULL, w->logits, 0);
        for (int b = 0; b < TF_B; b++) {
            if (done[b]) continue;
            const float *lg = w->logits + (size_t)b * TF_V;
            int best = 0;
            for (int v = 1; v < TF_V; v++)
                if (lg[v] > lg[best]) best = v;
            double se = 0;
            for (int v = 0; v < TF_V; v++) se += exp((double)lg[v] - (double)lg[best]);
            *nll += log(se);
            *dg = fb_digest(*dg, (uint64_t)best | (uint64_t)b << 16 | (uint64_t)t << 24);
            tok[b] = best;
            (*tokens)++;
            if (best == TF_EOS || t + 1 >= tmax[b]) {
                done[b] = 1;
                ndone++;
            }
        }
    }
    *tokens += nt;
}

/// Neural machine translation inference in fp32 (the class of Marian): a
/// pre-norm encoder-decoder transformer (width 256, 4 heads, feed-forward
/// 1024 with GELU, 2 + 2 layers, 3 000-token vocabulary) with weights from
/// the suite's generator. Batches of eight random source sentences (12-28
/// tokens) are encoded together, then decoded greedily with a key/value
/// cache, causal self-attention and cross-attention to the encoder output,
/// for up to 4 tokens more than the source. All matrix products go through
/// one hand-blocked fp32 kernel; exp and tanh are the file's own, so no
/// libm difference can flip a token. `value` is the summed negative log-likelihood of the chosen tokens;
/// `checksum` digests the chosen token ids. Sizes 1/2/3: 5, 28 and 120
/// batches.
int cbk_transformer(int size, cb_bench_result *out) {
    int batches = size == 1 ? 5 : (size == 2 ? 28 : 120);
    tf_model *m = malloc(sizeof(tf_model));
    tf_work *w = calloc(1, sizeof(tf_work));
    int rc = 0;
    if (m == NULL || w == NULL) {
        free(m);
        free(w);
        return 1;
    }
    m->blob = NULL;
    const size_t rows = (size_t)TF_B * TF_MAXS;
    w->X = malloc(rows * TF_D * sizeof(float));
    w->Hn = malloc(rows * TF_D * sizeof(float));
    w->Q = malloc(rows * TF_D * sizeof(float));
    w->K = malloc(rows * TF_D * sizeof(float));
    w->V = malloc(rows * TF_D * sizeof(float));
    w->A = malloc(rows * TF_D * sizeof(float));
    w->F = malloc(rows * TF_FF * sizeof(float));
    w->logits = malloc((size_t)TF_B * TF_V * sizeof(float));
    int ok = w->X && w->Hn && w->Q && w->K && w->V && w->A && w->F && w->logits;
    for (int l = 0; l < TF_ND; l++) {
        w->kc[l] = malloc((size_t)TF_B * TF_MAXT * TF_D * sizeof(float));
        w->vc[l] = malloc((size_t)TF_B * TF_MAXT * TF_D * sizeof(float));
        w->km[l] = malloc(rows * TF_D * sizeof(float));
        w->vm[l] = malloc(rows * TF_D * sizeof(float));
        ok = ok && w->kc[l] && w->vc[l] && w->km[l] && w->vm[l];
    }
    if (!ok || tf_init(m) != 0) {
        rc = 1;
    } else {
        fb_rng r;
        fb_seed(&r, 0x7F0A12ull);
        double nll = 0;
        uint64_t dg = 0;
        long tokens = 0;
        for (int k = 0; k < batches; k++) tf_batch(m, w, &r, &nll, &dg, &tokens);
        out->value = nll;
        out->checksum = dg;
        out->work = (double)tokens;
        out->unit = "tokens";
    }
    free(m->blob);
    free(m);
    free(w->X);
    free(w->Hn);
    free(w->Q);
    free(w->K);
    free(w->V);
    free(w->A);
    free(w->F);
    free(w->logits);
    for (int l = 0; l < TF_ND; l++) {
        free(w->kc[l]);
        free(w->vc[l]);
        free(w->km[l]);
        free(w->vm[l]);
    }
    free(w);
    return rc;
}

// ── sph: smoothed particle hydrodynamics ────────────────────────────────

#define SPH_GAMMA (5.0 / 3.0)
#define SPH_AV_ALPHA 1.0
#define SPH_AV_BETA 2.0

typedef struct {
    int n, nc, ncell;
    double h, m;
    double *x, *y, *z, *vx, *vy, *vz, *u;      // state, kept in cell order
    double *wx, *wy, *wz, *up;                 // velocity and energy predicted to the force time
    double *ax, *ay, *az, *du, *rho, *p, *cs;  // derived each step
    double *tmp;
    int *cell, *order, *start, *fill;
    int *nbs, *nbl;
    int nbcap;
} sph_sys;

/// The M4 cubic spline kernel's shape and its derivative, q = r / h.
static inline double sph_w(double q) {
    if (q < 1.0) return 1.0 - 1.5 * q * q + 0.75 * q * q * q;
    if (q < 2.0) {
        double t = 2.0 - q;
        return 0.25 * t * t * t;
    }
    return 0.0;
}

static inline double sph_dw(double q) {
    if (q < 1.0) return -3.0 * q + 2.25 * q * q;
    if (q < 2.0) {
        double t = 2.0 - q;
        return -0.75 * t * t;
    }
    return 0.0;
}

static inline double sph_wrap(double d) {
    return d > 0.5 ? d - 1.0 : (d < -0.5 ? d + 1.0 : d);
}

static inline int sph_cell1(double v, int nc) {
    int c = (int)(v * nc);
    return c < 0 ? 0 : (c >= nc ? nc - 1 : c);
}

/// Bins the particles into cells of at least 2h and reorders every state
/// array by cell (a counting sort, stable), so neighbours sit together in
/// memory as they do in a production code's space-filling-curve order.
static void sph_sort(sph_sys *s) {
    int N = s->n, nc = s->nc;
    memset(s->start, 0, (size_t)(s->ncell + 1) * sizeof(int));
    for (int i = 0; i < N; i++) {
        int c = (sph_cell1(s->z[i], nc) * nc + sph_cell1(s->y[i], nc)) * nc + sph_cell1(s->x[i], nc);
        s->cell[i] = c;
        s->start[c + 1]++;
    }
    for (int c = 0; c < s->ncell; c++) s->start[c + 1] += s->start[c];
    memcpy(s->fill, s->start, (size_t)s->ncell * sizeof(int));
    for (int i = 0; i < N; i++) s->order[s->fill[s->cell[i]]++] = i;
    double **arr[11] = {&s->x, &s->y, &s->z, &s->vx, &s->vy, &s->vz, &s->u, &s->wx, &s->wy, &s->wz, &s->up};
    for (int a = 0; a < 11; a++) {
        double *src = *arr[a];
        for (int k = 0; k < N; k++) s->tmp[k] = src[s->order[k]];
        *arr[a] = s->tmp;
        s->tmp = src;
    }
}

/// Density by kernel summation over the 27 surrounding cells (periodic),
/// building each particle's neighbour list on the way; then the ideal-gas
/// equation of state; then pressure and Monaghan artificial-viscosity
/// forces and the internal-energy equation, from velocities and energies
/// predicted to the end of the step. Returns the next time step
/// (CFL and acceleration limits), or a negative value when out of memory.
static double sph_forces(sph_sys *s) {
    sph_sort(s);
    const int N = s->n, nc = s->nc;
    const double h = s->h, m = s->m, h2x4 = 4.0 * h * h;
    const double wn = 1.0 / (3.141592653589793 * h * h * h), wdn = wn / h;
    int nn = 0;
    for (int i = 0; i < N; i++) {
        double xi = s->x[i], yi = s->y[i], zi = s->z[i];
        int cx = sph_cell1(xi, nc), cy = sph_cell1(yi, nc), cz = sph_cell1(zi, nc);
        double rho = m * wn;  // the particle itself
        s->nbs[i] = nn;
        for (int dz = -1; dz <= 1; dz++) {
            int zz = (cz + dz + nc) % nc;
            for (int dy = -1; dy <= 1; dy++) {
                int yy = (cy + dy + nc) % nc;
                for (int dx = -1; dx <= 1; dx++) {
                    int c = (zz * nc + yy) * nc + (cx + dx + nc) % nc;
                    for (int j = s->start[c]; j < s->start[c + 1]; j++) {
                        if (j == i) continue;
                        double ex = sph_wrap(xi - s->x[j]), ey = sph_wrap(yi - s->y[j]), ez = sph_wrap(zi - s->z[j]);
                        double r2 = ex * ex + ey * ey + ez * ez;
                        if (r2 >= h2x4) continue;
                        if (nn >= s->nbcap && fb_grow((void **)&s->nbl, &s->nbcap, nn + 1, sizeof(int))) return -1;
                        s->nbl[nn++] = j;
                        rho += m * wn * sph_w(sqrt(r2) / h);
                    }
                }
            }
        }
        s->rho[i] = rho;
    }
    s->nbs[N] = nn;
    for (int i = 0; i < N; i++) {
        s->p[i] = (SPH_GAMMA - 1.0) * s->rho[i] * s->up[i];
        s->cs[i] = sqrt(SPH_GAMMA * s->p[i] / s->rho[i]);
    }
    double vmax = 0, amax = 0;
    for (int i = 0; i < N; i++) {
        double xi = s->x[i], yi = s->y[i], zi = s->z[i];
        double vxi = s->wx[i], vyi = s->wy[i], vzi = s->wz[i];
        double pri = s->p[i] / (s->rho[i] * s->rho[i]);
        double axi = 0, ayi = 0, azi = 0, dui = 0, mumax = 0;
        for (int k = s->nbs[i]; k < s->nbs[i + 1]; k++) {
            int j = s->nbl[k];
            double ex = sph_wrap(xi - s->x[j]), ey = sph_wrap(yi - s->y[j]), ez = sph_wrap(zi - s->z[j]);
            double r2 = ex * ex + ey * ey + ez * ez;
            if (r2 <= 0) continue;
            double r = sqrt(r2);
            double f = wdn * sph_dw(r / h) / r;  // grad W = f * (ri - rj)
            double gx = f * ex, gy = f * ey, gz = f * ez;
            double dvx = vxi - s->wx[j], dvy = vyi - s->wy[j], dvz = vzi - s->wz[j];
            double vr = dvx * ex + dvy * ey + dvz * ez;
            double visc = 0;
            if (vr < 0) {
                double mu = h * vr / (r2 + 0.01 * h * h);
                if (-mu > mumax) mumax = -mu;
                double cbar = 0.5 * (s->cs[i] + s->cs[j]), rbar = 0.5 * (s->rho[i] + s->rho[j]);
                visc = (-SPH_AV_ALPHA * cbar * mu + SPH_AV_BETA * mu * mu) / rbar;
            }
            double prj = s->p[j] / (s->rho[j] * s->rho[j]);
            double fp = m * (pri + prj + visc);
            axi -= fp * gx;
            ayi -= fp * gy;
            azi -= fp * gz;
            dui += m * (pri + 0.5 * visc) * (dvx * gx + dvy * gy + dvz * gz);
        }
        s->ax[i] = axi;
        s->ay[i] = ayi;
        s->az[i] = azi;
        s->du[i] = dui;
        // Monaghan's signal speed, viscosity included.
        double sig = s->cs[i] + 1.2 * (SPH_AV_ALPHA * s->cs[i] + SPH_AV_BETA * mumax);
        double a = sqrt(axi * axi + ayi * ayi + azi * azi);
        if (sig > vmax) vmax = sig;
        if (a > amax) amax = a;
    }
    double dt = 0.3 * h / vmax;
    if (amax > 0) {
        double da = 0.25 * sqrt(h / amax);
        if (da < dt) dt = da;
    }
    return dt;
}

static void sph_free(sph_sys *s) {
    double *d[19] = {s->x, s->y, s->z, s->vx, s->vy, s->vz, s->u, s->wx, s->wy, s->wz, s->up,
                     s->ax, s->ay, s->az, s->du, s->rho, s->p, s->cs, s->tmp};
    for (int k = 0; k < 19; k++) free(d[k]);
    free(s->cell);
    free(s->order);
    free(s->start);
    free(s->fill);
    free(s->nbs);
    free(s->nbl);
}

/// Smoothed particle hydrodynamics (the class of SPH-EXA): a Sedov–Taylor
/// blast in a periodic unit box of ideal gas. Particles start on a
/// jittered lattice at rest; a unit of energy is deposited, kernel
/// weighted, in the particles nearest the centre. Each step sorts the
/// particles into a cell list, sums density with the cubic-spline kernel,
/// applies the equation of state, computes pressure forces with Monaghan
/// artificial viscosity and the energy equation, and advances with
/// kick-drift-kick leapfrog (velocity-dependent terms from predicted
/// velocities) under Monaghan's signal-speed time step. `value` is the
/// total (kinetic plus internal) energy at the end; conserved by the
/// symmetric forces, it drifts only by the integrator's error, which is the
/// part a wrong answer would change. `checksum` is the final neighbour-pair
/// count. Sizes 1/2/3: 16^3 particles for 22 steps, 24^3 for 40 steps,
/// 32^3 for 70 steps.
int cbk_sph(int size, cb_bench_result *out) {
    int n1 = size == 1 ? 16 : (size == 2 ? 24 : 32);
    int steps = size == 1 ? 22 : (size == 2 ? 40 : 70);
    sph_sys s;
    memset(&s, 0, sizeof s);
    int N = n1 * n1 * n1;
    s.n = N;
    s.h = 1.2 / n1;
    s.m = 1.0 / N;
    s.nc = (int)(1.0 / (2.0 * s.h));
    if (s.nc < 3) s.nc = 3;
    s.ncell = s.nc * s.nc * s.nc;
    double **d[19] = {&s.x, &s.y, &s.z, &s.vx, &s.vy, &s.vz, &s.u, &s.wx, &s.wy, &s.wz, &s.up,
                      &s.ax, &s.ay, &s.az, &s.du, &s.rho, &s.p, &s.cs, &s.tmp};
    int ok = 1;
    for (int k = 0; k < 19; k++) ok = ok && (*d[k] = calloc((size_t)N, sizeof(double))) != NULL;
    s.cell = malloc((size_t)N * sizeof(int));
    s.order = malloc((size_t)N * sizeof(int));
    s.start = malloc((size_t)(s.ncell + 1) * sizeof(int));
    s.fill = malloc((size_t)s.ncell * sizeof(int));
    s.nbs = malloc((size_t)(N + 1) * sizeof(int));
    if (!ok || !s.cell || !s.order || !s.start || !s.fill || !s.nbs || fb_grow((void **)&s.nbl, &s.nbcap, N * 64, sizeof(int))) {
        sph_free(&s);
        return 1;
    }

    fb_rng r;
    fb_seed(&r, 0x5EB0ull);
    double dl = 1.0 / n1, wsum = 0;
    const double wn = 1.0 / (3.141592653589793 * s.h * s.h * s.h);
    for (int k = 0, i = 0; k < n1; k++)
        for (int j = 0; j < n1; j++)
            for (int l = 0; l < n1; l++, i++) {
                s.x[i] = (l + 0.5 + 0.2 * (fb_u01(&r) - 0.5)) * dl;
                s.y[i] = (j + 0.5 + 0.2 * (fb_u01(&r) - 0.5)) * dl;
                s.z[i] = (k + 0.5 + 0.2 * (fb_u01(&r) - 0.5)) * dl;
                s.u[i] = 1e-5;
            }
    for (int i = 0; i < N; i++) {
        double ex = s.x[i] - 0.5, ey = s.y[i] - 0.5, ez = s.z[i] - 0.5;
        wsum += wn * sph_w(sqrt(ex * ex + ey * ey + ez * ez) / s.h);
    }
    for (int i = 0; i < N; i++) {
        double ex = s.x[i] - 0.5, ey = s.y[i] - 0.5, ez = s.z[i] - 0.5;
        s.u[i] += wn * sph_w(sqrt(ex * ex + ey * ey + ez * ez) / s.h) / (wsum * s.m);
        s.up[i] = s.u[i];
    }

    double dt = sph_forces(&s);
    for (int st = 0; st < steps && dt > 0; st++) {
        for (int i = 0; i < N; i++) {
            s.vx[i] += 0.5 * dt * s.ax[i];
            s.vy[i] += 0.5 * dt * s.ay[i];
            s.vz[i] += 0.5 * dt * s.az[i];
            s.u[i] += 0.5 * dt * s.du[i];
            double *pos[3] = {&s.x[i], &s.y[i], &s.z[i]};
            double vel[3] = {s.vx[i], s.vy[i], s.vz[i]};
            for (int a = 0; a < 3; a++) {
                double v = *pos[a] + dt * vel[a];
                if (v < 0) v += 1.0;
                else if (v >= 1.0) v -= 1.0;
                *pos[a] = v;
            }
            s.wx[i] = s.vx[i] + 0.5 * dt * s.ax[i];
            s.wy[i] = s.vy[i] + 0.5 * dt * s.ay[i];
            s.wz[i] = s.vz[i] + 0.5 * dt * s.az[i];
            s.up[i] = s.u[i] + 0.5 * dt * s.du[i];
        }
        double dtn = sph_forces(&s);
        for (int i = 0; i < N; i++) {
            s.vx[i] += 0.5 * dt * s.ax[i];
            s.vy[i] += 0.5 * dt * s.ay[i];
            s.vz[i] += 0.5 * dt * s.az[i];
            s.u[i] += 0.5 * dt * s.du[i];
        }
        dt = dtn;
    }
    if (dt < 0) {
        sph_free(&s);
        return 1;
    }
    double e = 0;
    for (int i = 0; i < N; i++)
        e += s.m * (0.5 * (s.vx[i] * s.vx[i] + s.vy[i] * s.vy[i] + s.vz[i] * s.vz[i]) + s.u[i]);
    out->value = e;
    out->checksum = (uint64_t)s.nbs[N];
    out->work = (double)N * steps;
    out->unit = "particle steps";
    sph_free(&s);
    return isfinite(e) ? 0 : 2;
}

// ── hydro: compressible hydrodynamics ───────────────────────────────────

#define HY_GAMMA 1.4

/// The HLLC approximate Riemann solver (Toro): the flux of mass, normal
/// momentum, tangential momentum and energy through an interface between
/// left and right primitive states (density, normal and tangential
/// velocity, pressure).
static void hy_hllc(const double *L, const double *R, double *f) {
    double rl = L[0], ul = L[1], vl = L[2], pl = L[3];
    double rr = R[0], ur = R[1], vr = R[2], pr = R[3];
    double cl = sqrt(HY_GAMMA * pl / rl), cr = sqrt(HY_GAMMA * pr / rr);
    double el = pl / (HY_GAMMA - 1.0) + 0.5 * rl * (ul * ul + vl * vl);
    double er = pr / (HY_GAMMA - 1.0) + 0.5 * rr * (ur * ur + vr * vr);
    double sl = fmin(ul - cl, ur - cr), sr = fmax(ul + cl, ur + cr);
    double ss = (pr - pl + rl * ul * (sl - ul) - rr * ur * (sr - ur)) / (rl * (sl - ul) - rr * (sr - ur));
    if (sl >= 0) {
        f[0] = rl * ul;
        f[1] = rl * ul * ul + pl;
        f[2] = rl * ul * vl;
        f[3] = ul * (el + pl);
    } else if (ss >= 0) {
        double k = rl * (sl - ul) / (sl - ss);
        f[0] = rl * ul + sl * (k - rl);
        f[1] = rl * ul * ul + pl + sl * (k * ss - rl * ul);
        f[2] = rl * ul * vl + sl * (k * vl - rl * vl);
        f[3] = ul * (el + pl) + sl * (k * (el / rl + (ss - ul) * (ss + pl / (rl * (sl - ul)))) - el);
    } else if (sr > 0) {
        double k = rr * (sr - ur) / (sr - ss);
        f[0] = rr * ur + sr * (k - rr);
        f[1] = rr * ur * ur + pr + sr * (k * ss - rr * ur);
        f[2] = rr * ur * vr + sr * (k * vr - rr * vr);
        f[3] = ur * (er + pr) + sr * (k * (er / rr + (ss - ur) * (ss + pr / (rr * (sr - ur)))) - er);
    } else {
        f[0] = rr * ur;
        f[1] = rr * ur * ur + pr;
        f[2] = rr * ur * vr;
        f[3] = ur * (er + pr);
    }
}

static inline double hy_vanleer(double a, double b) {
    return a * b > 0 ? 2.0 * a * b / (a + b) : 0.0;
}

typedef struct {
    double *w;   // primitives, 4 per cell, with two ghost cells each side
    double *wl;  // evolved left/right face states
    double *wr;
    double *f;   // interface fluxes
} hy_line;

/// One MUSCL-Hancock update of a line of cells: van Leer-limited slopes in
/// primitive variables, a half-step evolution of the face states, HLLC
/// fluxes, conservative update. The ghost cells mirror the walls.
static void hy_line_update(hy_line *ln, int n, double dtdx, double *rho, double *mn, double *mt, double *en, ptrdiff_t stride) {
    const int L = n + 4;
    double *w = ln->w;
    for (int g = 0; g < L; g++) {
        int i = g - 2, sgn = 1;
        if (i < 0) {
            i = -1 - i;
            sgn = -1;
        } else if (i >= n) {
            i = 2 * n - 1 - i;
            sgn = -1;
        }
        ptrdiff_t o = (ptrdiff_t)i * stride;
        double r = rho[o], u = mn[o] / r, v = mt[o] / r;
        double *c = w + 4 * g;
        c[0] = r;
        c[1] = sgn * u;
        c[2] = v;
        c[3] = (HY_GAMMA - 1.0) * (en[o] - 0.5 * r * (u * u + v * v));
    }
    for (int g = 1; g < L - 1; g++) {
        const double *c = w + 4 * g, *cm = c - 4, *cp = c + 4;
        double d[4];
        for (int k = 0; k < 4; k++) d[k] = hy_vanleer(c[k] - cm[k], cp[k] - c[k]);
        double r = c[0], u = c[1], p = c[3];
        double h = 0.5 * dtdx;
        double e[4] = {-h * (u * d[0] + r * d[1]), -h * (u * d[1] + d[3] / r), -h * (u * d[2]),
                       -h * (HY_GAMMA * p * d[1] + u * d[3])};
        double *l = ln->wl + 4 * g, *rr = ln->wr + 4 * g;
        for (int k = 0; k < 4; k++) {
            l[k] = c[k] - 0.5 * d[k] + e[k];
            rr[k] = c[k] + 0.5 * d[k] + e[k];
        }
        if (l[0] <= 0 || l[3] <= 0 || rr[0] <= 0 || rr[3] <= 0)
            for (int k = 0; k < 4; k++) l[k] = rr[k] = c[k];  // first order where the limiter is not enough
    }
    for (int g = 1; g < L - 2; g++) hy_hllc(ln->wr + 4 * g, ln->wl + 4 * (g + 1), ln->f + 4 * g);
    for (int i = 0; i < n; i++) {
        int g = i + 2;
        const double *fp = ln->f + 4 * g, *fm = ln->f + 4 * (g - 1);
        ptrdiff_t o = (ptrdiff_t)i * stride;
        rho[o] -= dtdx * (fp[0] - fm[0]);
        mn[o] -= dtdx * (fp[1] - fm[1]);
        mt[o] -= dtdx * (fp[2] - fm[2]);
        en[o] -= dtdx * (fp[3] - fm[3]);
    }
}

/// Explicit compressible hydrodynamics (the class of CloverLeaf): the 2D
/// Euler equations for an ideal gas on a structured grid in a closed box,
/// solved with the MUSCL-Hancock scheme and HLLC fluxes, dimensionally
/// split with the sweep order alternating each step, under a CFL time
/// step. The initial state is a Sod-style high-pressure slab along one
/// wall, a blast (a small disc at 200x the ambient pressure) and a dense
/// cylinder for the shocks to strike. Total mass and energy are conserved
/// to rounding (checked). `value` is the kinetic energy at t = 0.2, which
/// depends on the whole computed flow; `checksum` is the step count.
/// Sizes 1/2/3: 128^2, 232^2 and 352^2 cells.
int cbk_hydro(int size, cb_bench_result *out) {
    int n = size == 1 ? 128 : (size == 2 ? 232 : 352);
    const double tend = 0.2, cfl = 0.6, dx = 1.0 / n;
    size_t cells = (size_t)n * n;
    double *rho = malloc(cells * sizeof(double)), *mx = malloc(cells * sizeof(double));
    double *my = malloc(cells * sizeof(double)), *en = malloc(cells * sizeof(double));
    hy_line ln;
    ln.w = malloc((size_t)(n + 4) * 4 * sizeof(double));
    ln.wl = malloc((size_t)(n + 4) * 4 * sizeof(double));
    ln.wr = malloc((size_t)(n + 4) * 4 * sizeof(double));
    ln.f = malloc((size_t)(n + 4) * 4 * sizeof(double));
    int rc = 0;
    if (!rho || !mx || !my || !en || !ln.w || !ln.wl || !ln.wr || !ln.f) {
        rc = 1;
        goto done;
    }
    for (int j = 0; j < n; j++)
        for (int i = 0; i < n; i++) {
            double x = (i + 0.5) * dx, y = (j + 0.5) * dx, r = 1.0, p = 0.1;
            if (x < 0.25) p = 1.0;
            double bx = x - 0.68, by = y - 0.62, cx = x - 0.45, cy = y - 0.3;
            if (bx * bx + by * by < 0.12 * 0.12) p = 20.0;
            if (cx * cx + cy * cy < 0.1 * 0.1) r = 3.0;
            size_t o = (size_t)j * n + i;
            rho[o] = r;
            mx[o] = my[o] = 0;
            en[o] = p / (HY_GAMMA - 1.0);
        }
    double m0 = 0, e0 = 0;
    for (size_t o = 0; o < cells; o++) {
        m0 += rho[o];
        e0 += en[o];
    }
    double t = 0;
    long step = 0;
    for (int last = 0; !last; step++) {
        double smax = 0;
        for (size_t o = 0; o < cells; o++) {
            double r = rho[o], u = mx[o] / r, v = my[o] / r;
            double p = (HY_GAMMA - 1.0) * (en[o] - 0.5 * r * (u * u + v * v));
            double c = sqrt(HY_GAMMA * p / r);
            double s = fmax(fabs(u), fabs(v)) + c;
            if (s > smax) smax = s;
        }
        double dt = cfl * dx / smax;
        if (t + dt >= tend) {
            dt = tend - t;
            last = 1;
        }
        for (int pass = 0; pass < 2; pass++) {
            if ((pass == 0) == (step % 2 == 0)) {
                for (int j = 0; j < n; j++) {
                    size_t o = (size_t)j * n;
                    hy_line_update(&ln, n, dt / dx, rho + o, mx + o, my + o, en + o, 1);
                }
            } else {
                for (int i = 0; i < n; i++) hy_line_update(&ln, n, dt / dx, rho + i, my + i, mx + i, en + i, n);
            }
        }
        t += dt;
        if (step > 100000) {
            rc = 2;
            goto done;
        }
    }
    double m1 = 0, e1 = 0, ke = 0;
    for (size_t o = 0; o < cells; o++) {
        m1 += rho[o];
        e1 += en[o];
        ke += 0.5 * (mx[o] * mx[o] + my[o] * my[o]) / rho[o];
    }
    if (!(fabs(m1 - m0) <= 1e-9 * m0 && fabs(e1 - e0) <= 1e-9 * e0 && isfinite(ke))) {
        rc = 3;
        goto done;
    }
    out->value = ke * dx * dx;
    out->checksum = (uint64_t)step;
    out->work = (double)cells * step;
    out->unit = "cell updates";
done:
    free(rho);
    free(mx);
    free(my);
    free(en);
    free(ln.w);
    free(ln.wl);
    free(ln.wr);
    free(ln.f);
    return rc;
}
