"""
ManimStudio CLI & MCP Server
Headless rendering and MCP tool server for Codex integration.
Uses the same venv (manim_studio_default) and quality presets as the GUI.

Usage:
  ManimStudio render <file> [options]    Render a Manim scene headlessly
  ManimStudio validate <file>            Check scene code for syntax errors
  ManimStudio mcp                        Start MCP server (stdio, for Codex)
  ManimStudio presets                    List quality presets
"""

import os
import sys
import json
import time
import re
import subprocess
import argparse
import ast

# ── Shared constants (same values as app.py) ──
USER_DATA_DIR = os.path.join(os.path.expanduser('~'), '.manim_studio')
VENV_DIR = os.path.join(USER_DATA_DIR, 'venvs', 'manim_studio_default')
ASSETS_DIR = os.path.join(USER_DATA_DIR, 'assets')
MEDIA_DIR = os.path.join(USER_DATA_DIR, 'media')
RENDER_DIR = os.path.join(USER_DATA_DIR, 'render')

QUALITY_PRESETS = {
    "120p": ("-ql", 214, 120),
    "240p": ("-ql", 426, 240),
    "480p": ("-ql", 854, 480),
    "720p": ("-qm", 1280, 720),
    "1080p": ("-qh", 1920, 1080),
    "1440p": ("-qp", 2560, 1440),
    "4K": ("-qk", 3840, 2160),
    "8K": ("-qk", 7680, 4320),
}

APP_VERSION = "1.1.2.0"


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def _log(msg):
    """Log to stderr (stdout is reserved for MCP/JSON output)."""
    print(msg, file=sys.stderr)


def get_manim_cmd():
    """Get manim command list using the shared venv."""
    if os.name == 'nt':
        manim_exe = os.path.join(VENV_DIR, 'Scripts', 'manim.exe')
        python_exe = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
    else:
        manim_exe = os.path.join(VENV_DIR, 'bin', 'manim')
        python_exe = os.path.join(VENV_DIR, 'bin', 'python')

    if os.path.exists(manim_exe):
        return [manim_exe]
    if os.path.exists(python_exe):
        return [python_exe, '-m', 'manim']
    raise FileNotFoundError(
        f"Manim not found in venv at {VENV_DIR}. "
        "Run the ManimStudio GUI first to set up the environment."
    )


def get_clean_environment():
    """Clean env for manim subprocess (mirrors app.py)."""
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', '__PYVENV_LAUNCHER__'):
        env.pop(key, None)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    env['VIRTUAL_ENV'] = VENV_DIR

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        path_parts = env.get('PATH', '').split(os.pathsep)
        path_parts = [p for p in path_parts
                      if os.path.normpath(p) != os.path.normpath(exe_dir)]
        env['PATH'] = os.pathsep.join(path_parts)

    return env


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


def extract_scene_name(code):
    """Return the first Scene subclass name — or None. CLI users
    expect silent-pick-first, so this keeps that behaviour."""
    scenes = extract_all_scene_classes(code)
    if scenes:
        return scenes[0]['name']
    m = re.search(r'^[ \t]*class\s+(\w+)\s*\(', code, flags=re.MULTILINE)
    return m.group(1) if m else None


def validate_code(code):
    """Return None if valid, or an error string."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"Line {e.lineno}: {e.msg}"


def _inject_narrate_stub(code):
    """Inject no-op narrate() so TTS calls don't raise NameError."""
    code = re.sub(r'^(\s*)@narrate\(', r'\1narrate(', code, flags=re.MULTILINE)
    if 'narrate(' not in code:
        return code
    return 'def narrate(*_a, **_k): pass  # TTS stub\n' + code


def _sanitize_code(code):
    """Remove invisible Unicode chars that break LaTeX."""
    pattern = re.compile(
        r'[\u200B-\u200D\u200E\u200F\u202A-\u202F'
        r'\u2060-\u206F\uFEFF\u00AD]'
    )
    code = pattern.sub('', code)
    code = code.replace('\u00A0', ' ')
    return code


def create_manim_config(script_dir):
    """Create manim.cfg for asset paths."""
    cfg = os.path.join(script_dir, 'manim.cfg')
    with open(cfg, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f"[CLI]\nassets_dir = {ASSETS_DIR}\nmedia_dir = {MEDIA_DIR}\n"
                f"max_files_cached = -1\ninput_file_encoding = utf-8\n")


