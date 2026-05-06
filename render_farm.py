"""Render Farm (F-12)
====================

Split a Manim scene at ``self.wait()`` boundaries, render each fragment in
a separate subprocess, then stitch the outputs back together with ffmpeg.

**v1 scope (what ships):**
- AST-based splitter that finds ``self.wait()`` calls inside the target
  scene's ``construct()`` method.
- Conservative safety check: if any ``ValueTracker`` or cross-fragment
  attribute reference is detected, we abort and fall back to single-
  process rendering. (Full flow analysis is a TODO.)
- Local worker pool (N = settings.farm.workers_local). Each worker gets a
  synthesised scene file containing only the fragment's play calls.
- Progress reported via a module-level ``STATE`` dict queried by the
  frontend via ``farm_status()``.
- ffmpeg concat demuxer merger — lossless as long as codecs match.

**Non-scope (TODO):**
- SSH remote workers (the spec's ``[[workers]] remote`` array).
- Narration/subtitle retiming (falls through to single-process if narrate).
- Frame-offset in filenames (we use fragment index → ordered concat).

Public entry points:

    farm_render(scene_file, output_path, quality, fps, scene_name)
        kicks off the split+dispatch+merge pipeline in a background thread.
    farm_status() -> dict
    farm_cancel()
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Optional


# Shared module state (one active farm job at a time; safe for this UI).
STATE = {
    'active': False,
    'step': 'idle',   # fragments | concat | narration | done | error
    'message': '',
    'fragments': [],
    'output': None,
    'error': None,
    'started_at': 0.0,
    'job_id': None,
}
_LOCK = threading.Lock()
_CANCEL = threading.Event()

_FALLBACK_REASONS = {
    'value_tracker': 'ValueTracker detected; cross-fragment state is unsafe',
    'narration': 'narrate() detected; audio retiming not supported in farm v1',
    'no_splits': 'no self.wait() boundaries found',
    'single_fragment': 'only one fragment after split — no parallelism benefit',
    'gpu': 'GPU renderer — fragment processes serialise on the GPU anyway',
    'lib_missing': 'required library missing (ffmpeg)',
}


# ──────────────────────────────────────────────────────────────────
# Splitter
# ──────────────────────────────────────────────────────────────────

class _PlayCall:
    __slots__ = ('kind', 'line_start', 'line_end', 'source', 'run_time')

    def __init__(self, kind, line_start, line_end, source, run_time):
        self.kind = kind
        self.line_start = line_start
        self.line_end = line_end
        self.source = source
        self.run_time = run_time


def _find_scene_class(tree: ast.AST, scene_name: Optional[str]) -> Optional[ast.ClassDef]:
    candidates = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if scene_name:
        for c in candidates:
            if c.name == scene_name:
                return c
    # Fallback: first class with a construct method
    for c in candidates:
        if any(isinstance(m, ast.FunctionDef) and m.name == 'construct'
               for m in c.body):
            return c
    return None


def _collect_statements(construct: ast.FunctionDef, source_lines: list):
    """Return a list of dicts describing top-level statements inside
    construct(), with their source and kind classification."""
    out = []
    for node in construct.body:
        src_segment = ast.get_source_segment('\n'.join(source_lines), node) or ''
        kind = 'other'
        run_time = None
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            attr = _attr_chain(call.func)
            if attr.endswith('.wait'):
                kind = 'wait'
                run_time = _extract_numeric_arg(call, 0) or 1.0
            elif attr.endswith('.play'):
                kind = 'play'
                run_time = _extract_kwarg(call, 'run_time') or 1.0
            elif attr == 'narrate' or attr.endswith('.narrate'):
                kind = 'narrate'
        out.append({
            'node': node,
            'kind': kind,
            'source': src_segment,
            'run_time': run_time,
            'line': node.lineno,
        })
    return out


def _attr_chain(node) -> str:
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.insert(0, cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.insert(0, cur.id)
    return '.'.join(parts)


def _extract_numeric_arg(call: ast.Call, index: int):
    if len(call.args) > index and isinstance(call.args[index], (ast.Constant,)):
        v = call.args[index].value
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _detect_cross_fragment_refs(fragments: list) -> set:
    """Return the set of names that are bound in one fragment and referenced
    in a later fragment. If non-empty, the scene can't be split safely."""
    defined = [set() for _ in fragments]
    used = [set() for _ in fragments]
    for i, frag in enumerate(fragments):
        for stmt in frag:
            node = stmt['node']
            for n in ast.walk(node):
                if isinstance(n, ast.Assign):
                    for target in n.targets:
                        if isinstance(target, ast.Name):
                            defined[i].add(target.id)
                elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                    used[i].add(n.id)
    violations = set()
    prior = set()
    for i in range(len(fragments)):
        for name in used[i]:
            if name in prior and name not in defined[i]:
                violations.add(name)
        prior |= defined[i]
    return violations


