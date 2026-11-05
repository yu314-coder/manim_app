//
//  cb_bench_fp_c.c — three more floating-point workloads of `spec`, each
//  standing for one program that used to share a stand-in with another:
//  an ocean model (roms), a large-eddy simulation (palm) and an
//  atmosphere model's physics and dynamics (cam4).
//
//  Like the rest of the suite these are the KINDS of program SPEC CPU's
//  floating-point suites hold, written from scratch for CodeBench; no SPEC
//  (or other benchmark) source is used. What sets each apart from the
//  shallow-water and Riemann-solver workloads is how it touches memory:
//  roms streams some twenty three-dimensional fields through short loops
//  and solves every water column implicitly, as ROMS does, so it is bound
//  by memory bandwidth; palm spends its time in fifth-order advection and
//  an FFT pressure solver whose second transform walks the grid across
//  its rows; cam4 is dominated by column physics — saturation, convection,
//  radiation — full of exponentials and branches, over a grid that fits in
//  the larger caches.
//
//  The rules every workload keeps (see cb_bench.h): plain C17, reentrant
//  (all mutable state on the heap or the stack of the call), deterministic
//  (fixed seeds, this file's own exp/log/sin/cos, contraction off), under
//  256 KB of stack, everything freed before it returns.
//

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cb_bench.h"

#pragma STDC FP_CONTRACT OFF

// ── Shared helpers ──────────────────────────────────────────────────────

/// Doubles of padding between the arrays carved from one block, so that
/// power-of-two grids do not all map to the same cache sets.
#define FC_PAD 72

static int fc_level(int size) { return size <= 1 ? 1 : (size >= 3 ? 3 : 2); }

/// splitmix64, for seeding and for the few random numbers the set-ups use.
static uint64_t fc_next(uint64_t *x) {
    uint64_t z = (*x += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

static double fc_u01(uint64_t *x) { return (double)(fc_next(x) >> 11) * 0x1.0p-53; }

static const double FC_PI = 3.14159265358979323846;
static const double FC_LN2_HI = 6.93147180369123816490e-01;
static const double FC_LN2_LO = 1.90821492927058770002e-10;
static const double FC_PIO2_HI = 1.57079632673412561417e+00;
static const double FC_PIO2_LO = 6.07710050650619224932e-11;

/// e^x from + − × ÷ only, the same bits on every IEEE-754 machine.
static double fc_exp(double x) {
    if (x > 700.0) x = 700.0;
    if (x < -700.0) x = -700.0;
    const double kd = floor(x * 1.44269504088896340736 + 0.5);
    const double r = (x - kd * FC_LN2_HI) - kd * FC_LN2_LO;
    static const double c[14] = {
        1.0, 1.0, 1.0 / 2.0, 1.0 / 6.0, 1.0 / 24.0, 1.0 / 120.0, 1.0 / 720.0,
        1.0 / 5040.0, 1.0 / 40320.0, 1.0 / 362880.0, 1.0 / 3628800.0,
        1.0 / 39916800.0, 1.0 / 479001600.0, 1.0 / 6227020800.0};
    double p = c[13];
    for (int k = 12; k >= 0; k--) p = p * r + c[k];
    return ldexp(p, (int)kd);
}

/// ln x for x > 0, by frexp and the atanh series.
static double fc_log(double x) {
    int e;
    double m = frexp(x, &e);
    if (m < 0.70710678118654752440) { m *= 2.0; e -= 1; }
    const double s = (m - 1.0) / (m + 1.0), s2 = s * s;
    static const double c[13] = {
        1.0, 1.0 / 3.0, 1.0 / 5.0, 1.0 / 7.0, 1.0 / 9.0, 1.0 / 11.0, 1.0 / 13.0,
        1.0 / 15.0, 1.0 / 17.0, 1.0 / 19.0, 1.0 / 21.0, 1.0 / 23.0, 1.0 / 25.0};
    double p = c[12];
    for (int k = 11; k >= 0; k--) p = p * s2 + c[k];
    const double ed = (double)e;
    return ed * FC_LN2_HI + (2.0 * s * p + ed * FC_LN2_LO);
}

static void fc_sincos(double x, double *sn, double *cs) {
    const double kd = floor(x * 0.63661977236758134308 + 0.5);
    const double r = (x - kd * FC_PIO2_HI) - kd * FC_PIO2_LO;
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
    for (int k = 7; k >= 0; k--) { ps = ps * r2 + sc[k]; pc = pc * r2 + cc[k]; }
    const double s = r * ps, c = pc;
    switch ((int)((long long)kd & 3)) {
        case 0: *sn = s; *cs = c; break;
        case 1: *sn = c; *cs = -s; break;
        case 2: *sn = -s; *cs = -c; break;
        default: *sn = -c; *cs = s; break;
    }
}

/// Carves arrays of `n` doubles out of one block, FC_PAD apart.
typedef struct { double *p; } fc_arena;
static double *fc_take(fc_arena *a, size_t n) { double *r = a->p; a->p += n + FC_PAD; return r; }

/// Thomas algorithm for many independent tridiagonal systems at once, one
/// per element of a row of `w` values, over `n` levels: level k of system
/// i is a[k]·x[k−1] + b[k]·x[k] + c[k]·x[k+1] = d[k], with the
/// coefficients and right-hand sides stored level by level `stride` apart
/// (so the inner loop runs along the row, as ROMS and CAM vectorise their
/// column solves). `cp` is scratch of n·w. The answer replaces d.
static void fc_thomas_rows(int n, int w, ptrdiff_t stride, const double *a, const double *b,
                           const double *c, double *d, double *cp) {
    for (int i = 0; i < w; i++) {
        const double m = 1.0 / b[i];
        cp[i] = c[i] * m;
        d[i] *= m;
    }
    for (int k = 1; k < n; k++) {
        const double *ak = a + k * stride, *bk = b + k * stride, *ck = c + k * stride;
        double *dk = d + k * stride, *dp = d + (k - 1) * stride, *cpk = cp + (size_t)k * w;
        const double *cpp = cp + (size_t)(k - 1) * w;
        for (int i = 0; i < w; i++) {
            const double m = 1.0 / (bk[i] - ak[i] * cpp[i]);
            cpk[i] = ck[i] * m;
            dk[i] = (dk[i] - ak[i] * dp[i]) * m;
        }
    }
    for (int k = n - 2; k >= 0; k--) {
        double *dk = d + k * stride;
        const double *dn = d + (k + 1) * stride, *cpk = cp + (size_t)k * w;
        for (int i = 0; i < w; i++) dk[i] -= cpk[i] * dn[i];
    }
}

/// In-place iterative radix-2 complex FFT of length n (a power of two) on
/// separate real and imaginary arrays; `tw` holds cos and sin of 2πk/n for
/// k < n/2, interleaved. `inverse` conjugates the twiddles (no scaling).
static void fc_fft(int n, double *re, double *im, const double *tw, int inverse) {
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) {
            double t = re[i]; re[i] = re[j]; re[j] = t;
            t = im[i]; im[i] = im[j]; im[j] = t;
        }
    }
    const double sg = inverse ? 1.0 : -1.0;
    for (int len = 2; len <= n; len <<= 1) {
        const int half = len >> 1, step = n / len;
        for (int s = 0; s < n; s += len)
            for (int k = 0; k < half; k++) {
                const double wr = tw[2 * (k * step)], wi = sg * tw[2 * (k * step) + 1];
                const int a = s + k, b = a + half;
                const double xr = re[b] * wr - im[b] * wi, xi = re[b] * wi + im[b] * wr;
                re[b] = re[a] - xr; im[b] = im[a] - xi;
                re[a] += xr; im[a] += xi;
            }
    }
}

static void fc_twiddles(int n, double *tw) {
    for (int k = 0; k < n / 2; k++) fc_sincos(2.0 * FC_PI * k / n, &tw[2 * k + 1], &tw[2 * k]);
}

// ── roms: a split-explicit, terrain-following ocean model ───────────────

typedef struct {
    int nx, ny, nz;
    size_t n2, n3;
    double dx, dt, g, rho0;
    // 2-D
    double *h, *f, *zeta, *ubar, *vbar, *Du, *Dv, *rub, *rvb, *zs, *us, *vs, *ua, *va;
    // 3-D, [k][j][i]
    double *u, *v, *T, *S, *rho, *Hz, *zr, *W, *ru, *rv, *Akv, *Akt, *FX, *FY, *p, *un, *vn;
    // tridiagonal scratch, [k][i] for one row j at a time
    double *ta, *tb, *tc, *td, *tcp;
} rm_ctx;

#define RM(c, k, j, i) ((size_t)(k) * (c)->n2 + (size_t)(j) * (c)->nx + (size_t)(i))

/// Density anomaly from temperature, salinity and depth: a rational
/// polynomial fit of seawater's equation of state, the shape of the
/// Jackett–McDougall form ROMS uses (secant bulk modulus in the
/// denominator).
static inline double rm_eos(double T, double S, double z) {
    const double sq = sqrt(S > 0 ? S : 0);
    const double r0 = 999.842594 + T * (6.793952e-2 + T * (-9.095290e-3 + T * (1.001685e-4 + T * (-1.120083e-6 + T * 6.536332e-9))))
                    + S * (0.824493 + T * (-4.0899e-3 + T * (7.6438e-5 + T * (-8.2467e-7 + T * 5.3875e-9))))
                    + S * sq * (-5.72466e-3 + T * (1.0227e-4 - T * 1.6546e-6)) + S * S * 4.8314e-4;
    const double pb = -z * 0.1;    // bars, roughly
    const double K = 19652.21 + T * (148.4206 + T * (-2.327105 + T * (1.360477e-2 - T * 5.155288e-5)))
                   + S * (54.6746 + T * (-0.603459 + T * (1.09987e-2 - T * 6.1670e-5))) + S * sq * (7.944e-2 + T * (1.6483e-2 - T * 5.3009e-4))
                   + pb * (3.239908 + T * (1.43713e-3 + T * (1.16092e-4 - T * 5.77905e-7)));
    return r0 / (1.0 - pb / K) - 1000.0;
}

/// Third-order upstream face value, as ROMS's "U3H" advection.
static inline double rm_up3(double vel, double qm2, double qm1, double q0, double qp1) {
    const double cen = 0.5 * (q0 + qm1) - (1.0 / 12.0) * ((qp1 - q0) - (qm1 - qm2));
    const double up = (1.0 / 12.0) * ((qp1 - q0) - 2.0 * (q0 - qm1) + (qm1 - qm2));
    return vel * cen + fabs(vel) * up * 0.5;
}

