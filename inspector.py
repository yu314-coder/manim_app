"""Inspector (F-04) — AST-based mobject-kwarg resolver & mutator.

**v1 scope:**
- ``resolve(object_path)`` finds the constructor call in the current file
  and returns editable kwargs (``numeric``, ``color``, or ``readonly``).
- ``mutate(object_path, name, value)`` rewrites the literal in-place,
  preserving surrounding formatting.

We use Python's built-in ``ast`` + ``tokenize`` rather than libcst so the
feature works without extra deps. Formatting preservation is achieved by
operating on source-line byte ranges and splicing in the new literal
without reformatting the rest of the file.

**v1 non-scope (TODO):**
- Preview instrumentation that emits clickable bounding boxes.
- Auto-preview after slider release.
- ValueTracker / expression-based kwarg editing (we currently flag those
  as readonly).
- Rebind-on-source-change: if the user edits the file while the inspector
  is open, the next mutate() will re-resolve and may fail.
"""

from __future__ import annotations

import ast
import re
from typing import Optional


# Manim color constants → hex. Enough to round-trip the common cases.
_MANIM_COLORS = {
    'WHITE': '#FFFFFF', 'BLACK': '#000000', 'GRAY': '#888888', 'GREY': '#888888',
    'RED': '#FC6255', 'RED_A': '#F7A1A3', 'RED_B': '#FF8080', 'RED_C': '#FC6255',
    'RED_D': '#CF5044', 'RED_E': '#9A2525',
    'ORANGE': '#FF862F', 'YELLOW': '#FFFF00', 'YELLOW_A': '#FFF1B6',
    'YELLOW_B': '#FFEA94', 'YELLOW_C': '#FFFF00', 'YELLOW_D': '#F4D345',
    'YELLOW_E': '#E8C11C',
    'GREEN': '#83C167', 'GREEN_A': '#C9E2AE', 'GREEN_B': '#A6CF8C',
    'GREEN_C': '#83C167', 'GREEN_D': '#77B05D', 'GREEN_E': '#699C52',
    'BLUE': '#58C4DD', 'BLUE_A': '#C7E9F1', 'BLUE_B': '#9CDCEB',
    'BLUE_C': '#58C4DD', 'BLUE_D': '#29ABCA', 'BLUE_E': '#236B8E',
    'PURPLE': '#9A72AC', 'PURPLE_A': '#CAA3E8', 'PURPLE_B': '#B189C6',
    'PURPLE_C': '#9A72AC', 'PURPLE_D': '#715582', 'PURPLE_E': '#644172',
    'PINK': '#D147BD', 'MAROON': '#94424F', 'TEAL': '#5CD0B3',
    'GOLD': '#F0AC5F', 'LIGHT_BROWN': '#CD853F', 'DARK_BROWN': '#8B4513',
}
_COLOR_BY_HEX = {v.upper(): k for k, v in _MANIM_COLORS.items()}

# Common geometry kwargs → UI slider ranges. Fall back to (0, 10) if unknown.
_KWARG_RANGES = {
    'radius': (0.05, 10.0), 'stroke_width': (0.0, 30.0),
    'fill_opacity': (0.0, 1.0), 'stroke_opacity': (0.0, 1.0),
    'opacity': (0.0, 1.0), 'width': (0.1, 20.0), 'height': (0.1, 20.0),
    'side_length': (0.1, 20.0), 'scale_factor': (0.1, 5.0),
    'font_size': (8, 144), 'buff': (0.0, 5.0),
    'run_time': (0.1, 10.0), 't': (-5.0, 5.0),
    'x': (-10.0, 10.0), 'y': (-10.0, 10.0), 'z': (-10.0, 10.0),
}
_COLOR_KWARGS = {'color', 'fill_color', 'stroke_color',
                 'background_color', 'sheen_color'}
_GEOMETRY_KWARGS = {'radius', 'stroke_width', 'fill_opacity', 'stroke_opacity',
                    'opacity', 'width', 'height', 'side_length', 'buff',
                    'font_size'}
_TRANSFORM_KWARGS = {'x', 'y', 'z', 'scale_factor', 'run_time', 't'}


def _file_source(path: str) -> Optional[str]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def _source_offset(source: str, lineno: int, col: int) -> int:
    """Convert 1-based line / 0-based col to a byte offset."""
    lines = source.splitlines(keepends=True)
    off = 0
    for i in range(min(lineno - 1, len(lines))):
        off += len(lines[i])
    return off + col


def _kwarg_group(name: str) -> str:
    if name in _COLOR_KWARGS: return 'Color'
    if name in _GEOMETRY_KWARGS: return 'Geometry'
    if name in _TRANSFORM_KWARGS: return 'Transform'
    return 'Other'