def _extract_kwarg(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant) \
                and isinstance(kw.value.value, (int, float)):
            return float(kw.value.value)
    return None


def analyse(scene_file: str, scene_name: Optional[str] = None) -> dict:
    """Return either {ok: True, fragments: [...], setup_code: str,
    scene_name, imports} or {ok: False, reason}."""
    with open(scene_file, 'r', encoding='utf-8') as f:
        source = f.read()
    lines = source.split('\n')
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {'ok': False, 'reason': f'syntax error: {e}'}

    # Detect hard-blockers globally
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            attr = _attr_chain(node.func)
            if attr.endswith('ValueTracker') or attr == 'ValueTracker':
                return {'ok': False, 'reason_code': 'value_tracker',
                        'reason': _FALLBACK_REASONS['value_tracker']}
            if attr == 'narrate':
                return {'ok': False, 'reason_code': 'narration',
                        'reason': _FALLBACK_REASONS['narration']}

    cls = _find_scene_class(tree, scene_name)
    if not cls:
        return {'ok': False, 'reason': 'no Scene class with construct() found'}
    construct = next((m for m in cls.body if isinstance(m, ast.FunctionDef)
                      and m.name == 'construct'), None)
    if not construct:
        return {'ok': False, 'reason': 'no construct() method'}

    stmts = _collect_statements(construct, lines)

    # Split at every wait().
    fragments = []
    cur = []
    for s in stmts:
        cur.append(s)
        if s['kind'] == 'wait':
            fragments.append(cur)
            cur = []
    if cur:
        fragments.append(cur)

    fragments = [frag for frag in fragments if frag]
    if len(fragments) < 2:
        return {'ok': False, 'reason_code': 'single_fragment',
                'reason': _FALLBACK_REASONS['single_fragment']}

    # v1 safety: if any name bound inside construct() is referenced in a
    # later fragment, we bail. Full dataflow would fix this, but naively
    # splitting a scene that shares state across waits would produce
    # duplicated play calls in each fragment's file. See module docstring.
    cross = _detect_cross_fragment_refs(fragments)
    if cross:
        return {'ok': False, 'reason_code': 'cross_state',
                'reason': f"cross-fragment state: {', '.join(sorted(cross)[:4])}"}

    # Preserve everything outside construct() as the setup header: imports,
    # top-level code, class header, any methods other than construct.
    header_end = construct.lineno - 1  # 1-based → slice index
    header_src = '\n'.join(lines[:header_end])
    # The class body outside construct (other methods, class attrs).
    other_methods_src = []
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'construct':
            continue
        src = ast.get_source_segment(source, node)
        if src:
            other_methods_src.append(src)

    return {
        'ok': True,
        'scene_name': cls.name,
        'header_src': header_src,
        'class_other_src': '\n\n'.join(other_methods_src),
        'fragments': [
            {
                'index': i,
                'statements': [{'kind': s['kind'], 'source': s['source'],
                                 'line': s['line'], 'run_time': s['run_time']}
                                for s in frag],
                'estimated_duration': sum((s['run_time'] or 1.0) for s in frag),
            }
            for i, frag in enumerate(fragments)
        ],
    }