static void rm_step(rm_ctx *c, int nfast) {
    const int nx = c->nx, ny = c->ny, nz = c->nz;
    const size_t n2 = c->n2;
    const double dx = c->dx, idx = 1.0 / dx, dt = c->dt, g = c->g, rho0 = c->rho0;
#define IM(i) ((i) == 0 ? nx - 1 : (i) - 1)
#define IP(i) ((i) == nx - 1 ? 0 : (i) + 1)
    // 1. Equation of state, one pass over the volume.
    for (size_t q = 0; q < c->n3; q++) c->rho[q] = rm_eos(c->T[q], c->S[q], c->zr[q]);

    // 2. Hydrostatic pressure, integrated down each column from the surface.
    for (size_t q = 0; q < n2; q++) c->p[(size_t)(nz - 1) * n2 + q] = 0.5 * g * c->rho[(size_t)(nz - 1) * n2 + q] * c->Hz[(size_t)(nz - 1) * n2 + q];
    for (int k = nz - 2; k >= 0; k--) {
        const double *rk = c->rho + (size_t)k * n2, *ra = c->rho + (size_t)(k + 1) * n2;
        const double *hk = c->Hz + (size_t)k * n2, *ha = c->Hz + (size_t)(k + 1) * n2;
        double *pk = c->p + (size_t)k * n2;
        const double *pa = c->p + (size_t)(k + 1) * n2;
        for (size_t q = 0; q < n2; q++) pk[q] = pa[q] + 0.5 * g * (ra[q] * ha[q] + rk[q] * hk[q]);
    }

    // 3. Right-hand sides of the 3-D momentum: pressure gradient (along
    //    the σ surface, less the part that only measures their slope),
    //    Coriolis, upstream-biased advection, harmonic viscosity — separate
    //    passes.
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++) {
            const int jm = j == 0 ? ny - 1 : j - 1, jp = j == ny - 1 ? 0 : j + 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = RM(c, k, j, i);
                const double Hu = 0.5 * (c->Hz[q] + c->Hz[RM(c, k, j, IM(i))]);
                const double Hv = 0.5 * (c->Hz[q] + c->Hz[RM(c, k, jm, i)]);
                const size_t qw = RM(c, k, j, IM(i)), qs = RM(c, k, jm, i);
                c->ru[q] = -Hu * ((c->p[q] - c->p[qw]) + g * 0.5 * (c->rho[q] + c->rho[qw]) * (c->zr[q] - c->zr[qw])) * idx / rho0;
                c->rv[q] = -Hv * ((c->p[q] - c->p[qs]) + g * 0.5 * (c->rho[q] + c->rho[qs]) * (c->zr[q] - c->zr[qs])) * idx / rho0;
                const double vav = 0.25 * (c->v[q] + c->v[RM(c, k, jp, i)] + c->v[RM(c, k, j, IM(i))] + c->v[RM(c, k, jp, IM(i))]);
                const double uav = 0.25 * (c->u[q] + c->u[RM(c, k, j, IP(i))] + c->u[RM(c, k, jm, i)] + c->u[RM(c, k, jm, IP(i))]);
                c->ru[q] += Hu * c->f[(size_t)j * nx + i] * vav;
                c->rv[q] -= Hv * c->f[(size_t)j * nx + i] * uav;
            }
        }
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++) {
            const int jm = j == 0 ? ny - 1 : j - 1, jp = j == ny - 1 ? 0 : j + 1;
            const int jm2 = jm == 0 ? ny - 1 : jm - 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = RM(c, k, j, i);
                const int im = IM(i), ip = IP(i), im2 = IM(im);
                const double uu = c->u[q];
                const double fe = rm_up3(0.5 * (uu + c->u[RM(c, k, j, ip)]), c->u[RM(c, k, j, im)], uu, c->u[RM(c, k, j, ip)], c->u[RM(c, k, j, IP(ip))]);
                const double fw = rm_up3(0.5 * (uu + c->u[RM(c, k, j, im)]), c->u[RM(c, k, j, im2)], c->u[RM(c, k, j, im)], uu, c->u[RM(c, k, j, ip)]);
                const double vn = 0.5 * (c->v[RM(c, k, jp, i)] + c->v[RM(c, k, jp, im)]);
                const double vsx = 0.5 * (c->v[q] + c->v[RM(c, k, j, im)]);
                const double fn = rm_up3(vn, c->u[RM(c, k, jm, i)], uu, c->u[RM(c, k, jp, i)], c->u[RM(c, k, jp == ny - 1 ? 0 : jp + 1, i)]);
                const double fs = rm_up3(vsx, c->u[RM(c, k, jm2, i)], c->u[RM(c, k, jm, i)], uu, c->u[RM(c, k, jp, i)]);
                const double lap = c->u[RM(c, k, j, ip)] + c->u[RM(c, k, j, im)] + c->u[RM(c, k, jp, i)] + c->u[RM(c, k, jm, i)] - 4.0 * uu;
                c->ru[q] += -c->Hz[q] * ((fe - fw) + (fn - fs)) * idx + c->Hz[q] * 2.0 * lap * idx * idx;
            }
        }
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++) {
            const int jm = j == 0 ? ny - 1 : j - 1, jp = j == ny - 1 ? 0 : j + 1;
            const int jm2 = jm == 0 ? ny - 1 : jm - 1, jp2 = jp == ny - 1 ? 0 : jp + 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = RM(c, k, j, i);
                const int im = IM(i), ip = IP(i);
                const double vv = c->v[q];
                const double ue = 0.5 * (c->u[RM(c, k, j, ip)] + c->u[RM(c, k, jm, ip)]);
                const double uw = 0.5 * (c->u[q] + c->u[RM(c, k, jm, i)]);
                const double fe = rm_up3(ue, c->v[RM(c, k, j, im)], vv, c->v[RM(c, k, j, ip)], c->v[RM(c, k, j, IP(ip))]);
                const double fw = rm_up3(uw, c->v[RM(c, k, j, IM(im))], c->v[RM(c, k, j, im)], vv, c->v[RM(c, k, j, ip)]);
                const double fn = rm_up3(0.5 * (vv + c->v[RM(c, k, jp, i)]), c->v[RM(c, k, jm, i)], vv, c->v[RM(c, k, jp, i)], c->v[RM(c, k, jp2, i)]);
                const double fs = rm_up3(0.5 * (vv + c->v[RM(c, k, jm, i)]), c->v[RM(c, k, jm2, i)], c->v[RM(c, k, jm, i)], vv, c->v[RM(c, k, jp, i)]);
                const double lap = c->v[RM(c, k, j, ip)] + c->v[RM(c, k, j, im)] + c->v[RM(c, k, jp, i)] + c->v[RM(c, k, jm, i)] - 4.0 * vv;
                c->rv[q] += -c->Hz[q] * ((fe - fw) + (fn - fs)) * idx + c->Hz[q] * 2.0 * lap * idx * idx;
            }
        }

    // 4. Vertical mixing coefficients (Pacanowski–Philander, from the
    //    gradient Richardson number) at the interfaces between levels.
    for (int k = 0; k < nz - 1; k++) {
        const double *Ta = c->rho + (size_t)(k + 1) * n2, *Tb = c->rho + (size_t)k * n2;
        const double *ua = c->u + (size_t)(k + 1) * n2, *ub = c->u + (size_t)k * n2;
        const double *va = c->v + (size_t)(k + 1) * n2, *vb = c->v + (size_t)k * n2;
        const double *za = c->zr + (size_t)(k + 1) * n2, *zb = c->zr + (size_t)k * n2;
        double *av = c->Akv + (size_t)k * n2, *at = c->Akt + (size_t)k * n2;
        for (size_t q = 0; q < n2; q++) {
            const double dz = za[q] - zb[q];
            const double N2 = -g / rho0 * (Ta[q] - Tb[q]) / dz;
            const double du = (ua[q] - ub[q]) / dz, dv = (va[q] - vb[q]) / dz;
            const double S2 = du * du + dv * dv + 1e-10;
            double Ri = N2 / S2;
            if (Ri < 0) Ri = 0;
            const double d = 1.0 + 5.0 * Ri;
            av[q] = 1e-2 / (d * d) + 1e-4;
            at[q] = av[q] / d + 1e-5;
        }
    }

    // 5. Explicit step of the 3-D momentum, then implicit vertical
    //    viscosity: a tridiagonal system in every column, solved a row at
    //    a time across the levels.
    for (size_t q = 0; q < c->n3; q++) {
        c->un[q] = c->u[q] + dt * c->ru[q] / c->Hz[q];
        c->vn[q] = c->v[q] + dt * c->rv[q] / c->Hz[q];
    }
    for (int pass = 0; pass < 2; pass++) {
        double *fld = pass ? c->vn : c->un;
        for (int j = 0; j < ny; j++) {
            for (int k = 0; k < nz; k++)
                for (int i = 0; i < nx; i++) {
                    const size_t q = RM(c, k, j, i), r = (size_t)k * nx + i;
                    const double up = k < nz - 1 ? c->Akv[q] / (c->zr[q + n2] - c->zr[q]) : 0.0;
                    const double dn = k > 0 ? c->Akv[q - n2] / (c->zr[q] - c->zr[q - n2]) : 0.0;
                    const double hz = c->Hz[q];
                    c->ta[r] = -dt * dn / hz;
                    c->tc[r] = -dt * up / hz;
                    c->tb[r] = 1.0 + dt * (up + dn) / hz + (k == 0 ? dt * 3e-3 : 0.0);  // bottom drag
                    c->td[r] = fld[q];
                }
            fc_thomas_rows(nz, nx, nx, c->ta, c->tb, c->tc, c->td, c->tcp);
            for (int k = 0; k < nz; k++)
                for (int i = 0; i < nx; i++) fld[RM(c, k, j, i)] = c->td[(size_t)k * nx + i];
        }
    }

    // 6. The barotropic mode: depth-integrated forcing, then many short
    //    forward–backward steps of the free surface and the depth-mean
    //    velocity, averaged for the coupling.
    memset(c->rub, 0, n2 * sizeof(double));
    memset(c->rvb, 0, n2 * sizeof(double));
    for (int k = 0; k < nz; k++)
        for (size_t q = 0; q < n2; q++) {
            c->rub[q] += c->ru[(size_t)k * n2 + q];
            c->rvb[q] += c->rv[(size_t)k * n2 + q];
        }
    for (int j = 0; j < ny; j++) {        // less the Coriolis force the fast mode applies itself
        const int jm = j == 0 ? ny - 1 : j - 1, jp = j == ny - 1 ? 0 : j + 1;
        for (int i = 0; i < nx; i++) {
            const size_t q = (size_t)j * nx + i;
            const double Du = 0.5 * (c->h[q] + c->h[(size_t)j * nx + IM(i)]), Dv = 0.5 * (c->h[q] + c->h[(size_t)jm * nx + i]);
            const double vav = 0.25 * (c->vbar[q] + c->vbar[(size_t)jp * nx + i] + c->vbar[(size_t)j * nx + IM(i)] + c->vbar[(size_t)jp * nx + IM(i)]);
            const double uav = 0.25 * (c->ubar[q] + c->ubar[(size_t)j * nx + IP(i)] + c->ubar[(size_t)jm * nx + i] + c->ubar[(size_t)jm * nx + IP(i)]);
            c->rub[q] -= Du * c->f[q] * vav;
            c->rvb[q] += Dv * c->f[q] * uav;
        }
    }
    memcpy(c->zs, c->zeta, n2 * sizeof(double));
    memcpy(c->us, c->ubar, n2 * sizeof(double));
    memcpy(c->vs, c->vbar, n2 * sizeof(double));
    memset(c->ua, 0, n2 * sizeof(double));
    memset(c->va, 0, n2 * sizeof(double));
    const double dtf = dt / nfast;
    for (int s = 0; s < nfast; s++) {
        for (int j = 0; j < ny; j++) {
            const int jp = j == ny - 1 ? 0 : j + 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = (size_t)j * nx + i;
                c->Du[q] = 0.5 * (c->h[q] + c->h[(size_t)j * nx + IM(i)] + c->zs[q] + c->zs[(size_t)j * nx + IM(i)]) * c->us[q];
                (void)jp;
            }
        }
        for (int j = 0; j < ny; j++) {
            const int jm = j == 0 ? ny - 1 : j - 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = (size_t)j * nx + i;
                c->Dv[q] = 0.5 * (c->h[q] + c->h[(size_t)jm * nx + i] + c->zs[q] + c->zs[(size_t)jm * nx + i]) * c->vs[q];
            }
        }
        for (int j = 0; j < ny; j++) {
            const int jp = j == ny - 1 ? 0 : j + 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = (size_t)j * nx + i;
                c->zs[q] -= dtf * ((c->Du[(size_t)j * nx + IP(i)] - c->Du[q]) + (c->Dv[(size_t)jp * nx + i] - c->Dv[q])) * idx;
            }
        }
        for (int j = 0; j < ny; j++) {
            const int jm = j == 0 ? ny - 1 : j - 1, jp = j == ny - 1 ? 0 : j + 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = (size_t)j * nx + i;
                const double Du = 0.5 * (c->h[q] + c->h[(size_t)j * nx + IM(i)]) + 0.5 * (c->zs[q] + c->zs[(size_t)j * nx + IM(i)]);
                const double Dv = 0.5 * (c->h[q] + c->h[(size_t)jm * nx + i]) + 0.5 * (c->zs[q] + c->zs[(size_t)jm * nx + i]);
                const double vav = 0.25 * (c->vs[q] + c->vs[(size_t)jp * nx + i] + c->vs[(size_t)j * nx + IM(i)] + c->vs[(size_t)jp * nx + IM(i)]);
                const double uav = 0.25 * (c->us[q] + c->us[(size_t)j * nx + IP(i)] + c->us[(size_t)jm * nx + i] + c->us[(size_t)jm * nx + IP(i)]);
                const double nu = c->us[q] + dtf * (-g * (c->zs[q] - c->zs[(size_t)j * nx + IM(i)]) * idx + c->f[q] * vav + c->rub[q] / Du);
                const double nv = c->vs[q] + dtf * (-g * (c->zs[q] - c->zs[(size_t)jm * nx + i]) * idx - c->f[q] * uav + c->rvb[q] / Dv);
                c->Du[q] = nu;   // reuse as the new values
                c->Dv[q] = nv;
            }
        }
        for (size_t q = 0; q < n2; q++) {
            c->us[q] = c->Du[q];
            c->vs[q] = c->Dv[q];
            c->ua[q] += c->us[q];
            c->va[q] += c->vs[q];
        }
    }
    // The fast mode carries on from where it ended; the 3-D mode is
    // coupled to its average over the step.
    memcpy(c->zeta, c->zs, n2 * sizeof(double));
    memcpy(c->ubar, c->us, n2 * sizeof(double));
    memcpy(c->vbar, c->vs, n2 * sizeof(double));
    for (size_t q = 0; q < n2; q++) {
        c->ua[q] /= nfast;
        c->va[q] /= nfast;
    }

    // 7. Couple the modes: replace each column's depth mean with the
    //    barotropic one.
    memset(c->rub, 0, n2 * sizeof(double));
    memset(c->rvb, 0, n2 * sizeof(double));
    memset(c->zs, 0, n2 * sizeof(double));
    for (int k = 0; k < nz; k++)
        for (size_t q = 0; q < n2; q++) {
            const size_t r = (size_t)k * n2 + q;
            c->rub[q] += c->un[r] * c->Hz[r];
            c->rvb[q] += c->vn[r] * c->Hz[r];
            c->zs[q] += c->Hz[r];
        }
    for (int k = 0; k < nz; k++)
        for (size_t q = 0; q < n2; q++) {
            const size_t r = (size_t)k * n2 + q;
            c->u[r] = c->un[r] - c->rub[q] / c->zs[q] + c->ua[q];
            c->v[r] = c->vn[r] - c->rvb[q] / c->zs[q] + c->va[q];
        }

    // 8. Vertical velocity from continuity, summed up each column.
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++) {
            const int jp = j == ny - 1 ? 0 : j + 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = RM(c, k, j, i);
                c->FX[q] = c->u[q] * 0.5 * (c->Hz[q] + c->Hz[RM(c, k, j, IM(i))]);
                c->FY[q] = c->v[q] * 0.5 * (c->Hz[q] + c->Hz[RM(c, k, j == 0 ? ny - 1 : j - 1, i)]);
                (void)jp;
            }
        }
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++) {
            const int jp = j == ny - 1 ? 0 : j + 1;
            for (int i = 0; i < nx; i++) {
                const size_t q = RM(c, k, j, i);
                const double div = ((c->FX[RM(c, k, j, IP(i))] - c->FX[q]) + (c->FY[RM(c, k, jp, i)] - c->FY[q])) * idx;
                c->W[q] = (k > 0 ? c->W[q - n2] : 0.0) - div;
            }
        }

    // 9. Tracers: upstream-biased horizontal and vertical advection, then
    //    implicit vertical diffusion, for temperature and salinity.
    for (int tr = 0; tr < 2; tr++) {
        double *Q = tr ? c->S : c->T, *Qn = c->un;
        for (int k = 0; k < nz; k++)
            for (int j = 0; j < ny; j++) {
                const int jm = j == 0 ? ny - 1 : j - 1, jp = j == ny - 1 ? 0 : j + 1;
                const int jm2 = jm == 0 ? ny - 1 : jm - 1, jp2 = jp == ny - 1 ? 0 : jp + 1;
                for (int i = 0; i < nx; i++) {
                    const size_t q = RM(c, k, j, i);
                    const int im = IM(i), ip = IP(i);
                    const double fw = rm_up3(c->FX[q], Q[RM(c, k, j, IM(im))], Q[RM(c, k, j, im)], Q[q], Q[RM(c, k, j, ip)]);
                    const double fe = rm_up3(c->FX[RM(c, k, j, ip)], Q[RM(c, k, j, im)], Q[q], Q[RM(c, k, j, ip)], Q[RM(c, k, j, IP(ip))]);
                    const double fs = rm_up3(c->FY[q], Q[RM(c, k, jm2, i)], Q[RM(c, k, jm, i)], Q[q], Q[RM(c, k, jp, i)]);
                    const double fn = rm_up3(c->FY[RM(c, k, jp, i)], Q[RM(c, k, jm, i)], Q[q], Q[RM(c, k, jp, i)], Q[RM(c, k, jp2, i)]);
                    const double wb = k > 0 ? c->W[q - n2] * (c->W[q - n2] > 0 ? Q[q - n2] : Q[q]) : 0.0;
                    const double wt = k < nz - 1 ? c->W[q] * (c->W[q] > 0 ? Q[q] : Q[q + n2]) : 0.0;
                    Qn[q] = Q[q] - dt * (((fe - fw) + (fn - fs)) * idx + (wt - wb)) / c->Hz[q];
                }
            }
        for (int j = 0; j < ny; j++) {
            for (int k = 0; k < nz; k++)
                for (int i = 0; i < nx; i++) {
                    const size_t q = RM(c, k, j, i), r = (size_t)k * nx + i;
                    const double up = k < nz - 1 ? c->Akt[q] / (c->zr[q + n2] - c->zr[q]) : 0.0;
                    const double dn = k > 0 ? c->Akt[q - n2] / (c->zr[q] - c->zr[q - n2]) : 0.0;
                    const double hz = c->Hz[q];
                    c->ta[r] = -dt * dn / hz;
                    c->tc[r] = -dt * up / hz;
                    c->tb[r] = 1.0 + dt * (up + dn) / hz;
                    c->td[r] = Qn[q] + (tr == 0 && k == nz - 1 ? dt * 2e-6 * (c->zr[q] < -1 ? 1.0 : 0.5) : 0.0);
                }
            fc_thomas_rows(nz, nx, nx, c->ta, c->tb, c->tc, c->td, c->tcp);
            for (int k = 0; k < nz; k++)
                for (int i = 0; i < nx; i++) Q[RM(c, k, j, i)] = c->td[(size_t)k * nx + i];
        }
    }
