//
//  cb_bench.h — the native workloads behind the terminal's `spec`, `cpu-z`
//  and `gpu-z` commands.
//
//  Python reaches these through ctypes.CDLL(None) (the main executable's
//  exports), like cb_metal_matmul_ex. Every workload is plain C, reentrant
//  (no global mutable state: `spec --rate` runs one copy per thread), and
//  deterministic (its own PRNG, fixed seeds), so its answer can be checked
//  the way a benchmark harness checks one.
//

#ifndef CB_BENCH_H
#define CB_BENCH_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/// What one run of a workload produced.
typedef struct {
    /// Integer workloads: an exact digest of the answer (same on every
    /// device). Floating-point workloads may leave it 0 and use `value`.
    uint64_t checksum;
    /// Floating-point workloads: the answer, compared within a relative
    /// tolerance (1e-6). Integer workloads may report a count here too.
    double value;
    /// How much work was done, in `unit`s (nodes searched, cells updated,
    /// bytes compressed…), for a per-second readout.
    double work;
    /// The unit of `work`, a static string ("nodes", "cell updates", "MB").
    const char *unit;
} cb_bench_result;

/// One workload. `size`: 1 quick, 2 standard, 3 large. Returns 0 on
/// success; nonzero when it could not run (out of memory, a library
/// missing), with nothing written to `out` that matters.
typedef int (*cb_bench_fn)(int size, cb_bench_result *out);

// ── The suite table (cb_bench_core.c) ───────────────────────────────────

/// How many workloads are built in.
int cb_spec_count(void);
/// Workload `index`'s id ("chess", "lbm", …), or NULL past the end.
const char *cb_spec_id(int index);
/// Runs workload `id` at `size`. 0 on success; -1 unknown id; else the
/// workload's own failure code.
int cb_spec_run(const char *id, int size, cb_bench_result *out);

// ── cpu-z's micro-benchmarks (cb_bench_cpu.c) ───────────────────────────
// Each returns 0 at once for a negative `ms` (the keep-alive's call).

/// A performance core's clock in GHz, from a chain of dependent integer
/// adds (one per cycle on every Apple core), over about `ms` milliseconds.
double cb_cpu_clock_ghz(int ms);
/// FP throughput of one core in GFLOPS: `precision` 32 or 64, NEON FMA
/// on independent accumulators, over about `ms` milliseconds.
double cb_cpu_fma_gflops(int precision, int ms);
/// STREAM triad bandwidth (a[i] = b[i] + s*c[i]) of one thread, in GB/s,
/// over arrays of `megabytes` each.
double cb_cpu_triad_gbs(int megabytes, int ms);
/// Load-to-use latency in nanoseconds of a random pointer chase through
/// `kilobytes` of memory.
double cb_cpu_latency_ns(int kilobytes, int ms);

// ── The workloads ───────────────────────────────────────────────────────
// Integer, the classic kinds (cb_bench_int_a.c)
int cbk_interp(int size, cb_bench_result *out);
int cbk_compile(int size, cb_bench_result *out);
int cbk_mcf(int size, cb_bench_result *out);
int cbk_eventsim(int size, cb_bench_result *out);
int cbk_xml(int size, cb_bench_result *out);
int cbk_video(int size, cb_bench_result *out);
int cbk_chess(int size, cb_bench_result *out);
int cbk_nnue(int size, cb_bench_result *out);
int cbk_go(int size, cb_bench_result *out);
int cbk_sudoku(int size, cb_bench_result *out);
int cbk_lzma(int size, cb_bench_result *out);
int cbk_lzfast(int size, cb_bench_result *out);
// Integer, the newer kinds (cb_bench_int_b.c)
int cbk_othello(int size, cb_bench_result *out);
int cbk_sql(int size, cb_bench_result *out);
int cbk_lint(int size, cb_bench_result *out);
int cbk_sat(int size, cb_bench_result *out);
int cbk_placeroute(int size, cb_bench_result *out);
int cbk_archsim(int size, cb_bench_result *out);
int cbk_ntt(int size, cb_bench_result *out);
int cbk_bfs(int size, cb_bench_result *out);
int cbk_align(int size, cb_bench_result *out);
int cbk_csp(int size, cb_bench_result *out);
int cbk_flac(int size, cb_bench_result *out);
// Floating point, simulation (cb_bench_fp_a.c)
int cbk_lbm(int size, cb_bench_result *out);
int cbk_md(int size, cb_bench_result *out);
int cbk_raytrace(int size, cb_bench_result *out);
int cbk_fdtd(int size, cb_bench_result *out);
int cbk_cg(int size, cb_bench_result *out);
int cbk_stencil(int size, cb_bench_result *out);
int cbk_imagefilter(int size, cb_bench_result *out);
int cbk_shallow(int size, cb_bench_result *out);
int cbk_neutron(int size, cb_bench_result *out);
// Floating point, newer kinds (cb_bench_fp_b.c)
int cbk_astc(int size, cb_bench_result *out);
int cbk_color(int size, cb_bench_result *out);
int cbk_delaunay(int size, cb_bench_result *out);
int cbk_flight(int size, cb_bench_result *out);
int cbk_snn(int size, cb_bench_result *out);
int cbk_transformer(int size, cb_bench_result *out);
int cbk_sph(int size, cb_bench_result *out);
int cbk_hydro(int size, cb_bench_result *out);
// Integer, one program each (cb_bench_int_c.c)
int cbk_llvm(int size, cb_bench_result *out);
int cbk_ns3(int size, cb_bench_result *out);
int cbk_perl(int size, cb_bench_result *out);
// Floating point, one program each (cb_bench_fp_c.c)
int cbk_roms(int size, cb_bench_result *out);
int cbk_palm(int size, cb_bench_result *out);
int cbk_cam4(int size, cb_bench_result *out);
int cbk_bwaves(int size, cb_bench_result *out);
int cbk_fem(int size, cb_bench_result *out);

#ifdef __cplusplus
}
#endif

#endif