def _build_fragment_file(out_dir: str, idx: int, analysis: dict) -> str:
    """Materialise a mini scene.py containing only this fragment's
    statements. We prepend the header (imports etc.) and a stripped class
    with construct() containing just the fragment body."""
    frag = analysis['fragments'][idx]
    body_lines = [s['source'] for s in frag['statements']]
    # Indent by 8 spaces (inside class → inside def construct).
    body_indented = '\n'.join(
        '\n'.join('        ' + ln for ln in block.split('\n')) for block in body_lines
    )
    scene_name = f"{analysis['scene_name']}_Frag{idx}"
    class_src = (
        f"\n\nclass {scene_name}(Scene):\n"
        f"    def construct(self):\n"
        f"{body_indented or '        pass'}\n"
    )
    file_path = os.path.join(out_dir, f'frag_{idx:03d}.py')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(analysis['header_src'])
        f.write(class_src)
    return file_path


# ──────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────

def _render_fragment(scene_file: str, scene_name: str, quality_flag: str,
                     fps: int, manim_cmd: list, out_dir: str,
                     on_progress) -> dict:
    """Blocking render of one fragment. Returns {ok, video, error?}."""
    cmd = list(manim_cmd) + [
        quality_flag, '--fps', str(fps),
        '--output_file', f'{scene_name}.mp4',
        '--media_dir', out_dir,
        '--disable_caching',
        scene_file, scene_name,
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            bufsize=1,
        )
        prog = re.compile(r'(\d+)\s*%')
        for line in proc.stdout or []:
            if _CANCEL.is_set():
                proc.kill()
                return {'ok': False, 'error': 'cancelled'}
            m = prog.search(line)
            if m:
                try:
                    on_progress(int(m.group(1)) / 100.0)
                except Exception:
                    pass
        rc = proc.wait()
        if rc != 0:
            return {'ok': False, 'error': f'manim exited {rc}'}
        # Locate the output
        for root, _, files in os.walk(out_dir):
            for f in files:
                if f.endswith('.mp4') and scene_name in f:
                    return {'ok': True, 'video': os.path.join(root, f)}
        return {'ok': False, 'error': 'output mp4 not found'}
    except FileNotFoundError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _merge(fragment_videos: list, output_path: str) -> dict:
    """ffmpeg concat demuxer — lossless when all fragments share codec."""
    if not fragment_videos:
        return {'ok': False, 'error': 'no fragments to merge'}
    if shutil.which('ffmpeg') is None:
        return {'ok': False, 'error': 'ffmpeg not on PATH'}
    tmp_list = tempfile.NamedTemporaryFile(
        mode='w', delete=False, suffix='.txt', encoding='utf-8')
    try:
        for v in fragment_videos:
            tmp_list.write(f"file '{v.replace(chr(92), '/')}'\n")
        tmp_list.close()
        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
               '-i', tmp_list.name, '-c', 'copy', output_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return {'ok': False, 'error': (proc.stderr or '')[-400:]}
        return {'ok': True, 'output': output_path}
    finally:
        try: os.unlink(tmp_list.name)
        except OSError: pass


def farm_status() -> dict:
    with _LOCK:
        return {
            'status': 'ok',
            'active': STATE['active'],
            'step': STATE['step'],
            'message': STATE['message'],
            'fragments': list(STATE['fragments']),
            'output': STATE['output'],
            'error': STATE['error'],
        }


def farm_cancel() -> dict:
    _CANCEL.set()
    with _LOCK:
        STATE['message'] = 'Cancelling…'
    return {'status': 'ok'}