#undef IM
#undef IP
}

/// roms — a regional ocean model of the ROMS kind: hydrostatic primitive
/// equations on a terrain-following grid over a seamount in a doubly
/// periodic basin, stratified in temperature and salinity, with a
/// nonlinear equation of state, a split-explicit time step (a 3-D
/// baroclinic step around many short barotropic steps of the free surface,
/// averaged for the coupling), third-order upstream advection of momentum
/// and tracers, Richardson-number vertical mixing and implicit vertical
/// viscosity and diffusion (a tridiagonal solve in every water column).
/// Some twenty 3-D fields pass through short loops each step, so the
/// program streams memory the way ROMS does. `size` 1: 96×96×16 points for
/// 20 steps; 2: 160×160×24 for 28; 3: 256×256×32 for 30. `value` digests
/// the kinetic energy, the free surface and the tracer anomalies; work is
/// grid-point updates.
int cbk_roms(int size, cb_bench_result *out) {
    static const int cfg[3][4] = {{96, 96, 16, 20}, {160, 160, 24, 28}, {256, 256, 32, 30}};
    const int lv = fc_level(size) - 1;
    rm_ctx c;
    memset(&c, 0, sizeof c);
    c.nx = cfg[lv][0]; c.ny = cfg[lv][1]; c.nz = cfg[lv][2];
    const int steps = cfg[lv][3], nfast = 30;
    c.n2 = (size_t)c.nx * c.ny; c.n3 = c.n2 * c.nz;
    c.dx = 4000.0; c.g = 9.81; c.rho0 = 1025.0; c.dt = 240.0;
    const size_t total = 14 * c.n2 + 17 * c.n3 + 5 * (size_t)c.nz * c.nx + 40 * FC_PAD;
    double *mem = (double *)calloc(total, sizeof(double));
    if (!mem) return 1;
    fc_arena a = {mem};
    c.h = fc_take(&a, c.n2); c.f = fc_take(&a, c.n2); c.zeta = fc_take(&a, c.n2);
    c.ubar = fc_take(&a, c.n2); c.vbar = fc_take(&a, c.n2); c.Du = fc_take(&a, c.n2);
    c.Dv = fc_take(&a, c.n2); c.rub = fc_take(&a, c.n2); c.rvb = fc_take(&a, c.n2);
    c.zs = fc_take(&a, c.n2); c.us = fc_take(&a, c.n2); c.vs = fc_take(&a, c.n2);
    c.ua = fc_take(&a, c.n2); c.va = fc_take(&a, c.n2);
    c.u = fc_take(&a, c.n3); c.v = fc_take(&a, c.n3); c.T = fc_take(&a, c.n3); c.S = fc_take(&a, c.n3);
    c.rho = fc_take(&a, c.n3); c.Hz = fc_take(&a, c.n3); c.zr = fc_take(&a, c.n3); c.W = fc_take(&a, c.n3);
    c.ru = fc_take(&a, c.n3); c.rv = fc_take(&a, c.n3); c.Akv = fc_take(&a, c.n3); c.Akt = fc_take(&a, c.n3);
    c.FX = fc_take(&a, c.n3); c.FY = fc_take(&a, c.n3); c.p = fc_take(&a, c.n3); c.un = fc_take(&a, c.n3);
    c.vn = fc_take(&a, c.n3);
    const size_t row = (size_t)c.nz * c.nx;
    c.ta = fc_take(&a, row); c.tb = fc_take(&a, row); c.tc = fc_take(&a, row); c.td = fc_take(&a, row);
    c.tcp = fc_take(&a, row);

    // A 4000 m basin with a Gaussian seamount rising to 500 m, β-plane
    // Coriolis, stratification decaying with depth, a weak eastward flow.
    const double L = c.dx * c.nx;
    for (int j = 0; j < c.ny; j++)
        for (int i = 0; i < c.nx; i++) {
            const double x = (i + 0.5) * c.dx - 0.5 * L, y = (j + 0.5) * c.dx - 0.5 * L;
            const double r2 = (x * x + y * y) / (0.08 * L * L);
            const size_t q = (size_t)j * c.nx + i;
            c.h[q] = 4000.0 - 3500.0 * fc_exp(-r2);
            c.f[q] = 1e-4 + 2e-11 * y;
        }
    for (int k = 0; k < c.nz; k++)
        for (size_t q = 0; q < c.n2; q++) {
            const double s = (k + 0.5) / c.nz - 1.0;          // σ in (−1, 0)
            const double z = s * c.h[q];
            const size_t r = (size_t)k * c.n2 + q;
            c.zr[r] = z;
            c.Hz[r] = c.h[q] / c.nz;
            c.T[r] = 4.0 + 16.0 * fc_exp(z / 600.0);
            c.S[r] = 34.5 + 0.6 * fc_exp(z / 900.0);
            c.u[r] = 0.08 * fc_exp(z / 1500.0);
        }
    uint64_t seed = 0x0C3A5EA000000001ull;
    for (size_t q = 0; q < c.n3; q++) c.T[q] += 0.02 * (fc_u01(&seed) - 0.5);

    for (int s = 0; s < steps; s++) {
        rm_step(&c, nfast);
    }

    double ke = 0, z2 = 0, tv = 0;
    for (size_t q = 0; q < c.n3; q++) {
        ke += 0.5 * (c.u[q] * c.u[q] + c.v[q] * c.v[q]) * c.Hz[q];
        tv += (c.T[q] - 4.0) * (c.S[q] - 34.0) * 1e-3;
    }
    for (size_t q = 0; q < c.n2; q++) z2 += c.zeta[q] * c.zeta[q];
    out->value = ke / (double)c.n2 + z2 / (double)c.n2 + tv / (double)c.n3;
    out->work = (double)c.n3 * steps;
    out->unit = "point updates";
    free(mem);
    return isfinite(out->value) ? 0 : 2;
}

// ── palm: large-eddy simulation of a convective boundary layer ─────────

typedef struct {
    int nx, ny, nz;
    size_t n;
    double dx, dz, dt, nu;
    double *u, *v, *w, *pt;          // staggered C grid, [k][j][i]
    double *tu, *tv, *tw, *tpt;      // low-storage RK tendencies
    double *fu, *fv, *fw, *fpt;      // this stage's tendencies
    double *pre, *pim;               // pressure transform
    double *line_re, *line_im;       // one transposed line
    double *twx, *twy;
    double *lamx, *lamy;
    double *ta, *tb, *tc, *td, *tcp; // z tridiagonals, one ky row of kx systems
    int *xo, *yo;                    // periodic neighbour tables
} pm_ctx;

#define PM(c, k, j, i) ((size_t)(k) * (size_t)(c)->ny * (c)->nx + (size_t)(j) * (c)->nx + (size_t)(i))

/// Fifth-order upwind-biased flux (Wicker–Skamarock), as PALM's default
/// momentum and scalar advection: the face value from six neighbours,
/// times the advecting velocity.
static inline double pm_ws5(double vel, double qm2, double qm1, double q0, double qp1, double qp2, double qp3) {
    const double cen = (37.0 * (q0 + qp1) - 8.0 * (qm1 + qp2) + (qm2 + qp3)) * (1.0 / 60.0);
    const double up = (10.0 * (qp1 - q0) - 5.0 * (qp2 - qm1) + (qp3 - qm2)) * (1.0 / 60.0);
    return vel * cen - fabs(vel) * up;
}

