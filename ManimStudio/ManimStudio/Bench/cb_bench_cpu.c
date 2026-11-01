//
//  cb_bench_cpu.c — cpu-z's micro-benchmarks: the clock, one core's
//  floating-point throughput, memory bandwidth and memory latency.
//
//  Each runs on the calling thread for about the time asked and returns a
//  rate; cpu-z runs them from several threads at once for the all-core
//  figures. Timing is CLOCK_UPTIME_RAW, the clock that does not include
//  sleep and is not slewed.
//

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <pthread.h>
#include <sys/qos.h>
#include "cb_bench.h"

#if defined(__aarch64__)
#include <arm_neon.h>
#endif

#define CB_EXPORT __attribute__((used, visibility("default")))

static inline double cb_now(void) {
    return (double)clock_gettime_nsec_np(CLOCK_UPTIME_RAW) * 1e-9;
}

// ── The clock ───────────────────────────────────────────────────────────

#define CB_ADD1 "add %0, %0, #1\n\t"
#define CB_ADD10 CB_ADD1 CB_ADD1 CB_ADD1 CB_ADD1 CB_ADD1 CB_ADD1 CB_ADD1 CB_ADD1 CB_ADD1 CB_ADD1
#define CB_ADD100 CB_ADD10 CB_ADD10 CB_ADD10 CB_ADD10 CB_ADD10 CB_ADD10 CB_ADD10 CB_ADD10 CB_ADD10 CB_ADD10

/// 100 dependent adds: each needs the one before, so they take one cycle
/// apiece on any core that adds in a cycle, whatever its width.
static uint64_t cb_add_chain(uint64_t rounds) {
    uint64_t x = 0;
    for (uint64_t r = 0; r < rounds; r++) {
#if defined(__aarch64__)
        __asm__ volatile(CB_ADD100 : "+r"(x));
#else
        for (int i = 0; i < 100; i++) { __asm__ volatile("" : "+r"(x)); x += 1; }
#endif
    }
    return x;
}

typedef struct {
    int ms;
    double ghz;
} cb_clock_job;

static double cb_clock_here(int ms) {
    cb_add_chain(20000);                       // wake the core to its clock
    double best = 0;
    double deadline = cb_now() + (ms > 0 ? ms : 200) * 1e-3;
    do {
        uint64_t rounds = 200000;              // 20 M adds a sample
        double t0 = cb_now();
        uint64_t x = cb_add_chain(rounds);
        double dt = cb_now() - t0;
        if (x != rounds * 100) return 0;       // the chain was not run as written
        double ghz = (double)(rounds * 100) / dt * 1e-9;
        if (ghz > best) best = ghz;            // the fastest sample: least interrupted
    } while (cb_now() < deadline);
    return best;
}

static void *cb_clock_thread(void *arg) {
    cb_clock_job *job = arg;
    job->ghz = cb_clock_here(job->ms);
    return NULL;
}

/// On a thread of its own at user-interactive QoS, which the scheduler
/// puts on a performance core. (A background-QoS thread did not go to an
/// efficiency core on an M4 — only a whole background process did — so
/// the efficiency cores' clock is not measured.)
CB_EXPORT double cb_cpu_clock_ghz(int ms) {
    if (ms < 0) return 0;   // the keep-alive's call (GPUBench.swift)
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_set_qos_class_np(&attr, QOS_CLASS_USER_INTERACTIVE, 0);
    cb_clock_job job = {ms, 0};
    pthread_t thread;
    if (pthread_create(&thread, &attr, cb_clock_thread, &job) != 0) {
        pthread_attr_destroy(&attr);
        return cb_clock_here(ms);
    }
    pthread_join(thread, NULL);
    pthread_attr_destroy(&attr);
    return job.ghz;
}

// ── Floating-point throughput ───────────────────────────────────────────

