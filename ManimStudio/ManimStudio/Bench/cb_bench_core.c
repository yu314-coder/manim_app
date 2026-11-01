//
//  cb_bench_core.c — the table of workloads `spec` runs, by id.
//
//  Python asks for the ids (cb_spec_count / cb_spec_id), decides which
//  belong to which suite and at what size, and runs each through
//  cb_spec_run with the GIL released (ctypes does that for every foreign
//  call), so `spec --rate N` really is N copies on N cores.
//

#include <string.h>
#include "cb_bench.h"

#define CB_EXPORT __attribute__((used, visibility("default")))

typedef struct {
    const char *id;
    cb_bench_fn fn;
} cb_entry;

static const cb_entry kWorkloads[] = {
    // Integer, the classic kinds
    {"interp", cbk_interp},       {"compile", cbk_compile},
    {"mcf", cbk_mcf},             {"eventsim", cbk_eventsim},
    {"xml", cbk_xml},             {"video", cbk_video},
    {"chess", cbk_chess},         {"go", cbk_go},
    {"sudoku", cbk_sudoku},       {"lzma", cbk_lzma},
    {"lzfast", cbk_lzfast},
    // Integer, the newer kinds
    {"othello", cbk_othello},     {"sql", cbk_sql},
    {"lint", cbk_lint},           {"sat", cbk_sat},
    {"placeroute", cbk_placeroute}, {"archsim", cbk_archsim},
    {"ntt", cbk_ntt},             {"bfs", cbk_bfs},
    {"align", cbk_align},         {"csp", cbk_csp},
    {"flac", cbk_flac},
    // Floating point, simulation
    {"lbm", cbk_lbm},             {"md", cbk_md},
    {"raytrace", cbk_raytrace},   {"fdtd", cbk_fdtd},
    {"cg", cbk_cg},               {"stencil", cbk_stencil},
    {"imagefilter", cbk_imagefilter}, {"shallow", cbk_shallow},
    {"neutron", cbk_neutron},
    // Floating point, newer kinds
    {"astc", cbk_astc},           {"color", cbk_color},
    {"delaunay", cbk_delaunay},   {"flight", cbk_flight},
    {"snn", cbk_snn},             {"transformer", cbk_transformer},
    {"sph", cbk_sph},             {"hydro", cbk_hydro},
};

#define CB_COUNT ((int)(sizeof(kWorkloads) / sizeof(kWorkloads[0])))

CB_EXPORT int cb_spec_count(void) {
    return CB_COUNT;
}

CB_EXPORT const char *cb_spec_id(int index) {
    return (index >= 0 && index < CB_COUNT) ? kWorkloads[index].id : NULL;
}

CB_EXPORT int cb_spec_run(const char *id, int size, cb_bench_result *out) {
    if (id == NULL || out == NULL) return -1;
    for (int i = 0; i < CB_COUNT; i++) {
        if (strcmp(kWorkloads[i].id, id) == 0) {
            memset(out, 0, sizeof *out);
            out->unit = "";
            return kWorkloads[i].fn(size < 1 ? 1 : (size > 3 ? 3 : size), out);
        }
    }
    return -1;
}