def _color_literal_to_hex(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name) and node.id in _MANIM_COLORS:
        return _MANIM_COLORS[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        s = node.value.strip()
        if re.match(r'^#[0-9A-Fa-f]{6}$', s):
            return s.upper()
    return None


def _build_kwarg_descriptor(keyword: ast.keyword) -> Optional[dict]:
    """Classify a kwarg and return a dict the UI can render. Readonly for
    anything we can't safely mutate."""
    name = keyword.arg
    if not name:
        return None
    group = _kwarg_group(name)
    # Numeric literal (int or float).
    if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, (int, float)):
        val = keyword.value.value
        lo, hi = _KWARG_RANGES.get(name, (0, max(10, val * 2 if val else 10)))
        lo = min(lo, val)
        hi = max(hi, val)
        s = repr(val)
        decimals = len(s.split('.')[1]) if '.' in s else 0
        return {
            'name': name, 'type': 'numeric', 'group': group,
            'value': val, 'min': lo, 'max': hi, 'decimals': decimals,
        }
    # Color literal — either a Manim constant or a hex string.
    if name in _COLOR_KWARGS:
        hex_val = _color_literal_to_hex(keyword.value)
        if hex_val:
            return {'name': name, 'type': 'color', 'group': 'Color',
                    'value': hex_val}
    # Everything else: readonly.
    try:
        src = ast.unparse(keyword.value)
    except Exception:
        src = '<expr>'
    return {'name': name, 'type': 'readonly', 'group': group,
            'value': src, 'readonly_reason': 'expression — not inline-editable'}


def resolve(scene_file: str, object_path: str) -> dict:
    """Find the constructor call that assigns to ``object_path`` (e.g.
    ``self.c1`` or ``c1``) and return its editable kwargs."""
    source = _file_source(scene_file)
    if source is None:
        return {'status': 'error', 'message': f'cannot read {scene_file}'}
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {'status': 'error', 'message': f'syntax error: {e}'}

    target_expr = object_path.strip()
    call_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                try:
                    t_src = ast.unparse(t).strip()
                except Exception:
                    continue
                if t_src == target_expr:
                    if isinstance(node.value, ast.Call):
                        call_node = node.value
                        break
        if call_node:
            break

    if not call_node:
        return {'status': 'error',
                'message': f'no constructor call found for `{object_path}`'}

    kwargs = []
    for kw in call_node.keywords:
        desc = _build_kwarg_descriptor(kw)
        if desc:
            kwargs.append(desc)

    try:
        kind = ast.unparse(call_node.func)
    except Exception:
        kind = 'call'

    excerpt_start = max(0, call_node.lineno - 1)
    excerpt_end = min(len(source.splitlines()),
                      getattr(call_node, 'end_lineno', call_node.lineno))
    excerpt = '\n'.join(source.splitlines()[excerpt_start:excerpt_end])

    return {
        'status': 'ok',
        'object_path': object_path,
        'kind': kind,
        'line': call_node.lineno,
        'end_line': getattr(call_node, 'end_lineno', call_node.lineno),
        'kwargs': kwargs,
        'source_excerpt': excerpt,
    }


def _fmt_numeric(value: str, decimals: int) -> str:
    try:
        n = float(value)
    except (ValueError, TypeError):
        return str(value)
    if decimals <= 0:
        if n == int(n):
            return str(int(n))
        return f'{n:.0f}'
    return f'{n:.{decimals}f}'


def _hex_to_manim_color(hex_val: str) -> Optional[str]:
    return _COLOR_BY_HEX.get((hex_val or '').upper())


def mutate(scene_file: str, object_path: str, kwarg_name: str,
           new_value, decimals: int = 2) -> dict:
    """Rewrite the literal for (object_path, kwarg_name) in scene_file.
    Returns {status, source_excerpt?}."""
    source = _file_source(scene_file)
    if source is None:
        return {'status': 'error', 'message': f'cannot read {scene_file}'}
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {'status': 'error', 'message': f'syntax error: {e}'}

    target_expr = object_path.strip()
    keyword_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                try:
                    t_src = ast.unparse(t).strip()
                except Exception:
                    continue
                if t_src == target_expr and isinstance(node.value, ast.Call):
                    for kw in node.value.keywords:
                        if kw.arg == kwarg_name:
                            keyword_node = kw
                            break
            if keyword_node:
                break
        if keyword_node:
            break

    if not keyword_node:
        return {'status': 'error',
                'message': f'kwarg `{kwarg_name}` not found on `{object_path}`'}

    # Build the new literal text.
    value_node = keyword_node.value
    if isinstance(value_node, ast.Constant) and isinstance(value_node.value, (int, float)):
        new_literal = _fmt_numeric(new_value, decimals)
    elif kwarg_name in _COLOR_KWARGS:
        # Prefer a Manim color constant if the hex matches; else a hex string.
        named = _hex_to_manim_color(new_value)
        new_literal = named if named else f'"{str(new_value).upper()}"'
    else:
        return {'status': 'error',
                'message': 'value-type not editable'}

    # Splice into the source.
    start_line = value_node.lineno
    start_col = value_node.col_offset
    end_line = getattr(value_node, 'end_lineno', start_line)
    end_col = getattr(value_node, 'end_col_offset', start_col + 1)

    start_off = _source_offset(source, start_line, start_col)
    end_off = _source_offset(source, end_line, end_col)

    new_source = source[:start_off] + new_literal + source[end_off:]

    # Parse-check before writing so we never leave the file broken.
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        return {'status': 'error',
                'message': f'refusing to write — result would break syntax: {e}'}

    try:
        with open(scene_file, 'w', encoding='utf-8') as f:
            f.write(new_source)
    except OSError as e:
        return {'status': 'error', 'message': str(e)}

    return {
        'status': 'ok',
        'new_literal': new_literal,
        'source_excerpt': '\n'.join(new_source.splitlines()[
            max(0, start_line - 1):max(1, end_line)]),
    }