/// Advection and diffusion of one staggered field `q`: fifth-order fluxes
/// in x and y (periodic) and in z away from the walls (second order next
/// to them), each carried by the velocity at that face of q's own control
/// volume. `kind` says where q lives: 0 the cell centre (potential
/// temperature), 1 the west face (u), 2 the south face (v), 3 the top face
/// (w), so the advecting velocities are interpolated to q's faces, not the
/// cell's.
static void pm_advect(pm_ctx *c, const double *q, double *tend, int kind) {
    const int nx = c->nx, ny = c->ny, nz = c->nz;
    const size_t P = (size_t)nx * ny;
    const double idx = 1.0 / c->dx, idz = 1.0 / c->dz, nu = c->nu;
    const int *xo = c->xo, *yo = c->yo;     // neighbour i−3 … i+3, seven per point
    const double *U = c->u, *V = c->v, *W = c->w;
    const int top = kind == 3 ? nz - 1 : nz;        // w's last level is the lid
    for (int k = 0; k < top; k++)
        for (int j = 0; j < ny; j++) {
            const int *jj = yo + 7 * j + 1;              // jj[0] = j−2 … jj[5] = j+3
            const int jm = jj[1], jp = jj[3];
            for (int i = 0; i < nx; i++) {
                const int *ii = xo + 7 * i + 1;
                const int im = ii[1], ip = ii[3];
                const size_t s = PM(c, k, j, i);
                double ue, uw, vn, vs, wt, wb;
                switch (kind) {
                default:   // cell centre
                    ue = U[PM(c, k, j, ip)]; uw = U[s];
                    vn = V[PM(c, k, jp, i)]; vs = V[s];
                    wt = k + 1 < nz ? W[s] : 0.0; wb = k > 0 ? W[s - P] : 0.0;
                    break;
                case 1:    // u, at (i−½, j, k)
                    ue = 0.5 * (U[s] + U[PM(c, k, j, ip)]); uw = 0.5 * (U[PM(c, k, j, im)] + U[s]);
                    vn = 0.5 * (V[PM(c, k, jp, im)] + V[PM(c, k, jp, i)]); vs = 0.5 * (V[PM(c, k, j, im)] + V[s]);
                    wt = k + 1 < nz ? 0.5 * (W[PM(c, k, j, im)] + W[s]) : 0.0;
                    wb = k > 0 ? 0.5 * (W[PM(c, k - 1, j, im)] + W[s - P]) : 0.0;
                    break;
                case 2:    // v, at (i, j−½, k)
                    ue = 0.5 * (U[PM(c, k, jm, ip)] + U[PM(c, k, j, ip)]); uw = 0.5 * (U[PM(c, k, jm, i)] + U[s]);
                    vn = 0.5 * (V[s] + V[PM(c, k, jp, i)]); vs = 0.5 * (V[PM(c, k, jm, i)] + V[s]);
                    wt = k + 1 < nz ? 0.5 * (W[PM(c, k, jm, i)] + W[s]) : 0.0;
                    wb = k > 0 ? 0.5 * (W[PM(c, k - 1, jm, i)] + W[s - P]) : 0.0;
                    break;
                case 3:    // w, at (i, j, k+½)
                    ue = 0.5 * (U[PM(c, k, j, ip)] + U[PM(c, k + 1, j, ip)]); uw = 0.5 * (U[s] + U[s + P]);
                    vn = 0.5 * (V[PM(c, k, jp, i)] + V[PM(c, k + 1, jp, i)]); vs = 0.5 * (V[s] + V[s + P]);
                    wt = 0.5 * (W[s] + (k + 1 < nz - 1 ? W[s + P] : 0.0)); wb = 0.5 * ((k > 0 ? W[s - P] : 0.0) + W[s]);
                    break;
                }
                const double fe = pm_ws5(ue, q[PM(c, k, j, ii[0])], q[PM(c, k, j, ii[1])], q[s], q[PM(c, k, j, ii[3])], q[PM(c, k, j, ii[4])], q[PM(c, k, j, ii[5])]);
                const double fw = pm_ws5(uw, q[PM(c, k, j, ii[-1])], q[PM(c, k, j, ii[0])], q[PM(c, k, j, ii[1])], q[s], q[PM(c, k, j, ii[3])], q[PM(c, k, j, ii[4])]);
                const double fn = pm_ws5(vn, q[PM(c, k, jj[0], i)], q[PM(c, k, jj[1], i)], q[s], q[PM(c, k, jj[3], i)], q[PM(c, k, jj[4], i)], q[PM(c, k, jj[5], i)]);
                const double fs = pm_ws5(vs, q[PM(c, k, jj[-1], i)], q[PM(c, k, jj[0], i)], q[PM(c, k, jj[1], i)], q[s], q[PM(c, k, jj[3], i)], q[PM(c, k, jj[4], i)]);
                double ft = 0.0, fb = 0.0;
                if (k + 1 < top) {
                    if (k >= 2 && k + 3 < top)
                        ft = pm_ws5(wt, q[s - 2 * P], q[s - P], q[s], q[s + P], q[s + 2 * P], q[s + 3 * P]);
                    else
                        ft = wt * 0.5 * (q[s] + q[s + P]);
                }
                if (k > 0) {
                    if (k >= 3 && k + 2 < top)
                        fb = pm_ws5(wb, q[s - 3 * P], q[s - 2 * P], q[s - P], q[s], q[s + P], q[s + 2 * P]);
                    else
                        fb = wb * 0.5 * (q[s - P] + q[s]);
                }
                const double qz1 = k + 1 < top ? q[s + P] : q[s];
                const double qz0 = k > 0 ? q[s - P] : q[s];
                const double lap = (q[PM(c, k, j, ip)] + q[PM(c, k, j, im)] + q[PM(c, k, jp, i)] + q[PM(c, k, jm, i)] - 4.0 * q[s]) * idx * idx
                                 + (qz1 + qz0 - 2.0 * q[s]) * idz * idz;
                tend[s] = -((fe - fw) + (fn - fs)) * idx - (ft - fb) * idz + nu * lap;
            }
        }
    if (kind == 3)
        for (size_t s = (size_t)(nz - 1) * P; s < (size_t)nz * P; s++) tend[s] = 0.0;
}

/// The pressure step: the divergence of the provisional velocity, 2-D FFTs
/// over x and y (the y transform gathers each column of every level into a
/// line, PALM's transposition), a tridiagonal solve in z for every
/// wavenumber pair, the inverse transforms, and the gradient correction.
static void pm_pressure(pm_ctx *c, double dtau) {
    const int nx = c->nx, ny = c->ny, nz = c->nz;
    const size_t plane = (size_t)nx * ny;
    const double idx = 1.0 / c->dx, idz = 1.0 / c->dz;
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++)
            for (int i = 0; i < nx; i++) {
                const size_t s = PM(c, k, j, i);
                const double wt = k + 1 < nz ? c->w[s] : 0.0, wb = k > 0 ? c->w[s - plane] : 0.0;
                c->pre[s] = (((c->u[PM(c, k, j, (i + 1) % nx)] - c->u[s]) + (c->v[PM(c, k, (j + 1) % ny, i)] - c->v[s])) * idx
                             + (wt - wb) * idz) / dtau;
                c->pim[s] = 0.0;
            }
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++) fc_fft(nx, c->pre + PM(c, k, j, 0), c->pim + PM(c, k, j, 0), c->twx, 0);
    for (int k = 0; k < nz; k++)
        for (int i = 0; i < nx; i++) {
            for (int j = 0; j < ny; j++) { c->line_re[j] = c->pre[PM(c, k, j, i)]; c->line_im[j] = c->pim[PM(c, k, j, i)]; }
            fc_fft(ny, c->line_re, c->line_im, c->twy, 0);
            for (int j = 0; j < ny; j++) { c->pre[PM(c, k, j, i)] = c->line_re[j]; c->pim[PM(c, k, j, i)] = c->line_im[j]; }
        }
    // For each ky row: nx systems in z (Neumann at top and bottom).
    for (int pass = 0; pass < 2; pass++) {
        double *F = pass ? c->pim : c->pre;
        for (int j = 0; j < ny; j++) {
            for (int k = 0; k < nz; k++)
                for (int i = 0; i < nx; i++) {
                    const size_t r = (size_t)k * nx + i;
                    const double lam = c->lamx[i] + c->lamy[j];
                    const double lo = k > 0 ? idz * idz : 0.0, hi = k + 1 < nz ? idz * idz : 0.0;
                    c->ta[r] = lo; c->tc[r] = hi;
                    c->tb[r] = -(lo + hi) + lam;
                    c->td[r] = F[PM(c, k, j, i)];
                    if (i == 0 && j == 0) {           // the mean pressure is free: pin it
                        if (k == 0) { c->tb[r] = 1.0; c->tc[r] = 0.0; c->td[r] = 0.0; }
                    }
                }
            fc_thomas_rows(nz, nx, nx, c->ta, c->tb, c->tc, c->td, c->tcp);
            for (int k = 0; k < nz; k++)
                for (int i = 0; i < nx; i++) F[PM(c, k, j, i)] = c->td[(size_t)k * nx + i];
        }
    }
    for (int k = 0; k < nz; k++)
        for (int i = 0; i < nx; i++) {
            for (int j = 0; j < ny; j++) { c->line_re[j] = c->pre[PM(c, k, j, i)]; c->line_im[j] = c->pim[PM(c, k, j, i)]; }
            fc_fft(ny, c->line_re, c->line_im, c->twy, 1);
            for (int j = 0; j < ny; j++) { c->pre[PM(c, k, j, i)] = c->line_re[j]; c->pim[PM(c, k, j, i)] = c->line_im[j]; }
        }
    const double scale = 1.0 / ((double)nx * ny);
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++) {
            fc_fft(nx, c->pre + PM(c, k, j, 0), c->pim + PM(c, k, j, 0), c->twx, 1);
            double *pr = c->pre + PM(c, k, j, 0);
            for (int i = 0; i < nx; i++) pr[i] *= scale;
        }
    for (int k = 0; k < nz; k++)
        for (int j = 0; j < ny; j++)
            for (int i = 0; i < nx; i++) {
                const size_t s = PM(c, k, j, i);
                c->u[s] -= dtau * (c->pre[s] - c->pre[PM(c, k, j, (i + nx - 1) % nx)]) * idx;
                c->v[s] -= dtau * (c->pre[s] - c->pre[PM(c, k, (j + ny - 1) % ny, i)]) * idx;
                if (k + 1 < nz) c->w[s] -= dtau * (c->pre[s + plane] - c->pre[s]) * idz;
            }
}

/// palm — a large-eddy simulation of the PALM kind: the incompressible
/// Boussinesq equations for a dry convective boundary layer heated from
/// below, on a staggered grid periodic in x and y between rigid walls,
/// with PALM's fifth-order Wicker–Skamarock advection of momentum and
/// potential temperature, constant eddy diffusion, a three-stage
/// Runge–Kutta step, and after every stage a pressure solve by FFT in the
/// horizontal and a tridiagonal solve in the vertical. `size` 1: 64×64×32
/// for 8 steps; 2: 128×128×48 for 6; 3: 256×128×64 for 8. `value`
/// digests the resolved kinetic energy and the heat flux; work is
/// grid-point updates (three stages each).
int cbk_palm(int size, cb_bench_result *out) {
    static const int cfg[3][4] = {{64, 64, 32, 8}, {128, 128, 48, 6}, {256, 128, 64, 8}};
    const int lv = fc_level(size) - 1;
    pm_ctx c;
    memset(&c, 0, sizeof c);
    c.nx = cfg[lv][0]; c.ny = cfg[lv][1]; c.nz = cfg[lv][2];
    const int steps = cfg[lv][3];
    c.n = (size_t)c.nx * c.ny * c.nz;
    c.dx = 50.0; c.dz = 25.0; c.nu = 2.0; c.dt = 1.5;
    const size_t row = (size_t)c.nz * c.nx;
    const size_t total = 14 * c.n + 2 * (size_t)c.ny + (size_t)c.nx + (size_t)c.ny + (size_t)c.nx + (size_t)c.ny + 5 * row + 30 * FC_PAD;
    double *mem = (double *)calloc(total, sizeof(double));
    if (!mem) return 1;
    fc_arena a = {mem};
    c.u = fc_take(&a, c.n); c.v = fc_take(&a, c.n); c.w = fc_take(&a, c.n); c.pt = fc_take(&a, c.n);
    c.tu = fc_take(&a, c.n); c.tv = fc_take(&a, c.n); c.tw = fc_take(&a, c.n); c.tpt = fc_take(&a, c.n);
    c.fu = fc_take(&a, c.n); c.fv = fc_take(&a, c.n); c.fw = fc_take(&a, c.n); c.fpt = fc_take(&a, c.n);
    c.pre = fc_take(&a, c.n); c.pim = fc_take(&a, c.n);
    c.line_re = fc_take(&a, c.ny); c.line_im = fc_take(&a, c.ny);
    c.twx = fc_take(&a, c.nx); c.twy = fc_take(&a, c.ny);
    c.lamx = fc_take(&a, c.nx); c.lamy = fc_take(&a, c.ny);
    c.ta = fc_take(&a, row); c.tb = fc_take(&a, row); c.tc = fc_take(&a, row); c.td = fc_take(&a, row);
    c.tcp = fc_take(&a, row);
    c.xo = (int *)malloc(sizeof(int) * 7 * (size_t)(c.nx + c.ny));
    if (!c.xo) { free(mem); return 1; }
    c.yo = c.xo + 7 * c.nx;
    for (int i = 0; i < c.nx; i++) for (int d = 0; d < 7; d++) c.xo[7 * i + d] = (i + d - 3 + c.nx) % c.nx;
    for (int j = 0; j < c.ny; j++) for (int d = 0; d < 7; d++) c.yo[7 * j + d] = (j + d - 3 + c.ny) % c.ny;
    fc_twiddles(c.nx, c.twx);
    fc_twiddles(c.ny, c.twy);
    for (int i = 0; i < c.nx; i++) {
        double s, co;
        fc_sincos(2.0 * FC_PI * i / c.nx, &s, &co);
        c.lamx[i] = -(2.0 - 2.0 * co) / (c.dx * c.dx);
    }
    for (int j = 0; j < c.ny; j++) {
        double s, co;
        fc_sincos(2.0 * FC_PI * j / c.ny, &s, &co);
        c.lamy[j] = -(2.0 - 2.0 * co) / (c.dx * c.dx);
    }
    // A stably stratified layer over a heated surface, small random
    // temperature perturbations near the ground, a weak mean wind.
    uint64_t seed = 0x9A1B5EED00000002ull;
    for (int k = 0; k < c.nz; k++)
        for (size_t q = 0; q < (size_t)c.nx * c.ny; q++) {
            const size_t s = (size_t)k * c.nx * c.ny + q;
            const double z = (k + 0.5) * c.dz;
            c.pt[s] = 300.0 + (z > 600.0 ? 0.003 * (z - 600.0) : 0.0) + (k < 4 ? 0.4 * (fc_u01(&seed) - 0.5) : 0.0);
            c.u[s] = 1.0;
        }
    const double g_t0 = 9.81 / 300.0;
    // Low-storage RK3 (Williamson): q += β·(tend_acc = α·tend_acc + Δt·f).
    static const double ra[3] = {0.0, -5.0 / 9.0, -153.0 / 128.0};
    static const double rb[3] = {1.0 / 3.0, 15.0 / 16.0, 8.0 / 15.0};
    const size_t plane = (size_t)c.nx * c.ny;
    for (int s = 0; s < steps; s++)
        for (int st = 0; st < 3; st++) {
            pm_advect(&c, c.u, c.fu, 1);
            pm_advect(&c, c.v, c.fv, 2);
            pm_advect(&c, c.w, c.fw, 3);
            pm_advect(&c, c.pt, c.fpt, 0);
            // Buoyancy on w (at the faces between levels) and the surface heat flux.
            for (int k = 0; k + 1 < c.nz; k++)
                for (size_t q = 0; q < plane; q++) {
                    const size_t r = (size_t)k * plane + q;
                    c.fw[r] += g_t0 * (0.5 * (c.pt[r] + c.pt[r + plane]) - 300.0);
                }
            for (size_t q = 0; q < plane; q++) c.fpt[q] += 0.1 / c.dz;
            for (size_t q = 0; q < c.n; q++) {
                c.tu[q] = ra[st] * c.tu[q] + c.dt * c.fu[q];
                c.tv[q] = ra[st] * c.tv[q] + c.dt * c.fv[q];
                c.tw[q] = ra[st] * c.tw[q] + c.dt * c.fw[q];
                c.tpt[q] = ra[st] * c.tpt[q] + c.dt * c.fpt[q];
                c.u[q] += rb[st] * c.tu[q];
                c.v[q] += rb[st] * c.tv[q];
                c.w[q] += rb[st] * c.tw[q];
                c.pt[q] += rb[st] * c.tpt[q];
            }
            for (size_t q = 0; q < plane; q++) c.w[(size_t)(c.nz - 1) * plane + q] = 0.0;
            pm_pressure(&c, rb[st] * c.dt);
        }
    double ke = 0, hf = 0;
    for (size_t q = 0; q < c.n; q++) {
        ke += 0.5 * ((c.u[q] - 1.0) * (c.u[q] - 1.0) + c.v[q] * c.v[q] + c.w[q] * c.w[q]);
        hf += c.w[q] * (c.pt[q] - 300.0);
    }
    out->value = ke / (double)c.n + hf / (double)c.n;
    out->work = (double)c.n * steps * 3;
    out->unit = "point updates";
    free(c.xo);
    free(mem);
    return isfinite(out->value) ? 0 : 2;
}