def farm_render(scene_file: str, output_path: str, quality_flag: str = '-qm',
                fps: int = 30, scene_name: Optional[str] = None,
                manim_cmd: Optional[list] = None,
                workers: int = 4) -> dict:
    """Entry point. Runs async in a background thread. Returns immediately
    with {status: 'started', job_id} or {status: 'fallback', reason} if
    the scene can't be split safely."""
    analysis = analyse(scene_file, scene_name)
    if not analysis.get('ok'):
        return {'status': 'fallback', 'reason': analysis.get('reason'),
                'reason_code': analysis.get('reason_code', 'other')}

    manim_cmd = manim_cmd or ['manim']
    job_id = uuid.uuid4().hex[:10]
    work_dir = os.path.join(tempfile.gettempdir(), f'manim_farm_{job_id}')
    os.makedirs(work_dir, exist_ok=True)

    _CANCEL.clear()
    with _LOCK:
        STATE.update({
            'active': True,
            'step': 'fragments',
            'message': f'Rendering {len(analysis["fragments"])} fragments…',
            'fragments': [
                {'id': f'f{i:03d}', 'name': f'Fragment {i + 1}',
                 'progress': 0, 'eta': '', 'status': 'pending'}
                for i in range(len(analysis['fragments']))
            ],
            'output': None, 'error': None,
            'started_at': time.time(), 'job_id': job_id,
        })

    def _run():
        try:
            fragment_files = []
            for i in range(len(analysis['fragments'])):
                fragment_files.append(_build_fragment_file(work_dir, i, analysis))

            # Parallel render with a small thread-pool (subprocess is CPU-bound,
            # but ffmpeg within the subprocess is already multi-threaded, so
            # we keep the pool modest).
            sem = threading.Semaphore(max(1, workers))
            videos = [None] * len(fragment_files)
            errors = []

            def _worker(i, path):
                with sem:
                    if _CANCEL.is_set():
                        return
                    def on_progress(p):
                        with _LOCK:
                            STATE['fragments'][i]['progress'] = p
                            STATE['fragments'][i]['status'] = 'running'
                    scene = f"{analysis['scene_name']}_Frag{i}"
                    res = _render_fragment(
                        path, scene, quality_flag, fps, manim_cmd,
                        os.path.join(work_dir, f'out_{i:03d}'),
                        on_progress,
                    )
                    with _LOCK:
                        if res.get('ok'):
                            videos[i] = res['video']
                            STATE['fragments'][i]['progress'] = 1.0
                            STATE['fragments'][i]['status'] = 'done'
                        else:
                            errors.append(f'frag {i}: {res.get("error")}')
                            STATE['fragments'][i]['status'] = 'error'

            threads = [threading.Thread(target=_worker, args=(i, p), daemon=True)
                       for i, p in enumerate(fragment_files)]
            for t in threads: t.start()
            for t in threads: t.join()

            if _CANCEL.is_set():
                with _LOCK:
                    STATE.update({'active': False, 'step': 'error',
                                  'message': 'Cancelled', 'error': 'cancelled'})
                return
            if errors:
                with _LOCK:
                    STATE.update({'active': False, 'step': 'error',
                                  'message': '; '.join(errors)[:400],
                                  'error': errors[0]})
                return

            # Concat
            with _LOCK:
                STATE['step'] = 'concat'
                STATE['message'] = 'Merging fragments via ffmpeg…'
            merge_res = _merge([v for v in videos if v], output_path)
            if not merge_res.get('ok'):
                with _LOCK:
                    STATE.update({'active': False, 'step': 'error',
                                  'message': merge_res.get('error', ''),
                                  'error': merge_res.get('error')})
                return

            # (narration step is a TODO — we skip straight to done.)
            with _LOCK:
                STATE['step'] = 'narration'
                STATE['message'] = 'Skipping narration (v1)'
            time.sleep(0.2)

            with _LOCK:
                STATE.update({
                    'active': False, 'step': 'done',
                    'message': f'Done: {output_path}',
                    'output': output_path,
                })

            # Keep work_dir for inspection; pruned lazily on next job.
            _prune_old_farm_dirs()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f'[FARM] error: {tb}')
            with _LOCK:
                STATE.update({'active': False, 'step': 'error',
                              'message': str(e)[:200], 'error': str(e)})

    threading.Thread(target=_run, daemon=True).start()
    return {'status': 'started', 'job_id': job_id,
            'fragments': len(analysis['fragments'])}


def _prune_old_farm_dirs(keep: int = 3):
    tmp = tempfile.gettempdir()
    try:
        dirs = [os.path.join(tmp, d) for d in os.listdir(tmp)
                if d.startswith('manim_farm_')]
        dirs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for d in dirs[keep:]:
            shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass
