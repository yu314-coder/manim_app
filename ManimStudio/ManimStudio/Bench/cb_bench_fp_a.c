//
//  cb_bench_fp_a.c — the floating-point simulation workloads of `spec`:
//  lattice Boltzmann flow, molecular dynamics, path tracing, FDTD
//  electromagnetics, preconditioned conjugate gradient, a BSSN-like
//  relativity stencil, an image pipeline, shallow-water dynamics and Monte
//  Carlo neutron transport.
//
//  They are the KINDS of program SPEC CPU's floating-point suites are made
//  of, but every algorithm here is written from scratch for CodeBench; no
//  SPEC (or other benchmark) source is used.
//
//  What every workload in this file keeps to:
//  - Reentrant. All mutable state lives in the call's own heap blocks and
//    locals (tables are const), so `spec --rate` can run a copy per core.
//  - Deterministic. Fixed seeds and a private xoshiro256** generator; no
//    rand(), no clocks, no output.
//  - Reproducible. Floating-point contraction is off for this file (below),
//    so -O0 and -Os round every product the same way. Where a one-ulp
//    difference could be amplified — chaotic dynamics, Monte Carlo
//    branches — the code uses only correctly rounded operations (+ − × ÷ √)
//    and this file's own polynomial exp/log/sin/cos, so the answer does not
//    depend on the platform's libm either.
//  - Bounded. Under 256 KB of stack; big arrays on the heap, all freed.
//

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cb_bench.h"

// Fusing a*b+c into one FMA rounds once instead of twice, and whether the
// compiler does it depends on the optimisation level. Keep every product
// rounded, so the answer is the same at -O0 and -Os.
#pragma STDC FP_CONTRACT OFF

// ── Shared helpers ──────────────────────────────────────────────────────

/// Doubles of padding between the arrays a workload carves from one block,
/// so that arrays whose size is a multiple of the cache's set stride (a
/// power-of-two grid, say) do not all land on the same cache sets.
#define FPA_PAD 72

/// `size` clamped to the three levels.
static int fpa_level(int size) {
    return size <= 1 ? 1 : (size >= 3 ? 3 : 2);
}

/// xoshiro256** state. Seeded through splitmix64 from one 64-bit seed.
typedef struct {
    uint64_t s[4];
} fpa_rng;

