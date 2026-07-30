"""
Scene-class detection for Manim code.
Shared parsing helpers (AST-first, regex fallback) used by cli.py.
"""

import re
import ast


def extract_all_scene_classes(code):
    """Return every Scene-subclass class in ``code`` as
    ``[{name, line, parent}]``. AST-first with a regex fallback so
    partially-edited files still produce useful output.

    Previously the module used ``re.search`` which returned only the
    first match — meaning files with 2+ scenes only ever had the first
    one detected. Fixed April 2026."""

    def _parent_contains_scene(base_node) -> bool:
        if isinstance(base_node, ast.Name):
            return 'Scene' in base_node.id
        if isinstance(base_node, ast.Attribute):
            return 'Scene' in base_node.attr
        if isinstance(base_node, ast.Subscript):
            return _parent_contains_scene(base_node.value)
        if isinstance(base_node, ast.Call):
            return _parent_contains_scene(base_node.func)
        return False

    def _parent_label(base_node) -> str:
        try:
            return ast.unparse(base_node)
        except Exception:
            return '?'

    scenes = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        for m in re.finditer(
                r'^[ \t]*class\s+(\w+)\s*\(([^)]*)\)\s*:',
                code, flags=re.MULTILINE):
            parents = m.group(2)
            if 'Scene' in parents:
                line = code.count('\n', 0, m.start()) + 1
                scenes.append({'name': m.group(1), 'line': line,
                                'parent': parents.strip()})
        return scenes

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if any(_parent_contains_scene(b) for b in node.bases):
            scenes.append({'name': node.name, 'line': node.lineno,
                            'parent': ', '.join(_parent_label(b) for b in node.bases)})
    return scenes