/// Sixteen independent fused multiply-add chains, enough to keep every FMA
/// pipe of an Apple core busy through each one's latency (4 pipes × 4
/// cycles). x = x·m + c converges, so nothing overflows or goes subnormal.
CB_EXPORT double cb_cpu_fma_gflops(int precision, int ms) {
    if (ms < 0) return 0;
#if defined(__aarch64__)
    double seconds = (ms > 0 ? ms : 200) * 1e-3;
    uint64_t iters = 0;
    double sink = 0;
    double t0 = cb_now(), t;
    if (precision == 64) {
        float64x2_t m = vdupq_n_f64(0.999999), c = vdupq_n_f64(1e-7);
        float64x2_t a0 = vdupq_n_f64(1.0), a1 = vdupq_n_f64(1.1), a2 = vdupq_n_f64(1.2),
                    a3 = vdupq_n_f64(1.3), a4 = vdupq_n_f64(1.4), a5 = vdupq_n_f64(1.5),
                    a6 = vdupq_n_f64(1.6), a7 = vdupq_n_f64(1.7), a8 = vdupq_n_f64(1.8),
                    a9 = vdupq_n_f64(1.9), a10 = vdupq_n_f64(2.0), a11 = vdupq_n_f64(2.1),
                    a12 = vdupq_n_f64(2.2), a13 = vdupq_n_f64(2.3), a14 = vdupq_n_f64(2.4),
                    a15 = vdupq_n_f64(2.5);
        do {
            for (int i = 0; i < 4096; i++) {
                a0 = vfmaq_f64(c, a0, m);   a1 = vfmaq_f64(c, a1, m);
                a2 = vfmaq_f64(c, a2, m);   a3 = vfmaq_f64(c, a3, m);
                a4 = vfmaq_f64(c, a4, m);   a5 = vfmaq_f64(c, a5, m);
                a6 = vfmaq_f64(c, a6, m);   a7 = vfmaq_f64(c, a7, m);
                a8 = vfmaq_f64(c, a8, m);   a9 = vfmaq_f64(c, a9, m);
                a10 = vfmaq_f64(c, a10, m); a11 = vfmaq_f64(c, a11, m);
                a12 = vfmaq_f64(c, a12, m); a13 = vfmaq_f64(c, a13, m);
                a14 = vfmaq_f64(c, a14, m); a15 = vfmaq_f64(c, a15, m);
            }
            iters += 4096;
            t = cb_now();
        } while (t - t0 < seconds);
        float64x2_t s = vaddq_f64(vaddq_f64(vaddq_f64(a0, a1), vaddq_f64(a2, a3)),
                                  vaddq_f64(vaddq_f64(a4, a5), vaddq_f64(a6, a7)));
        s = vaddq_f64(s, vaddq_f64(vaddq_f64(vaddq_f64(a8, a9), vaddq_f64(a10, a11)),
                                   vaddq_f64(vaddq_f64(a12, a13), vaddq_f64(a14, a15))));
        sink = vgetq_lane_f64(s, 0);
        // 16 chains × 2 lanes × 2 flops
        return sink == sink ? (double)iters * 64.0 / (t - t0) * 1e-9 : 0;
    } else {
        float32x4_t m = vdupq_n_f32(0.9999f), c = vdupq_n_f32(1e-5f);
        float32x4_t a0 = vdupq_n_f32(1.0f), a1 = vdupq_n_f32(1.1f), a2 = vdupq_n_f32(1.2f),
                    a3 = vdupq_n_f32(1.3f), a4 = vdupq_n_f32(1.4f), a5 = vdupq_n_f32(1.5f),
                    a6 = vdupq_n_f32(1.6f), a7 = vdupq_n_f32(1.7f), a8 = vdupq_n_f32(1.8f),
                    a9 = vdupq_n_f32(1.9f), a10 = vdupq_n_f32(2.0f), a11 = vdupq_n_f32(2.1f),
                    a12 = vdupq_n_f32(2.2f), a13 = vdupq_n_f32(2.3f), a14 = vdupq_n_f32(2.4f),
                    a15 = vdupq_n_f32(2.5f);
        do {
            for (int i = 0; i < 4096; i++) {
                a0 = vfmaq_f32(c, a0, m);   a1 = vfmaq_f32(c, a1, m);
                a2 = vfmaq_f32(c, a2, m);   a3 = vfmaq_f32(c, a3, m);
                a4 = vfmaq_f32(c, a4, m);   a5 = vfmaq_f32(c, a5, m);
                a6 = vfmaq_f32(c, a6, m);   a7 = vfmaq_f32(c, a7, m);
                a8 = vfmaq_f32(c, a8, m);   a9 = vfmaq_f32(c, a9, m);
                a10 = vfmaq_f32(c, a10, m); a11 = vfmaq_f32(c, a11, m);
                a12 = vfmaq_f32(c, a12, m); a13 = vfmaq_f32(c, a13, m);
                a14 = vfmaq_f32(c, a14, m); a15 = vfmaq_f32(c, a15, m);
            }
            iters += 4096;
            t = cb_now();
        } while (t - t0 < seconds);
        float32x4_t s = vaddq_f32(vaddq_f32(vaddq_f32(a0, a1), vaddq_f32(a2, a3)),
                                  vaddq_f32(vaddq_f32(a4, a5), vaddq_f32(a6, a7)));
        s = vaddq_f32(s, vaddq_f32(vaddq_f32(vaddq_f32(a8, a9), vaddq_f32(a10, a11)),
                                   vaddq_f32(vaddq_f32(a12, a13), vaddq_f32(a14, a15))));
        sink = vgetq_lane_f32(s, 0);
        // 16 chains × 4 lanes × 2 flops
        return sink == sink ? (double)iters * 128.0 / (t - t0) * 1e-9 : 0;
    }
#else
    (void)precision; (void)ms;
    return 0;
#endif
}