def _find_output_video(output_dir, fmt='mp4'):
    """Walk output_dir for the rendered video file."""
    ext = f'.{fmt.lower()}'
    videos_dir = os.path.join(output_dir, 'videos')
    if os.path.exists(videos_dir):
        for root, _dirs, files in os.walk(videos_dir):
            for f in sorted(files, key=lambda x: os.path.getmtime(os.path.join(root, x)), reverse=True):
                if f.endswith(ext) and not f.startswith('temp_'):
                    return os.path.join(root, f)
    for f in os.listdir(output_dir):
        if f.endswith(ext) and not f.startswith('temp_'):
            return os.path.join(output_dir, f)
    return None


# ═══════════════════════════════════════════════════════════════
#  Headless Render
# ═══════════════════════════════════════════════════════════════

def render(code, quality='720p', fps=30, width=None, height=None,
           format='mp4', scene_name=None, output_dir=None):
    """
    Render a Manim scene headlessly. Returns a result dict:
      {status, output_file, scene_name, resolution, fps, format}
    or {status: 'error', error: '...'}
    """
    # Validate code
    err = validate_code(code)
    if err:
        return {'status': 'error', 'error': f'Syntax error: {err}'}

    if not scene_name:
        scene_name = extract_scene_name(code)
    if not scene_name:
        return {'status': 'error', 'error': 'No Scene class found in code'}

    # Resolve quality preset
    if quality in QUALITY_PRESETS:
        quality_flag, preset_w, preset_h = QUALITY_PRESETS[quality]
    else:
        quality_flag, preset_w, preset_h = '-qm', 1280, 720

    final_w = width if width else preset_w
    final_h = height if height else preset_h

    # Output directory
    if output_dir is None:
        output_dir = os.path.join(RENDER_DIR, f'cli_{int(time.time() * 1000)}')
    os.makedirs(output_dir, exist_ok=True)

    # Prepare code
    code = _sanitize_code(code)
    code = _inject_narrate_stub(code)
    code = '# -*- coding: utf-8 -*-\n' + code

    # Write temp .py file
    temp_file = os.path.join(output_dir, 'scene_render.py')
    with open(temp_file, 'w', encoding='utf-8', newline='\n') as f:
        f.write(code)

    create_manim_config(output_dir)

    try:
        cmd = get_manim_cmd()
        cmd.extend([temp_file, scene_name, quality_flag])
        cmd.extend(['--media_dir', output_dir])
        cmd.extend(['--frame_rate', str(fps)])

        # Custom resolution override
        if width or height:
            cmd.extend(['-r', f'{final_w},{final_h}'])

        if format and format.lower() != 'mp4':
            cmd.extend(['--format', format.lower()])

        cmd.extend(['--renderer=cairo'])
        cmd.extend(['--progress_bar', 'display'])

        _log(f"[RENDER] {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=get_clean_environment(),
            cwd=output_dir,
            timeout=3600,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )

        if result.returncode != 0:
            error = (result.stderr or result.stdout or 'Unknown error')[-1500:]
            return {'status': 'error', 'error': error}

        video = _find_output_video(output_dir, format)
        if video:
            return {
                'status': 'success',
                'output_file': video,
                'scene_name': scene_name,
                'resolution': f'{final_w}x{final_h}',
                'fps': fps,
                'format': format,
            }
        return {'status': 'error', 'error': 'Render succeeded but output file not found'}

    except FileNotFoundError as e:
        return {'status': 'error', 'error': str(e)}
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'error': 'Render timed out (1 hour limit)'}
    finally:
        try:
            os.remove(temp_file)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════
#  MCP Server (stdio, Content-Length framing — MCP 2024-11-05)
# ═══════════════════════════════════════════════════════════════

