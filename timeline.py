"""Timeline (F-01) — parse ``construct()`` into a track-per-mobject model,
apply retime edits back to source.

**v1 scope:**
- Parse top-level statements inside ``construct()``; emit one track per
  "primary mobject" of each ``self.play()`` call.
- Detect ``self.wait()`` and ``narrate()`` as special tracks.
- ``apply_edits`` handles ``retime`` edits (updates ``run_time=``);
  reorder edits are rejected with a ``unsafe`` reason.

**v1 non-scope (TODO):**
- Reorder + dependency analysis (spec's "dirty, needs review" state).
- File-watcher two-way binding (caller is expected to reparse manually).
- Camera-move / non-play tracks.
"""

from __future__ import annotations

import ast
import re
from typing import Optional


_DEFAULT_RUN_TIME = 1.0
_DEFAULT_WAIT = 1.0


def _attr_chain(node) -> str:
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.insert(0, cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.insert(0, cur.id)
    return '.'.join(parts)


def _primary_mobject(call: ast.Call) -> str:
    """Guess the primary mobject touched by a play call. For ``play(Create(c))``
    that's ``c``. For ``play(Transform(a, b))`` that's ``a``. Falls back to
    the animation's class name if no obvious mobject is found."""
    for arg in call.args:
        if isinstance(arg, ast.Call):
            # Walk into the animation wrapper (Create / Transform / etc.)
            for inner in arg.args:
                if isinstance(inner, ast.Name):
                    return inner.id
                if isinstance(inner, ast.Attribute):
                    return _attr_chain(inner)
            f_name = _attr_chain(arg.func)
            if f_name:
                return f_name.split('.')[-1]
        elif isinstance(arg, ast.Name):
            return arg.id
        elif isinstance(arg, ast.Attribute):
            return _attr_chain(arg)
    return 'anonymous'


def _animation_kind(call: ast.Call) -> str:
    """Best-effort animation class name for colour-coding the bar."""
    for arg in call.args:
        if isinstance(arg, ast.Call):
            name = _attr_chain(arg.func).split('.')[-1]
            if name:
                return name
    return 'Play'


def _extract_run_time(call: ast.Call) -> float:
    for kw in call.keywords:
        if kw.arg == 'run_time' and isinstance(kw.value, ast.Constant) \
                and isinstance(kw.value.value, (int, float)):
            return float(kw.value.value)
    return _DEFAULT_RUN_TIME


def _extract_wait_duration(call: ast.Call) -> float:
    if call.args and isinstance(call.args[0], ast.Constant) \
            and isinstance(call.args[0].value, (int, float)):
        return float(call.args[0].value)
    return _DEFAULT_WAIT


def parse(scene_file: str, scene_name: Optional[str] = None) -> dict:
    """Return {status, model?, message?}."""
    try:
        with open(scene_file, 'r', encoding='utf-8') as f:
            source = f.read()
    except OSError as e:
        return {'status': 'error', 'message': str(e)}

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {'status': 'error', 'message': f'syntax error: {e}'}

    # Find the target Scene class.
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    cls = None
    if scene_name:
        cls = next((c for c in classes if c.name == scene_name), None)
    if cls is None:
        for c in classes:
            if any(isinstance(m, ast.FunctionDef) and m.name == 'construct'
                   for m in c.body):
                cls = c
                break
    if cls is None:
        return {'status': 'error', 'message': 'no Scene class with construct()'}
    construct = next((m for m in cls.body if isinstance(m, ast.FunctionDef)
                      and m.name == 'construct'), None)
    if not construct:
        return {'status': 'error', 'message': 'no construct()'}

    # Walk top-level statements.
    cursor = 0.0
    bar_seq = 0
    tracks = {}  # id -> {label, kind, bars}
    for stmt in construct.body:
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
            continue
        call = stmt.value
        attr = _attr_chain(call.func)
        if attr.endswith('.play'):
            obj = _primary_mobject(call)
            kind = _animation_kind(call)
            rt = _extract_run_time(call)
            bar_id = f'b{bar_seq}'
            bar_seq += 1
            track_id = f'mo:{obj}'
            tracks.setdefault(track_id, {
                'id': track_id, 'label': obj, 'bars': [], 'kind': 'mobject',
            })
            tracks[track_id]['bars'].append({
                'id': bar_id, 'kind': kind,
                'start': round(cursor, 3), 'run_time': rt,
                'line': stmt.lineno,
                'call_col': call.col_offset,
                'end_line': getattr(stmt, 'end_lineno', stmt.lineno),
            })
            cursor += rt
        elif attr.endswith('.wait'):
            wt = _extract_wait_duration(call)
            bar_id = f'b{bar_seq}'
            bar_seq += 1
            tracks.setdefault('wait', {'id': 'wait', 'label': '⟨wait⟩',
                                        'bars': [], 'kind': 'wait'})
            tracks['wait']['bars'].append({
                'id': bar_id, 'kind': 'Wait',
                'start': round(cursor, 3), 'run_time': wt,
                'line': stmt.lineno,
                'end_line': getattr(stmt, 'end_lineno', stmt.lineno),
            })
            cursor += wt
        elif attr == 'narrate' or attr.endswith('.narrate'):
            bar_id = f'b{bar_seq}'
            bar_seq += 1
            tracks.setdefault('narrate', {'id': 'narrate',
                                           'label': '⟨narrate⟩',
                                           'bars': [], 'kind': 'narrate'})
            tracks['narrate']['bars'].append({
                'id': bar_id, 'kind': 'Narrate',
                'start': round(cursor, 3), 'run_time': 0.0,
                'line': stmt.lineno,
                'end_line': getattr(stmt, 'end_lineno', stmt.lineno),
            })

    return {
        'status': 'ok',
        'model': {
            'scene': cls.name,
            'total_duration': round(cursor, 3),
            'tracks': list(tracks.values()),
        },
    }


# ── Retime mutation ──────────────────────────────────────────────

_RUNTIME_KW = re.compile(r'run_time\s*=\s*([\d]+(?:\.\d+)?)')
_WAIT_CALL = re.compile(r'self\.wait\s*\(\s*([\d]+(?:\.\d+)?)?\s*\)')


def _rewrite_line_run_time(line: str, new_rt: float) -> Optional[str]:
    """Mutate a `run_time=X` kwarg on this line, preserving decimals.
    Returns the new line or None if the pattern wasn't found."""
    m = _RUNTIME_KW.search(line)
    if not m:
        return None
    old = m.group(1)
    decimals = len(old.split('.')[1]) if '.' in old else 0
    new_val = f'{new_rt:.{max(decimals, 1)}f}' if decimals else f'{int(round(new_rt))}'
    return line[:m.start(1)] + new_val + line[m.end(1):]


def _rewrite_line_wait(line: str, new_rt: float) -> Optional[str]:
    """Mutate `self.wait(...)` on this line."""
    m = _WAIT_CALL.search(line)
    if not m:
        return None
    old = m.group(1)
    decimals = len(old.split('.')[1]) if old and '.' in old else 0
    new_val = f'{new_rt:.{max(decimals, 1)}f}' if decimals else f'{new_rt:g}'
    if old is None:
        return line[:m.end(0) - 1] + f'{new_val}' + line[m.end(0) - 1:]
    return line[:m.start(1)] + new_val + line[m.end(1):]


def parse_string(source: str, scene_name: Optional[str] = None) -> dict:
    """Same as ``parse`` but takes the source code directly instead of a
    file path. Lets the caller work with an unsaved editor buffer with
    no disk I/O."""
    import tempfile, os as _os
    fd, p = tempfile.mkstemp(suffix='.py')
    try:
        with _os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(source)
        return parse(p, scene_name)
    finally:
        try: _os.unlink(p)
        except OSError: pass


def apply_edits_to_source(source: str, edits: list) -> dict:
    """Pure-string variant of ``apply_edits``. Applies retime edits to
    the given source code, returns ``{status, code, applied, rejected}``
    with the updated code. No disk I/O. Use this when the caller is
    already managing the editor buffer."""
    parse_res = parse_string(source)
    if parse_res.get('status') != 'ok':
        return parse_res
    model = parse_res['model']

    bars = {}
    for t in model['tracks']:
        for b in t['bars']:
            bars[b['id']] = (b, t)

    lines = source.split('\n')
    applied = 0
    rejected = []
    for edit in edits or []:
        bid = edit.get('id')
        kind = edit.get('kind')
        bar_info = bars.get(bid)
        if not bar_info:
            rejected.append({'id': bid, 'reason': 'bar not found'}); continue
        bar, track = bar_info
        if kind == 'retime':
            try:
                rt = float(edit.get('run_time', bar['run_time']))
            except (TypeError, ValueError):
                rejected.append({'id': bid, 'reason': 'invalid run_time'}); continue
            line_idx = bar['line'] - 1
            if line_idx < 0 or line_idx >= len(lines):
                rejected.append({'id': bid, 'reason': 'line out of range'}); continue
            if track['kind'] == 'wait':
                new_line = _rewrite_line_wait(lines[line_idx], rt)
                if new_line is None:
                    rejected.append({'id': bid, 'reason': 'pattern not found'}); continue
                lines[line_idx] = new_line
                applied += 1
            else:
                end = bar.get('end_line', bar['line'])
                placed = False
                for i in range(line_idx, min(len(lines), end)):
                    nl = _rewrite_line_run_time(lines[i], rt)
                    if nl is not None:
                        lines[i] = nl
                        placed = True; break
                if not placed:
                    nl = _append_run_time_kwarg(lines, line_idx, end, rt)
                    if nl is None:
                        rejected.append({'id': bid, 'reason': 'cannot place run_time'}); continue
                applied += 1
        elif kind == 'reorder':
            rejected.append({'id': bid, 'reason': 'reorder not supported in v1'})
        else:
            rejected.append({'id': bid, 'reason': f'unknown kind: {kind}'})

    new_source = '\n'.join(lines)
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        return {'status': 'error', 'message': f'result would break syntax: {e}'}
    return {'status': 'ok', 'code': new_source,
            'applied': applied, 'rejected': rejected}


def apply_edits(scene_file: str, edits: list) -> dict:
    """Apply a list of edits. Each edit is:
        {id, kind: 'retime', run_time: float}    — updates `run_time=` or wait arg
        {id, kind: 'reorder', ...}               — v1 rejects (needs dep check)
    ``id`` matches the ``bar.id`` returned by ``parse()``; callers MUST
    reparse after applying because bar IDs are regenerated each parse."""
    parse_res = parse(scene_file)
    if parse_res.get('status') != 'ok':
        return parse_res
    model = parse_res['model']

    # Build an id → bar map for O(1) lookup.
    bars = {}
    for t in model['tracks']:
        for b in t['bars']:
            bars[b['id']] = (b, t)

    try:
        with open(scene_file, 'r', encoding='utf-8') as f:
            source = f.read()
    except OSError as e:
        return {'status': 'error', 'message': str(e)}
    lines = source.split('\n')

    applied = 0
    rejected = []
    for edit in edits or []:
        bid = edit.get('id')
        kind = edit.get('kind')
        bar_info = bars.get(bid)
        if not bar_info:
            rejected.append({'id': bid, 'reason': 'bar not found'})
            continue
        bar, track = bar_info
        if kind == 'retime':
            try:
                rt = float(edit.get('run_time', bar['run_time']))
            except (TypeError, ValueError):
                rejected.append({'id': bid, 'reason': 'invalid run_time'})
                continue
            line_idx = bar['line'] - 1
            if line_idx < 0 or line_idx >= len(lines):
                rejected.append({'id': bid, 'reason': 'line out of range'})
                continue
            if track['kind'] == 'wait':
                new_line = _rewrite_line_wait(lines[line_idx], rt)
            else:
                # Multi-line play calls: search forward for run_time= until
                # the call's end line. If not present, append ", run_time=X".
                new_line = None
                end = bar.get('end_line', bar['line'])
                for i in range(line_idx, min(len(lines), end)):
                    nl = _rewrite_line_run_time(lines[i], rt)
                    if nl is not None:
                        lines[i] = nl
                        new_line = nl
                        break
                if new_line is None:
                    new_line = _append_run_time_kwarg(lines, line_idx, end, rt)
                    if new_line is None:
                        rejected.append({'id': bid, 'reason': 'cannot place run_time'})
                        continue
                applied += 1
                continue
            if new_line is None:
                rejected.append({'id': bid, 'reason': 'pattern not found'})
                continue
            lines[line_idx] = new_line
            applied += 1
        elif kind == 'reorder':
            rejected.append({'id': bid, 'reason': 'reorder not supported in v1'})
        else:
            rejected.append({'id': bid, 'reason': f'unknown kind: {kind}'})

    new_source = '\n'.join(lines)
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        return {'status': 'error', 'message': f'result would break: {e}'}
    try:
        with open(scene_file, 'w', encoding='utf-8') as f:
            f.write(new_source)
    except OSError as e:
        return {'status': 'error', 'message': str(e)}

    return {'status': 'ok', 'applied': applied, 'rejected': rejected}


def _append_run_time_kwarg(lines: list, start: int, end: int,
                           rt: float) -> Optional[str]:
    """Append ``, run_time=X`` before the closing paren of a play call
    spanning lines[start:end]. Returns the modified line or None."""
    # Locate the final `)` of the call.
    for i in range(min(end - 1, len(lines) - 1), start - 1, -1):
        idx = lines[i].rfind(')')
        if idx >= 0:
            before = lines[i][:idx].rstrip()
            # Avoid leaving "foo(, run_time=X)" — check if there's a prior arg.
            needs_comma = before and not before.endswith('(')
            sep = ', ' if needs_comma else ''
            lines[i] = lines[i][:idx] + f'{sep}run_time={rt:g}' + lines[i][idx:]
            return lines[i]
    return None