// ── cam4: an atmosphere model's dynamics and column physics ─────────────

typedef struct {
    int nlon, nlat, nlev;
    size_t n2, n3;
    double dt, a, cp, Rd, Lv, g;
    double *T, *q, *u, *v, *ps;           // [k][j][i]; ps 2-D
    double *Tn, *qn, *un, *vn;            // after dynamics
    double *phi;                          // geopotential at full levels
    double *lat, *coslat, *sinlat;        // per latitude
    double *sig, *dsig, *dln;             // per level
    double *fre, *fim, *twl;              // polar-filter FFT line
    double *precip, *olr;                 // diagnostics, 2-D
    // per-column scratch
    double *ca, *cb, *cc, *cd, *ccp, *col;
} cm_ctx;

#define CM(c, k, j, i) ((size_t)(k) * (c)->n2 + (size_t)(j) * (c)->nlon + (size_t)(i))

/// Saturation specific humidity over water (Bolton's fit of the
/// Clausius–Clapeyron relation), from temperature in K and pressure in Pa.
static inline double cm_qsat(double T, double p) {
    const double es = 611.2 * fc_exp(17.67 * (T - 273.15) / (T - 29.65));
    const double d = p - 0.378 * es;
    return 0.622 * es / (d > es ? d : es);
}

/// Monotonized-central limited flux of `q` through the face between `q0`
/// and `qp1`, carried by `vel` (Courant number `cr`): the second-order
/// van Leer scheme the finite-volume core builds on.
static inline double cm_flux(double vel, double cr, double qm1, double q0, double qp1, double qp2) {
    if (vel >= 0) {
        const double dl = q0 - qm1, dr = qp1 - q0;
        double sl = 0.0;
        if (dl * dr > 0) {
            const double m = fmin(fabs(0.5 * (dl + dr)), 2.0 * fmin(fabs(dl), fabs(dr)));
            sl = dl > 0 ? m : -m;
        }
        return vel * (q0 + 0.5 * (1.0 - cr) * sl);
    } else {
        const double dl = qp1 - q0, dr = qp2 - qp1;
        double sl = 0.0;
        if (dl * dr > 0) {
            const double m = fmin(fabs(0.5 * (dl + dr)), 2.0 * fmin(fabs(dl), fabs(dr)));
            sl = dl > 0 ? m : -m;
        }
        return vel * (qp1 - 0.5 * (1.0 + cr) * sl);
    }
}

static void cm_geopotential(cm_ctx *c, const double *T, const double *q) {
    const size_t n2 = c->n2;
    for (size_t r2 = 0; r2 < n2; r2++) {
        double ph = 0.0;
        for (int k = c->nlev - 1; k >= 0; k--) {
            const size_t r = (size_t)k * n2 + r2;
            ph += c->Rd * T[r] * (1.0 + 0.608 * q[r]) * c->dln[k];
            c->phi[r] = ph;
        }
    }
}

/// Advection tendency of field F at (k, j, i) by the face winds, from
/// limited fluxes.
static inline double cm_adv(const cm_ctx *c, const double *F, int k, int j, int i, double ue, double uw,
                            double vn, double vsx, double crx, double cry, double rdx, double rdy) {
    const int nlon = c->nlon, nlat = c->nlat;
    const int im = i ? i - 1 : nlon - 1, ip = i + 1 < nlon ? i + 1 : 0;
    const int im2 = im ? im - 1 : nlon - 1, ip2 = ip + 1 < nlon ? ip + 1 : 0;
    const int jn = j + 1 < nlat ? j + 1 : j, js = j > 0 ? j - 1 : j;
    const int jn2 = jn + 1 < nlat ? jn + 1 : jn, js2 = js > 0 ? js - 1 : js;
    const size_t r = CM(c, k, j, i);
    const double cl = c->coslat[j];
    const double fe = cm_flux(ue, fabs(ue) * crx, F[CM(c, k, j, im)], F[r], F[CM(c, k, j, ip)], F[CM(c, k, j, ip2)]);
    const double fw = cm_flux(uw, fabs(uw) * crx, F[CM(c, k, j, im2)], F[CM(c, k, j, im)], F[r], F[CM(c, k, j, ip)]);
    const double fn = j + 1 < nlat ? cm_flux(vn, fabs(vn) * cry, F[CM(c, k, js, i)], F[r], F[CM(c, k, jn, i)], F[CM(c, k, jn2, i)]) : 0.0;
    const double fs = j > 0 ? cm_flux(vsx, fabs(vsx) * cry, F[CM(c, k, js2, i)], F[CM(c, k, js, i)], F[r], F[CM(c, k, jn, i)]) : 0.0;
    const double cn = j + 1 < nlat ? 0.5 * (cl + c->coslat[jn]) : 0.0, cs = j > 0 ? 0.5 * (cl + c->coslat[js]) : 0.0;
    // Flux form less F times the divergence of the face winds: the
    // advective form, as for a quantity carried by the air rather than a
    // density of it.
    const double div = (ue - uw) * rdx + (vn * cn - vsx * cs) * rdy / cl;
    return -(fe - fw) * rdx - (fn * cn - fs * cs) * rdy / cl + F[r] * div;
}

/// Dynamics, forward–backward: temperature and humidity advected by the
/// old winds, the hydrostatic geopotential of the new temperatures, then
/// the winds advected and pushed by its gradient, with the Coriolis force
/// applied as an exact-energy (Crank–Nicolson) rotation; and the polar
/// filter (an FFT round each latitude circle poleward of 45°, damping the
/// zonal waves the grid's converging meridians cannot carry stably).
static void cm_dynamics(cm_ctx *c) {
    const int nlon = c->nlon, nlat = c->nlat, nlev = c->nlev;
    const double dlon = 2.0 * FC_PI / nlon, dlat = FC_PI / nlat, dt = c->dt, a = c->a;
    for (int pass = 0; pass < 2; pass++) {
        if (pass == 1) cm_geopotential(c, c->Tn, c->qn);
        for (int k = 0; k < nlev; k++)
            for (int j = 0; j < nlat; j++) {
                const double cl = c->coslat[j], f = 2.0 * 7.292e-5 * c->sinlat[j];
                const double rdx = 1.0 / (a * cl * dlon), rdy = 1.0 / (a * dlat);
                const int jn = j + 1 < nlat ? j + 1 : j, js = j > 0 ? j - 1 : j;
                for (int i = 0; i < nlon; i++) {
                    const int im = i ? i - 1 : nlon - 1, ip = i + 1 < nlon ? i + 1 : 0;
                    const size_t r = CM(c, k, j, i);
                    const double uu = c->u[r], vv = c->v[r];
                    const double ue = 0.5 * (uu + c->u[CM(c, k, j, ip)]), uw = 0.5 * (uu + c->u[CM(c, k, j, im)]);
                    const double vn = 0.5 * (vv + c->v[CM(c, k, jn, i)]), vsx = 0.5 * (vv + c->v[CM(c, k, js, i)]);
                    const double crx = dt * rdx, cry = dt * rdy;
                    if (pass == 0) {
                        c->Tn[r] = c->T[r] + dt * cm_adv(c, c->T, k, j, i, ue, uw, vn, vsx, crx, cry, rdx, rdy);
                        c->qn[r] = c->q[r] + dt * cm_adv(c, c->q, k, j, i, ue, uw, vn, vsx, crx, cry, rdx, rdy);
                        continue;
                    }
                    const double dphx = (c->phi[CM(c, k, j, ip)] - c->phi[CM(c, k, j, im)]) * 0.5 * rdx;
                    const double dphy = (c->phi[CM(c, k, jn, i)] - c->phi[CM(c, k, js, i)]) * 0.5 * rdy;
                    double un = uu + dt * (cm_adv(c, c->u, k, j, i, ue, uw, vn, vsx, crx, cry, rdx, rdy) - 0.02 * dphx - 1e-5 * uu);
                    double vn2 = vv + dt * (cm_adv(c, c->v, k, j, i, ue, uw, vn, vsx, crx, cry, rdx, rdy) - 0.02 * dphy - 1e-5 * vv);
                    const double fa = 0.5 * dt * (f + uu * c->sinlat[j] / (a * cl));
                    const double den = 1.0 / (1.0 + fa * fa);
                    c->un[r] = ((1.0 - fa * fa) * un + 2.0 * fa * vn2) * den;
                    c->vn[r] = ((1.0 - fa * fa) * vn2 - 2.0 * fa * un) * den;
                }
            }
    }
    // Polar filter on the new fields.
    for (int j = 0; j < nlat; j++) {
        const double cl = c->coslat[j];
        if (cl > 0.7071) continue;                       // |lat| < 45°
        const int kmax = (int)(nlon * cl / 0.7071 * 0.5);
        for (int k = 0; k < nlev; k++)
            for (int m = 0; m < 4; m++) {
                double *F = m == 0 ? c->Tn : m == 1 ? c->qn : m == 2 ? c->un : c->vn;
                double *row = F + CM(c, k, j, 0);
                for (int i = 0; i < nlon; i++) { c->fre[i] = row[i]; c->fim[i] = 0.0; }
                fc_fft(nlon, c->fre, c->fim, c->twl, 0);
                for (int w = 1; w < nlon; w++) {
                    const int wn = w <= nlon / 2 ? w : nlon - w;
                    if (wn > kmax) {
                        const double damp = (double)kmax / wn;
                        c->fre[w] *= damp * damp; c->fim[w] *= damp * damp;
                    }
                }
                fc_fft(nlon, c->fre, c->fim, c->twl, 1);
                for (int i = 0; i < nlon; i++) row[i] = c->fre[i] / nlon;
            }
    }
    double *t;
    t = c->T; c->T = c->Tn; c->Tn = t;
    t = c->q; c->q = c->qn; c->qn = t;
    t = c->u; c->u = c->un; c->un = t;
    t = c->v; c->v = c->vn; c->vn = t;
}