// ── Memory ──────────────────────────────────────────────────────────────

/// STREAM's triad, a[i] = b[i] + s·c[i], counted as STREAM counts it: 24
/// bytes an element (two reads and a write, no write-allocate traffic).
CB_EXPORT double cb_cpu_triad_gbs(int megabytes, int ms) {
    if (ms < 0) return 0;
    size_t n = (size_t)(megabytes > 0 ? megabytes : 64) * (1u << 20) / sizeof(double);
    double *a = malloc(n * sizeof(double)), *b = malloc(n * sizeof(double)),
           *c = malloc(n * sizeof(double));
    if (!a || !b || !c) { free(a); free(b); free(c); return 0; }
    for (size_t i = 0; i < n; i++) { a[i] = 0; b[i] = (double)(i & 1023); c[i] = 1.0; }
    const double s = 3.0;
    for (size_t i = 0; i < n; i++) a[i] = b[i] + s * c[i];   // first touch, not timed
    double seconds = (ms > 0 ? ms : 300) * 1e-3, best = 0, deadline = cb_now() + seconds;
    do {
        double t0 = cb_now();
        for (size_t i = 0; i < n; i++) a[i] = b[i] + s * c[i];
        double dt = cb_now() - t0;
        double gbs = 24.0 * (double)n / dt * 1e-9;
        if (gbs > best) best = gbs;
    } while (cb_now() < deadline);
    double check = a[n / 2];
    free(a); free(b); free(c);
    return check == check ? best : 0;
}

/// The cache lines of `kilobytes` of memory in a shuffled order, each
/// pointing at the next (one cycle through all of them, so no prefetcher
/// can guess the next line), followed one dependent load at a time: each
/// load's address is the last load's value.
CB_EXPORT double cb_cpu_latency_ns(int kilobytes, int ms) {
    if (ms < 0) return 0;
    size_t lines = (size_t)(kilobytes > 0 ? kilobytes : 64) * 1024 / 64;
    if (lines < 2) lines = 2;
    void **mem = NULL;
    if (posix_memalign((void **)&mem, 128, lines * 64) != 0) return 0;
    uint32_t *order = malloc(lines * sizeof(uint32_t));
    if (!order) { free(mem); return 0; }
    for (size_t i = 0; i < lines; i++) order[i] = (uint32_t)i;
    uint64_t seed = 0x9E3779B97F4A7C15ull;
    for (size_t i = lines - 1; i > 0; i--) {
        seed ^= seed >> 12; seed ^= seed << 25; seed ^= seed >> 27;
        size_t j = (size_t)((seed * 2685821657736338717ull) % (i + 1));
        uint32_t t = order[i]; order[i] = order[j]; order[j] = t;
    }
    const size_t stride = 64 / sizeof(void *);
    for (size_t i = 0; i < lines; i++)
        mem[(size_t)order[i] * stride] = &mem[(size_t)order[(i + 1) % lines] * stride];
    free(order);

    void **p = mem;
    for (size_t i = 0; i < lines; i++) p = (void **)*p;   // warm
    double seconds = (ms > 0 ? ms : 200) * 1e-3, t0 = cb_now(), t;
    uint64_t loads = 0;
    do {
        for (int i = 0; i < 1 << 16; i++) p = (void **)*p;
        loads += 1 << 16;
        t = cb_now();
    } while (t - t0 < seconds);
    double ns = (t - t0) / (double)loads * 1e9;
    int ok = p != NULL;
    free(mem);
    return ok ? ns : 0;
}