class MCPServer:
    """Minimal MCP server over stdio for Codex integration."""

    TOOLS = {
        'render_manim_animation': {
            'description': (
                'Render a Manim animation from Python code. '
                'Returns the output file path on success. '
                'The code must contain a class that inherits from Scene.'
            ),
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'code': {
                        'type': 'string',
                        'description': 'Complete Manim Python code with a Scene class',
                    },
                    'quality': {
                        'type': 'string',
                        'enum': list(QUALITY_PRESETS.keys()),
                        'default': '720p',
                        'description': 'Quality preset (determines default resolution)',
                    },
                    'width': {
                        'type': 'integer',
                        'description': 'Custom pixel width (overrides preset)',
                    },
                    'height': {
                        'type': 'integer',
                        'description': 'Custom pixel height (overrides preset)',
                    },
                    'fps': {
                        'type': 'integer',
                        'default': 30,
                        'description': 'Frames per second',
                    },
                    'format': {
                        'type': 'string',
                        'enum': ['mp4', 'gif', 'webm'],
                        'default': 'mp4',
                    },
                    'scene_name': {
                        'type': 'string',
                        'description': 'Scene class name (auto-detected if omitted)',
                    },
                },
                'required': ['code'],
            },
        },
        'check_render_status': {
            'description': (
                'Check if a previously started render has completed. '
                'Pass the output_dir returned by render_manim_animation.'
            ),
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'output_dir': {
                        'type': 'string',
                        'description': 'The output directory from a previous render',
                    },
                    'format': {
                        'type': 'string',
                        'enum': ['mp4', 'gif', 'webm'],
                        'default': 'mp4',
                    },
                },
                'required': ['output_dir'],
            },
        },
        'validate_scene': {
            'description': 'Validate Manim scene code for syntax errors and extract the Scene class name.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'code': {
                        'type': 'string',
                        'description': 'Manim Python code to validate',
                    },
                },
                'required': ['code'],
            },
        },
        'list_scenes': {
            'description': 'List every Scene-subclass class in the provided Manim code (name, line, parent).',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'code': {
                        'type': 'string',
                        'description': 'Manim Python code to scan',
                    },
                },
                'required': ['code'],
            },
        },
        'list_quality_presets': {
            'description': 'List all available quality presets with their default width, height, and manim flag.',
            'inputSchema': {
                'type': 'object',
                'properties': {},
            },
        },
    }

    # ── stdio framing (Content-Length, like LSP) ──

    @staticmethod
    def _read_message():
        """Read one Content-Length framed JSON-RPC message from stdin."""
        stdin = sys.stdin.buffer
        content_length = None
        while True:
            line = stdin.readline()
            if not line:
                return None  # EOF
            line_str = line.decode('utf-8').strip()
            if not line_str:
                break  # blank line → end of headers
            if line_str.lower().startswith('content-length:'):
                content_length = int(line_str.split(':', 1)[1].strip())
        if content_length is None:
            return None
        body = stdin.read(content_length)
        return json.loads(body.decode('utf-8'))

    @staticmethod
    def _write_message(msg):
        """Write one Content-Length framed JSON-RPC message to stdout."""
        stdout = sys.stdout.buffer
        body = json.dumps(msg).encode('utf-8')
        header = f'Content-Length: {len(body)}\r\n\r\n'.encode('utf-8')
        stdout.write(header)
        stdout.write(body)
        stdout.flush()

    # ── JSON-RPC helpers ──

    @staticmethod
    def _result(req_id, result):
        return {'jsonrpc': '2.0', 'id': req_id, 'result': result}

    @staticmethod
    def _error_resp(req_id, code, message):
        return {'jsonrpc': '2.0', 'id': req_id,
                'error': {'code': code, 'message': message}}

    # ── Dispatch ──

    def handle(self, request):
        method = request.get('method', '')
        params = request.get('params', {})
        req_id = request.get('id')

        if method == 'initialize':
            return self._result(req_id, {
                'protocolVersion': '2024-11-05',
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'ManimStudio', 'version': APP_VERSION},
            })

        if method == 'notifications/initialized':
            return None  # notification — no response

        if method == 'tools/list':
            tools = [
                {'name': n, 'description': t['description'],
                 'inputSchema': t['inputSchema']}
                for n, t in self.TOOLS.items()
            ]
            return self._result(req_id, {'tools': tools})

        if method == 'tools/call':
            return self._call_tool(req_id, params)

        if method == 'ping':
            return self._result(req_id, {})

        return self._error_resp(req_id, -32601, f'Method not found: {method}')

    def _call_tool(self, req_id, params):
        name = params.get('name', '')
        args = params.get('arguments', {})

        try:
            if name == 'render_manim_animation':
                res = render(
                    code=args['code'],
                    quality=args.get('quality', '720p'),
                    width=args.get('width'),
                    height=args.get('height'),
                    fps=args.get('fps', 30),
                    format=args.get('format', 'mp4'),
                    scene_name=args.get('scene_name'),
                )
                is_err = res['status'] != 'success'
                text = json.dumps(res, indent=2)
                return self._result(req_id, {
                    'content': [{'type': 'text', 'text': text}],
                    'isError': is_err,
                })

            if name == 'check_render_status':
                output_dir = args['output_dir']
                fmt = args.get('format', 'mp4')
                video = _find_output_video(output_dir, fmt)
                if video:
                    res = {'status': 'complete', 'output_file': video}
                else:
                    res = {'status': 'pending'}
                return self._result(req_id, {
                    'content': [{'type': 'text', 'text': json.dumps(res)}],
                })

            if name == 'validate_scene':
                err = validate_code(args['code'])
                all_scenes = extract_all_scene_classes(args['code'])
                scene = all_scenes[0]['name'] if all_scenes else extract_scene_name(args['code'])
                res = {
                    'valid': err is None,
                    'error': err,
                    'scene_name': scene,
                    'scene_count': len(all_scenes),
                    'scenes': all_scenes,
                }
                return self._result(req_id, {
                    'content': [{'type': 'text', 'text': json.dumps(res)}],
                })

            if name == 'list_scenes':
                scenes = extract_all_scene_classes(args['code'])
                return self._result(req_id, {
                    'content': [{'type': 'text', 'text': json.dumps({
                        'count': len(scenes), 'scenes': scenes,
                    }, indent=2)}],
                })

            if name == 'list_quality_presets':
                presets = {
                    k: {'width': w, 'height': h, 'manim_flag': flag}
                    for k, (flag, w, h) in QUALITY_PRESETS.items()
                }
                return self._result(req_id, {
                    'content': [{'type': 'text', 'text': json.dumps(presets, indent=2)}],
                })

            return self._error_resp(req_id, -32602, f'Unknown tool: {name}')

        except Exception as e:
            return self._result(req_id, {
                'content': [{'type': 'text', 'text': str(e)}],
                'isError': True,
            })

    def run(self):
        """Main loop — read stdin, dispatch, write stdout."""
        _log('[ManimStudio MCP] Server started (stdio, Content-Length framing)')
        while True:
            msg = self._read_message()
            if msg is None:
                break
            resp = self.handle(msg)
            if resp is not None:
                self._write_message(resp)
        _log('[ManimStudio MCP] Server stopped')