/// Column physics for every column: large-scale condensation with
/// evaporation of falling rain, moist convective adjustment, two-stream
/// longwave and absorbing shortwave radiation, and implicit vertical
/// diffusion in the boundary layer — each column on its own, the way the
/// physics packages of CAM run.
static void cm_physics(cm_ctx *c, double tday) {
    const int nlon = c->nlon, nlat = c->nlat, nlev = c->nlev;
    const double dt = c->dt, cp = c->cp, Lv = c->Lv, g = c->g;
    const double sigma_sb = 5.670374e-8;
    double *Tc = c->col, *qc = c->col + nlev, *pc = c->col + 2 * nlev, *dp = c->col + 3 * nlev;
    double *fup = c->col + 4 * nlev, *fdn = c->col + 5 * nlev + 1;
    double sdec, cdec;
    fc_sincos(0.4091 * fc_exp(-0.0 * tday) * 0.5, &sdec, &cdec);
    for (int j = 0; j < nlat; j++)
        for (int i = 0; i < nlon; i++) {
            const size_t q2 = (size_t)j * nlon + i;
            for (int k = 0; k < nlev; k++) {
                const size_t r = CM(c, k, j, i);
                Tc[k] = c->T[r];
                qc[k] = c->q[r] > 0 ? c->q[r] : 0.0;
                pc[k] = c->ps[q2] * c->sig[k];
                dp[k] = c->ps[q2] * c->dsig[k];
            }
            // Large-scale condensation, top down, with the rain evaporating
            // into dry layers below.
            double rain = 0.0;
            for (int k = 0; k < nlev; k++) {
                const double qs = cm_qsat(Tc[k], pc[k]);
                if (qc[k] > qs) {
                    const double gam = Lv * Lv * qs / (cp * 461.5 * Tc[k] * Tc[k]);
                    const double cond = (qc[k] - qs) / (1.0 + gam);
                    qc[k] -= cond;
                    Tc[k] += Lv / cp * cond;
                    rain += cond * dp[k] / g;
                } else if (rain > 0.0) {
                    const double deficit = (qs - qc[k]) * dp[k] / g;
                    double evap = 2e-5 * dt * deficit * sqrt(rain);
                    if (evap > rain) evap = rain;
                    if (evap > deficit) evap = deficit;
                    rain -= evap;
                    qc[k] += evap * g / dp[k];
                    Tc[k] -= Lv / cp * evap * g / dp[k];
                }
            }
            // Moist convective adjustment between neighbouring layers, swept
            // until stable (at most six sweeps).
            for (int sweep = 0; sweep < 6; sweep++) {
                int changed = 0;
                for (int k = nlev - 1; k > 0; k--) {
                    const double kap = c->Rd / cp;
                    const double th_lo = Tc[k] * fc_exp(kap * fc_log(1e5 / pc[k]));
                    const double th_hi = Tc[k - 1] * fc_exp(kap * fc_log(1e5 / pc[k - 1]));
                    const double ql = Lv / cp * qc[k], qh = Lv / cp * qc[k - 1];
                    if (th_lo + ql > th_hi + qh + 0.5) {
                        const double h_lo = cp * Tc[k] + Lv * qc[k], h_hi = cp * Tc[k - 1] + Lv * qc[k - 1];
                        const double hm = (h_lo * dp[k] + h_hi * dp[k - 1]) / (dp[k] + dp[k - 1]);
                        const double qm = (qc[k] * dp[k] + qc[k - 1] * dp[k - 1]) / (dp[k] + dp[k - 1]);
                        // Mix to one moist enthalpy and humidity, then lay
                        // the pair on a dry adiabat (equal θ): neutral.
                        qc[k] = qm; qc[k - 1] = qm;
                        const double ex = fc_exp(kap * fc_log(pc[k - 1] / pc[k]));
                        const double Tlo = 2.0 * (hm - Lv * qm) / cp / (1.0 + ex);
                        Tc[k] = Tlo;
                        Tc[k - 1] = Tlo * ex;
                        changed = 1;
                    }
                }
                if (!changed) break;
            }
            // Longwave: grey two-stream with water-vapour emissivity.
            fup[nlev] = sigma_sb * Tc[nlev - 1] * Tc[nlev - 1] * Tc[nlev - 1] * Tc[nlev - 1];
            for (int k = nlev - 1; k >= 0; k--) {
                const double eps = 1.0 - fc_exp(-(0.08 + 30.0 * qc[k]) * dp[k] / g * 0.01);
                const double B = sigma_sb * Tc[k] * Tc[k] * Tc[k] * Tc[k];
                fup[k] = fup[k + 1] * (1.0 - eps) + eps * B;
            }
            fdn[0] = 0.0;
            for (int k = 0; k < nlev; k++) {
                const double eps = 1.0 - fc_exp(-(0.08 + 30.0 * qc[k]) * dp[k] / g * 0.01);
                const double B = sigma_sb * Tc[k] * Tc[k] * Tc[k] * Tc[k];
                fdn[k + 1] = fdn[k] * (1.0 - eps) + eps * B;
            }
            // Shortwave: absorption along the slant path at this hour.
            double sh, ch;
            fc_sincos(2.0 * FC_PI * (tday + (double)i / nlon), &sh, &ch);
            const double cosz = c->sinlat[j] * sdec + c->coslat[j] * cdec * ch;
            double sw = cosz > 0 ? 1361.0 * cosz : 0.0, path = 0.0;
            for (int k = 0; k < nlev; k++) {
                const double net = (fup[k + 1] - fup[k]) + (fdn[k] - fdn[k + 1]);
                double heat = net * g / (cp * dp[k]);
                if (sw > 0) {
                    path += (0.02 + 10.0 * qc[k]) * dp[k] / g * 1e-3;
                    const double nsw = 1361.0 * cosz * fc_exp(-path / cosz);
                    heat += (sw - nsw) * g / (cp * dp[k]);
                    sw = nsw;
                }
                heat *= dt;                                   // limited, as CAM's physics checks
                Tc[k] += heat > 4.0 ? 4.0 : heat < -4.0 ? -4.0 : heat;
            }
            // Boundary-layer vertical diffusion of T and q (implicit).
            for (int fld = 0; fld < 2; fld++) {
                double *X = fld ? qc : Tc;
                for (int k = 0; k < nlev; k++) {
                    const double K = k >= nlev - 6 ? 30.0 * (k - (nlev - 7)) : 0.5;
                    const double rho_dz = dp[k] / g;
                    const double lo = k + 1 < nlev ? K * 1e-4 : 0.0, hi = k > 0 ? K * 1e-4 : 0.0;
                    c->ca[k] = -dt * hi / rho_dz * 50.0;
                    c->cc[k] = -dt * lo / rho_dz * 50.0;
                    c->cb[k] = 1.0 - c->ca[k] - c->cc[k];
                    c->cd[k] = X[k];
                }
                fc_thomas_rows(nlev, 1, 1, c->ca, c->cb, c->cc, c->cd, c->ccp);
                for (int k = 0; k < nlev; k++) X[k] = c->cd[k];
            }
            // Surface evaporation into the lowest layer.
            qc[nlev - 1] += dt * 2e-8 * (1.0 + c->coslat[j]);
            for (int k = 0; k < nlev; k++) {
                const size_t r = CM(c, k, j, i);
                c->T[r] = Tc[k] < 150.0 ? 150.0 : Tc[k] > 340.0 ? 340.0 : Tc[k];
                c->q[r] = qc[k];
            }
            c->precip[q2] += rain;
            c->olr[q2] = fup[0];
        }
}

/// cam4 — an atmosphere model of the CAM kind: a latitude–longitude grid
/// with a flux-form finite-volume dynamical core (limited second-order
/// advection, hydrostatic geopotential, a polar FFT filter) and column
/// physics — Bolton saturation humidity, large-scale condensation with
/// rain evaporation, moist convective adjustment, two-stream longwave and
/// slant-path shortwave radiation, implicit boundary-layer diffusion —
/// most of whose time goes to exponentials, logarithms and branches in the
/// columns. `size` 1: 64×32×18 for 30 steps; 2: 128×64×26 for 29; 3:
/// 256×128×26 for 32. `value` digests mean temperature, humidity,
/// precipitation and outgoing longwave; work is column-level updates.
int cbk_cam4(int size, cb_bench_result *out) {
    static const int cfg[3][4] = {{64, 32, 18, 30}, {128, 64, 26, 29}, {256, 128, 26, 32}};
    const int lv = fc_level(size) - 1;
    cm_ctx c;
    memset(&c, 0, sizeof c);
    c.nlon = cfg[lv][0]; c.nlat = cfg[lv][1]; c.nlev = cfg[lv][2];
    const int steps = cfg[lv][3];
    c.n2 = (size_t)c.nlon * c.nlat; c.n3 = c.n2 * c.nlev;
    c.a = 6.371e6; c.cp = 1004.6; c.Rd = 287.04; c.Lv = 2.501e6; c.g = 9.81;
    c.dt = 1800.0 * 64.0 / c.nlon;
    const size_t total = 8 * c.n3 + 3 * c.n2 + 3 * (size_t)c.nlat + 3 * (size_t)c.nlev
                       + 3 * (size_t)c.nlon + 5 * (size_t)c.nlev + 6 * (size_t)c.nlev + 8 + 30 * FC_PAD + c.n3;
    double *mem = (double *)calloc(total, sizeof(double));
    if (!mem) return 1;
    fc_arena a = {mem};
    c.T = fc_take(&a, c.n3); c.q = fc_take(&a, c.n3); c.u = fc_take(&a, c.n3); c.v = fc_take(&a, c.n3);
    c.Tn = fc_take(&a, c.n3); c.qn = fc_take(&a, c.n3); c.un = fc_take(&a, c.n3); c.vn = fc_take(&a, c.n3);
    c.phi = fc_take(&a, c.n3);
    c.ps = fc_take(&a, c.n2); c.precip = fc_take(&a, c.n2); c.olr = fc_take(&a, c.n2);
    c.lat = fc_take(&a, c.nlat); c.coslat = fc_take(&a, c.nlat); c.sinlat = fc_take(&a, c.nlat);
    c.sig = fc_take(&a, c.nlev); c.dsig = fc_take(&a, c.nlev); c.dln = fc_take(&a, c.nlev);
    c.fre = fc_take(&a, c.nlon); c.fim = fc_take(&a, c.nlon); c.twl = fc_take(&a, c.nlon);
    c.ca = fc_take(&a, c.nlev); c.cb = fc_take(&a, c.nlev); c.cc = fc_take(&a, c.nlev);
    c.cd = fc_take(&a, c.nlev); c.ccp = fc_take(&a, c.nlev);
    c.col = fc_take(&a, 6 * (size_t)c.nlev + 8);
    fc_twiddles(c.nlon, c.twl);
    for (int j = 0; j < c.nlat; j++) {
        c.lat[j] = -0.5 * FC_PI + (j + 0.5) * FC_PI / c.nlat;
        fc_sincos(c.lat[j], &c.sinlat[j], &c.coslat[j]);
    }
    for (int k = 0; k < c.nlev; k++) {
        const double s0 = (double)k / c.nlev, s1 = (double)(k + 1) / c.nlev;
        const double e0 = 0.01 + 0.99 * s0 * s0 * (3.0 - 2.0 * s0), e1 = 0.01 + 0.99 * s1 * s1 * (3.0 - 2.0 * s1);
        c.sig[k] = 0.5 * (e0 + e1);
        c.dsig[k] = e1 - e0;
    }
    for (int k = 0; k < c.nlev; k++) c.dln[k] = fc_log((k + 1 < c.nlev ? c.sig[k + 1] : 1.0) / c.sig[k]);
    uint64_t seed = 0xCA44A7E500000003ull;
    for (int j = 0; j < c.nlat; j++)
        for (int i = 0; i < c.nlon; i++) {
            const size_t q2 = (size_t)j * c.nlon + i;
            c.ps[q2] = 1.0e5 - 800.0 * c.sinlat[j] * c.sinlat[j];
            for (int k = 0; k < c.nlev; k++) {
                const size_t r = CM(&c, k, j, i);
                const double p = c.ps[q2] * c.sig[k];
                const double Ts = 300.0 - 45.0 * c.sinlat[j] * c.sinlat[j];
                double T = Ts * fc_exp(0.19 * fc_log(p / 1e5));
                if (T < 205.0) T = 205.0;
                c.T[r] = T + 0.3 * (fc_u01(&seed) - 0.5);
                c.q[r] = 0.75 * cm_qsat(T, p) * (p > 3e4 ? 1.0 : 0.05);
                c.u[r] = 25.0 * c.coslat[j] * (1.0 - p / 1e5) * 2.0;
                c.v[r] = 0.0;
            }
        }
    for (int s = 0; s < steps; s++) {
        cm_dynamics(&c);
        cm_physics(&c, s * c.dt / 86400.0);
    }
    double tm = 0, qm = 0, pr = 0, ol = 0;
    for (size_t r = 0; r < c.n3; r++) { tm += c.T[r]; qm += c.q[r]; }
    for (size_t q = 0; q < c.n2; q++) { pr += c.precip[q]; ol += c.olr[q]; }
    out->value = tm / (double)c.n3 + 1e3 * qm / (double)c.n3 + pr / (double)c.n2 + 1e-3 * ol / (double)c.n2;
    out->work = (double)c.n3 * steps;
    out->unit = "column-level updates";
    free(mem);
    return isfinite(out->value) ? 0 : 2;
}