static uint64_t fpa_splitmix(uint64_t *x) {
    uint64_t z = (*x += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

static void fpa_seed(fpa_rng *r, uint64_t seed) {
    uint64_t x = seed;
    for (int i = 0; i < 4; i++) r->s[i] = fpa_splitmix(&x);
}

static inline uint64_t fpa_rotl(uint64_t x, int k) {
    return (x << k) | (x >> (64 - k));
}

static uint64_t fpa_next(fpa_rng *r) {
    uint64_t *s = r->s;
    const uint64_t result = fpa_rotl(s[1] * 5, 7) * 9;
    const uint64_t t = s[1] << 17;
    s[2] ^= s[0];
    s[3] ^= s[1];
    s[1] ^= s[2];
    s[0] ^= s[3];
    s[2] ^= t;
    s[3] = fpa_rotl(s[3], 45);
    return result;
}

/// Uniform in [0, 1), 53 bits.
static double fpa_u01(fpa_rng *r) {
    return (double)(fpa_next(r) >> 11) * 0x1.0p-53;
}

/// Uniform in (0, 1]: safe to take the logarithm of.
static double fpa_u01_open(fpa_rng *r) {
    return (double)((fpa_next(r) >> 11) + 1) * 0x1.0p-53;
}

static const double FPA_PI = 3.14159265358979323846;
// ln 2 and π/2 split into a short head (exact when multiplied by a small
// integer) and a tail, for range reduction.
static const double FPA_LN2_HI = 6.93147180369123816490e-01;
static const double FPA_LN2_LO = 1.90821492927058770002e-10;
static const double FPA_PIO2_HI = 1.57079632673412561417e+00;
static const double FPA_PIO2_LO = 6.07710050650619224932e-11;

/// e^x from + − × ÷ only (a Taylor series after reduction by ln 2), so it
/// gives the same bits on every IEEE-754 machine. About 1 ulp accurate.
static double fpa_exp(double x) {
    if (x > 700.0) x = 700.0;
    if (x < -700.0) x = -700.0;
    const double kd = floor(x * 1.44269504088896340736 + 0.5);
    const double r = (x - kd * FPA_LN2_HI) - kd * FPA_LN2_LO;   // |r| <= 0.35
    static const double c[14] = {
        1.0, 1.0, 1.0 / 2.0, 1.0 / 6.0, 1.0 / 24.0, 1.0 / 120.0, 1.0 / 720.0,
        1.0 / 5040.0, 1.0 / 40320.0, 1.0 / 362880.0, 1.0 / 3628800.0,
        1.0 / 39916800.0, 1.0 / 479001600.0, 1.0 / 6227020800.0};
    double p = c[13];
    for (int k = 12; k >= 0; k--) p = p * r + c[k];
    return ldexp(p, (int)kd);
}

/// ln x for x > 0, the same way: frexp, then the atanh series of
/// (m−1)/(m+1).
static double fpa_log(double x) {
    int e;
    double m = frexp(x, &e);                       // x = m·2^e, m in [½, 1)
    if (m < 0.70710678118654752440) {
        m *= 2.0;
        e -= 1;
    }
    const double s = (m - 1.0) / (m + 1.0), s2 = s * s;   // |s| <= 0.172
    static const double c[13] = {
        1.0, 1.0 / 3.0, 1.0 / 5.0, 1.0 / 7.0, 1.0 / 9.0, 1.0 / 11.0, 1.0 / 13.0,
        1.0 / 15.0, 1.0 / 17.0, 1.0 / 19.0, 1.0 / 21.0, 1.0 / 23.0, 1.0 / 25.0};
    double p = c[12];
    for (int k = 11; k >= 0; k--) p = p * s2 + c[k];
    const double ed = (double)e;
    return ed * FPA_LN2_HI + (2.0 * s * p + ed * FPA_LN2_LO);
}

/// sin x and cos x the same way, for |x| up to about 1e5.
static void fpa_sincos(double x, double *sn, double *cs) {
    const double kd = floor(x * 0.63661977236758134308 + 0.5);
    const double r = (x - kd * FPA_PIO2_HI) - kd * FPA_PIO2_LO;  // |r| <= π/4
    const double r2 = r * r;
    static const double sc[9] = {
        1.0, -1.0 / 6.0, 1.0 / 120.0, -1.0 / 5040.0, 1.0 / 362880.0,
        -1.0 / 39916800.0, 1.0 / 6227020800.0, -1.0 / 1307674368000.0,
        1.0 / 355687428096000.0};
    static const double cc[9] = {
        1.0, -1.0 / 2.0, 1.0 / 24.0, -1.0 / 720.0, 1.0 / 40320.0,
        -1.0 / 3628800.0, 1.0 / 479001600.0, -1.0 / 87178291200.0,
        1.0 / 20922789888000.0};
    double ps = sc[8], pc = cc[8];
    for (int k = 7; k >= 0; k--) {
        ps = ps * r2 + sc[k];
        pc = pc * r2 + cc[k];
    }
    const double s = r * ps, c = pc;
    switch ((int)((long long)kd & 3)) {
        case 0: *sn = s; *cs = c; break;
        case 1: *sn = c; *cs = -s; break;
        case 2: *sn = -s; *cs = -c; break;
        default: *sn = -c; *cs = s; break;
    }
}

static double fpa_sin(double x) {
    double s, c;
    fpa_sincos(x, &s, &c);
    return s;
}

/// tanh from fpa_exp.
static double fpa_tanh(double x) {
    if (x > 20.0) return 1.0;
    if (x < -20.0) return -1.0;
    const double e = fpa_exp(2.0 * x);
    return (e - 1.0) / (e + 1.0);
}

// ── 1. Lattice Boltzmann (lbm) ──────────────────────────────────────────

// D3Q19 velocities: rest, 6 faces, 12 edges; and each one's opposite.
static const signed char lbm_cx[19] = {0, 1, -1, 0, 0, 0, 0, 1, -1, 1, -1, 1, -1, 1, -1, 0, 0, 0, 0};
static const signed char lbm_cy[19] = {0, 0, 0, 1, -1, 0, 0, 1, -1, -1, 1, 0, 0, 0, 0, 1, -1, 1, -1};
static const signed char lbm_cz[19] = {0, 0, 0, 0, 0, 1, -1, 0, 0, 0, 0, 1, -1, -1, 1, 1, -1, -1, 1};
static const unsigned char lbm_opp[19] = {0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17};

/// Lattice Boltzmann flow through an obstructed duct: the kind of
/// computational fluid dynamics program SPEC's lbm is. A D3Q19 lattice with
/// BGK (single relaxation time) collision, streamed by "pull" between two
/// lattices and fused with the collision; half-way bounce-back on the duct
/// walls, on three spherical obstacles and on a scatter of small blocks;
/// periodic along the duct; driven by a body force. The answer is the total
/// streamwise momentum of the fluid (lattice units) after the last step.
/// `size` 1: 48×24×24 cells for 250 steps (10 MB); 2: 112×40×40 for 170
/// (54 MB); 3: 160×64×64 for 195 (192 MB). Work: fluid-cell updates.
int cbk_lbm(int size, cb_bench_result *out) {
    static const int cfg[3][4] = {{48, 24, 24, 250}, {112, 40, 40, 170}, {160, 64, 64, 195}};
    const int *cf = cfg[fpa_level(size) - 1];
    const int nx = cf[0], ny = cf[1], nz = cf[2], steps = cf[3];
    const size_t n = (size_t)nx * (size_t)ny * (size_t)nz, ns = n + FPA_PAD;
    double *fa = calloc(19 * ns, sizeof(double));     // populations, one array per direction
    double *fb = malloc(19 * ns * sizeof(double));
    unsigned char *solid = calloc(n, 1);
    if (!fa || !fb || !solid) {
        free(fa); free(fb); free(solid);
        return 1;
    }

    // Weights, velocities as doubles, and the offset of the upstream cell
    // x − c (with the x wrap at either end of a row).
    double w[19], cx[19], cy[19], cz[19];
    ptrdiff_t off[19], offlo[19], offhi[19];
    for (int q = 0; q < 19; q++) {
        w[q] = q == 0 ? 1.0 / 3.0 : (q < 7 ? 1.0 / 18.0 : 1.0 / 36.0);
        cx[q] = lbm_cx[q];
        cy[q] = lbm_cy[q];
        cz[q] = lbm_cz[q];
        off[q] = -(((ptrdiff_t)lbm_cz[q] * ny + lbm_cy[q]) * nx + lbm_cx[q]);
        offlo[q] = off[q] + (lbm_cx[q] > 0 ? nx : 0);
        offhi[q] = off[q] - (lbm_cx[q] < 0 ? nx : 0);
    }

    // The duct: walls on the y and z faces, open (periodic) along x.
    for (int z = 0; z < nz; z++)
        for (int y = 0; y < ny; y++)
            if (y == 0 || y == ny - 1 || z == 0 || z == nz - 1)
                memset(solid + ((size_t)z * ny + y) * nx, 1, (size_t)nx);
    // Three spheres, staggered so the flow has to weave between them.
    for (int s = 0; s < 3; s++) {
        const int ox = nx * (2 * s + 1) / 6;
        const int oy = ny / 2 + (s == 1 ? ny / 8 : -ny / 10);
        const int oz = nz / 2 + (s == 2 ? nz / 8 : -nz / 12);
        const int r = ny / 6;
        for (int z = oz - r; z <= oz + r; z++)
            for (int y = oy - r; y <= oy + r; y++)
                for (int x = ox - r; x <= ox + r; x++) {
                    if (z < 0 || z >= nz || y < 0 || y >= ny || x < 0 || x >= nx) continue;
                    const int dx = x - ox, dy = y - oy, dz = z - oz;
                    if (dx * dx + dy * dy + dz * dz <= r * r)
                        solid[((size_t)z * ny + y) * nx + x] = 1;
                }
    }
    // A scatter of 2- and 3-cell blocks, like a porous insert.
    fpa_rng rng;
    fpa_seed(&rng, 0x1B3D5A1Bull);
    for (int b = 0; b < nx / 4; b++) {
        const int side = 2 + (int)(fpa_next(&rng) % 2);
        const int bx = (int)(fpa_next(&rng) % (uint64_t)(nx - side));
        const int by = 1 + (int)(fpa_next(&rng) % (uint64_t)(ny - 2 - side));
        const int bz = 1 + (int)(fpa_next(&rng) % (uint64_t)(nz - 2 - side));
        for (int z = bz; z < bz + side; z++)
            for (int y = by; y < by + side; y++)
                for (int x = bx; x < bx + side; x++)
                    solid[((size_t)z * ny + y) * nx + x] = 1;
    }
    size_t fluid = 0;
    for (size_t i = 0; i < n; i++) fluid += solid[i] ? 0 : 1;

    // At rest, unit density.
    for (int q = 0; q < 19; q++)
        for (size_t i = 0; i < n; i++)
            fa[(size_t)q * ns + i] = solid[i] ? 0.0 : w[q];
    memcpy(fb, fa, 19 * ns * sizeof(double));

    const double tau = 0.8, omega = 1.0 / tau;
    const double ushift = tau * 2e-5;    // body force, as an equilibrium velocity shift
    double *src = fa, *dst = fb;
    for (int step = 0; step < steps; step++) {
        const double *sq[19];
        double *dq[19];
        for (int q = 0; q < 19; q++) {
            sq[q] = src + (size_t)q * ns;
            dq[q] = dst + (size_t)q * ns;
        }
        for (int z = 1; z < nz - 1; z++) {
            for (int y = 1; y < ny - 1; y++) {
                const ptrdiff_t row = ((ptrdiff_t)z * ny + y) * nx;
                for (int x = 0; x < nx; x++) {
                    const ptrdiff_t idx = row + x;
                    if (solid[idx]) continue;
                    const ptrdiff_t *o = x == 0 ? offlo : (x == nx - 1 ? offhi : off);
                    double f[19];
                    for (int q = 0; q < 19; q++) {
                        // Pull from upstream; off a wall, bounce back what this cell sent.
                        const ptrdiff_t from = idx + o[q];
                        const double pulled = sq[q][from], bounced = sq[lbm_opp[q]][idx];
                        f[q] = solid[from] ? bounced : pulled;
                    }
                    double rho = f[0];
                    for (int q = 1; q < 19; q++) rho += f[q];
                    const double mx = (f[1] + f[7] + f[9] + f[11] + f[13]) - (f[2] + f[8] + f[10] + f[12] + f[14]);
                    const double my = (f[3] + f[7] + f[10] + f[15] + f[17]) - (f[4] + f[8] + f[9] + f[16] + f[18]);
                    const double mz = (f[5] + f[11] + f[14] + f[15] + f[18]) - (f[6] + f[12] + f[13] + f[16] + f[17]);
                    const double ux = mx / rho + ushift, uy = my / rho, uz = mz / rho;
                    const double usq = 1.5 * (ux * ux + uy * uy + uz * uz);
                    for (int q = 0; q < 19; q++) {
                        const double cu = 3.0 * (cx[q] * ux + cy[q] * uy + cz[q] * uz);
                        const double feq = w[q] * rho * (1.0 + cu + 0.5 * cu * cu - usq);
                        dq[q][idx] = f[q] + omega * (feq - f[q]);
                    }
                }
            }
        }
        double *t = src;
        src = dst;
        dst = t;
    }

    double momentum = 0.0;
    for (size_t i = 0; i < n; i++) {
        if (solid[i]) continue;
        double m = 0.0;
        for (int q = 0; q < 19; q++) m += cx[q] * src[(size_t)q * ns + i];
        momentum += m;
    }
    free(fa); free(fb); free(solid);
    out->checksum = 0;
    out->value = momentum;
    out->work = (double)fluid * steps;
    out->unit = "cell updates";
    return 0;
}

// ── 2. Molecular dynamics (md) ──────────────────────────────────────────

typedef struct {
    int np, nc, brute;
    double L, half, rc, rc2, rl2, irc, irc2, ecut;
    double *x, *y, *z, *rx, *ry, *rz, *vx, *vy, *vz, *fx, *fy, *fz, *q;
    size_t *nstart;
    int *nlist;
    size_t cap;
    int *cellof, *cellstart, *cellcur, *cellidx;
} md_sys;

static inline double md_wrap(double d, double L, double half) {
    if (d > half) return d - L;
    if (d < -half) return d + L;
    return d;
}

static int md_push(md_sys *s, size_t *cnt, int j) {
    if (*cnt == s->cap) {
        const size_t ncap = s->cap * 2;
        int *nl = realloc(s->nlist, ncap * sizeof(int));
        if (!nl) return -1;
        s->nlist = nl;
        s->cap = ncap;
    }
    s->nlist[(*cnt)++] = j;
    return 0;
}

/// Rebuilds the Verlet list (every pair within rc + skin, each once) from a
/// cell list, and remembers where everyone was.
static int md_build(md_sys *s) {
    const int np = s->np, nc = s->nc;
    size_t cnt = 0;
    if (!s->brute) {
        const int ncell = nc * nc * nc;
        memset(s->cellstart, 0, sizeof(int) * (size_t)(ncell + 1));
        const double scale = nc / s->L;
        for (int i = 0; i < np; i++) {
            int cx = (int)(s->x[i] * scale), cy = (int)(s->y[i] * scale), cz = (int)(s->z[i] * scale);
            if (cx >= nc) cx = nc - 1;
            if (cy >= nc) cy = nc - 1;
            if (cz >= nc) cz = nc - 1;
            if (cx < 0) cx = 0;
            if (cy < 0) cy = 0;
            if (cz < 0) cz = 0;
            const int c = (cz * nc + cy) * nc + cx;
            s->cellof[i] = c;
            s->cellstart[c + 1]++;
        }
        for (int c = 0; c < ncell; c++) s->cellstart[c + 1] += s->cellstart[c];
        memcpy(s->cellcur, s->cellstart, sizeof(int) * (size_t)ncell);
        for (int i = 0; i < np; i++) s->cellidx[s->cellcur[s->cellof[i]]++] = i;
    }
    for (int i = 0; i < np; i++) {
        s->nstart[i] = cnt;
        const double xi = s->x[i], yi = s->y[i], zi = s->z[i];
        if (s->brute) {
            for (int j = i + 1; j < np; j++) {
                const double dx = md_wrap(xi - s->x[j], s->L, s->half);
                const double dy = md_wrap(yi - s->y[j], s->L, s->half);
                const double dz = md_wrap(zi - s->z[j], s->L, s->half);
                if (dx * dx + dy * dy + dz * dz < s->rl2 && md_push(s, &cnt, j)) return -1;
            }
            continue;
        }
        const int c = s->cellof[i];
        const int cx = c % nc, cy = (c / nc) % nc, cz = c / (nc * nc);
        for (int dz = -1; dz <= 1; dz++) {
            const int zz = (cz + dz + nc) % nc;
            for (int dy = -1; dy <= 1; dy++) {
                const int yy = (cy + dy + nc) % nc;
                for (int dx = -1; dx <= 1; dx++) {
                    const int xx = (cx + dx + nc) % nc;
                    const int c2 = (zz * nc + yy) * nc + xx;
                    for (int k = s->cellstart[c2]; k < s->cellstart[c2 + 1]; k++) {
                        const int j = s->cellidx[k];
                        if (j <= i) continue;
                        const double ex = md_wrap(xi - s->x[j], s->L, s->half);
                        const double ey = md_wrap(yi - s->y[j], s->L, s->half);
                        const double ez = md_wrap(zi - s->z[j], s->L, s->half);
                        if (ex * ex + ey * ey + ez * ez < s->rl2 && md_push(s, &cnt, j)) return -1;
                    }
                }
            }
        }
    }
    s->nstart[np] = cnt;
    memcpy(s->rx, s->x, sizeof(double) * (size_t)np);
    memcpy(s->ry, s->y, sizeof(double) * (size_t)np);
    memcpy(s->rz, s->z, sizeof(double) * (size_t)np);
    return 0;
}

/// Forces and potential energy: Lennard-Jones (shifted to zero at the
/// cutoff) plus shifted-force Coulomb between the partial charges.
static double md_forces(md_sys *s) {
    const int np = s->np;
    memset(s->fx, 0, sizeof(double) * (size_t)np);
    memset(s->fy, 0, sizeof(double) * (size_t)np);
    memset(s->fz, 0, sizeof(double) * (size_t)np);
    double pe = 0.0;
    for (int i = 0; i < np; i++) {
        const double xi = s->x[i], yi = s->y[i], zi = s->z[i], qi = s->q[i];
        double fxi = 0.0, fyi = 0.0, fzi = 0.0;
        for (size_t k = s->nstart[i]; k < s->nstart[i + 1]; k++) {
            const int j = s->nlist[k];
            const double dx = md_wrap(xi - s->x[j], s->L, s->half);
            const double dy = md_wrap(yi - s->y[j], s->L, s->half);
            const double dz = md_wrap(zi - s->z[j], s->L, s->half);
            const double r2 = dx * dx + dy * dy + dz * dz;
            if (r2 >= s->rc2) continue;
            const double inv2 = 1.0 / r2, inv6 = inv2 * inv2 * inv2;
            double ff = 24.0 * inv6 * (2.0 * inv6 - 1.0) * inv2;
            double e = 4.0 * inv6 * (inv6 - 1.0) - s->ecut;
            const double qq = qi * s->q[j];
            const double r = sqrt(r2), invr = 1.0 / r;
            ff += qq * (inv2 - s->irc2) * invr;
            e += qq * (invr - s->irc + (r - s->rc) * s->irc2);
            pe += e;
            fxi += ff * dx;
            fyi += ff * dy;
            fzi += ff * dz;
            s->fx[j] -= ff * dx;
            s->fy[j] -= ff * dy;
            s->fz[j] -= ff * dz;
        }
        s->fx[i] += fxi;
        s->fy[i] += fyi;
        s->fz[i] += fzi;
    }
    return pe;
}

/// Classical molecular dynamics of a charged Lennard-Jones liquid: the kind
/// of program NAMD and nab (SPEC's biomolecular codes) are. Particles start
/// on an FCC lattice in a periodic box (reduced density 0.84) with random
/// velocities at T = 1 and alternating ±0.4 charges, and melt. Forces are
/// Lennard-Jones plus shifted-force Coulomb, both cut off at 2.5σ, found
/// through a Verlet neighbour list (skin 0.3σ) built from cell lists and
/// rebuilt when anyone has moved half the skin; integration is velocity
/// Verlet, dt = 0.004. The answer is the total energy per particle at the
/// end (it is conserved, to about 1e-5, so this also checks the
/// integrator). Only correctly rounded operations are used: the trajectory
/// is chaotic, and that keeps it bit-identical on every machine.
/// `size` 1: 2048 particles for 320 steps; 2: 6912 for 440; 3: 23328 for
/// 540. Work: particle steps.
int cbk_md(int size, cb_bench_result *out) {
    static const int cfg[3][2] = {{8, 320}, {12, 440}, {18, 540}};
    const int lv = fpa_level(size) - 1;
    const int kc = cfg[lv][0], steps = cfg[lv][1];
    md_sys s;
    memset(&s, 0, sizeof s);
    const int np = s.np = 4 * kc * kc * kc;
    const double a = 1.68;
    s.L = a * kc;
    s.half = 0.5 * s.L;
    s.rc = 2.5;
    s.rc2 = s.rc * s.rc;
    const double rl = 2.8;                      // cutoff + skin
    s.rl2 = rl * rl;
    s.irc = 1.0 / s.rc;
    s.irc2 = s.irc * s.irc;
    const double ir6 = s.irc2 * s.irc2 * s.irc2;
    s.ecut = 4.0 * ir6 * (ir6 - 1.0);
    s.nc = (int)(s.L / rl);
    s.brute = s.nc < 3;
    if (s.brute) s.nc = 1;
    const int ncell = s.nc * s.nc * s.nc;
    const double dt = 0.004, hdt = 0.5 * dt;
    const double maxdisp2 = 0.15 * 0.15;       // (skin / 2)²

    double *buf = malloc(sizeof(double) * (size_t)np * 13);
    s.nstart = malloc(sizeof(size_t) * (size_t)(np + 1));
    s.cap = (size_t)np * 48;
    s.nlist = malloc(sizeof(int) * s.cap);
    s.cellof = malloc(sizeof(int) * (size_t)np);
    s.cellidx = malloc(sizeof(int) * (size_t)np);
    s.cellstart = malloc(sizeof(int) * (size_t)(ncell + 1));
    s.cellcur = malloc(sizeof(int) * (size_t)ncell);
    int rc = 1;
    if (!buf || !s.nstart || !s.nlist || !s.cellof || !s.cellidx || !s.cellstart || !s.cellcur)
        goto done;
    s.x = buf;            s.y = s.x + np;  s.z = s.y + np;
    s.rx = s.z + np;      s.ry = s.rx + np; s.rz = s.ry + np;
    s.vx = s.rz + np;     s.vy = s.vx + np; s.vz = s.vy + np;
    s.fx = s.vz + np;     s.fy = s.fx + np; s.fz = s.fy + np;
    s.q = s.fz + np;

    // FCC lattice, alternating charges (each cell is neutral).
    static const double basis[4][3] = {{0, 0, 0}, {0.5, 0.5, 0}, {0.5, 0, 0.5}, {0, 0.5, 0.5}};
    int i = 0;
    for (int cz = 0; cz < kc; cz++)
        for (int cy = 0; cy < kc; cy++)
            for (int cx = 0; cx < kc; cx++)
                for (int b = 0; b < 4; b++, i++) {
                    s.x[i] = (cx + basis[b][0] + 0.25) * a;
                    s.y[i] = (cy + basis[b][1] + 0.25) * a;
                    s.z[i] = (cz + basis[b][2] + 0.25) * a;
                    s.q[i] = (i & 1) ? -0.4 : 0.4;
                }
    fpa_rng rng;
    fpa_seed(&rng, 0x3D4D0001ull);
    double sx = 0.0, sy = 0.0, sz = 0.0;
    for (i = 0; i < np; i++) {
        s.vx[i] = fpa_u01(&rng) - 0.5;
        s.vy[i] = fpa_u01(&rng) - 0.5;
        s.vz[i] = fpa_u01(&rng) - 0.5;
        sx += s.vx[i]; sy += s.vy[i]; sz += s.vz[i];
    }
    sx /= np; sy /= np; sz /= np;
    double ke = 0.0;
    for (i = 0; i < np; i++) {
        s.vx[i] -= sx; s.vy[i] -= sy; s.vz[i] -= sz;
        ke += s.vx[i] * s.vx[i] + s.vy[i] * s.vy[i] + s.vz[i] * s.vz[i];
    }
    const double vscale = sqrt(3.0 * np * 1.0 / ke);   // T = 1
    for (i = 0; i < np; i++) {
        s.vx[i] *= vscale; s.vy[i] *= vscale; s.vz[i] *= vscale;
    }

    if (md_build(&s)) goto done;
    double pe = md_forces(&s);
    for (int step = 0; step < steps; step++) {
        for (i = 0; i < np; i++) {
            s.vx[i] += hdt * s.fx[i];
            s.vy[i] += hdt * s.fy[i];
            s.vz[i] += hdt * s.fz[i];
            double px = s.x[i] + dt * s.vx[i], py = s.y[i] + dt * s.vy[i], pz = s.z[i] + dt * s.vz[i];
            if (px >= s.L) px -= s.L; else if (px < 0.0) px += s.L;
            if (py >= s.L) py -= s.L; else if (py < 0.0) py += s.L;
            if (pz >= s.L) pz -= s.L; else if (pz < 0.0) pz += s.L;
            s.x[i] = px; s.y[i] = py; s.z[i] = pz;
        }
        int rebuild = 0;
        for (i = 0; i < np && !rebuild; i++) {
            const double dx = md_wrap(s.x[i] - s.rx[i], s.L, s.half);
            const double dy = md_wrap(s.y[i] - s.ry[i], s.L, s.half);
            const double dz = md_wrap(s.z[i] - s.rz[i], s.L, s.half);
            rebuild = dx * dx + dy * dy + dz * dz > maxdisp2;
        }
        if (rebuild && md_build(&s)) goto done;
        pe = md_forces(&s);
        for (i = 0; i < np; i++) {
            s.vx[i] += hdt * s.fx[i];
            s.vy[i] += hdt * s.fy[i];
            s.vz[i] += hdt * s.fz[i];
        }
    }
    ke = 0.0;
    for (i = 0; i < np; i++)
        ke += s.vx[i] * s.vx[i] + s.vy[i] * s.vy[i] + s.vz[i] * s.vz[i];
    ke *= 0.5;

    out->checksum = 0;
    out->value = (ke + pe) / np;
    out->work = (double)np * steps;
    out->unit = "particle steps";
    rc = 0;
done:
    free(buf); free(s.nstart); free(s.nlist); free(s.cellof);
    free(s.cellidx); free(s.cellstart); free(s.cellcur);
    return rc;
}

// ── 3. Path tracing (raytrace) ──────────────────────────────────────────

typedef struct {
    double x, y, z;
} rt_v3;

static inline rt_v3 rt_v(double x, double y, double z) {
    rt_v3 r;
    r.x = x; r.y = y; r.z = z;
    return r;
}
static inline rt_v3 rt_add(rt_v3 a, rt_v3 b) { return rt_v(a.x + b.x, a.y + b.y, a.z + b.z); }
static inline rt_v3 rt_sub(rt_v3 a, rt_v3 b) { return rt_v(a.x - b.x, a.y - b.y, a.z - b.z); }
static inline rt_v3 rt_scale(rt_v3 a, double s) { return rt_v(a.x * s, a.y * s, a.z * s); }
static inline rt_v3 rt_mul(rt_v3 a, rt_v3 b) { return rt_v(a.x * b.x, a.y * b.y, a.z * b.z); }
static inline double rt_dot(rt_v3 a, rt_v3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static inline rt_v3 rt_cross(rt_v3 a, rt_v3 b) {
    return rt_v(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}
static inline rt_v3 rt_unit(rt_v3 a) { return rt_scale(a, 1.0 / sqrt(rt_dot(a, a))); }

enum { RT_DIFFUSE, RT_MIRROR, RT_GLASS, RT_LIGHT };
#define RT_MAXMAT 16
#define RT_BINS 12

typedef struct {
    int kind;
    rt_v3 albedo, emit;
} rt_mat;

typedef struct {
    rt_v3 p0, e1, e2, n;
    int m;
} rt_tri;

typedef struct {
    rt_v3 c;
    double r;
    int m;
} rt_sph;

/// A BVH node: a leaf when count > 0 (primitives order[first..first+count)),
/// else an inner node with two children split on `axis`.
typedef struct {
    double lo[3], hi[3];
    int left, right, first, count, axis;
} rt_node;

typedef struct {
    int ntri, nsph, nprim, nnodes;
    rt_tri *tri;
    rt_sph *sph;
    int *order;
    rt_node *node;
    double *blo, *bhi, *cen;      // per-primitive bounds and centroid, for the build
    rt_mat mats[RT_MAXMAT];
} rt_scene;

static void rt_add_tri(rt_scene *s, rt_v3 a, rt_v3 b, rt_v3 c, int m) {
    rt_tri *t = &s->tri[s->ntri++];
    t->p0 = a;
    t->e1 = rt_sub(b, a);
    t->e2 = rt_sub(c, a);
    t->n = rt_unit(rt_cross(t->e1, t->e2));
    t->m = m;
}

/// The parallelogram p + s·u + t·v, as a g×g grid of triangle pairs.
static void rt_add_quad(rt_scene *s, rt_v3 p, rt_v3 u, rt_v3 v, int g, int m) {
    for (int j = 0; j < g; j++)
        for (int i = 0; i < g; i++) {
            const double s0 = (double)i / g, s1 = (double)(i + 1) / g;
            const double t0 = (double)j / g, t1 = (double)(j + 1) / g;
            const rt_v3 a = rt_add(p, rt_add(rt_scale(u, s0), rt_scale(v, t0)));
            const rt_v3 b = rt_add(p, rt_add(rt_scale(u, s1), rt_scale(v, t0)));
            const rt_v3 c = rt_add(p, rt_add(rt_scale(u, s1), rt_scale(v, t1)));
            const rt_v3 d = rt_add(p, rt_add(rt_scale(u, s0), rt_scale(v, t1)));
            rt_add_tri(s, a, b, c, m);
            rt_add_tri(s, a, c, d, m);
        }
}

static double rt_area(const double lo[3], const double hi[3]) {
    const double dx = hi[0] - lo[0], dy = hi[1] - lo[1], dz = hi[2] - lo[2];
    return 2.0 * (dx * dy + dy * dz + dz * dx);
}

static inline int rt_bin(const rt_scene *s, int p, int axis, double clo, double kscale) {
    int b = (int)((s->cen[3 * p + axis] - clo) * kscale);
    if (b >= RT_BINS) b = RT_BINS - 1;
    if (b < 0) b = 0;
    return b;
}

/// Builds the subtree over order[first..first+count) with a binned
/// surface-area heuristic; returns its node index.
static int rt_build(rt_scene *s, int first, int count, int depth) {
    const int ni = s->nnodes++;
    double lo[3] = {1e300, 1e300, 1e300}, hi[3] = {-1e300, -1e300, -1e300};
    double clo[3] = {1e300, 1e300, 1e300}, chi[3] = {-1e300, -1e300, -1e300};
    for (int k = first; k < first + count; k++) {
        const int p = s->order[k];
        for (int a = 0; a < 3; a++) {
            if (s->blo[3 * p + a] < lo[a]) lo[a] = s->blo[3 * p + a];
            if (s->bhi[3 * p + a] > hi[a]) hi[a] = s->bhi[3 * p + a];
            if (s->cen[3 * p + a] < clo[a]) clo[a] = s->cen[3 * p + a];
            if (s->cen[3 * p + a] > chi[a]) chi[a] = s->cen[3 * p + a];
        }
    }
    rt_node *nd = &s->node[ni];
    for (int a = 0; a < 3; a++) {
        nd->lo[a] = lo[a];
        nd->hi[a] = hi[a];
    }
    nd->first = first;
    nd->count = count;
    nd->left = nd->right = -1;
    nd->axis = 0;
    if (count <= 2 || depth >= 40) return ni;

    int axis = 0;
    if (chi[1] - clo[1] > chi[axis] - clo[axis]) axis = 1;
    if (chi[2] - clo[2] > chi[axis] - clo[axis]) axis = 2;
    const double ext = chi[axis] - clo[axis];
    if (!(ext > 0.0)) return ni;
    const double kscale = RT_BINS / ext;

    int bcnt[RT_BINS];
    double blo[RT_BINS][3], bhi[RT_BINS][3];
    for (int b = 0; b < RT_BINS; b++) {
        bcnt[b] = 0;
        for (int a = 0; a < 3; a++) {
            blo[b][a] = 1e300;
            bhi[b][a] = -1e300;
        }
    }
    for (int k = first; k < first + count; k++) {
        const int p = s->order[k];
        const int b = rt_bin(s, p, axis, clo[axis], kscale);
        bcnt[b]++;
        for (int a = 0; a < 3; a++) {
            if (s->blo[3 * p + a] < blo[b][a]) blo[b][a] = s->blo[3 * p + a];
            if (s->bhi[3 * p + a] > bhi[b][a]) bhi[b][a] = s->bhi[3 * p + a];
        }
    }
    // Sweep: cost of splitting after bin i = nL·area(L) + nR·area(R).
    double costL[RT_BINS], costR[RT_BINS];
    int nL[RT_BINS], nR[RT_BINS];
    double rlo[3] = {1e300, 1e300, 1e300}, rhi[3] = {-1e300, -1e300, -1e300};
    int run = 0;
    for (int b = 0; b < RT_BINS - 1; b++) {
        run += bcnt[b];
        for (int a = 0; a < 3; a++) {
            if (blo[b][a] < rlo[a]) rlo[a] = blo[b][a];
            if (bhi[b][a] > rhi[a]) rhi[a] = bhi[b][a];
        }
        nL[b] = run;
        costL[b] = run ? run * rt_area(rlo, rhi) : 0.0;
    }
    for (int a = 0; a < 3; a++) {
        rlo[a] = 1e300;
        rhi[a] = -1e300;
    }
    run = 0;
    for (int b = RT_BINS - 1; b > 0; b--) {
        run += bcnt[b];
        for (int a = 0; a < 3; a++) {
            if (blo[b][a] < rlo[a]) rlo[a] = blo[b][a];
            if (bhi[b][a] > rhi[a]) rhi[a] = bhi[b][a];
        }
        nR[b - 1] = run;
        costR[b - 1] = run ? run * rt_area(rlo, rhi) : 0.0;
    }
    int best = -1;
    double bestcost = 1e300;
    for (int b = 0; b < RT_BINS - 1; b++) {
        if (nL[b] == 0 || nR[b] == 0) continue;
        const double c = costL[b] + costR[b];
        if (c < bestcost) {
            bestcost = c;
            best = b;
        }
    }
    if (best < 0) return ni;
    // A leaf beats a split when intersecting everything costs no more than
    // one traversal step plus the expected tests on each side.
    if (count <= 8 && bestcost >= (count - 1.0) * rt_area(lo, hi)) return ni;

    int i = first, j = first + count - 1;
    while (i <= j) {
        if (rt_bin(s, s->order[i], axis, clo[axis], kscale) <= best) {
            i++;
        } else {
            const int t = s->order[i];
            s->order[i] = s->order[j];
            s->order[j] = t;
            j--;
        }
    }
    const int mid = i;
    s->node[ni].count = 0;
    s->node[ni].axis = axis;
    const int l = rt_build(s, first, mid - first, depth + 1);
    const int r = rt_build(s, mid, first + count - mid, depth + 1);
    s->node[ni].left = l;
    s->node[ni].right = r;
    return ni;
}

/// Closest hit along o + t·d (|d| = 1) with t in (1e-9, *t); returns the
/// primitive (triangles first, then spheres) or -1, and updates *t.
static int rt_intersect(const rt_scene *s, rt_v3 o, rt_v3 d, double *tmax) {
    const double org[3] = {o.x, o.y, o.z}, dir[3] = {d.x, d.y, d.z};
    double inv[3];
    for (int a = 0; a < 3; a++) {
        double c = dir[a];
        if (fabs(c) < 1e-12) c = c < 0.0 ? -1e-12 : 1e-12;
        inv[a] = 1.0 / c;
    }
    int stack[96], sp = 0, hit = -1;
    double best = *tmax;
    stack[sp++] = 0;
    while (sp > 0) {
        const rt_node *nd = &s->node[stack[--sp]];
        double t0 = 1e-9, t1 = best;
        for (int a = 0; a < 3; a++) {
            double ta = (nd->lo[a] - org[a]) * inv[a], tb = (nd->hi[a] - org[a]) * inv[a];
            if (ta > tb) {
                const double t = ta;
                ta = tb;
                tb = t;
            }
            if (ta > t0) t0 = ta;
            if (tb < t1) t1 = tb;
        }
        if (t0 > t1) continue;
        if (nd->count == 0) {
            // Visit the nearer child first.
            if (dir[nd->axis] < 0.0) {
                stack[sp++] = nd->left;
                stack[sp++] = nd->right;
            } else {
                stack[sp++] = nd->right;
                stack[sp++] = nd->left;
            }
            continue;
        }
        for (int k = nd->first; k < nd->first + nd->count; k++) {
            const int p = s->order[k];
            if (p < s->ntri) {                      // Möller–Trumbore
                const rt_tri *tr = &s->tri[p];
                const rt_v3 pv = rt_cross(d, tr->e2);
                const double det = rt_dot(tr->e1, pv);
                if (fabs(det) < 1e-14) continue;
                const double idet = 1.0 / det;
                const rt_v3 tv = rt_sub(o, tr->p0);
                const double u = rt_dot(tv, pv) * idet;
                if (u < 0.0 || u > 1.0) continue;
                const rt_v3 qv = rt_cross(tv, tr->e1);
                const double v = rt_dot(d, qv) * idet;
                if (v < 0.0 || u + v > 1.0) continue;
                const double t = rt_dot(tr->e2, qv) * idet;
                if (t > 1e-9 && t < best) {
                    best = t;
                    hit = p;
                }
            } else {
                const rt_sph *sp_ = &s->sph[p - s->ntri];
                const rt_v3 oc = rt_sub(o, sp_->c);
                const double b = rt_dot(oc, d), c = rt_dot(oc, oc) - sp_->r * sp_->r;
                const double disc = b * b - c;
                if (disc < 0.0) continue;
                const double sq = sqrt(disc);
                double t = -b - sq;
                if (t <= 1e-9) t = -b + sq;
                if (t > 1e-9 && t < best) {
                    best = t;
                    hit = p;
                }
            }
        }
    }
    *tmax = best;
    return hit;
}

/// A point uniform on the unit disc, by rejection (no trigonometry).
static void rt_disc(fpa_rng *rng, double *a, double *b) {
    double x, y;
    do {
        x = 2.0 * fpa_u01(rng) - 1.0;
        y = 2.0 * fpa_u01(rng) - 1.0;
    } while (x * x + y * y >= 1.0);
    *a = x;
    *b = y;
}

/// Radiance arriving along o + t·d, by unidirectional path tracing with
/// Russian roulette.
static rt_v3 rt_radiance(const rt_scene *s, rt_v3 o, rt_v3 d, fpa_rng *rng, double *rays) {
    const rt_v3 env = rt_v(0.20, 0.22, 0.26);
    rt_v3 L = rt_v(0, 0, 0), T = rt_v(1, 1, 1);
    const double eps = 1e-6;
    for (int depth = 0; depth < 12; depth++) {
        double t = 1e30;
        *rays += 1.0;
        const int p = rt_intersect(s, o, d, &t);
        if (p < 0) {
            L = rt_add(L, rt_mul(T, env));
            break;
        }
        const rt_v3 hp = rt_add(o, rt_scale(d, t));
        rt_v3 n;
        int m;
        if (p < s->ntri) {
            n = s->tri[p].n;
            m = s->tri[p].m;
        } else {
            const rt_sph *sp_ = &s->sph[p - s->ntri];
            n = rt_scale(rt_sub(hp, sp_->c), 1.0 / sp_->r);
            m = sp_->m;
        }
        const rt_mat *mt = &s->mats[m];
        if (mt->kind == RT_LIGHT) {
            L = rt_add(L, rt_mul(T, mt->emit));
            break;
        }
        const double cosd = rt_dot(d, n);
        const int front = cosd < 0.0;
        const rt_v3 nl = front ? n : rt_scale(n, -1.0);
        if (mt->kind == RT_DIFFUSE) {
            // Cosine-weighted bounce in an orthonormal basis around nl.
            double a, b;
            rt_disc(rng, &a, &b);
            const double sg = nl.z >= 0.0 ? 1.0 : -1.0;
            const double aa = -1.0 / (sg + nl.z), bb = nl.x * nl.y * aa;
            const rt_v3 t1 = rt_v(1.0 + sg * nl.x * nl.x * aa, sg * bb, -sg * nl.x);
            const rt_v3 t2 = rt_v(bb, sg + nl.y * nl.y * aa, -nl.y);
            const double h = sqrt(1.0 - a * a - b * b);
            d = rt_unit(rt_add(rt_add(rt_scale(t1, a), rt_scale(t2, b)), rt_scale(nl, h)));
            o = rt_add(hp, rt_scale(nl, eps));
        } else if (mt->kind == RT_MIRROR) {
            d = rt_unit(rt_sub(d, rt_scale(n, 2.0 * cosd)));
            o = rt_add(hp, rt_scale(nl, eps));
        } else {
            // Glass, n = 1.5: Fresnel (Schlick) chooses reflection or refraction.
            const double eta = front ? 1.0 / 1.5 : 1.5;
            const double ci = -rt_dot(d, nl);
            const double k = 1.0 - eta * eta * (1.0 - ci * ci);
            int reflect = k < 0.0;
            double ct = 0.0;
            if (!reflect) {
                ct = sqrt(k);
                const double c = front ? ci : ct, x = 1.0 - c;
                const double fr = 0.04 + 0.96 * x * x * x * x * x;
                reflect = fpa_u01(rng) < fr;
            }
            if (reflect) {
                d = rt_unit(rt_add(d, rt_scale(nl, 2.0 * ci)));
                o = rt_add(hp, rt_scale(nl, eps));
            } else {
                d = rt_unit(rt_add(rt_scale(d, eta), rt_scale(nl, eta * ci - ct)));
                o = rt_sub(hp, rt_scale(nl, eps));
            }
        }
        T = rt_mul(T, mt->albedo);
        if (depth >= 3) {
            double pr = T.x > T.y ? T.x : T.y;
            if (T.z > pr) pr = T.z;
            if (pr > 0.95) pr = 0.95;
            if (fpa_u01(rng) >= pr) break;
            T = rt_scale(T, 1.0 / pr);
        }
    }
    return L;
}

/// A path tracer: the kind of rendering program POV-Ray and Blender's Cycles
/// (SPEC's povray and blender) are. The scene is a Cornell-style room of
/// tessellated walls lit by an area light, a procedurally generated bumpy
/// torus (7680 triangles), a mirror sphere, a glass sphere and 24 small
/// coloured spheres, all in one bounding volume hierarchy built with a
/// binned surface-area heuristic. Materials are Lambertian, mirror and glass
/// (Fresnel by Schlick); paths bounce until Russian roulette ends them, with
/// jittered samples per pixel from a per-pixel PRNG. The answer is the mean
/// pixel value (linear radiance, averaged over R, G and B). Only correctly
/// rounded operations are used, so every path takes the same branches on
/// every machine. `size` 1: 160×120 at 9 samples per pixel; 2: 320×240 at
/// 13; 3: 512×384 at 24. Work: rays cast.
int cbk_raytrace(int size, cb_bench_result *out) {
    static const int cfg[3][3] = {{160, 120, 9}, {320, 240, 13}, {512, 384, 24}};
    const int lv = fpa_level(size) - 1;
    const int W = cfg[lv][0], H = cfg[lv][1], spp = cfg[lv][2];
    const int G = 6, NU = 96, NV = 40, NSMALL = 24;
    const int maxtri = 5 * 2 * G * G + 2 + 2 * NU * NV, maxsph = 2 + NSMALL;

    rt_scene s;
    memset(&s, 0, sizeof s);
    const int maxprim = maxtri + maxsph;
    s.tri = malloc(sizeof(rt_tri) * (size_t)maxtri);
    s.sph = malloc(sizeof(rt_sph) * (size_t)maxsph);
    s.order = malloc(sizeof(int) * (size_t)maxprim);
    s.node = malloc(sizeof(rt_node) * (size_t)(2 * maxprim));
    s.blo = malloc(sizeof(double) * 3 * (size_t)maxprim);
    s.bhi = malloc(sizeof(double) * 3 * (size_t)maxprim);
    s.cen = malloc(sizeof(double) * 3 * (size_t)maxprim);
    rt_v3 *verts = malloc(sizeof(rt_v3) * (size_t)(NU * NV));
    int rc = 1;
    if (!s.tri || !s.sph || !s.order || !s.node || !s.blo || !s.bhi || !s.cen || !verts) goto done;

    // Materials.
    fpa_rng rng;
    fpa_seed(&rng, 0x7A7ACE00ull);
    s.mats[0] = (rt_mat){RT_DIFFUSE, rt_v(0.73, 0.73, 0.73), rt_v(0, 0, 0)};
    s.mats[1] = (rt_mat){RT_DIFFUSE, rt_v(0.65, 0.06, 0.05), rt_v(0, 0, 0)};
    s.mats[2] = (rt_mat){RT_DIFFUSE, rt_v(0.12, 0.45, 0.15), rt_v(0, 0, 0)};
    s.mats[3] = (rt_mat){RT_LIGHT, rt_v(0, 0, 0), rt_v(14.0, 13.0, 11.0)};
    s.mats[4] = (rt_mat){RT_DIFFUSE, rt_v(0.80, 0.55, 0.20), rt_v(0, 0, 0)};
    s.mats[5] = (rt_mat){RT_MIRROR, rt_v(0.95, 0.95, 0.95), rt_v(0, 0, 0)};
    s.mats[6] = (rt_mat){RT_GLASS, rt_v(0.99, 0.99, 0.99), rt_v(0, 0, 0)};
    for (int m = 7; m < 15; m++) {
        const double r = 0.2 + 0.7 * fpa_u01(&rng), g = 0.2 + 0.7 * fpa_u01(&rng);
        const double b = 0.2 + 0.7 * fpa_u01(&rng);
        s.mats[m] = (rt_mat){RT_DIFFUSE, rt_v(r, g, b), rt_v(0, 0, 0)};
    }

    // The room [-1,1]×[0,2]×[-1,1], open at the front (+z), and its light.
    rt_add_quad(&s, rt_v(-1, 0, -1), rt_v(2, 0, 0), rt_v(0, 0, 2), G, 0);   // floor
    rt_add_quad(&s, rt_v(-1, 2, -1), rt_v(2, 0, 0), rt_v(0, 0, 2), G, 0);   // ceiling
    rt_add_quad(&s, rt_v(-1, 0, -1), rt_v(2, 0, 0), rt_v(0, 2, 0), G, 0);   // back
    rt_add_quad(&s, rt_v(-1, 0, -1), rt_v(0, 0, 2), rt_v(0, 2, 0), G, 1);   // left
    rt_add_quad(&s, rt_v(1, 0, -1), rt_v(0, 0, 2), rt_v(0, 2, 0), G, 2);    // right
    rt_add_quad(&s, rt_v(-0.3, 1.995, -0.3), rt_v(0.6, 0, 0), rt_v(0, 0, 0.6), 1, 3);

    // A bumpy torus, tilted, generated on a (u, v) grid.
    {
        const double R = 0.42, r0 = 0.14;
        double st, ct;
        fpa_sincos(1.1, &st, &ct);
        const rt_v3 center = rt_v(0.1, 0.62, -0.2);
        for (int iu = 0; iu < NU; iu++) {
            const double u = 2.0 * FPA_PI * iu / NU;
            double su, cu;
            fpa_sincos(u, &su, &cu);
            const double s5u = fpa_sin(5.0 * u);
            for (int iv = 0; iv < NV; iv++) {
                const double v = 2.0 * FPA_PI * iv / NV;
                double sv, cv;
                fpa_sincos(v, &sv, &cv);
                const double rr = r0 * (1.0 + 0.18 * s5u * fpa_sin(3.0 * v));
                const double x = (R + rr * cv) * cu, y = rr * sv, z = (R + rr * cv) * su;
                verts[iu * NV + iv] = rt_add(center, rt_v(x, y * ct - z * st, y * st + z * ct));
            }
        }
        for (int iu = 0; iu < NU; iu++)
            for (int iv = 0; iv < NV; iv++) {
                const int u1 = (iu + 1) % NU, v1 = (iv + 1) % NV;
                const rt_v3 a = verts[iu * NV + iv], b = verts[u1 * NV + iv];
                const rt_v3 c = verts[u1 * NV + v1], d = verts[iu * NV + v1];
                rt_add_tri(&s, a, b, c, 4);
                rt_add_tri(&s, a, c, d, 4);
            }
    }
    // Spheres: a mirror, a glass ball and small coloured ones on the floor.
    s.sph[s.nsph++] = (rt_sph){rt_v(-0.58, 0.34, -0.5), 0.34, 5};
    s.sph[s.nsph++] = (rt_sph){rt_v(0.52, 0.30, 0.42), 0.30, 6};
    for (int k = 0; k < NSMALL; k++) {
        const double r = 0.04 + 0.05 * fpa_u01(&rng);
        const double x = -0.9 + 1.8 * fpa_u01(&rng), z = -0.2 + 1.1 * fpa_u01(&rng);
        s.sph[s.nsph++] = (rt_sph){rt_v(x, r, z), r, 7 + k % 8};
    }

    // Bounds, then the BVH.
    s.nprim = s.ntri + s.nsph;
    for (int p = 0; p < s.nprim; p++) {
        double lo[3], hi[3];
        if (p < s.ntri) {
            const rt_tri *t = &s.tri[p];
            const rt_v3 b = rt_add(t->p0, t->e1), c = rt_add(t->p0, t->e2);
            const double vx[3] = {t->p0.x, b.x, c.x}, vy[3] = {t->p0.y, b.y, c.y}, vz[3] = {t->p0.z, b.z, c.z};
            lo[0] = hi[0] = vx[0]; lo[1] = hi[1] = vy[0]; lo[2] = hi[2] = vz[0];
            for (int k = 1; k < 3; k++) {
                if (vx[k] < lo[0]) lo[0] = vx[k];
                if (vx[k] > hi[0]) hi[0] = vx[k];
                if (vy[k] < lo[1]) lo[1] = vy[k];
                if (vy[k] > hi[1]) hi[1] = vy[k];
                if (vz[k] < lo[2]) lo[2] = vz[k];
                if (vz[k] > hi[2]) hi[2] = vz[k];
            }
        } else {
            const rt_sph *sp_ = &s.sph[p - s.ntri];
            lo[0] = sp_->c.x - sp_->r; hi[0] = sp_->c.x + sp_->r;
            lo[1] = sp_->c.y - sp_->r; hi[1] = sp_->c.y + sp_->r;
            lo[2] = sp_->c.z - sp_->r; hi[2] = sp_->c.z + sp_->r;
        }
        for (int a = 0; a < 3; a++) {
            s.blo[3 * p + a] = lo[a];
            s.bhi[3 * p + a] = hi[a];
            s.cen[3 * p + a] = 0.5 * (lo[a] + hi[a]);
        }
        s.order[p] = p;
    }
    rt_build(&s, 0, s.nprim, 0);

    // Render: pinhole camera at z = 3.6 looking down −z.
    const rt_v3 eye = rt_v(0.0, 0.9, 3.6);
    const double tanf = 0.31, aspect = (double)W / H;
    double rays = 0.0, total = 0.0;
    for (int py = 0; py < H; py++) {
        for (int px = 0; px < W; px++) {
            fpa_rng pr;
            fpa_seed(&pr, 0xC0FFEE00ull + (uint64_t)py * (uint64_t)W + (uint64_t)px);
            rt_v3 acc = rt_v(0, 0, 0);
            for (int k = 0; k < spp; k++) {
                const double jx = fpa_u01(&pr), jy = fpa_u01(&pr);
                const double sx = ((px + jx) / W * 2.0 - 1.0) * tanf * aspect;
                const double sy = (1.0 - (py + jy) / H * 2.0) * tanf;
                const rt_v3 d = rt_unit(rt_v(sx, sy, -1.0));
                acc = rt_add(acc, rt_radiance(&s, eye, d, &pr, &rays));
            }
            total += (acc.x + acc.y + acc.z) / spp;
        }
    }
    out->checksum = 0;
    out->value = total / (3.0 * W * H);
    out->work = rays;
    out->unit = "rays";
    rc = 0;
done:
    free(s.tri); free(s.sph); free(s.order); free(s.node);
    free(s.blo); free(s.bhi); free(s.cen); free(verts);
    return rc;
}

// ── 4. FDTD electromagnetics (fdtd) ─────────────────────────────────────

/// Maxwell's equations in the time domain on a Yee grid: the kind of
/// program SPEC's fotonik3d is. A cube of n³ cells (dx = c = 1, Courant
/// number 0.5) holds a dielectric sphere (εr = 4) and a dielectric slab
/// (εr = 2.25) in vacuum. A short dipole (a soft Ez source along eight
/// cells) drives a ramped sinusoid with a wavelength of 20 cells. The walls
/// are graded-conductivity absorbing layers (a "PML-lite": matched electric
/// and magnetic loss, cubic profile, n/8 cells thick) backed by PEC. The
/// answer is the electromagnetic field energy in the box after the last
/// step. `size` 1: 56³ cells for 400 steps (13 MB); 2: 104³ for 240
/// (72 MB); 3: 144³ for 450 (191 MB). Work: cell updates (all six field
/// components).
int cbk_fdtd(int size, cb_bench_result *out) {
    static const int cfg[3][2] = {{56, 400}, {104, 240}, {144, 450}};
    const int lv = fpa_level(size) - 1;
    const int n = cfg[lv][0], steps = cfg[lv][1];
    const size_t nn = (size_t)n * n * n, sy = (size_t)n, sz = (size_t)n * n, st = nn + FPA_PAD;
    double *f = calloc(6 * st, sizeof(double));
    float *co = calloc(4 * st, sizeof(float));
    unsigned char *mat = malloc(nn);
    if (!f || !co || !mat) {
        free(f); free(co); free(mat);
        return 1;
    }
    double *ex = f, *ey = f + st, *ez = f + 2 * st, *hx = f + 3 * st, *hy = f + 4 * st, *hz = f + 5 * st;
    float *ca = co, *cb = co + st, *da = co + 2 * st, *db = co + 3 * st;
    static const double eps_of[3] = {1.0, 4.0, 2.25};

    const double dt = 0.5;
    const int D = n / 8;                        // absorbing-layer thickness
    const double smax = 1.0;
    double sig[256];
    for (int i = 0; i < n; i++) {
        double d = 0.0;
        if (i < D) d = (double)(D - i) / D;
        else if (i > n - 1 - D) d = (double)(i - (n - 1 - D)) / D;
        sig[i] = smax * d * d * d;
    }
    for (int k = 0; k < n; k++)
        for (int j = 0; j < n; j++)
            for (int i = 0; i < n; i++) {
                const size_t c = (size_t)k * sz + (size_t)j * sy + (size_t)i;
                const double x = (double)i / n, y = (double)j / n, z = (double)k / n;
                const double rx = x - 0.62, ry = y - 0.5, rz = z - 0.48;
                unsigned char m = 0;
                if (rx * rx + ry * ry + rz * rz < 0.14 * 0.14) m = 1;
                else if (x >= 0.38 && x < 0.42 && y > 0.2 && y < 0.8 && z > 0.2 && z < 0.8) m = 2;
                mat[c] = m;
                const double s = sig[i] + sig[j] + sig[k], e = eps_of[m];
                const double ae = s * dt / (2.0 * e), am = s * dt / 2.0;
                ca[c] = (float)((1.0 - ae) / (1.0 + ae));
                cb[c] = (float)((dt / e) / (1.0 + ae));
                da[c] = (float)((1.0 - am) / (1.0 + am));
                db[c] = (float)(dt / (1.0 + am));
            }
    // The source: a short z-directed dipole, eight cells with a cosine taper.
    const size_t src = (size_t)(n / 2 - 4) * sz + (size_t)(n / 2) * sy + (size_t)(n / 4);
    double taper[8];
    for (int k = 0; k < 8; k++) taper[k] = 0.25 * fpa_sin(FPA_PI * (k + 0.5) / 8.0);
    const double w0 = 2.0 * FPA_PI / 20.0, tau = 30.0;

    for (int step = 0; step < steps; step++) {
        // H from the curl of E (forward differences).
        for (int k = 0; k < n - 1; k++)
            for (int j = 0; j < n - 1; j++) {
                const size_t base = (size_t)k * sz + (size_t)j * sy;
                for (int i = 0; i < n - 1; i++) {
                    const size_t c = base + (size_t)i;
                    const double exc = ex[c], eyc = ey[c], ezc = ez[c];
                    hx[c] = da[c] * hx[c] - db[c] * ((ez[c + sy] - ezc) - (ey[c + sz] - eyc));
                    hy[c] = da[c] * hy[c] - db[c] * ((ex[c + sz] - exc) - (ez[c + 1] - ezc));
                    hz[c] = da[c] * hz[c] - db[c] * ((ey[c + 1] - eyc) - (ex[c + sy] - exc));
                }
            }
        // E from the curl of H (backward differences); tangential E on the
        // outer faces stays 0.
        for (int k = 1; k < n - 1; k++)
            for (int j = 1; j < n - 1; j++) {
                const size_t base = (size_t)k * sz + (size_t)j * sy;
                for (int i = 1; i < n - 1; i++) {
                    const size_t c = base + (size_t)i;
                    const double hxc = hx[c], hyc = hy[c], hzc = hz[c];
                    ex[c] = ca[c] * ex[c] + cb[c] * ((hzc - hz[c - sy]) - (hyc - hy[c - sz]));
                    ey[c] = ca[c] * ey[c] + cb[c] * ((hxc - hx[c - sz]) - (hzc - hz[c - 1]));
                    ez[c] = ca[c] * ez[c] + cb[c] * ((hyc - hy[c - 1]) - (hxc - hx[c - sy]));
                }
            }
        const double t = (step + 1) * dt, ramp = 1.0 - fpa_exp(-(t / tau) * (t / tau));
        const double drive = fpa_sin(w0 * t) * ramp;
        for (int k = 0; k < 8; k++) ez[src + (size_t)k * sz] += drive * taper[k];
    }

    double energy = 0.0;
    for (size_t c = 0; c < nn; c++) {
        const double e2 = ex[c] * ex[c] + ey[c] * ey[c] + ez[c] * ez[c];
        const double h2 = hx[c] * hx[c] + hy[c] * hy[c] + hz[c] * hz[c];
        energy += 0.5 * (eps_of[mat[c]] * e2 + h2);
    }
    free(f); free(co); free(mat);
    out->checksum = 0;
    out->value = energy;
    out->work = (double)nn * steps;
    out->unit = "cell updates";
    return 0;
}

// ── 5. Preconditioned conjugate gradient (cg) ───────────────────────────

typedef struct {
    int n;
    int *rowptr, *col, *diagpos;
    double *val, *invd;      // invd = ω / a_ii, for SSOR
} cg_mat;

static void cg_spmv(const cg_mat *A, const double *x, double *y) {
    for (int i = 0; i < A->n; i++) {
        double s = 0.0;
        for (int k = A->rowptr[i]; k < A->rowptr[i + 1]; k++) s += A->val[k] * x[A->col[k]];
        y[i] = s;
    }
}

/// z = M⁻¹ r for the SSOR preconditioner (up to a constant factor, which
/// conjugate gradient does not see): a forward sweep (D/ω + L) y = r, then
/// a backward sweep (D/ω + U) z = (D/ω) y, done in place in z.
static void cg_ssor(const cg_mat *A, const double *r, double *z) {
    for (int i = 0; i < A->n; i++) {
        double s = r[i];
        for (int k = A->rowptr[i]; k < A->diagpos[i]; k++) s -= A->val[k] * z[A->col[k]];
        z[i] = s * A->invd[i];
    }
    for (int i = A->n - 1; i >= 0; i--) {
        double s = 0.0;
        for (int k = A->diagpos[i] + 1; k < A->rowptr[i + 1]; k++) s += A->val[k] * z[A->col[k]];
        z[i] -= A->invd[i] * s;
    }
}

static double cg_dot(const double *a, const double *b, int n) {
    double s = 0.0;
    for (int i = 0; i < n; i++) s += a[i] * b[i];
    return s;
}

/// Preconditioned CG on A x = b from the x given, to ‖r‖ <= tol·‖b‖.
/// Returns the iterations taken.
static int cg_solve(const cg_mat *A, const double *b, double *x, double *r, double *z,
                    double *p, double *ap, double tol, int maxit) {
    const int n = A->n;
    cg_spmv(A, x, ap);
    for (int i = 0; i < n; i++) r[i] = b[i] - ap[i];
    const double stop = tol * sqrt(cg_dot(b, b, n));
    if (sqrt(cg_dot(r, r, n)) <= stop) return 0;
    cg_ssor(A, r, z);
    memcpy(p, z, sizeof(double) * (size_t)n);
    double rz = cg_dot(r, z, n);
    int it = 0;
    while (it < maxit) {
        it++;
        cg_spmv(A, p, ap);
        const double alpha = rz / cg_dot(p, ap, n);
        for (int i = 0; i < n; i++) {
            x[i] += alpha * p[i];
            r[i] -= alpha * ap[i];
        }
        if (sqrt(cg_dot(r, r, n)) <= stop) break;
        cg_ssor(A, r, z);
        const double rz1 = cg_dot(r, z, n), beta = rz1 / rz;
        rz = rz1;
        for (int i = 0; i < n; i++) p[i] = z[i] + beta * p[i];
    }
    return it;
}

/// Implicit heat conduction solved by SSOR-preconditioned conjugate
/// gradient: the kind of program SPEC's parest, femflow and tealeaf are. A
/// cube of n³ cells has conductivity 1 with randomly placed blocks of good
/// (30) and poor (0.02) conductors, two heated blocks and cold (Dirichlet)
/// walls. Each backward-Euler step (dt = 4) solves (I + dt·K) uₙ₊₁ =
/// uₙ + dt·f, K the 7-point finite-volume operator in CSR with harmonic-mean
/// face conductances, by PCG with an SSOR (ω = 1.3) preconditioner to a
/// relative residual of 1e-10 (about 55 iterations a step at size 1). The
/// answer is the total heat Σu after the last step; the final residual is
/// far below the 1e-6 tolerance of it. `size` 1: 36³ unknowns for 5 steps;
/// 2: 56³ for 6; 3: 84³ for 6. Work: matrix nonzeros processed (the SpMV
/// plus the two SSOR sweeps, every iteration).
int cbk_cg(int size, cb_bench_result *out) {
    static const int cfg[3][2] = {{36, 5}, {56, 6}, {84, 6}};
    const int lv = fpa_level(size) - 1;
    const int n = cfg[lv][0], nsteps = cfg[lv][1];
    const int nu = n * n * n;
    cg_mat A;
    A.n = nu;
    A.rowptr = malloc(sizeof(int) * (size_t)(nu + 1));
    A.col = malloc(sizeof(int) * 7 * (size_t)nu);
    A.diagpos = malloc(sizeof(int) * (size_t)nu);
    A.val = malloc(sizeof(double) * 7 * (size_t)nu);
    A.invd = malloc(sizeof(double) * (size_t)nu);
    double *vec = malloc(sizeof(double) * 8 * (size_t)nu);
    int rc = 1;
    if (!A.rowptr || !A.col || !A.diagpos || !A.val || !A.invd || !vec) goto done;
    double *kap = vec, *heat = vec + nu, *u = vec + 2 * (size_t)nu, *b = vec + 3 * (size_t)nu;
    double *r = vec + 4 * (size_t)nu, *z = vec + 5 * (size_t)nu, *p = vec + 6 * (size_t)nu;
    double *ap = vec + 7 * (size_t)nu;

    // Materials: blocks of conductor and insulator, two heaters.
    fpa_rng rng;
    fpa_seed(&rng, 0xC6C6C6C6ull);
    for (int i = 0; i < nu; i++) {
        kap[i] = 1.0;
        heat[i] = 0.0;
        u[i] = 0.0;
    }
    for (int blk = 0; blk < 14; blk++) {
        int lo[3], hi[3];
        for (int a = 0; a < 3; a++) {
            const int side = n / 8 + (int)(fpa_next(&rng) % (uint64_t)(n / 4));
            lo[a] = (int)(fpa_next(&rng) % (uint64_t)(n - side));
            hi[a] = lo[a] + side;
        }
        const double kv = (blk & 1) ? 0.02 : 30.0;
        for (int k = lo[2]; k < hi[2]; k++)
            for (int j = lo[1]; j < hi[1]; j++)
                for (int i = lo[0]; i < hi[0]; i++) kap[(k * n + j) * n + i] = kv;
    }
    for (int k = n / 5; k < 2 * n / 5; k++)
        for (int j = n / 4; j < n / 2; j++)
            for (int i = n / 5; i < n / 3; i++) heat[(k * n + j) * n + i] = 1.0;
    for (int k = 3 * n / 5; k < 4 * n / 5; k++)
        for (int j = n / 2; j < 3 * n / 4; j++)
            for (int i = 3 * n / 5; i < 5 * n / 6; i++) heat[(k * n + j) * n + i] = 0.5;

    // Assemble I + dt·K, columns in ascending order.
    const double dt = 4.0, omega = 1.3;
    int cnt = 0;
    for (int k = 0; k < n; k++)
        for (int j = 0; j < n; j++)
            for (int i = 0; i < n; i++) {
                const int row = (k * n + j) * n + i;
                const int nb[6] = {k > 0 ? row - n * n : -1, j > 0 ? row - n : -1, i > 0 ? row - 1 : -1,
                                   i < n - 1 ? row + 1 : -1, j < n - 1 ? row + n : -1,
                                   k < n - 1 ? row + n * n : -1};
                const double kr = kap[row];
                double d = 1.0;
                A.rowptr[row] = cnt;
                for (int f = 0; f < 6; f++) {
                    if (f == 3) {
                        A.diagpos[row] = cnt;
                        A.col[cnt] = row;
                        A.val[cnt++] = 0.0;
                    }
                    if (nb[f] < 0) {
                        d += dt * 2.0 * kr;            // cold wall half a cell away
                        continue;
                    }
                    const double kn = kap[nb[f]], kf = 2.0 * kr * kn / (kr + kn);
                    A.col[cnt] = nb[f];
                    A.val[cnt++] = -dt * kf;
                    d += dt * kf;
                }
                A.val[A.diagpos[row]] = d;
                A.invd[row] = omega / d;
            }
    A.rowptr[nu] = cnt;

    long iters = 0;
    for (int step = 0; step < nsteps; step++) {
        for (int i = 0; i < nu; i++) b[i] = u[i] + dt * heat[i];
        iters += cg_solve(&A, b, u, r, z, p, ap, 1e-10, 2000);
    }
    double total = 0.0;
    for (int i = 0; i < nu; i++) total += u[i];
    out->checksum = 0;
    out->value = total;
    out->work = (double)iters * 3.0 * cnt;
    out->unit = "nonzeros";
    rc = 0;
done:
    free(A.rowptr); free(A.col); free(A.diagpos); free(A.val); free(A.invd); free(vec);
    return rc;
}

// ── 6. BSSN-like relativity stencil (stencil) ───────────────────────────

enum { BS_G = 0, BS_A = 6, BS_CHI = 12, BS_K = 13, BS_ALP = 14, BS_NF = 15 };
// Symmetric 3×3 tensor components stored as xx, xy, xz, yy, yz, zz.
static const int bs_sym[3][3] = {{0, 1, 2}, {1, 3, 4}, {2, 4, 5}};

typedef struct {
    int n;
    size_t np, fs;                 // points; stride between fields
    double c12, c144, sko;
    const int *xw, *yw, *zw;   // [5·c + a]: offset of coordinate c + a − 2, wrapped
} bs_grid;

/// All six second derivatives (xx, xy, xz, yy, yz, zz) of f, fourth order.
static void bs_d2(const double *f, const int *xo, const int *yo, const int *zo, const bs_grid *g, double d[6]) {
#define BS_F(a, b, c) f[zo[c] + yo[b] + xo[a]]
    static const double w1[5] = {1.0, -8.0, 0.0, 8.0, -1.0};
    const double f0 = BS_F(2, 2, 2);
    d[0] = (-BS_F(0, 2, 2) + 16.0 * BS_F(1, 2, 2) - 30.0 * f0 + 16.0 * BS_F(3, 2, 2) - BS_F(4, 2, 2)) * g->c12;
    d[3] = (-BS_F(2, 0, 2) + 16.0 * BS_F(2, 1, 2) - 30.0 * f0 + 16.0 * BS_F(2, 3, 2) - BS_F(2, 4, 2)) * g->c12;
    d[5] = (-BS_F(2, 2, 0) + 16.0 * BS_F(2, 2, 1) - 30.0 * f0 + 16.0 * BS_F(2, 2, 3) - BS_F(2, 2, 4)) * g->c12;
    double sxy = 0.0, sxz = 0.0, syz = 0.0;
    for (int a = 0; a < 5; a++) {
        if (a == 2) continue;
        for (int b = 0; b < 5; b++) {
            if (b == 2) continue;
            const double w = w1[a] * w1[b];
            sxy += w * BS_F(a, b, 2);
            sxz += w * BS_F(a, 2, b);
            syz += w * BS_F(2, a, b);
        }
    }
    d[1] = sxy * g->c144;
    d[2] = sxz * g->c144;
    d[4] = syz * g->c144;
}

/// Kreiss–Oliger dissipation: −σ/(16h) times the sum over directions of the
/// fourth difference.
static double bs_ko(const double *f, const int *xo, const int *yo, const int *zo, const bs_grid *g) {
    const double f0 = 6.0 * BS_F(2, 2, 2);
    const double dx = BS_F(0, 2, 2) - 4.0 * BS_F(1, 2, 2) + f0 - 4.0 * BS_F(3, 2, 2) + BS_F(4, 2, 2);
    const double dy = BS_F(2, 0, 2) - 4.0 * BS_F(2, 1, 2) + f0 - 4.0 * BS_F(2, 3, 2) + BS_F(2, 4, 2);
    const double dz = BS_F(2, 2, 0) - 4.0 * BS_F(2, 2, 1) + f0 - 4.0 * BS_F(2, 2, 3) + BS_F(2, 2, 4);
    return -g->sko * (dx + dy + dz);
#undef BS_F
}

/// γ^{kl} X_kl for symmetric γ⁻¹ and X.
static inline double bs_trace(const double gi[6], const double x[6]) {
    return gi[0] * x[0] + gi[3] * x[3] + gi[5] * x[5] + 2.0 * (gi[1] * x[1] + gi[2] * x[2] + gi[4] * x[4]);
}

/// The right-hand side of the evolution system at every point.
static void bs_rhs(const bs_grid *g, const double *u, double *r) {
    const int n = g->n;
    const size_t fs = g->fs;
    for (int z = 0; z < n; z++)
        for (int y = 0; y < n; y++)
            for (int x = 0; x < n; x++) {
                const int *xo = g->xw + 5 * x, *yo = g->yw + 5 * y, *zo = g->zw + 5 * z;
                const size_t p = (size_t)(zo[2] + yo[2] + xo[2]);
                double gm[6], am[6], gi[6];
                for (int c = 0; c < 6; c++) {
                    gm[c] = u[(BS_G + c) * fs + p];
                    am[c] = u[(BS_A + c) * fs + p];
                }
                const double chi = u[BS_CHI * fs + p], K = u[BS_K * fs + p], alp = u[BS_ALP * fs + p];
                // Inverse conformal metric.
                const double c00 = gm[3] * gm[5] - gm[4] * gm[4];
                const double c01 = gm[2] * gm[4] - gm[1] * gm[5];
                const double c02 = gm[1] * gm[4] - gm[2] * gm[3];
                const double idet = 1.0 / (gm[0] * c00 + gm[1] * c01 + gm[2] * c02);
                gi[0] = c00 * idet;
                gi[1] = c01 * idet;
                gi[2] = c02 * idet;
                gi[3] = (gm[0] * gm[5] - gm[2] * gm[2]) * idet;
                gi[4] = (gm[1] * gm[2] - gm[0] * gm[4]) * idet;
                gi[5] = (gm[0] * gm[3] - gm[1] * gm[1]) * idet;
                // ∂i∂j α and the principal part of the Ricci tensor,
                // R_ij ≈ −½ γ^{kl} ∂k∂l γ_ij.
                double dda[6], X[6];
                bs_d2(u + BS_ALP * fs, xo, yo, zo, g, dda);
                for (int c = 0; c < 6; c++) {
                    double dd[6];
                    bs_d2(u + (BS_G + c) * fs, xo, yo, zo, g, dd);
                    X[c] = -dda[c] - 0.5 * alp * bs_trace(gi, dd);
                }
                const double trX = bs_trace(gi, X), lapa = bs_trace(gi, dda);
                // M = γ⁻¹Ã; (Ã γ⁻¹ Ã)_ij and Ã_ij Ã^ij.
                double M[3][3];
                for (int i = 0; i < 3; i++)
                    for (int j = 0; j < 3; j++) {
                        double s = 0.0;
                        for (int k = 0; k < 3; k++) s += gi[bs_sym[i][k]] * am[bs_sym[k][j]];
                        M[i][j] = s;
                    }
                double AA = 0.0;
                for (int i = 0; i < 3; i++)
                    for (int j = 0; j < 3; j++) AA += M[i][j] * M[j][i];
                for (int i = 0; i < 3; i++)
                    for (int j = i; j < 3; j++) {
                        const int c = bs_sym[i][j];
                        double aga = 0.0;
                        for (int k = 0; k < 3; k++) aga += am[bs_sym[i][k]] * M[k][j];
                        r[(BS_G + c) * fs + p] = -2.0 * alp * am[c];
                        r[(BS_A + c) * fs + p] = chi * (X[c] - trX * gm[c] / 3.0) + alp * (K * am[c] - 2.0 * aga);
                    }
                r[BS_CHI * fs + p] = (2.0 / 3.0) * chi * alp * K;
                r[BS_K * fs + p] = -chi * lapa + alp * (AA + K * K / 3.0);
                r[BS_ALP * fs + p] = -2.0 * alp * K;
                for (int f = 0; f < BS_NF; f++) r[f * fs + p] += bs_ko(u + f * fs, xo, yo, zo, g);
            }
}

/// A BSSN-like numerical-relativity evolution: the kind of program SPEC's
/// cactuBSSN is. Fifteen coupled fields on a periodic n³ grid (the
/// conformal metric γ̃ij, the trace-free extrinsic curvature Ãij, the
/// conformal factor χ, the trace K and the lapse α, with 1+log slicing and
/// zero shift) evolved by the BSSN equations kept to their principal and
/// quadratic parts: fourth-order centred second and mixed derivatives, the
/// inverse metric and the trace-free projection at every point,
/// Kreiss–Oliger dissipation, classical RK4 with dt = h/4. The start is a
/// smooth perturbation of flat space. The answer is the squared L2 norm of
/// the departure from flat space at the end. `size` 1: 24³ for 22 steps;
/// 2: 40³ for 20 (31 MB); 3: 64³ for 19 (122 MB). Work: grid-point updates
/// (each is four right-hand-side evaluations, one per RK stage).
int cbk_stencil(int size, cb_bench_result *out) {
    static const int cfg[3][2] = {{24, 22}, {40, 20}, {64, 19}};
    const int lv = fpa_level(size) - 1;
    const int n = cfg[lv][0], steps = cfg[lv][1];
    const size_t np = (size_t)n * n * n, fs = np + FPA_PAD, tot = BS_NF * fs;
    double *mem = calloc(4 * tot, sizeof(double));
    int *wrap = malloc(sizeof(int) * 15 * (size_t)n);
    if (!mem || !wrap) {
        free(mem); free(wrap);
        return 1;
    }
    double *u = mem, *acc = mem + tot, *tmp = mem + 2 * tot, *rhs = mem + 3 * tot;
    int *xw = wrap, *yw = wrap + 5 * n, *zw = wrap + 10 * n;
    for (int c = 0; c < n; c++)
        for (int a = 0; a < 5; a++) {
            const int w = (c + a - 2 + n) % n;
            xw[5 * c + a] = w;
            yw[5 * c + a] = w * n;
            zw[5 * c + a] = w * n * n;
        }
    const double h = 1.0 / n, dt = 0.25 * h;
    bs_grid g;
    g.n = n;
    g.np = np;
    g.fs = fs;
    g.c12 = 1.0 / (12.0 * h * h);
    g.c144 = 1.0 / (144.0 * h * h);
    g.sko = 0.2 / (16.0 * h);
    g.xw = xw;
    g.yw = yw;
    g.zw = zw;

    // A smooth, periodic perturbation of flat space.
    const double eps = 0.05, tp = 2.0 * FPA_PI;
    for (int z = 0; z < n; z++)
        for (int y = 0; y < n; y++)
            for (int x = 0; x < n; x++) {
                const size_t p = ((size_t)z * n + y) * n + x;
                double sx, cx, sy, cy, sz, cz;
                fpa_sincos(tp * x * h, &sx, &cx);
                fpa_sincos(tp * y * h, &sy, &cy);
                fpa_sincos(tp * z * h, &sz, &cz);
                const double s2x = fpa_sin(2.0 * tp * x * h);
                u[(BS_G + 0) * fs + p] = 1.0 + eps * sx * cy;
                u[(BS_G + 1) * fs + p] = 0.5 * eps * sx * sy;
                u[(BS_G + 2) * fs + p] = 0.5 * eps * cz * s2x;
                u[(BS_G + 3) * fs + p] = 1.0 + eps * sy * cz;
                u[(BS_G + 4) * fs + p] = 0.5 * eps * sy * sz;
                u[(BS_G + 5) * fs + p] = 1.0 + eps * sz * cx;
                for (int c = 0; c < 6; c++) u[(BS_A + c) * fs + p] = 0.0;
                u[BS_CHI * fs + p] = 1.0;
                u[BS_K * fs + p] = 0.02 * (cx + cy * cz);
                u[BS_ALP * fs + p] = 1.0 + 0.1 * sx * sy * sz;
            }

    for (int step = 0; step < steps; step++) {
        memcpy(acc, u, sizeof(double) * tot);
        bs_rhs(&g, u, rhs);
        for (size_t i = 0; i < tot; i++) {
            acc[i] += dt / 6.0 * rhs[i];
            tmp[i] = u[i] + 0.5 * dt * rhs[i];
        }
        bs_rhs(&g, tmp, rhs);
        for (size_t i = 0; i < tot; i++) {
            acc[i] += dt / 3.0 * rhs[i];
            tmp[i] = u[i] + 0.5 * dt * rhs[i];
        }
        bs_rhs(&g, tmp, rhs);
        for (size_t i = 0; i < tot; i++) {
            acc[i] += dt / 3.0 * rhs[i];
            tmp[i] = u[i] + dt * rhs[i];
        }
        bs_rhs(&g, tmp, rhs);
        for (size_t i = 0; i < tot; i++) acc[i] += dt / 6.0 * rhs[i];
        double *t = u;
        u = acc;
        acc = t;
    }

    static const double flat[6] = {1.0, 0.0, 0.0, 1.0, 0.0, 1.0};
    double norm = 0.0;
    for (size_t p = 0; p < np; p++) {
        double s = 0.0;
        for (int c = 0; c < 6; c++) {
            const double dg = u[(BS_G + c) * fs + p] - flat[c], da = u[(BS_A + c) * fs + p];
            s += dg * dg + da * da;
        }
        const double dchi = u[BS_CHI * fs + p] - 1.0, dk = u[BS_K * fs + p], dal = u[BS_ALP * fs + p] - 1.0;
        norm += s + dchi * dchi + dk * dk + dal * dal;
    }
    free(mem); free(wrap);
    out->checksum = 0;
    out->value = norm * h * h * h;
    out->work = (double)np * steps;
    out->unit = "point updates";
    return 0;
}

// ── 7. Image processing (imagefilter) ───────────────────────────────────

/// Resampling weights: output sample o reads input first[o] .. + taps − 1
/// (clamped at the edges) with weights w[o·taps ..].
typedef struct {
    int taps;
    int *first;
    float *w;
} if_rs;

static double if_lanczos3(double x) {
    if (x < 0.0) x = -x;
    if (x < 1e-9) return 1.0;
    if (x >= 3.0) return 0.0;
    const double px = FPA_PI * x;
    return 3.0 * sin(px) * sin(px / 3.0) / (px * px);
}

/// Lanczos-3 weights from `in` samples to `out`, widened by the scale
/// factor when shrinking (so it also low-passes).
static int if_rs_build(if_rs *t, int in, int out) {
    const double scale = (double)out / in, fs = scale < 1.0 ? 1.0 / scale : 1.0;
    const double support = 3.0 * fs;
    t->taps = (int)ceil(2.0 * support) + 1;
    t->first = malloc(sizeof(int) * (size_t)out);
    t->w = malloc(sizeof(float) * (size_t)out * (size_t)t->taps);
    if (!t->first || !t->w) return -1;
    for (int o = 0; o < out; o++) {
        const double center = (o + 0.5) / scale - 0.5;
        const int first = (int)floor(center - support) + 1;
        double sum = 0.0;
        for (int k = 0; k < t->taps; k++) sum += if_lanczos3((first + k - center) / fs);
        for (int k = 0; k < t->taps; k++)
            t->w[(size_t)o * t->taps + k] = (float)(if_lanczos3((first + k - center) / fs) / sum);
        t->first[o] = first;
    }
    return 0;
}

static inline int if_clamp(int v, int lo, int hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static inline float if_clampf(float v) {
    return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
}

/// Resample each row of src (sw wide, h rows) into dst (dw wide).
static void if_rs_h(const float *src, int sw, int h, float *dst, int dw, const if_rs *t) {
    for (int y = 0; y < h; y++) {
        const float *s = src + (size_t)y * sw;
        float *d = dst + (size_t)y * dw;
        for (int o = 0; o < dw; o++) {
            const float *w = t->w + (size_t)o * t->taps;
            float acc = 0.0f;
            for (int k = 0; k < t->taps; k++) acc += w[k] * s[if_clamp(t->first[o] + k, 0, sw - 1)];
            d[o] = acc;
        }
    }
}

/// Resample each column of src (w wide, sh rows) into dst (dh rows).
static void if_rs_v(const float *src, int w, int sh, float *dst, int dh, const if_rs *t) {
    for (int o = 0; o < dh; o++) {
        float *d = dst + (size_t)o * w;
        for (int x = 0; x < w; x++) d[x] = 0.0f;
        for (int k = 0; k < t->taps; k++) {
            const float wk = t->w[(size_t)o * t->taps + k];
            const float *s = src + (size_t)if_clamp(t->first[o] + k, 0, sh - 1) * w;
            for (int x = 0; x < w; x++) d[x] += wk * s[x];
        }
    }
}

/// Separable convolution with a symmetric kernel of radius r: rows from
/// src into tmp, then columns from tmp into dst.
static void if_blur(const float *src, float *tmp, float *dst, int w, int h, const float *k, int r) {
    for (int y = 0; y < h; y++) {
        const float *s = src + (size_t)y * w;
        float *d = tmp + (size_t)y * w;
        for (int x = 0; x < w; x++) {
            float acc = 0.0f;
            if (x >= r && x < w - r) {
                for (int t = -r; t <= r; t++) acc += k[t + r] * s[x + t];
            } else {
                for (int t = -r; t <= r; t++) acc += k[t + r] * s[if_clamp(x + t, 0, w - 1)];
            }
            d[x] = acc;
        }
    }
    for (int y = 0; y < h; y++) {
        float *d = dst + (size_t)y * w;
        for (int x = 0; x < w; x++) d[x] = 0.0f;
        for (int t = -r; t <= r; t++) {
            const float kt = k[t + r];
            const float *s = tmp + (size_t)if_clamp(y + t, 0, h - 1) * w;
            for (int x = 0; x < w; x++) d[x] += kt * s[x];
        }
    }
}

/// dst = clamp(a·src + b·(K ∗ src) + c) for a 3×3 kernel K, edges
/// replicated.
static void if_conv3(const float *src, float *dst, int w, int h, const float K[9], float a, float b, float c) {
    for (int y = 0; y < h; y++) {
        const float *r0 = src + (size_t)(y > 0 ? y - 1 : 0) * w;
        const float *r1 = src + (size_t)y * w;
        const float *r2 = src + (size_t)(y < h - 1 ? y + 1 : h - 1) * w;
        float *d = dst + (size_t)y * w;
        for (int x = 0; x < w; x++) {
            const int xm = x > 0 ? x - 1 : 0, xp = x < w - 1 ? x + 1 : w - 1;
            const float v = K[0] * r0[xm] + K[1] * r0[x] + K[2] * r0[xp] +
                            K[3] * r1[xm] + K[4] * r1[x] + K[5] * r1[xp] +
                            K[6] * r2[xm] + K[7] * r2[x] + K[8] * r2[xp];
            d[x] = if_clampf(a * r1[x] + b * v + c);
        }
    }
}

static inline float if_lab_f(float t) {
    return t > 0.008856f ? cbrtf(t) : 7.787f * t + 16.0f / 116.0f;
}

static inline float if_lab_finv(float f) {
    const float f3 = f * f * f;
    return f3 > 0.008856f ? f3 : (f - 16.0f / 116.0f) / 7.787f;
}

/// An image-processing pipeline in single precision: the kind of program
/// SPEC's imagick (ImageMagick) is. A generated sRGB test card goes, each
/// pass, through: sRGB → linear; a separable Gaussian blur (σ = 2) used for
/// an unsharp mask; a Lanczos-3 resize down to 60 % and back up; linear →
/// CIE XYZ → L*a*b*, a contrast and saturation boost, and back to sRGB;
/// and a chain of 3×3 convolutions (sharpen, smooth, emboss blend). Each
/// pass feeds the next. The answer is the mean of the final image over all
/// channels. `size` 1: 960×640 for 3 passes; 2: 1920×1200 for 4 (54 MB);
/// 3: 3840×2160 for 5 (190 MB). Work: pixels processed (counted per pass).
int cbk_imagefilter(int size, cb_bench_result *out) {
    static const int cfg[3][3] = {{960, 640, 3}, {1920, 1200, 4}, {3840, 2160, 5}};
    const int lv = fpa_level(size) - 1;
    const int W = cfg[lv][0], H = cfg[lv][1], passes = cfg[lv][2];
    const int W2 = W * 3 / 5, H2 = H * 3 / 5;
    const size_t wh = (size_t)W * H;
    float *img = malloc(sizeof(float) * 3 * wh);
    float *t1 = malloc(sizeof(float) * wh), *t2 = malloc(sizeof(float) * wh);
    float *th = malloc(sizeof(float) * (size_t)W2 * H);
    float *sm = malloc(sizeof(float) * (size_t)W2 * H2);
    if_rs dx = {0, NULL, NULL}, dy = {0, NULL, NULL}, ux = {0, NULL, NULL}, uy = {0, NULL, NULL};
    int rc = 1;
    if (!img || !t1 || !t2 || !th || !sm) goto done;
    if (if_rs_build(&dx, W, W2) || if_rs_build(&dy, H, H2) || if_rs_build(&ux, W2, W) ||
        if_rs_build(&uy, H2, H))
        goto done;

    // Gaussian kernel, σ = 2, radius 6.
    float gk[13];
    {
        double s = 0.0, kd[13];
        for (int t = -6; t <= 6; t++) s += (kd[t + 6] = exp(-(double)(t * t) / 8.0));
        for (int t = 0; t < 13; t++) gk[t] = (float)(kd[t] / s);
    }

    // A test card: colour gradients, rings, a checkerboard and noise.
    fpa_rng rng;
    fpa_seed(&rng, 0x1DEA0001ull);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            const float fx = (float)x / W, fy = (float)y / H;
            const float ddx = fx - 0.5f, ddy = fy - 0.45f;
            const float dist = sqrtf(ddx * ddx + ddy * ddy);
            const float check = (((x >> 5) ^ (y >> 5)) & 1) ? 0.08f : -0.08f;
            const float noise = (float)(fpa_u01(&rng) - 0.5) * 0.1f;
            const size_t p = (size_t)y * W + x;
            img[p] = if_clampf(0.5f + 0.4f * sinf(6.2831853f * (3.0f * fx + fy)) + check + noise);
            img[wh + p] = if_clampf(0.5f + 0.4f * cosf(40.0f * dist) + noise);
            img[2 * wh + p] = if_clampf(0.15f + 0.7f * fx * fy - check + noise);
        }

    static const float k_sharpen[9] = {0, -1, 0, -1, 5, -1, 0, -1, 0};
    static const float k_smooth[9] = {1.f / 16, 2.f / 16, 1.f / 16, 2.f / 16, 4.f / 16, 2.f / 16, 1.f / 16, 2.f / 16, 1.f / 16};
    static const float k_emboss[9] = {-2, -1, 0, -1, 1, 1, 0, 1, 2};

    for (int pass = 0; pass < passes; pass++) {
        // sRGB → linear.
        for (size_t i = 0; i < 3 * wh; i++) {
            const float c = img[i];
            img[i] = c <= 0.04045f ? c / 12.92f : powf((c + 0.055f) / 1.055f, 2.4f);
        }
        for (int ch = 0; ch < 3; ch++) {
            float *pl = img + (size_t)ch * wh;
            // Unsharp mask.
            if_blur(pl, t1, t2, W, H, gk, 6);
            for (size_t i = 0; i < wh; i++) pl[i] = if_clampf(pl[i] + 0.7f * (pl[i] - t2[i]));
            // Lanczos-3 down to 60 %, and back up.
            if_rs_h(pl, W, H, th, W2, &dx);
            if_rs_v(th, W2, H, sm, H2, &dy);
            if_rs_v(sm, W2, H2, th, H, &uy);
            if_rs_h(th, W2, H, pl, W, &ux);
            for (size_t i = 0; i < wh; i++) pl[i] = if_clampf(pl[i]);
        }
        // Linear → XYZ → Lab, adjust, and back to sRGB.
        for (size_t i = 0; i < wh; i++) {
            const float R = img[i], G = img[wh + i], B = img[2 * wh + i];
            const float X = (0.4124564f * R + 0.3575761f * G + 0.1804375f * B) / 0.95047f;
            const float Y = 0.2126729f * R + 0.7151522f * G + 0.0721750f * B;
            const float Z = (0.0193339f * R + 0.1191920f * G + 0.9503041f * B) / 1.08883f;
            const float fx = if_lab_f(X), fy = if_lab_f(Y), fz = if_lab_f(Z);
            float L = 116.0f * fy - 16.0f, a = 500.0f * (fx - fy), b = 200.0f * (fy - fz);
            L = 50.0f + (L - 50.0f) * 1.08f;
            a *= 1.12f;
            b *= 1.12f;
            const float gy = (L + 16.0f) / 116.0f, gx = gy + a / 500.0f, gz = gy - b / 200.0f;
            const float X2 = if_lab_finv(gx) * 0.95047f, Y2 = if_lab_finv(gy), Z2 = if_lab_finv(gz) * 1.08883f;
            const float lin[3] = {
                3.2404542f * X2 - 1.5371385f * Y2 - 0.4985314f * Z2,
                -0.9692660f * X2 + 1.8760108f * Y2 + 0.0415560f * Z2,
                0.0556434f * X2 - 0.2040259f * Y2 + 1.0572252f * Z2};
            for (int ch = 0; ch < 3; ch++) {
                const float c = if_clampf(lin[ch]);
                img[(size_t)ch * wh + i] = c <= 0.0031308f ? 12.92f * c : 1.055f * powf(c, 1.0f / 2.4f) - 0.055f;
            }
        }
        // 3×3 chain: sharpen, smooth, then blend in an emboss.
        for (int ch = 0; ch < 3; ch++) {
            float *pl = img + (size_t)ch * wh;
            if_conv3(pl, t1, W, H, k_sharpen, 0.0f, 1.0f, 0.0f);
            if_conv3(t1, t2, W, H, k_smooth, 0.0f, 1.0f, 0.0f);
            if_conv3(t2, pl, W, H, k_emboss, 0.8f, 0.2f, 0.0f);
        }
    }

    double sum = 0.0;
    for (size_t i = 0; i < 3 * wh; i++) sum += img[i];
    out->checksum = 0;
    out->value = sum / (3.0 * (double)wh);
    out->work = (double)wh * passes;
    out->unit = "pixels";
    rc = 0;
done:
    free(img); free(t1); free(t2); free(th); free(sm);
    free(dx.first); free(dx.w); free(dy.first); free(dy.w);
    free(ux.first); free(ux.w); free(uy.first); free(uy.w);
    return rc;
}

// ── 8. Shallow water (shallow) ──────────────────────────────────────────

typedef struct {
    int nx, ny;
    double d, g, nu, f0, beta, ly;
    const int *im, *ip, *im2;     // periodic x neighbours
    double *U, *V, *B, *q, *th, *Fx, *Fy;
} sw_ctx;

/// 3rd-order upwind-biased face value times the flux:
/// U·(centred 4th order) + |U|·(upwind correction).
static inline double sw_flux3(double U, double tm2, double tm1, double t0, double tp1) {
    const double cen = (7.0 * (t0 + tm1) - (tp1 + tm2)) / 12.0;
    const double up = ((tp1 - tm2) - 3.0 * (t0 - tm1)) / 12.0;
    return U * cen + fabs(U) * up;
}

/// Tendencies of h, u, v and the tracer mass m = h·θ on the C grid.
/// Centres and u-points are [j·nx + i], j < ny; v-points and corners
/// (vorticity) are [j·nx + i], j <= ny.
static void sw_tend(sw_ctx *c, const double *h, const double *u, const double *v, const double *m,
                    double *dh, double *du, double *dv, double *dm) {
    const int nx = c->nx, ny = c->ny;
    const double d = c->d, id = 1.0 / d, id2 = id * id;
    double *U = c->U, *V = c->V, *B = c->B, *q = c->q, *th = c->th, *Fx = c->Fx, *Fy = c->Fy;
    for (int j = 0; j < ny; j++)
        for (int i = 0; i < nx; i++) {
            const int k = j * nx + i;
            U[k] = 0.5 * (h[j * nx + c->im[i]] + h[k]) * u[k];
            const double ke = 0.25 * (u[k] * u[k] + u[j * nx + c->ip[i]] * u[j * nx + c->ip[i]] +
                                      v[k] * v[k] + v[k + nx] * v[k + nx]);
            B[k] = c->g * h[k] + ke;
            th[k] = m[k] / h[k];
        }
    for (int j = 0; j <= ny; j++)
        for (int i = 0; i < nx; i++) {
            const int k = j * nx + i, im = c->im[i];
            double zeta, hc;
            if (j == 0 || j == ny) {
                V[k] = 0.0;
                const int jj = j == 0 ? 0 : ny - 1;
                zeta = 0.0;                                   // free slip
                hc = 0.5 * (h[jj * nx + im] + h[jj * nx + i]);
            } else {
                V[k] = 0.5 * (h[k - nx] + h[k]) * v[k];
                zeta = (v[k] - v[j * nx + im]) * id - (u[k] - u[k - nx]) * id;
                hc = 0.25 * (h[k - nx + im - i] + h[k - nx] + h[j * nx + im] + h[k]);
            }
            const double f = c->f0 + c->beta * (j * d - 0.5 * c->ly);
            q[k] = (f + zeta) / hc;
        }
    for (int j = 0; j < ny; j++)
        for (int i = 0; i < nx; i++) {
            const int k = j * nx + i, im = c->im[i], ip = c->ip[i];
            const double vs = V[j * nx + im] + V[k] + V[k + nx - i + im] + V[k + nx];
            const double qs = q[k] + q[k + nx];
            const double un = j + 1 < ny ? u[k + nx] : u[k], us = j > 0 ? u[k - nx] : u[k];
            const double lap = (u[j * nx + ip] + u[j * nx + im] + un + us - 4.0 * u[k]) * id2;
            du[k] = 0.125 * qs * vs - (B[k] - B[j * nx + im]) * id + c->nu * lap;
            dh[k] = -((U[j * nx + ip] - U[k]) + (V[k + nx] - V[k])) * id;
            Fx[k] = sw_flux3(U[k], th[j * nx + c->im2[i]], th[j * nx + im], th[k], th[j * nx + ip]);
        }
    for (int j = 0; j <= ny; j++)
        for (int i = 0; i < nx; i++) {
            const int k = j * nx + i, ip = c->ip[i];
            if (j == 0 || j == ny) {
                dv[k] = 0.0;
                Fy[k] = 0.0;
                continue;
            }
            const double us = U[k - nx] + U[k - nx - i + ip] + U[k] + U[j * nx + ip];
            const double qs = q[k] + q[j * nx + ip];
            const double lap = (v[j * nx + ip] + v[j * nx + c->im[i]] + v[k + nx] + v[k - nx] - 4.0 * v[k]) * id2;
            dv[k] = -0.125 * qs * us - (B[k] - B[k - nx]) * id + c->nu * lap;
            if (j >= 2 && j <= ny - 2)
                Fy[k] = sw_flux3(V[k], th[k - 2 * nx], th[k - nx], th[k], th[k + nx]);
            else
                Fy[k] = V[k] * 0.5 * (th[k - nx] + th[k]);
        }
    for (int j = 0; j < ny; j++)
        for (int i = 0; i < nx; i++) {
            const int k = j * nx + i;
            dm[k] = -((Fx[j * nx + c->ip[i]] - Fx[k]) + (Fy[k + nx] - Fy[k])) * id;
        }
}

/// The shallow-water equations on a β-plane channel: the dynamical core of
/// the kind of weather, ocean and climate model SPEC's wrf, roms, cam4,
/// palm and pot3d are. Arakawa C grid over 6000×3000 km, periodic east–west
/// with free-slip walls north and south; vector-invariant momentum
/// equations with the potential-vorticity (Coriolis plus relative
/// vorticity) flux, Bernoulli gradient and Laplacian viscosity; flux-form
/// continuity; a passive tracer with third-order upwind-biased fluxes (as
/// WRF's); Wicker–Skamarock RK3 at gravity-wave Courant number 0.5. It
/// starts from a geostrophically balanced jet with a wave-4 disturbance,
/// which grows by barotropic instability. The answer is the mean total
/// energy per unit area (g·h²/2 plus kinetic, per unit density); mass and
/// tracer are conserved to rounding by the flux form. `size` 1: 192×96
/// cells for 380 steps; 2: 384×192 for 400; 3: 768×384 for 450.
/// Work: cell updates (each is three RK stages).
int cbk_shallow(int size, cb_bench_result *out) {
    static const int cfg[3][2] = {{192, 380}, {384, 400}, {768, 450}};
    const int lv = fpa_level(size) - 1;
    const int nx = cfg[lv][0], ny = nx / 2, steps = cfg[lv][1];
    const size_t nc = (size_t)nx * ny, nv = (size_t)nx * (ny + 1);
    // State, stage, tendencies (h, u, v, m each) and work arrays.
    double *mem = malloc(sizeof(double) * (13 * nc + 6 * nv + 19 * FPA_PAD));
    int *idx = malloc(sizeof(int) * 3 * (size_t)nx);
    if (!mem || !idx) {
        free(mem); free(idx);
        return 1;
    }
    double *p = mem;
#define SW_TAKE(len) (p += (len) + FPA_PAD, p - (len) - FPA_PAD)
    double *h = SW_TAKE(nc), *u = SW_TAKE(nc), *v = SW_TAKE(nv), *m = SW_TAKE(nc);
    double *hs = SW_TAKE(nc), *us = SW_TAKE(nc), *vs = SW_TAKE(nv), *ms = SW_TAKE(nc);
    double *dh = SW_TAKE(nc), *du = SW_TAKE(nc), *dv = SW_TAKE(nv), *dm = SW_TAKE(nc);
    sw_ctx c;
    c.U = SW_TAKE(nc);
    c.B = SW_TAKE(nc);
    c.th = SW_TAKE(nc);
    c.Fx = SW_TAKE(nc);
    c.V = SW_TAKE(nv);
    c.q = SW_TAKE(nv);
    c.Fy = SW_TAKE(nv);
#undef SW_TAKE
    int *im = idx, *ip = idx + nx, *im2 = idx + 2 * nx;
    for (int i = 0; i < nx; i++) {
        im[i] = (i + nx - 1) % nx;
        ip[i] = (i + 1) % nx;
        im2[i] = (i + nx - 2) % nx;
    }
    c.nx = nx;
    c.ny = ny;
    c.im = im;
    c.ip = ip;
    c.im2 = im2;
    c.d = 6.0e6 / nx;
    c.g = 9.81;
    c.f0 = 1.0e-4;
    c.beta = 1.6e-11;
    c.ly = ny * c.d;
    const double H0 = 1000.0, lx = nx * c.d;
    const double dt = 0.5 * c.d / sqrt(c.g * H0);
    c.nu = 0.002 * c.d * c.d / dt;

    // A balanced jet, h(y) = H0 − (f0·U0·Lj/g)·tanh(η), u = U0·sech²(η).
    const double y0 = 0.5 * c.ly, Lj = 0.08 * c.ly, U0 = 30.0;
    for (int j = 0; j < ny; j++) {
        const double yc = (j + 0.5) * c.d, eta = (yc - y0) / Lj, tn = fpa_tanh(eta);
        const double bump = fpa_exp(-eta * eta);
        for (int i = 0; i < nx; i++) {
            const int k = j * nx + i;
            const double xc = (i + 0.5) * c.d;
            h[k] = H0 - (c.f0 * U0 * Lj / c.g) * tn + 10.0 * fpa_sin(2.0 * FPA_PI * 4.0 * xc / lx) * bump;
            u[k] = U0 * (1.0 - tn * tn);
            const double rx = (xc - lx / 3.0) / Lj, ry = eta;
            m[k] = h[k] * (1.0 + 0.5 * tn + 0.3 * fpa_exp(-(rx * rx + ry * ry)));
        }
    }
    // A wave-4 meridional wind across the jet seeds its instability.
    for (int j = 0; j <= ny; j++)
        for (int i = 0; i < nx; i++) {
            const double eta = (j * c.d - y0) / Lj;
            v[j * nx + i] = (j == 0 || j == ny) ? 0.0
                          : 1.0 * fpa_sin(2.0 * FPA_PI * 4.0 * (i * c.d) / lx) * fpa_exp(-eta * eta);
        }

    for (int step = 0; step < steps; step++) {
        sw_tend(&c, h, u, v, m, dh, du, dv, dm);
        for (size_t k = 0; k < nc; k++) {
            hs[k] = h[k] + dt / 3.0 * dh[k];
            us[k] = u[k] + dt / 3.0 * du[k];
            ms[k] = m[k] + dt / 3.0 * dm[k];
        }
        for (size_t k = 0; k < nv; k++) vs[k] = v[k] + dt / 3.0 * dv[k];
        sw_tend(&c, hs, us, vs, ms, dh, du, dv, dm);
        for (size_t k = 0; k < nc; k++) {
            hs[k] = h[k] + 0.5 * dt * dh[k];
            us[k] = u[k] + 0.5 * dt * du[k];
            ms[k] = m[k] + 0.5 * dt * dm[k];
        }
        for (size_t k = 0; k < nv; k++) vs[k] = v[k] + 0.5 * dt * dv[k];
        sw_tend(&c, hs, us, vs, ms, dh, du, dv, dm);
        for (size_t k = 0; k < nc; k++) {
            h[k] += dt * dh[k];
            u[k] += dt * du[k];
            m[k] += dt * dm[k];
        }
        for (size_t k = 0; k < nv; k++) v[k] += dt * dv[k];
    }

    double energy = 0.0;
    for (int j = 0; j < ny; j++)
        for (int i = 0; i < nx; i++) {
            const int k = j * nx + i, kp = j * nx + ip[i];
            const double ke = 0.25 * (u[k] * u[k] + u[kp] * u[kp] + v[k] * v[k] + v[k + nx] * v[k + nx]);
            energy += 0.5 * c.g * h[k] * h[k] + h[k] * ke;
        }
    free(mem); free(idx);
    out->checksum = 0;
    out->value = energy / (double)nc;
    out->work = (double)nc * steps;
    out->unit = "cell updates";
    return 0;
}

// ── 9. Monte Carlo neutron transport (neutron) ──────────────────────────

#define NT_NNUC 5
#define NT_MAXSITES 6
static const double NT_PITCH = 1.26, NT_RF = 0.4096, NT_RC = 0.475;
#define NT_NPIN 51                      // 3×3 assemblies of 17×17 pins
static const double NT_HLAT = 32.13;    // half-width of the pin lattice
static const double NT_HOUT = 42.13;    // with 10 cm of water reflector
static const double NT_ZH = 60.0;       // half-height

/// A nuclide's pointwise cross sections (barns) on its own energy grid (eV):
/// xs[4i ..] = total, scattering, absorption, fission at e[i].
typedef struct {
    int n;
    double awr, nu;
    double *e, *xs;
} nt_nuc;

/// How a synthetic nuclide's data are made: 1/v absorption, a smooth
/// scattering cross section, resolved resonances, fast fission.
typedef struct {
    double awr, nu, pot, cap0, fis0, fastfis;
    int npts, nres;
    double res_lo, res_hi, peak_lo, peak_hi, gam_lo, gam_hi, capfrac, fisfrac;
} nt_spec;

static const nt_spec nt_specs[NT_NNUC] = {
    // fissile (U-235-like)
    {233.0, 2.43, 11.0, 99.0, 585.0, 1.2, 6000, 40, 1.0, 2000.0, 20.0, 400.0, 0.05, 0.3, 0.4, 0.6},
    // fertile (U-238-like)
    {236.0, 2.60, 9.0, 2.7, 0.0, 0.0, 12000, 40, 6.0, 20000.0, 200.0, 3000.0, 0.02, 0.15, 0.85, 0.0},
    // hydrogen
    {0.999, 0.0, 0.0, 0.332, 0.0, 0.0, 1500, 0, 0, 0, 0, 0, 0, 0, 0, 0},
    // oxygen
    {15.86, 0.0, 3.8, 0.00019, 0.0, 0.0, 2500, 6, 4.0e5, 5.0e6, 2.0, 10.0, 2.0e4, 1.0e5, 0.0, 0.0},
    // zirconium
    {90.2, 0.0, 6.4, 0.185, 0.0, 0.0, 5000, 20, 200.0, 1.0e5, 20.0, 300.0, 0.5, 20.0, 0.6, 0.0},
};

// Materials: fuel (UO2), clad (Zr), water; nuclide and atoms per barn·cm.
static const int nt_mat_len[3] = {3, 1, 2};
static const int nt_mat_nuc[3][3] = {{0, 1, 3}, {4, 0, 0}, {2, 3, 0}};
static const double nt_mat_den[3][3] = {{7.5e-4, 2.22e-2, 4.59e-2}, {4.25e-2, 0, 0}, {6.69e-2, 3.345e-2, 0}};
// Region → material: fuel, clad, moderator, reflector.
static const int nt_region_mat[4] = {0, 1, 2, 2};

static int nt_build(nt_nuc *nuc, double *store) {
    double *p = store;
    for (int k = 0; k < NT_NNUC; k++) {
        const nt_spec *sp = &nt_specs[k];
        nt_nuc *nk = &nuc[k];
        nk->n = sp->npts;
        nk->awr = sp->awr;
        nk->nu = sp->nu;
        nk->e = p; p += sp->npts;
        nk->xs = p; p += 4 * (size_t)sp->npts;
        // Resonances: energy log-uniform, peak and width uniform.
        double r_e[64], r_pk[64], r_g[64];
        fpa_rng rng;
        fpa_seed(&rng, 0xA70Bull + (uint64_t)k);
        for (int r = 0; r < sp->nres; r++) {
            r_e[r] = sp->res_lo * fpa_exp(fpa_u01(&rng) * fpa_log(sp->res_hi / sp->res_lo));
            r_pk[r] = sp->peak_lo + (sp->peak_hi - sp->peak_lo) * fpa_u01(&rng);
            r_g[r] = sp->gam_lo + (sp->gam_hi - sp->gam_lo) * fpa_u01(&rng);
        }
        const double l0 = fpa_log(1e-5), l1 = fpa_log(2e7);
        for (int i = 0; i < sp->npts; i++) {
            const double E = fpa_exp(l0 + (l1 - l0) * i / (sp->npts - 1));
            const double inv_v = sqrt(0.0253 / E);
            double sc = k == 2 ? 4.0 + 16.4 / (1.0 + E / 5.0e4) : sp->pot;
            double ca = sp->cap0 * inv_v, fi = sp->fis0 * inv_v + sp->fastfis;
            if (k == 1) fi += 0.5 / (1.0 + fpa_exp(-(E - 1.4e6) / 1.0e5));   // threshold fission
            for (int r = 0; r < sp->nres; r++) {
                const double x = (E - r_e[r]) / (0.5 * r_g[r]);
                const double shape = r_pk[r] / (1.0 + x * x);
                ca += sp->capfrac * shape;
                fi += sp->fisfrac * shape;
                sc += (1.0 - sp->capfrac - sp->fisfrac) * shape;
            }
            nk->e[i] = E;
            nk->xs[4 * i + 0] = sc + ca + fi;
            nk->xs[4 * i + 1] = sc;
            nk->xs[4 * i + 2] = ca + fi;
            nk->xs[4 * i + 3] = fi;
        }
    }
    return 0;
}

/// Macroscopic cross sections (1/cm) of a material at energy E.
typedef struct {
    double tot, sca, abs, fis, nufis;
    double sca_c[3];
} nt_macro;

static void nt_lookup(const nt_nuc *nuc, int mat, double E, nt_macro *x) {
    x->sca = x->abs = x->fis = x->nufis = 0.0;
    for (int c = 0; c < nt_mat_len[mat]; c++) {
        const nt_nuc *nk = &nuc[nt_mat_nuc[mat][c]];
        const double N = nt_mat_den[mat][c];
        int lo = 0, hi = nk->n - 1;
        while (hi - lo > 1) {                          // binary search
            const int mid = (lo + hi) >> 1;
            if (nk->e[mid] > E) hi = mid;
            else lo = mid;
        }
        const double f = (E - nk->e[lo]) / (nk->e[lo + 1] - nk->e[lo]);
        const double *a = nk->xs + 4 * lo, *b = a + 4;
        const double ss = a[1] + f * (b[1] - a[1]);
        const double sa = a[2] + f * (b[2] - a[2]);
        const double sf = a[3] + f * (b[3] - a[3]);
        x->sca_c[c] = N * ss;
        x->sca += N * ss;
        x->abs += N * sa;
        x->fis += N * sf;
        x->nufis += N * nk->nu * sf;
    }
    x->tot = x->sca + x->abs;
}

/// The region a point is in: 0 fuel, 1 clad, 2 moderator, 3 reflector, −1
/// outside (leaked).
static int nt_locate(double x, double y, double z) {
    if (z <= -NT_ZH || z >= NT_ZH || fabs(x) >= NT_HOUT || fabs(y) >= NT_HOUT) return -1;
    if (fabs(x) >= NT_HLAT || fabs(y) >= NT_HLAT) return 3;
    int ix = (int)floor((x + NT_HLAT) / NT_PITCH), iy = (int)floor((y + NT_HLAT) / NT_PITCH);
    ix = ix < 0 ? 0 : (ix > NT_NPIN - 1 ? NT_NPIN - 1 : ix);
    iy = iy < 0 ? 0 : (iy > NT_NPIN - 1 ? NT_NPIN - 1 : iy);
    const double lx = x - (-NT_HLAT + (ix + 0.5) * NT_PITCH), ly = y - (-NT_HLAT + (iy + 0.5) * NT_PITCH);
    const double r2 = lx * lx + ly * ly;
    if (r2 < NT_RF * NT_RF)                      // guide tubes hold water
        return ((ix % 17) % 6 == 2 && (iy % 17) % 6 == 2) ? 2 : 0;
    if (r2 < NT_RC * NT_RC) return 1;
    return 2;
}

static double nt_plane(double p, double u, double lo, double hi) {
    if (u > 0.0) return (hi - p) / u;
    if (u < 0.0) return (lo - p) / u;
    return 1e300;
}

static double nt_cyl(double lx, double ly, double u, double v, double R) {
    const double a = u * u + v * v;
    if (a < 1e-20) return 1e300;
    const double b = lx * u + ly * v, c = lx * lx + ly * ly - R * R, disc = b * b - a * c;
    if (disc < 0.0) return 1e300;
    const double sq = sqrt(disc);
    if (c < 0.0) return (-b + sq) / a;          // inside: the exit
    if (b >= 0.0) return 1e300;                  // outside, moving away
    return (-b - sq) / a;                        // outside: the entry
}

/// Distance along (u, v, w) to the next surface of the region the point is
/// in.
static double nt_distance(int region, double x, double y, double z, double u, double v, double w) {
    double d = nt_plane(z, w, -NT_ZH, NT_ZH);
    if (region <= 2) {
        int ix = (int)floor((x + NT_HLAT) / NT_PITCH), iy = (int)floor((y + NT_HLAT) / NT_PITCH);
        ix = ix < 0 ? 0 : (ix > NT_NPIN - 1 ? NT_NPIN - 1 : ix);
        iy = iy < 0 ? 0 : (iy > NT_NPIN - 1 ? NT_NPIN - 1 : iy);
        const double lx = x - (-NT_HLAT + (ix + 0.5) * NT_PITCH), ly = y - (-NT_HLAT + (iy + 0.5) * NT_PITCH);
        const double t[4] = {nt_plane(lx, u, -0.5 * NT_PITCH, 0.5 * NT_PITCH),
                             nt_plane(ly, v, -0.5 * NT_PITCH, 0.5 * NT_PITCH),
                             nt_cyl(lx, ly, u, v, NT_RF), nt_cyl(lx, ly, u, v, NT_RC)};
        for (int k = 0; k < 4; k++)
            if (t[k] < d) d = t[k];
        return d;
    }
    double t = nt_plane(x, u, -NT_HOUT, NT_HOUT);
    if (t < d) d = t;
    t = nt_plane(y, v, -NT_HOUT, NT_HOUT);
    if (t < d) d = t;
    // Entry into the lattice square, if the flight crosses it.
    double t0 = 0.0, t1 = 1e300;
    const double pp[2] = {x, y}, dd[2] = {u, v};
    for (int a = 0; a < 2; a++) {
        if (fabs(dd[a]) < 1e-300) {
            if (pp[a] <= -NT_HLAT || pp[a] >= NT_HLAT) return d;
            continue;
        }
        double ta = (-NT_HLAT - pp[a]) / dd[a], tb = (NT_HLAT - pp[a]) / dd[a];
        if (ta > tb) {
            const double s = ta;
            ta = tb;
            tb = s;
        }
        if (ta > t0) t0 = ta;
        if (tb < t1) t1 = tb;
    }
    if (t0 <= t1 && t0 > 0.0 && t0 < d) d = t0;
    return d;
}

/// Maxwellian energy at temperature T (eV): −T(ln ξ1 + ln ξ2·cos²θ), with
/// cos²θ for a uniform angle taken from a point in the unit disc.
static double nt_maxwell(fpa_rng *rng, double T) {
    double a, b, r2;
    do {
        a = 2.0 * fpa_u01(rng) - 1.0;
        b = 2.0 * fpa_u01(rng) - 1.0;
        r2 = a * a + b * b;
    } while (r2 >= 1.0 || r2 == 0.0);
    return -T * (fpa_log(fpa_u01_open(rng)) + fpa_log(fpa_u01_open(rng)) * (a * a / r2));
}

/// A uniform azimuth as (cos φ, sin φ), from a point in the unit disc.
static void nt_azimuth(fpa_rng *rng, double *c, double *s) {
    double a, b, r2;
    do {
        a = 2.0 * fpa_u01(rng) - 1.0;
        b = 2.0 * fpa_u01(rng) - 1.0;
        r2 = a * a + b * b;
    } while (r2 >= 1.0 || r2 == 0.0);
    *c = (a * a - b * b) / r2;
    *s = 2.0 * a * b / r2;
}

static void nt_isotropic(fpa_rng *rng, double *u, double *v, double *w) {
    const double mu = 2.0 * fpa_u01(rng) - 1.0, st = sqrt(1.0 - mu * mu);
    double c, s;
    nt_azimuth(rng, &c, &s);
    *u = st * c;
    *v = st * s;
    *w = mu;
}

typedef struct {
    double x, y, z, E;
} nt_site;

/// Monte Carlo neutron transport, a k-eigenvalue calculation: the kind of
/// program a reactor-physics code like OpenMC is. A mini-core of 3×3
/// assemblies, each 17×17 pins (UO2 fuel, zirconium clad, nine water-filled
/// guide tubes) in water, with a 10 cm water reflector and vacuum outside,
/// 120 cm tall. Five synthetic nuclides carry pointwise energy-dependent
/// cross sections (1/v absorption, resolved resonances, threshold fission)
/// on 1500 to 12000 energy points each, found by binary search and
/// interpolated whenever the energy changes. Each history is tracked from
/// surface to surface with its own PRNG: elastic scattering with two-body
/// kinematics, a Maxwellian thermal treatment for light nuclei, capture,
/// and fission that banks Maxwellian-spectrum neutrons for the next
/// generation (power iteration with systematic resampling). The answer is
/// k-effective (about 1.14), averaged over the active generations and over
/// the collision, absorption and track-length estimators. `size` 1: 10
/// generations (4 inactive) of 2400 neutrons; 2: 20 (6) of 6000; 3: 30
/// (10) of 16000. Work: neutron histories.
int cbk_neutron(int size, cb_bench_result *out) {
    static const int cfg[3][3] = {{10, 4, 2400}, {20, 6, 6000}, {30, 10, 16000}};
    const int lv = fpa_level(size) - 1;
    const int nbatch = cfg[lv][0], ninactive = cfg[lv][1], N = cfg[lv][2];
    size_t nstore = 0;
    for (int k = 0; k < NT_NNUC; k++) nstore += 5 * (size_t)nt_specs[k].npts;
    double *store = malloc(sizeof(double) * nstore);
    nt_site *src = malloc(sizeof(nt_site) * (size_t)N);
    nt_site *bank = malloc(sizeof(nt_site) * (size_t)N * NT_MAXSITES);
    int *nsites = malloc(sizeof(int) * (size_t)N);
    if (!store || !src || !bank || !nsites) {
        free(store); free(src); free(bank); free(nsites);
        return 1;
    }
    nt_nuc nuc[NT_NNUC];
    nt_build(nuc, store);

    // First source: uniform over the fuel, fission spectrum.
    fpa_rng rng;
    fpa_seed(&rng, 0x4E55000Aull);
    for (int i = 0; i < N; i++) {
        double x, y, z;
        do {
            x = (2.0 * fpa_u01(&rng) - 1.0) * NT_HLAT;
            y = (2.0 * fpa_u01(&rng) - 1.0) * NT_HLAT;
            z = (2.0 * fpa_u01(&rng) - 1.0) * NT_ZH;
        } while (nt_locate(x, y, z) != 0);
        src[i].x = x;
        src[i].y = y;
        src[i].z = z;
        src[i].E = nt_maxwell(&rng, 1.2895e6);
    }

    const double NUDGE = 1e-8;
    double kprev = 1.0, ksum = 0.0;
    int nactive = 0;
    for (int batch = 0; batch < nbatch; batch++) {
        double kcol = 0.0, kabs = 0.0, ktl = 0.0;
        for (int i = 0; i < N; i++) {
            fpa_seed(&rng, 0x5EED0000ull ^ ((uint64_t)batch << 40) ^ ((uint64_t)i * 0x9E3779B97F4A7C15ull));
            double x = src[i].x, y = src[i].y, z = src[i].z, E = src[i].E;
            double u, v, w;
            nt_isotropic(&rng, &u, &v, &w);
            int region = nt_locate(x, y, z), mat = -1, ns = 0;
            double xsE = -1.0;
            nt_macro mx;
            memset(&mx, 0, sizeof mx);
            for (int events = 0; events < 5000 && region >= 0; events++) {
                const int m = nt_region_mat[region];
                if (m != mat || E != xsE) {
                    nt_lookup(nuc, m, E, &mx);
                    mat = m;
                    xsE = E;
                }
                const double s = -fpa_log(fpa_u01_open(&rng)) / mx.tot;
                const double db = nt_distance(region, x, y, z, u, v, w);
                if (s >= db) {                                  // to the surface
                    const double step = db + NUDGE;
                    x += step * u;
                    y += step * v;
                    z += step * w;
                    ktl += db * mx.nufis;
                    region = nt_locate(x, y, z);
                    continue;
                }
                x += s * u;                                     // to a collision
                y += s * v;
                z += s * w;
                ktl += s * mx.nufis;
                kcol += mx.nufis / mx.tot;
                const double xi = fpa_u01(&rng) * mx.tot;
                if (xi >= mx.sca) {                             // absorbed
                    kabs += mx.nufis / mx.abs;
                    if (mx.fis > 0.0 && fpa_u01(&rng) * mx.abs < mx.fis) {
                        int nn = (int)(mx.nufis / mx.fis / kprev + fpa_u01(&rng));
                        if (nn > NT_MAXSITES) nn = NT_MAXSITES;
                        for (int k = 0; k < nn; k++) {
                            nt_site *b = &bank[(size_t)i * NT_MAXSITES + (size_t)ns++];
                            b->x = x;
                            b->y = y;
                            b->z = z;
                            b->E = nt_maxwell(&rng, 1.2895e6);
                        }
                    }
                    break;
                }
                // Elastic scatter off one nuclide of the mixture.
                double pick = fpa_u01(&rng) * mx.sca;
                int c = 0;
                while (c < nt_mat_len[mat] - 1 && pick >= mx.sca_c[c]) {
                    pick -= mx.sca_c[c];
                    c++;
                }
                const double A = nuc[nt_mat_nuc[mat][c]].awr;
                if (E < 1.0 && A < 20.0) {                      // thermalised by light nuclei
                    E = nt_maxwell(&rng, 0.0253);
                    nt_isotropic(&rng, &u, &v, &w);
                } else {
                    const double mucm = 2.0 * fpa_u01(&rng) - 1.0;
                    const double s2 = A * A + 2.0 * A * mucm + 1.0;
                    E = E * s2 / ((A + 1.0) * (A + 1.0));
                    const double mu = (1.0 + A * mucm) / sqrt(s2);
                    double cphi, sphi;
                    nt_azimuth(&rng, &cphi, &sphi);
                    const double st = sqrt(1.0 - mu * mu);
                    if (fabs(w) < 0.9999) {
                        const double sw = sqrt(1.0 - w * w);
                        const double u2 = mu * u + st * (u * w * cphi - v * sphi) / sw;
                        const double v2 = mu * v + st * (v * w * cphi + u * sphi) / sw;
                        const double w2 = mu * w - st * sw * cphi;
                        u = u2;
                        v = v2;
                        w = w2;
                    } else {
                        u = st * cphi;
                        v = st * sphi;
                        w = mu * w;
                    }
                }
                if (E < 1e-5) E = 1e-5;
                if (E > 1.99e7) E = 1.99e7;
            }
            nsites[i] = ns;
        }
        const double kgen = (kcol + kabs + ktl) / (3.0 * N);
        if (batch >= ninactive) {
            ksum += kgen;
            nactive++;
        }
        kprev = kgen < 0.3 ? 0.3 : (kgen > 3.0 ? 3.0 : kgen);
        // Next generation: the banked sites in history order, resampled to N.
        size_t nb = 0;
        for (int i = 0; i < N; i++)
            for (int k = 0; k < nsites[i]; k++) bank[nb++] = bank[(size_t)i * NT_MAXSITES + (size_t)k];
        if (nb == 0) break;
        fpa_seed(&rng, 0xBA7C4000ull + (uint64_t)batch);
        const double xi0 = fpa_u01(&rng);
        for (int i = 0; i < N; i++) {
            size_t j = (size_t)(((double)i + xi0) * (double)nb / N);
            if (j >= nb) j = nb - 1;
            src[i] = bank[j];
        }
    }
    free(store); free(src); free(bank); free(nsites);
    if (nactive == 0) return 2;
    out->checksum = 0;
    out->value = ksum / nactive;
    out->work = (double)N * nbatch;
    out->unit = "histories";
    return 0;
}