# ═══════════════════════════════════════════════════════════════
#  CLI Entry Point
# ═══════════════════════════════════════════════════════════════

def cli_main(argv=None):
    """Parse args and dispatch to render / validate / mcp / presets."""
    parser = argparse.ArgumentParser(
        prog='ManimStudio',
        description='Manim Studio — Animation IDE with CLI & MCP support',
    )
    sub = parser.add_subparsers(dest='command')

    # ── render ──
    rp = sub.add_parser('render', help='Render a Manim scene headlessly')
    rp.add_argument('file', help='Path to .py file containing a Scene class')
    rp.add_argument('--quality', '-q', default='720p',
                     choices=list(QUALITY_PRESETS.keys()),
                     help='Quality preset (default: 720p)')
    rp.add_argument('--width', '-W', type=int,
                     help='Custom pixel width (overrides preset)')
    rp.add_argument('--height', '-H', type=int,
                     help='Custom pixel height (overrides preset)')
    rp.add_argument('--fps', type=int, default=30, help='Frames per second')
    rp.add_argument('--format', '-f', default='mp4',
                     choices=['mp4', 'gif', 'webm'])
    rp.add_argument('--scene', '-s',
                     help='Scene class name (auto-detected if omitted)')
    rp.add_argument('--output-dir', '-o', help='Output directory')

    # ── validate ──
    vp = sub.add_parser('validate', help='Validate scene code for errors')
    vp.add_argument('file', help='Path to .py file')

    # ── mcp ──
    sub.add_parser('mcp', help='Start MCP server for Codex (stdio)')

    # ── presets ──
    sub.add_parser('presets', help='List quality presets')

    args = parser.parse_args(argv)

    if args.command == 'render':
        with open(args.file, 'r', encoding='utf-8') as f:
            code = f.read()
        result = render(
            code=code,
            quality=args.quality,
            width=args.width,
            height=args.height,
            fps=args.fps,
            format=args.format,
            scene_name=args.scene,
            output_dir=args.output_dir,
        )
        print(json.dumps(result, indent=2))
        sys.exit(0 if result['status'] == 'success' else 1)

    elif args.command == 'validate':
        with open(args.file, 'r', encoding='utf-8') as f:
            code = f.read()
        err = validate_code(code)
        scene = extract_scene_name(code)
        result = {'valid': err is None, 'error': err, 'scene_name': scene}
        print(json.dumps(result, indent=2))
        sys.exit(0 if err is None else 1)

    elif args.command == 'mcp':
        MCPServer().run()

    elif args.command == 'presets':
        print(f"{'Preset':>8s}  {'Width':>5s} x {'Height':<5s}  Flag")
        print('-' * 38)
        for name, (flag, w, h) in QUALITY_PRESETS.items():
            print(f"{name:>8s}  {w:5d} x {h:<5d}  {flag}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    cli_main()