// ── bwaves: implicit 3-D compressible flow with block BiCGSTAB ──────────

#define BW_NV 5                       // ρ, ρu, ρv, ρw, E
#define BW_GAMMA 1.4

typedef struct {
    int nx, ny, nz;
    size_t n;                         // cells
    double dx, dt, mu;
    double *U, *R, *dU;               // [cell][5]
    double *A;                        // [cell][7][5][5]: centre, −x, +x, −y, +y, −z, +z
    double *r, *r0, *p, *v, *s, *t;   // BiCGSTAB vectors, [cell][5]
    int32_t *nb;                      // [cell][6] neighbours (periodic)
} bw_ctx;

/// The Euler flux in direction d of state q, and its Jacobian ∂F/∂q.
static void bw_flux(const double *q, int d, double *f, double *J) {
    const double rho = q[0], ir = 1.0 / rho;
    const double u[3] = {q[1] * ir, q[2] * ir, q[3] * ir};
    const double E = q[4], k = 0.5 * (u[0] * u[0] + u[1] * u[1] + u[2] * u[2]);
    const double p = (BW_GAMMA - 1.0) * (E - rho * k);
    const double un = u[d], H = (E + p) * ir;
    f[0] = q[1 + d];
    for (int a = 0; a < 3; a++) f[1 + a] = q[1 + a] * un + (a == d ? p : 0.0);
    f[4] = (E + p) * un;
    if (!J) return;
    const double g1 = BW_GAMMA - 1.0;
    for (int i = 0; i < 25; i++) J[i] = 0.0;
    J[0 * 5 + 1 + d] = 1.0;
    for (int a = 0; a < 3; a++) {
        double *row = J + (1 + a) * 5;
        row[0] = -u[a] * un + (a == d ? g1 * k : 0.0);
        for (int b = 0; b < 3; b++) row[1 + b] = (a == b ? un : 0.0) + (b == d ? u[a] : 0.0) - (a == d ? g1 * u[b] : 0.0);
        row[4] = a == d ? g1 : 0.0;
    }
    double *row = J + 20;
    row[0] = un * (g1 * k - H);
    for (int b = 0; b < 3; b++) row[1 + b] = (b == d ? H : 0.0) - g1 * u[b] * un;
    row[4] = BW_GAMMA * un;
}

/// y = A x for the block 7-point operator.
static void bw_matvec(const bw_ctx *c, const double *x, double *y) {
    for (size_t i = 0; i < c->n; i++) {
        const double *Ai = c->A + i * 175;
        double acc[5] = {0, 0, 0, 0, 0};
        for (int b = 0; b < 7; b++) {
            const double *xb = x + (size_t)(b == 0 ? (int32_t)i : c->nb[i * 6 + b - 1]) * 5;
            const double *M = Ai + b * 25;
            for (int r = 0; r < 5; r++)
                acc[r] += M[r * 5] * xb[0] + M[r * 5 + 1] * xb[1] + M[r * 5 + 2] * xb[2] + M[r * 5 + 3] * xb[3] + M[r * 5 + 4] * xb[4];
        }
        for (int r = 0; r < 5; r++) y[i * 5 + r] = acc[r];
    }
}

static double bw_dot(const double *a, const double *b, size_t n) {
    double s = 0.0;
    for (size_t i = 0; i < n; i++) s += a[i] * b[i];
    return s;
}

/// Residual (central fluxes plus a little numerical and physical
/// viscosity) and the implicit operator I/Δt + ∂R/∂U, block by block.
static void bw_assemble(bw_ctx *c) {
    const double idx = 1.0 / c->dx, nu = c->mu * idx * idx;
    double f[2][5], Jm[25], Jp[25];
    for (size_t i = 0; i < c->n; i++) {
        const double *qi = c->U + i * 5;
        double *Ri = c->R + i * 5, *Ai = c->A + i * 175;
        for (int k = 0; k < 175; k++) Ai[k] = 0.0;
        for (int r = 0; r < 5; r++) { Ri[r] = 0.0; Ai[r * 5 + r] = 1.0 / c->dt; }
        for (int d = 0; d < 3; d++) {
            const int32_t im = c->nb[i * 6 + 2 * d], ip = c->nb[i * 6 + 2 * d + 1];
            const double *qm = c->U + (size_t)im * 5, *qp = c->U + (size_t)ip * 5;
            bw_flux(qm, d, f[0], Jm);
            bw_flux(qp, d, f[1], Jp);
            double *Am = Ai + (1 + 2 * d) * 25, *Ap = Ai + (2 + 2 * d) * 25;
            for (int r = 0; r < 5; r++) {
                Ri[r] += 0.5 * (f[1][r] - f[0][r]) * idx - nu * (qp[r] - 2.0 * qi[r] + qm[r]);
                for (int s = 0; s < 5; s++) {
                    Am[r * 5 + s] = -0.5 * idx * Jm[r * 5 + s] - (r == s ? nu : 0.0);
                    Ap[r * 5 + s] = 0.5 * idx * Jp[r * 5 + s] - (r == s ? nu : 0.0);
                }
                Ai[r * 5 + r] += 2.0 * nu;
            }
        }
    }
}

/// BiCGSTAB on A ΔU = −R; returns the iterations taken.
static int bw_bicgstab(bw_ctx *c, int maxit, double tol) {
    const size_t N = c->n * 5;
    for (size_t k = 0; k < N; k++) { c->dU[k] = 0.0; c->r[k] = -c->R[k]; c->r0[k] = c->r[k]; c->p[k] = 0.0; c->v[k] = 0.0; }
    double rho = 1.0, alpha = 1.0, omega = 1.0;
    const double stop = tol * sqrt(bw_dot(c->r, c->r, N));
    int it;
    for (it = 0; it < maxit; it++) {
        const double rho1 = bw_dot(c->r0, c->r, N);
        if (rho1 == 0.0) break;
        const double beta = (rho1 / rho) * (alpha / omega);
        rho = rho1;
        for (size_t k = 0; k < N; k++) c->p[k] = c->r[k] + beta * (c->p[k] - omega * c->v[k]);
        bw_matvec(c, c->p, c->v);
        alpha = rho / bw_dot(c->r0, c->v, N);
        for (size_t k = 0; k < N; k++) c->s[k] = c->r[k] - alpha * c->v[k];
        bw_matvec(c, c->s, c->t);
        const double tt = bw_dot(c->t, c->t, N);
        omega = tt > 0.0 ? bw_dot(c->t, c->s, N) / tt : 0.0;
        for (size_t k = 0; k < N; k++) {
            c->dU[k] += alpha * c->p[k] + omega * c->s[k];
            c->r[k] = c->s[k] - omega * c->t[k];
        }
        if (sqrt(bw_dot(c->r, c->r, N)) <= stop || omega == 0.0) { it++; break; }
    }
    return it;
}

/// bwaves — implicit compressible flow of the kind SPEC's bwaves is: a
/// blast wave in a periodic box of air, the Euler equations with a little
/// viscosity on a uniform grid, advanced by backward Euler. Every step
/// builds the residual and the linearised operator — a 5×5 block for the
/// cell and each of its six neighbours from the flux Jacobians, 1.4 KB a
/// cell — and solves it by BiCGSTAB, whose two block matrix–vector
/// products an iteration stream the whole operator from memory. `size`
/// 1: 24³ cells for 4 steps; 2: 40³ for 4; 3: 56³ for 6. `value` digests
/// the total energy and the density variance; work is cell updates.
int cbk_bwaves(int size, cb_bench_result *out) {
    static const int cfg[3][2] = {{24, 4}, {40, 4}, {56, 6}};
    const int lv = fc_level(size) - 1;
    bw_ctx c;
    memset(&c, 0, sizeof c);
    c.nx = c.ny = c.nz = cfg[lv][0];
    const int steps = cfg[lv][1];
    c.n = (size_t)c.nx * c.ny * c.nz;
    c.dx = 1.0 / c.nx; c.dt = 0.5 * c.dx; c.mu = 2e-3;
    const size_t total = c.n * (175 + 9 * 5) + 12 * FC_PAD;
    double *mem = (double *)calloc(total, sizeof(double));
    c.nb = (int32_t *)malloc(sizeof(int32_t) * 6 * c.n);
    if (!mem || !c.nb) { free(mem); free(c.nb); return 1; }
    fc_arena a = {mem};
    c.A = fc_take(&a, c.n * 175);
    c.U = fc_take(&a, c.n * 5); c.R = fc_take(&a, c.n * 5); c.dU = fc_take(&a, c.n * 5);
    c.r = fc_take(&a, c.n * 5); c.r0 = fc_take(&a, c.n * 5); c.p = fc_take(&a, c.n * 5);
    c.v = fc_take(&a, c.n * 5); c.s = fc_take(&a, c.n * 5); c.t = fc_take(&a, c.n * 5);
    for (int k = 0; k < c.nz; k++)
        for (int j = 0; j < c.ny; j++)
            for (int i = 0; i < c.nx; i++) {
                const size_t q = ((size_t)k * c.ny + j) * c.nx + i;
                int32_t *nb = c.nb + q * 6;
                nb[0] = (int32_t)(((size_t)k * c.ny + j) * c.nx + (i + c.nx - 1) % c.nx);
                nb[1] = (int32_t)(((size_t)k * c.ny + j) * c.nx + (i + 1) % c.nx);
                nb[2] = (int32_t)(((size_t)k * c.ny + (j + c.ny - 1) % c.ny) * c.nx + i);
                nb[3] = (int32_t)(((size_t)k * c.ny + (j + 1) % c.ny) * c.nx + i);
                nb[4] = (int32_t)(((size_t)((k + c.nz - 1) % c.nz) * c.ny + j) * c.nx + i);
                nb[5] = (int32_t)(((size_t)((k + 1) % c.nz) * c.ny + j) * c.nx + i);
                const double x = (i + 0.5) / c.nx - 0.5, y = (j + 0.5) / c.ny - 0.5, z = (k + 0.5) / c.nz - 0.5;
                const double r2 = x * x + y * y + z * z;
                const double pr = 1.0 + 9.0 * fc_exp(-r2 / 0.01);    // a high-pressure kernel at the centre
                double *U = c.U + q * 5;
                U[0] = 1.0 + 0.5 * fc_exp(-r2 / 0.02);
                U[1] = 0.1 * U[0]; U[2] = 0.0; U[3] = 0.0;
                U[4] = pr / (BW_GAMMA - 1.0) + 0.5 * U[1] * U[1] / U[0];
            }
    int its = 0;
    for (int s = 0; s < steps; s++) {
        bw_assemble(&c);
        its += bw_bicgstab(&c, 40, 1e-8);
        for (size_t k = 0; k < c.n * 5; k++) c.U[k] += c.dU[k];
    }
    double E = 0, rm = 0, rv = 0;
    for (size_t q = 0; q < c.n; q++) { E += c.U[q * 5 + 4]; rm += c.U[q * 5]; }
    rm /= (double)c.n;
    for (size_t q = 0; q < c.n; q++) rv += (c.U[q * 5] - rm) * (c.U[q * 5] - rm);
    out->value = E / (double)c.n + rv / (double)c.n + 1e-3 * its;
    out->work = (double)c.n * steps;
    out->unit = "cell updates";
    free(mem); free(c.nb);
    return isfinite(out->value) ? 0 : 2;
}

// ── fem: finite-element parameter estimation ────────────────────────────

typedef struct {
    int nn, ne;                       // nodes, triangles
    double *x, *y;
    int32_t *tri;                     // [e][3]
    int32_t *rowptr, *col;            // CSR pattern (P1 couplings)
    double *val, *diag;
    int nnz;
} fe_mesh;

/// Adds v into A(i, j), finding j in row i by binary search, as a sparse
/// matrix add does.
static inline void fe_add(fe_mesh *m, int i, int j, double v) {
    int lo = m->rowptr[i], hi = m->rowptr[i + 1] - 1;
    while (lo < hi) {
        const int mid = (lo + hi) >> 1;
        if (m->col[mid] < j) lo = mid + 1; else hi = mid;
    }
    m->val[lo] += v;
}

/// Assembles −∇·(a ∇u) on P1 triangles (a constant per element, from the
/// parameter field) with a mass term: element by element, the local 3×3
/// matrix from the shape-function gradients, scattered into the CSR
/// matrix; Dirichlet nodes on the boundary are kept as identity rows.
static void fe_assemble(fe_mesh *m, const double *a, const uint8_t *bnd) {
    memset(m->val, 0, sizeof(double) * (size_t)m->nnz);
    for (int e = 0; e < m->ne; e++) {
        const int32_t *t = m->tri + 3 * e;
        const double x0 = m->x[t[0]], y0 = m->y[t[0]], x1 = m->x[t[1]], y1 = m->y[t[1]], x2 = m->x[t[2]], y2 = m->y[t[2]];
        const double det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
        const double area = 0.5 * fabs(det);
        const double bx[3] = {(y1 - y2) / det, (y2 - y0) / det, (y0 - y1) / det};
        const double by[3] = {(x2 - x1) / det, (x0 - x2) / det, (x1 - x0) / det};
        for (int i = 0; i < 3; i++) {
            if (bnd[t[i]]) continue;
            for (int j = 0; j < 3; j++) {
                const double k = a[e] * area * (bx[i] * bx[j] + by[i] * by[j]) + area * (i == j ? 1.0 / 6.0 : 1.0 / 12.0) * 0.1;
                if (!bnd[t[j]]) fe_add(m, t[i], t[j], k);
            }
        }
    }
    for (int i = 0; i < m->nn; i++) if (bnd[i]) fe_add(m, i, i, 1.0);
    for (int i = 0; i < m->nn; i++) {
        double d = 1.0;
        for (int k = m->rowptr[i]; k < m->rowptr[i + 1]; k++) if (m->col[k] == i) d = m->val[k];
        m->diag[i] = 1.0 / d;
    }
}

static void fe_spmv(const fe_mesh *m, const double *x, double *y) {
    for (int i = 0; i < m->nn; i++) {
        double s = 0.0;
        for (int k = m->rowptr[i]; k < m->rowptr[i + 1]; k++) s += m->val[k] * x[m->col[k]];
        y[i] = s;
    }
}

/// Jacobi-preconditioned CG; returns the iterations taken.
static int fe_cg(const fe_mesh *m, const double *b, double *x, double *r, double *z, double *p, double *q, double tol, int maxit) {
    const int n = m->nn;
    fe_spmv(m, x, q);
    double bb = 0, rz = 0;
    for (int i = 0; i < n; i++) { r[i] = b[i] - q[i]; z[i] = r[i] * m->diag[i]; p[i] = z[i]; rz += r[i] * z[i]; bb += b[i] * b[i]; }
    const double stop = tol * tol * (bb > 0 ? bb : 1.0);
    int it;
    for (it = 0; it < maxit; it++) {
        fe_spmv(m, p, q);
        double pq = 0;
        for (int i = 0; i < n; i++) pq += p[i] * q[i];
        const double al = rz / pq;
        double rr = 0, rz1 = 0;
        for (int i = 0; i < n; i++) { x[i] += al * p[i]; r[i] -= al * q[i]; rr += r[i] * r[i]; }
        if (rr <= stop) { it++; break; }
        for (int i = 0; i < n; i++) { z[i] = r[i] * m->diag[i]; rz1 += r[i] * z[i]; }
        const double be = rz1 / rz;
        rz = rz1;
        for (int i = 0; i < n; i++) p[i] = z[i] + be * p[i];
    }
    return it;
}

/// fem — finite-element parameter estimation of the kind SPEC's parest
/// is: recover a diffusion coefficient field from measurements of the
/// solution. P1 triangles on a perturbed, locally refined mesh of the unit
/// square (nodes shuffled, so the matrix is irregular); every Gauss–Newton
/// round assembles −∇·(a∇u) element by element into a CSR matrix (binary
/// search for each entry, as a sparse-matrix add does), solves the
/// forward problem and its adjoint by Jacobi-preconditioned CG, and
/// updates the coefficient on every element from the gradient. `size` 1:
/// 88² cells for 6 rounds; 2: 150² for 6; 3: 230² for 6. `value` digests
/// the misfit and the recovered coefficient; work is element assemblies.
int cbk_fem(int size, cb_bench_result *out) {
    static const int cfg[3][2] = {{88, 6}, {150, 6}, {230, 6}};
    const int lv = fc_level(size) - 1;
    const int g = cfg[lv][0], rounds = cfg[lv][1];
    fe_mesh m;
    memset(&m, 0, sizeof m);
    m.nn = (g + 1) * (g + 1); m.ne = 2 * g * g;
    const int nn = m.nn, ne = m.ne;
    int32_t *perm = (int32_t *)malloc(sizeof(int32_t) * (size_t)nn);
    m.x = (double *)malloc(sizeof(double) * (size_t)nn); m.y = (double *)malloc(sizeof(double) * (size_t)nn);
    m.tri = (int32_t *)malloc(sizeof(int32_t) * 3 * (size_t)ne);
    m.rowptr = (int32_t *)calloc((size_t)nn + 1, sizeof(int32_t));
    double *work = (double *)calloc((size_t)nn * 9 + (size_t)ne * 3, sizeof(double));
    uint8_t *bnd = (uint8_t *)calloc((size_t)nn, 1);
    int32_t *deg = (int32_t *)calloc((size_t)nn, sizeof(int32_t));
    int rc = 1;
    if (!perm || !m.x || !m.y || !m.tri || !m.rowptr || !work || !bnd || !deg) goto done;
    {
        // nodes numbered in a shuffled order, positions perturbed, refined
        // towards an interior feature
        uint64_t seed = 0xFE3FE3FE00000004ull;
        for (int i = 0; i < nn; i++) perm[i] = i;
        for (int i = nn - 1; i > 0; i--) { const int j = (int)(fc_next(&seed) % (uint64_t)(i + 1)); const int32_t t = perm[i]; perm[i] = perm[j]; perm[j] = t; }
        for (int j = 0; j <= g; j++)
            for (int i = 0; i <= g; i++) {
                const int id = perm[j * (g + 1) + i];
                double u = (double)i / g, v = (double)j / g;
                u = u + 0.15 * u * (1 - u) * (u - 0.4); v = v + 0.15 * v * (1 - v) * (v - 0.6);
                if (i > 0 && i < g && j > 0 && j < g) { u += (fc_u01(&seed) - 0.5) * 0.3 / g; v += (fc_u01(&seed) - 0.5) * 0.3 / g; }
                m.x[id] = u; m.y[id] = v;
                bnd[id] = (uint8_t)(i == 0 || j == 0 || i == g || j == g);
            }
        int e = 0;
        for (int j = 0; j < g; j++)
            for (int i = 0; i < g; i++) {
                const int a = perm[j * (g + 1) + i], b = perm[j * (g + 1) + i + 1], c = perm[(j + 1) * (g + 1) + i], d = perm[(j + 1) * (g + 1) + i + 1];
                if ((i + j) & 1) { m.tri[3 * e] = a; m.tri[3 * e + 1] = b; m.tri[3 * e + 2] = d; e++; m.tri[3 * e] = a; m.tri[3 * e + 1] = d; m.tri[3 * e + 2] = c; e++; }
                else { m.tri[3 * e] = a; m.tri[3 * e + 1] = b; m.tri[3 * e + 2] = c; e++; m.tri[3 * e] = b; m.tri[3 * e + 1] = d; m.tri[3 * e + 2] = c; e++; }
            }
        // the CSR pattern: every node coupled to itself and its element neighbours
        int32_t *adj = (int32_t *)malloc(sizeof(int32_t) * (size_t)nn * 16);
        if (!adj) goto done;
        for (int i = 0; i < nn; i++) { adj[i * 16] = i; deg[i] = 1; }
        for (int t = 0; t < ne; t++)
            for (int a2 = 0; a2 < 3; a2++)
                for (int b2 = 0; b2 < 3; b2++) {
                    const int i = m.tri[3 * t + a2], j = m.tri[3 * t + b2];
                    int found = 0;
                    for (int k = 0; k < deg[i]; k++) if (adj[i * 16 + k] == j) { found = 1; break; }
                    if (!found && deg[i] < 16) adj[i * 16 + deg[i]++] = j;
                }
        for (int i = 0; i < nn; i++) {
            for (int a2 = 1; a2 < deg[i]; a2++) {              // sort the row
                const int32_t v = adj[i * 16 + a2];
                int b2 = a2 - 1;
                while (b2 >= 0 && adj[i * 16 + b2] > v) { adj[i * 16 + b2 + 1] = adj[i * 16 + b2]; b2--; }
                adj[i * 16 + b2 + 1] = v;
            }
            m.rowptr[i + 1] = m.rowptr[i] + deg[i];
        }
        m.nnz = m.rowptr[nn];
        m.col = (int32_t *)malloc(sizeof(int32_t) * (size_t)m.nnz);
        m.val = (double *)malloc(sizeof(double) * (size_t)m.nnz);
        m.diag = (double *)malloc(sizeof(double) * (size_t)nn);
        if (!m.col || !m.val || !m.diag) { free(adj); goto done; }
        for (int i = 0; i < nn; i++) memcpy(m.col + m.rowptr[i], adj + i * 16, sizeof(int32_t) * (size_t)deg[i]);
        free(adj);
    }
    {
        double *u = work, *lam = work + nn, *b = work + 2 * nn, *r = work + 3 * nn, *z = work + 4 * nn;
        double *p = work + 5 * nn, *q = work + 6 * nn, *obs = work + 7 * nn, *src = work + 8 * nn;
        double *a = work + 9 * (size_t)nn, *atrue = a + ne, *grad = a + 2 * (size_t)ne;
        // the true coefficient: an inclusion; the source: a smooth bump
        for (int e = 0; e < ne; e++) {
            const int32_t *t = m.tri + 3 * e;
            const double cx = (m.x[t[0]] + m.x[t[1]] + m.x[t[2]]) / 3.0, cy = (m.y[t[0]] + m.y[t[1]] + m.y[t[2]]) / 3.0;
            atrue[e] = 1.0 + 2.0 * fc_exp(-((cx - 0.4) * (cx - 0.4) + (cy - 0.6) * (cy - 0.6)) / 0.02);
            a[e] = 1.0;
        }
        for (int i = 0; i < nn; i++) src[i] = bnd[i] ? 0.0 : 1.0 + m.x[i] * m.y[i];
        // synthetic measurements from the true field
        fe_assemble(&m, atrue, bnd);
        double h = 1.0 / g;
        for (int i = 0; i < nn; i++) b[i] = bnd[i] ? 0.0 : src[i] * h * h;
        memset(obs, 0, sizeof(double) * (size_t)nn);
        int its = fe_cg(&m, b, obs, r, z, p, q, 1e-10, 4000);
        double misfit = 0;
        for (int round = 0; round < rounds; round++) {
            fe_assemble(&m, a, bnd);
            memset(u, 0, sizeof(double) * (size_t)nn);
            its += fe_cg(&m, b, u, r, z, p, q, 1e-9, 4000);
            misfit = 0;
            for (int i = 0; i < nn; i++) { const double d = u[i] - obs[i]; misfit += d * d; b[i] = bnd[i] ? 0.0 : -d; }
            memset(lam, 0, sizeof(double) * (size_t)nn);
            its += fe_cg(&m, b, lam, r, z, p, q, 1e-9, 4000);        // adjoint (the operator is symmetric)
            // gradient per element: −a_e ∫ ∇u·∇λ, a projected step
            double gmax = 0;
            for (int e = 0; e < ne; e++) {
                const int32_t *t = m.tri + 3 * e;
                const double x0 = m.x[t[0]], y0 = m.y[t[0]], x1 = m.x[t[1]], y1 = m.y[t[1]], x2 = m.x[t[2]], y2 = m.y[t[2]];
                const double det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
                const double bx[3] = {(y1 - y2) / det, (y2 - y0) / det, (y0 - y1) / det};
                const double by[3] = {(x2 - x1) / det, (x0 - x2) / det, (x1 - x0) / det};
                double gux = 0, guy = 0, glx = 0, gly = 0;
                for (int k = 0; k < 3; k++) { gux += bx[k] * u[t[k]]; guy += by[k] * u[t[k]]; glx += bx[k] * lam[t[k]]; gly += by[k] * lam[t[k]]; }
                grad[e] = 0.5 * fabs(det) * (gux * glx + guy * gly);
                if (fabs(grad[e]) > gmax) gmax = fabs(grad[e]);
            }
            const double step = gmax > 0 ? 0.3 / gmax : 0.0;
            for (int e = 0; e < ne; e++) {
                double na = a[e] * fc_exp(-step * grad[e] * a[e]);
                a[e] = na < 0.2 ? 0.2 : na > 10.0 ? 10.0 : na;
            }
            for (int i = 0; i < nn; i++) b[i] = bnd[i] ? 0.0 : src[i] * h * h;
        }
        double am = 0;
        for (int e = 0; e < ne; e++) am += a[e];
        out->value = misfit * 1e6 + am / ne + 1e-6 * its;
        out->work = (double)ne * (rounds + 1);
        out->unit = "element assemblies";
        rc = isfinite(out->value) ? 0 : 2;
    }
done:
    free(perm); free(m.x); free(m.y); free(m.tri); free(m.rowptr); free(m.col); free(m.val); free(m.diag);
    free(work); free(bnd); free(deg);
    return rc;
}
