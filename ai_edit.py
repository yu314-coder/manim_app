"""
AI Edit Module — OpenAI Codex + Claude Code integration.
Provides AIEditMixin class that ManimAPI inherits from.

Claude Code uses ``claude -p --output-format stream-json`` for clean
structured streaming output.  No PTY, no ANSI stripping, no permission
prompt auto-accept needed.
"""
import os
import subprocess
import time
import re
import json
import base64
import threading
import shutil
import gc
import uuid

# ── Module-level refs injected by init_ai_edit() ──
_preview_dir = None
_get_clean_env = None
_assets_dir = None


def init_ai_edit(preview_dir, get_clean_env_func, assets_dir=None):
    """Initialise module-level dependencies (called once from app.py)."""
    global _preview_dir, _get_clean_env, _assets_dir
    _preview_dir = preview_dir
    _get_clean_env = get_clean_env_func
    _assets_dir = assets_dir


def _link_assets(workspace_dir):
    """Create a junction/symlink from workspace_dir/assets → _assets_dir."""
    if not _assets_dir or not os.path.isdir(_assets_dir):
        return
    target = os.path.join(workspace_dir, 'assets')
    if os.path.exists(target):
        return
    try:
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', target, _assets_dir],
                           capture_output=True, timeout=10)
        else:
            os.symlink(_assets_dir, target)
        print(f"[AI EDIT] Linked assets: {target} → {_assets_dir}")
    except Exception as e:
        print(f"[AI EDIT] Failed to link assets: {e}")


def _init_workspace_git(workspace_dir):
    """Run ``git init`` in the workspace so Claude CLI trusts it."""
    git_dir = os.path.join(workspace_dir, '.git')
    if os.path.exists(git_dir):
        return
    try:
        r = subprocess.run(['git', 'init'], cwd=workspace_dir,
                           capture_output=True, timeout=10)
        if r.returncode == 0:
            print(f"[AI EDIT] git init OK: {workspace_dir}")
        else:
            print(f"[AI EDIT] git init failed (rc={r.returncode}): {(r.stderr or b'').decode('utf-8', errors='replace')[:200]}")
    except Exception as e:
        print(f"[AI EDIT] git init error: {e}")


def _downscale_image(img_path, max_width=960):
    """Downscale an image to max_width to reduce token cost.
    A 1920x1080 image = ~2764 tokens, 960x540 = ~691 tokens (4x savings).
    Modifies the file in-place. Requires Pillow; silently skips if unavailable."""
    try:
        from PIL import Image
        with Image.open(img_path) as img:
            if img.width <= max_width:
                return
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            img.save(img_path, 'JPEG', quality=80)
    except ImportError:
        pass  # Pillow not installed — skip downscaling
    except Exception as e:
        print(f"[AI EDIT] Image downscale error: {e}")


def _cleanup_old_workspaces(max_age=3600):
    """Remove ai_workspace_* and ai_images dirs older than max_age seconds."""
    if not _preview_dir or not os.path.isdir(_preview_dir):
        return
    now = time.time()
    for name in os.listdir(_preview_dir):
        if not (name.startswith('ai_workspace_') or name.startswith('ai_agent_ws_')
               or name == 'ai_images'):
            continue
        path = os.path.join(_preview_dir, name)
        if not os.path.isdir(path):
            continue
        try:
            age = now - os.path.getmtime(path)
            if age > max_age:
                shutil.rmtree(path, ignore_errors=True)
                print(f"[AI CLEANUP] Removed old dir: {name} (age={int(age)}s)")
        except Exception:
            pass
    gc.collect()


class AIEditMixin:
    """Mixin providing AI-edit pywebview API methods (Codex + Claude Code).

    ManimAPI inherits this so every method is callable from JS
    via ``pywebview.api.<method>()``.
    """

    # ── Codex streaming state (JSONL via --json) ──
    _ai_proc = None           # subprocess.Popen
    _ai_codex_events = []     # parsed JSONL events for panel display
    _ai_codex_raw_chunks = [] # raw ANSI-formatted chunks for xterm.js
    _ai_done = False
    _ai_returncode = None
    _ai_workspace = None      # isolated temp workspace directory
    _ai_code_file = None      # path to scene.py inside workspace
    _ai_prompt_file = None    # path to instruction file inside workspace
    _ai_original_code = ''    # original code for comparison
    _ai_image_dir = None      # directory for uploaded images

    # ── Claude Code stream-json state ──
    _ai_claude_proc = None          # subprocess.Popen
    _ai_claude_events = []          # parsed stream-json events for panel display
    _ai_claude_raw_chunks = []      # raw output chunks for xterm.js window mode
    _ai_claude_workspace = None
    _ai_claude_code_file = None
    _ai_claude_original_code = ''
    _ai_claude_done = False
    _ai_claude_result_text = ''     # final result text from stream

    # ── Agent session memory ──
    _ai_agent_session_id = None     # UUID for Claude --session-id / --resume
    _ai_agent_workspace = None      # Reused workspace path across iterations
    _ai_agent_first_edit = True     # True → use --session-id, False → use --resume

    # ── Continuous chat session ──
    _ai_chat_session_id = None      # UUID for chat --session-id / --resume
    _ai_chat_workspace = None       # Reused workspace for chat session
    _ai_chat_first_message = True   # True → use --session-id, False → use --resume

    # ── Image upload for AI context ──

    def ai_edit_save_image(self, filename, data_url):
        """Save a base64 data URL image to a temp directory for AI context.
        Returns the saved file path.
        """
        if not _preview_dir:
            return {'status': 'error', 'message': 'Preview dir not set'}

        img_dir = os.path.join(_preview_dir, 'ai_images')
        os.makedirs(img_dir, exist_ok=True)

        # Parse data URL: data:image/png;base64,iVBOR...
        try:
            header, b64data = data_url.split(',', 1)
            img_bytes = base64.b64decode(b64data)
        except Exception as e:
            return {'status': 'error', 'message': f'Invalid image data: {e}'}

        # Sanitize filename
        safe_name = re.sub(r'[^\w.\-]', '_', filename)
        ts = int(time.time() * 1000)
        path = os.path.join(img_dir, f'{ts}_{safe_name}')

        with open(path, 'wb') as f:
            f.write(img_bytes)

        AIEditMixin._ai_image_dir = img_dir
        print(f"[AI EDIT] Saved image: {path} ({len(img_bytes)} bytes)")
        return {'status': 'success', 'path': path}

    # ══════════════════════════════════════════════════════════════════════
    # Claude Code (stream-json subprocess)
    # ══════════════════════════════════════════════════════════════════════

    def check_claude_code_installed(self):
        """Check if Claude Code CLI is installed."""
        try:
            result = subprocess.run(
                'claude --version',
                capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=10, shell=True, env=_get_clean_env()
            )
            stdout = (result.stdout or '').strip()
            stderr = (result.stderr or '').strip()
            output = stdout or stderr
            print(f"[CLAUDE CODE] check: rc={result.returncode}, stdout='{stdout}', stderr='{stderr}'")
            if output and ('claude' in output.lower() or len(output) > 5):
                print(f"[CLAUDE CODE] Found: {output}")
                return {'status': 'success', 'installed': True, 'version': output}
            elif result.returncode == 0:
                return {'status': 'success', 'installed': True, 'version': 'installed'}
            else:
                return {'status': 'success', 'installed': False,
                        'message': f'Claude Code CLI not found (rc={result.returncode})'}
        except FileNotFoundError:
            return {'status': 'success', 'installed': False,
                    'message': 'Claude Code not installed. Install from: https://claude.ai/download'}
        except Exception as e:
            print(f"[CLAUDE CODE] check error: {e}")
            return {'status': 'error', 'message': str(e), 'installed': False}

    def get_claude_models(self):
        """Return available models for Claude Code."""
        return {
            'models': [
                {'id': 'claude-sonnet-4-6', 'display_name': 'Claude Sonnet 4.6'},
                {'id': 'claude-opus-4-6', 'display_name': 'Claude Opus 4.6'},
                {'id': 'claude-haiku-4-5-20251001', 'display_name': 'Claude Haiku 4.5'},
                {'id': 'claude-sonnet-4-5-20250514', 'display_name': 'Claude Sonnet 4.5'},
            ]
        }

    def _build_ai_instruction(self, prompt, selected_code, selection_start,
                              selection_end, search, image_paths):
        """Build the instruction string used by both Codex and Claude.
        Does NOT embed code — AI reads scene.py from disk to save tokens."""
        has_selection = bool(selected_code and selected_code.strip())
        search_hint = ("\nUse web search to look up any documentation, APIs, "
                       "or examples you need to complete this task." if search else "")
        image_hint = ""
        if image_paths:
            names = [os.path.basename(p) for p in image_paths]
            image_hint = (f"\n\nI've attached {len(image_paths)} image(s) in the `images/` folder "
                          f"for reference: {', '.join(names)}. "
                          f"Look at them to understand what I'm referring to.")

        if has_selection:
            return (
                f"Edit the file `scene.py` in this directory.\n"
                f"ONLY modify lines {selection_start}-{selection_end}.\n\n"
                f"Selected code (lines {selection_start}-{selection_end}):\n"
                f"```python\n{selected_code}\n```\n\n"
                f"Instruction: {prompt}\n\n"
                f"Apply the changes to scene.py and write it back. "
                f"Keep all existing code that wasn't asked to change."
                f"{search_hint}{image_hint}"
            )
        else:
            return (
                f"Read `scene.py` in this directory first, then edit it.\n"
                f"This is a Manim (Python math animation library) file.\n\n"
                f"Instruction: {prompt}\n\n"
                f"Apply the changes and write the result back to scene.py. "
                f"Keep all existing code that wasn't asked to change."
                f"{search_hint}{image_hint}"
            )

    def _setup_ai_workspace(self, code, image_paths):
        """Create isolated workspace with scene.py, AGENTS.md, and images.
        Returns (workspace, code_file, copied_image_paths).
        """
        _cleanup_old_workspaces()

        ts = int(time.time())
        workspace = os.path.join(_preview_dir, f'ai_workspace_{ts}')
        os.makedirs(workspace, exist_ok=True)

        _init_workspace_git(workspace)

        code_file = os.path.join(workspace, 'scene.py')
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code)

        _link_assets(workspace)

        copied_images = []
        if image_paths:
            img_ws_dir = os.path.join(workspace, 'images')
            os.makedirs(img_ws_dir, exist_ok=True)
            for ip in image_paths:
                if os.path.isfile(ip):
                    dest = os.path.join(img_ws_dir, os.path.basename(ip))
                    shutil.copy2(ip, dest)
                    copied_images.append(dest)

        # AGENTS.md / CLAUDE.md
        md_content = (
            "# Workspace Rules\n\n"
            "Edit `scene.py` only. No explanations.\n\n"
            "## CRITICAL: ALWAYS read scene.py FIRST before any edit.\n"
            "Never guess file contents. Use Read tool or cat to read it.\n\n"
            "## NOT Allowed\n"
            "- Do NOT run pip, python, manim, or any execution commands\n"
            "- Do NOT create files other than editing `scene.py`\n\n"
            "## Manim Context\n"
            "- `scene.py` is a Manim (Python math animation library) file\n"
            "- Always include `from manim import *`\n"
            "- Must have a Scene class with `construct(self)` method\n"
            "- Common: Text, MathTex, Circle, Square, Arrow, VGroup, "
            "FadeIn, FadeOut, Write, Transform, Create\n"
            "- Use `self.play(...)` to animate, `self.wait()` to pause\n"
            "- Keep all existing code that wasn't asked to change\n"
        )
        # List available assets
        if _assets_dir and os.path.isdir(_assets_dir):
            try:
                asset_files = [f for f in os.listdir(_assets_dir)
                               if os.path.isfile(os.path.join(_assets_dir, f))]
                if asset_files:
                    md_content += (
                        "\n## Available Assets\n"
                        "These files are in the `./assets/` folder:\n"
                    )
                    for af in sorted(asset_files):
                        md_content += f"- {af}\n"
                    md_content += (
                        "\nUse relative path `./assets/filename` in code to reference them.\n"
                    )
            except Exception:
                pass

        for fname in ('AGENTS.md', 'CLAUDE.md'):
            md_path = os.path.join(workspace, fname)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

        return workspace, code_file, copied_images

    def ai_edit_claude_start(self, code, prompt, model='', search=False,
                             selected_code='', selection_start=0, selection_end=0,
                             image_paths=None):
        """Start Claude Code via ``claude -p --output-format stream-json``.
        Poll with ai_edit_claude_poll().
        Supports continuous chat: reuses workspace and session across calls.
        """
        # Cancel any running process (but preserve session state)
        proc = AIEditMixin._ai_claude_proc
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
            AIEditMixin._ai_claude_proc = None

        try:
            check = self.check_claude_code_installed()
            if not check.get('installed', False):
                return {'status': 'error',
                        'message': 'Claude Code not installed. Get it from https://claude.ai/download'}

            use_model = (model or '').strip()
            print(f"[AI CLAUDE] Starting Claude Code edit (stream-json)...")
            print(f"[AI CLAUDE] Prompt: {prompt}")
            if use_model:
                print(f"[AI CLAUDE] Model: {use_model}")

            # Continuous chat: reuse workspace and session
            if AIEditMixin._ai_chat_session_id and AIEditMixin._ai_chat_workspace:
                workspace = AIEditMixin._ai_chat_workspace
                code_file = os.path.join(workspace, 'scene.py')
                # Update scene.py with current code
                with open(code_file, 'w', encoding='utf-8') as f:
                    f.write(code)
                image_paths = image_paths or []
                copied_images = []
                if image_paths:
                    img_ws_dir = os.path.join(workspace, 'images')
                    os.makedirs(img_ws_dir, exist_ok=True)
                    for ip in image_paths:
                        if os.path.isfile(ip):
                            dest = os.path.join(img_ws_dir, os.path.basename(ip))
                            shutil.copy2(ip, dest)
                            copied_images.append(dest)
                    image_paths = copied_images
            else:
                workspace, code_file, image_paths = self._setup_ai_workspace(code, image_paths or [])
                AIEditMixin._ai_chat_session_id = str(uuid.uuid4())
                AIEditMixin._ai_chat_workspace = workspace
                AIEditMixin._ai_chat_first_message = True

            instruction = self._build_ai_instruction(
                prompt, selected_code, selection_start, selection_end, search, image_paths)

            # Reset streaming state (not session state)
            AIEditMixin._ai_claude_events = []
            AIEditMixin._ai_claude_raw_chunks = []
            AIEditMixin._ai_claude_done = False
            AIEditMixin._ai_claude_workspace = workspace
            AIEditMixin._ai_claude_code_file = code_file
            AIEditMixin._ai_claude_original_code = code
            AIEditMixin._ai_claude_result_text = ''

            # Build command with session support
            session_id = AIEditMixin._ai_chat_session_id
            if AIEditMixin._ai_chat_first_message:
                cmd_parts = [
                    'claude', '-p', instruction,
                    '--output-format', 'stream-json',
                    '--verbose',
                    '--session-id', session_id,
                    '--allowedTools', 'Read,Write,Edit,Bash,Glob,Grep,WebSearch,WebFetch',
                ]
            else:
                cmd_parts = [
                    'claude', '-p', instruction,
                    '--output-format', 'stream-json',
                    '--verbose',
                    '--resume', session_id,
                    '--allowedTools', 'Read,Write,Edit,Bash,Glob,Grep,WebSearch,WebFetch',
                ]
            if use_model:
                cmd_parts.extend(['--model', use_model])

            session_flag = '--session-id' if AIEditMixin._ai_chat_first_message else '--resume'
            print(f"[AI CLAUDE] Command: claude -p <{len(instruction)} chars> "
                  f"--output-format stream-json {session_flag} {session_id[:8]}... "
                  f"--allowedTools Read,Write,Edit,Bash,Glob,Grep,WebSearch,WebFetch"
                  + (f" --model {use_model}" if use_model else ""))

            env = _get_clean_env()
            # Remove CLAUDECODE env var to avoid "nested session" error
            # when launched from within a Claude Code session
            for key in ('CLAUDECODE', 'CLAUDE_CODE'):
                env.pop(key, None)

            proc = subprocess.Popen(
                cmd_parts,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, cwd=workspace, env=env
            )
            AIEditMixin._ai_claude_proc = proc
            AIEditMixin._ai_chat_first_message = False

            # Background reader: parse stream-json events into structured
            # events (for panel) and ANSI-formatted chunks (for xterm.js)
            def _reader():
                try:
                    for line in proc.stdout:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            AIEditMixin._ai_claude_events.append({'_kind': 'raw', '_text': line})
                            AIEditMixin._ai_claude_raw_chunks.append(line + '\r\n')
                            continue

                        ev_type = event.get('type', '')

                        # Final result
                        if ev_type == 'result':
                            AIEditMixin._ai_claude_result_text = event.get('result', '')
                            cost = event.get('total_cost_usd')
                            dur = event.get('duration_ms')
                            rt = event.get('result', '')
                            if rt:
                                AIEditMixin._ai_claude_events.append({'_kind': 'text', '_text': rt})
                                AIEditMixin._ai_claude_raw_chunks.append(
                                    f"\r\n\x1b[32m{rt}\x1b[0m\r\n")
                            if cost is not None:
                                AIEditMixin._ai_claude_raw_chunks.append(
                                    f"\x1b[90mCost: ${cost:.4f}  Duration: {(dur or 0)/1000:.1f}s\x1b[0m\r\n")
                            continue

                        # Skip noisy events
                        if ev_type in ('system', 'rate_limit_event'):
                            continue

                        # Assistant messages — iterate content blocks
                        if ev_type == 'assistant':
                            for block in (event.get('message', {}).get('content') or []):
                                if not isinstance(block, dict):
                                    continue
                                btype = block.get('type', '')
                                if btype == 'tool_use':
                                    tool = block.get('name', '')
                                    inp = block.get('input', {})
                                    arg = ''
                                    if isinstance(inp, dict):
                                        arg = (inp.get('file_path') or inp.get('path')
                                               or inp.get('command') or inp.get('query') or '')
                                        if isinstance(arg, str) and len(arg) > 60:
                                            arg = '...' + arg[-50:]
                                    AIEditMixin._ai_claude_events.append({
                                        '_kind': 'tool_use', '_tool': tool, '_arg': arg, '_input': inp})
                                    AIEditMixin._ai_claude_raw_chunks.append(
                                        f"\x1b[35m● {tool}\x1b[0m({arg})\r\n")
                                    # Show Write/Edit content preview
                                    content = inp.get('content', '') if isinstance(inp, dict) else ''
                                    if content and tool in ('Write', 'Edit'):
                                        for i, cl in enumerate(content.split('\n'), 1):
                                            AIEditMixin._ai_claude_raw_chunks.append(
                                                f"  \x1b[90m{i:>3}\x1b[0m {cl}\r\n")
                                elif btype == 'text':
                                    text = block.get('text', '').strip()
                                    if text:
                                        AIEditMixin._ai_claude_events.append({
                                            '_kind': 'text', '_text': text})
                                        AIEditMixin._ai_claude_raw_chunks.append(text + '\r\n')
                                elif btype == 'thinking':
                                    thinking = block.get('thinking', '').strip()
                                    if thinking:
                                        short = thinking[:120] + ('...' if len(thinking) > 120 else '')
                                        AIEditMixin._ai_claude_raw_chunks.append(
                                            f"\x1b[90m{short}\x1b[0m\r\n")
                            continue

                        # User messages — tool results
                        if ev_type == 'user':
                            tr = event.get('tool_use_result', {})
                            if isinstance(tr, dict):
                                stdout = tr.get('stdout', '')
                                file_info = tr.get('file', {})
                                content = tr.get('content', '')
                                if stdout:
                                    out_lines = stdout.strip().split('\n')
                                    for ol in out_lines[:15]:
                                        AIEditMixin._ai_claude_events.append({
                                            '_kind': 'result_line', '_text': ol})
                                        AIEditMixin._ai_claude_raw_chunks.append(
                                            f"  \x1b[36m{ol}\x1b[0m\r\n")
                                    if len(out_lines) > 15:
                                        AIEditMixin._ai_claude_events.append({
                                            '_kind': 'collapsed', '_text': f'+{len(out_lines)-15} lines'})
                                        AIEditMixin._ai_claude_raw_chunks.append(
                                            f"  \x1b[90m+{len(out_lines)-15} lines\x1b[0m\r\n")
                                elif isinstance(file_info, dict) and file_info.get('content'):
                                    fc_lines = file_info['content'].split('\n')
                                    for i, fl in enumerate(fc_lines[:20], 1):
                                        AIEditMixin._ai_claude_events.append({
                                            '_kind': 'code_line', '_num': i, '_text': fl})
                                        AIEditMixin._ai_claude_raw_chunks.append(
                                            f"  \x1b[90m{i:>3}\x1b[0m {fl}\r\n")
                                    if len(fc_lines) > 20:
                                        AIEditMixin._ai_claude_events.append({
                                            '_kind': 'collapsed', '_text': f'+{len(fc_lines)-20} lines'})
                                        AIEditMixin._ai_claude_raw_chunks.append(
                                            f"  \x1b[90m+{len(fc_lines)-20} lines\x1b[0m\r\n")
                                elif isinstance(content, str) and content.strip():
                                    short = content.strip()[:200]
                                    AIEditMixin._ai_claude_events.append({
                                        '_kind': 'result_line', '_text': short})
                                    AIEditMixin._ai_claude_raw_chunks.append(
                                        f"  \x1b[32m{short}\x1b[0m\r\n")
                            continue

                except Exception as e:
                    print(f"[AI CLAUDE] Reader error: {e}")

                proc.wait()
                AIEditMixin._ai_claude_done = True
                rc = proc.returncode
                print(f"[AI CLAUDE] Process finished, rc={rc}")
                if rc != 0 and not AIEditMixin._ai_claude_events:
                    # Process failed with no events — capture any remaining output
                    AIEditMixin._ai_claude_events.append({
                        '_kind': 'text',
                        '_text': f'Claude Code exited with error (rc={rc})'
                    })

            threading.Thread(target=_reader, daemon=True).start()
            return {'status': 'started', 'message': 'Claude Code is editing...', 'mode': 'stream-json'}

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[AI CLAUDE ERROR] {e}\n{tb}")
            return {'status': 'error', 'message': f'{e}\n{tb}'}

    @staticmethod
    def _format_stream_events(events):
        """Convert parsed events into clean text for the panel display.

        Uses the ``_kind`` field set by the reader thread.
        Produces lines like:
          Read(scene.py)
            1 from manim import *
          Write(scene.py)
          Wrote 24 lines to scene.py
        """
        lines = []
        for ev in events:
            kind = ev.get('_kind', '')
            if kind == 'tool_use':
                lines.append(f"{ev['_tool']}({ev.get('_arg', '')})")
                # Show Write/Edit content
                inp = ev.get('_input', {})
                content = inp.get('content', '') if isinstance(inp, dict) else ''
                if content and ev['_tool'] in ('Write', 'Edit'):
                    for i, cl in enumerate(content.split('\n'), 1):
                        lines.append(f"  {i} {cl}")
            elif kind == 'text':
                lines.append(ev.get('_text', ''))
            elif kind == 'result_line':
                lines.append(ev.get('_text', ''))
            elif kind == 'code_line':
                lines.append(f"  {ev.get('_num', '')} {ev.get('_text', '')}")
            elif kind == 'collapsed':
                lines.append(ev.get('_text', ''))
            elif kind == 'raw':
                lines.append(ev.get('_text', ''))
        return '\n'.join(lines)

    def ai_edit_claude_poll(self):
        """Poll Claude Code stream-json output.

        Returns ``output`` (raw stream-json for xterm.js window mode)
        and ``filtered_output`` (formatted text for panel mode).
        """
        # Drain raw chunks for xterm.js
        raw_chunks = AIEditMixin._ai_claude_raw_chunks
        AIEditMixin._ai_claude_raw_chunks = []
        raw_output = ''.join(raw_chunks)

        if not raw_output and not AIEditMixin._ai_claude_done:
            return {'status': 'streaming', 'output': '', 'filtered_output': '',
                    'done': False, 'chars': 0}

        # Format ALL events so far for panel display (full replace, not incremental)
        filtered = self._format_stream_events(AIEditMixin._ai_claude_events)

        if AIEditMixin._ai_claude_done:
            # Try to read the edited file
            code_file = AIEditMixin._ai_claude_code_file
            original = AIEditMixin._ai_claude_original_code
            edited_code = None

            if code_file and os.path.exists(code_file):
                try:
                    with open(code_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if content.strip() and content != original:
                        edited_code = content
                        print(f"[AI CLAUDE] Got modified scene.py ({len(edited_code)} chars)")
                    else:
                        print("[AI CLAUDE] scene.py unchanged")
                except Exception as e:
                    print(f"[AI CLAUDE] Read error: {e}")

            # Fallback: extract code from result text
            if not edited_code and AIEditMixin._ai_claude_result_text:
                extracted = self._extract_code_from_ai_response(AIEditMixin._ai_claude_result_text)
                if extracted:
                    edited_code = extracted
                    print(f"[AI CLAUDE] Extracted code from result ({len(edited_code)} chars)")

            if edited_code:
                return {
                    'status': 'success', 'output': raw_output,
                    'filtered_output': filtered,
                    'edited_code': edited_code, 'done': True, 'message': 'Done!'
                }
            else:
                return {
                    'status': 'error', 'output': raw_output,
                    'filtered_output': filtered,
                    'done': True, 'message': 'Claude finished but no code changes detected'
                }

        return {'status': 'streaming', 'output': raw_output,
                'filtered_output': filtered,
                'done': False, 'chars': len(raw_output)}

    def ai_edit_claude_send(self, text):
        """Send text to Claude Code stdin (not applicable in -p mode)."""
        # stream-json mode uses -p (non-interactive), no stdin interaction
        return {'status': 'error', 'message': 'Non-interactive mode — cannot send input'}

    def ai_edit_claude_cancel(self):
        """Kill Claude Code process. Preserves chat session for continuity."""
        proc = AIEditMixin._ai_claude_proc
        if proc:
            try:
                proc.kill()
                print("[AI CLAUDE] Process cancelled")
            except Exception:
                pass
            AIEditMixin._ai_claude_proc = None

        # Don't destroy workspace if it's the chat session workspace
        workspace = AIEditMixin._ai_claude_workspace
        if workspace and os.path.exists(workspace) and workspace != AIEditMixin._ai_chat_workspace:
            try:
                shutil.rmtree(workspace, ignore_errors=True)
            except Exception:
                pass

        AIEditMixin._ai_claude_events = []
        AIEditMixin._ai_claude_raw_chunks = []
        AIEditMixin._ai_claude_done = False
        AIEditMixin._ai_claude_workspace = None
        AIEditMixin._ai_claude_code_file = None
        AIEditMixin._ai_claude_original_code = ''
        AIEditMixin._ai_claude_result_text = ''
        return {'status': 'cancelled'}

    def ai_edit_new_chat(self):
        """Reset chat session state for a fresh conversation."""
        # Clean up old chat workspace
        workspace = AIEditMixin._ai_chat_workspace
        if workspace and os.path.exists(workspace):
            try:
                shutil.rmtree(workspace, ignore_errors=True)
            except Exception:
                pass
        AIEditMixin._ai_chat_session_id = None
        AIEditMixin._ai_chat_workspace = None
        AIEditMixin._ai_chat_first_message = True
        print("[AI CLAUDE] Chat session reset")
        return {'status': 'ok'}

    # ══════════════════════════════════════════════════════════════════════
    # OpenAI Codex CLI
    # ══════════════════════════════════════════════════════════════════════

    def check_codex_installed(self):
        """Check if OpenAI Codex CLI is installed (npm i -g @openai/codex)."""
        try:
            result = subprocess.run(
                'codex --help',
                capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=10, shell=True, env=_get_clean_env()
            )
            output = (result.stdout or '').strip() + (result.stderr or '').strip()
            if output and ('codex' in output.lower() or 'usage' in output.lower()
                          or 'openai' in output.lower() or len(output) > 20):
                print(f"[CODEX CLI] Found (help output: {len(output)} chars)")
                return {'status': 'success', 'installed': True, 'version': 'installed'}
            else:
                return {'status': 'success', 'installed': False,
                        'message': 'Codex CLI not found'}
        except FileNotFoundError:
            return {'status': 'success', 'installed': False,
                    'message': 'Codex CLI not installed. Install with: npm install -g @openai/codex'}
        except Exception as e:
            return {'status': 'error', 'message': str(e), 'installed': False}

    def ai_edit_codex(self, code, prompt, model='', search=False,
                      selected_code='', selection_start=0, selection_end=0,
                      image_paths=None):
        """Start an AI edit using ``codex exec --json`` for structured JSONL output.
        Poll with ai_edit_poll().
        """
        self.ai_edit_cancel()
        self.ai_edit_claude_cancel()

        try:
            check_result = self.check_codex_installed()
            if not check_result.get('installed', False):
                return {
                    'status': 'error',
                    'message': 'Codex CLI not installed. Install it with: npm install -g @openai/codex'
                }

            has_selection = bool(selected_code and selected_code.strip())
            use_model = (model or '').strip()

            print(f"[AI EDIT] Starting Codex CLI edit (--json)...")
            print(f"[AI EDIT] Prompt: {prompt}")
            if has_selection:
                print(f"[AI EDIT] Selection: lines {selection_start}-{selection_end}")
            if use_model:
                print(f"[AI EDIT] Model: {use_model}")
            if image_paths:
                print(f"[AI EDIT] Images: {len(image_paths)} attached")

            workspace, code_file, image_paths = self._setup_ai_workspace(code, image_paths or [])
            instruction = self._build_ai_instruction(
                prompt, selected_code, selection_start, selection_end, search, image_paths)

            # Save instruction for reference
            prompt_file = os.path.join(workspace, 'instruction.txt')
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(instruction)

            # ── Build command as list (no shell=True — prevents injection) ──
            cmd_parts = ['codex', 'exec', '-', '--full-auto',
                         '--skip-git-repo-check', '--json']
            if use_model:
                cmd_parts.extend(['-m', use_model])
            if search:
                cmd_parts.extend(['-c', 'web_search=live'])
            if image_paths:
                for ip in image_paths:
                    cmd_parts.extend(['-i', ip])

            # Reset state
            AIEditMixin._ai_codex_events = []
            AIEditMixin._ai_codex_raw_chunks = []
            AIEditMixin._ai_done = False
            AIEditMixin._ai_returncode = None
            AIEditMixin._ai_workspace = workspace
            AIEditMixin._ai_code_file = code_file
            AIEditMixin._ai_prompt_file = prompt_file
            AIEditMixin._ai_original_code = code

            env = _get_clean_env()
            print(f"[AI EDIT] Command: codex exec - --full-auto --json"
                  + (f" -m {use_model}" if use_model else ""))

            proc = subprocess.Popen(
                cmd_parts,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=workspace,
                env=env
            )
            AIEditMixin._ai_proc = proc

            # Write instruction to stdin then close it
            try:
                proc.stdin.write(instruction)
                proc.stdin.close()
            except Exception as e:
                print(f"[AI EDIT] Failed to write stdin: {e}")

            # Background thread: parse JSONL events
            def _reader():
                try:
                    for line in proc.stdout:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            AIEditMixin._ai_codex_events.append({'_kind': 'raw', '_text': line})
                            AIEditMixin._ai_codex_raw_chunks.append(line + '\r\n')
                            continue

                        ev_type = event.get('type', '')
                        item = event.get('item', {})
                        item_type = item.get('type', '') if isinstance(item, dict) else ''

                        # ── Item events ──
                        if ev_type in ('item.started', 'item.updated', 'item.completed'):
                            if item_type == 'command_execution':
                                cmd = item.get('command', '')
                                AIEditMixin._ai_codex_events.append({
                                    '_kind': 'tool_use', '_tool': 'Bash', '_arg': cmd, '_input': item})
                                AIEditMixin._ai_codex_raw_chunks.append(
                                    f"\x1b[35m● Bash\x1b[0m({cmd})\r\n")
                                # Show output on completion
                                if ev_type == 'item.completed':
                                    output = item.get('aggregated_output', '').strip()
                                    exit_code = item.get('exit_code')
                                    if output:
                                        out_lines = output.split('\n')
                                        for ol in out_lines[:15]:
                                            AIEditMixin._ai_codex_events.append({
                                                '_kind': 'result_line', '_text': ol})
                                            AIEditMixin._ai_codex_raw_chunks.append(
                                                f"  \x1b[36m{ol}\x1b[0m\r\n")
                                        if len(out_lines) > 15:
                                            AIEditMixin._ai_codex_events.append({
                                                '_kind': 'collapsed', '_text': f'+{len(out_lines)-15} lines'})
                                            AIEditMixin._ai_codex_raw_chunks.append(
                                                f"  \x1b[90m+{len(out_lines)-15} lines\x1b[0m\r\n")
                                    if exit_code is not None and exit_code != 0:
                                        AIEditMixin._ai_codex_events.append({
                                            '_kind': 'result_line', '_text': f'Exit code: {exit_code}'})
                                        AIEditMixin._ai_codex_raw_chunks.append(
                                            f"  \x1b[31mExit code: {exit_code}\x1b[0m\r\n")

                            elif item_type == 'file_change':
                                changes = item.get('changes', [])
                                for ch in changes:
                                    path = ch.get('path', '')
                                    kind = ch.get('kind', '')
                                    tool = 'Write' if kind == 'add' else 'Edit'
                                    AIEditMixin._ai_codex_events.append({
                                        '_kind': 'tool_use', '_tool': tool, '_arg': path, '_input': ch})
                                    AIEditMixin._ai_codex_raw_chunks.append(
                                        f"\x1b[35m● {tool}\x1b[0m({path}) [{kind}]\r\n")

                            elif item_type == 'agent_message':
                                text = item.get('text', '').strip()
                                if text:
                                    AIEditMixin._ai_codex_events.append({'_kind': 'text', '_text': text})
                                    AIEditMixin._ai_codex_raw_chunks.append(text + '\r\n')

                            elif item_type == 'reasoning':
                                text = item.get('text', '').strip()
                                if text:
                                    short = text[:120] + ('...' if len(text) > 120 else '')
                                    AIEditMixin._ai_codex_raw_chunks.append(
                                        f"\x1b[90m{short}\x1b[0m\r\n")

                            elif item_type == 'web_search':
                                query = item.get('query', '')
                                AIEditMixin._ai_codex_events.append({
                                    '_kind': 'tool_use', '_tool': 'WebSearch', '_arg': query, '_input': item})
                                AIEditMixin._ai_codex_raw_chunks.append(
                                    f"\x1b[35m● WebSearch\x1b[0m({query})\r\n")

                            elif item_type == 'mcp_tool_call':
                                tool = item.get('tool', '')
                                args = item.get('arguments', {})
                                arg_str = json.dumps(args)[:60] if args else ''
                                AIEditMixin._ai_codex_events.append({
                                    '_kind': 'tool_use', '_tool': tool, '_arg': arg_str, '_input': item})
                                AIEditMixin._ai_codex_raw_chunks.append(
                                    f"\x1b[35m● {tool}\x1b[0m({arg_str})\r\n")

                            elif item_type == 'todo_list':
                                items = item.get('items', [])
                                for ti in items:
                                    done = '✓' if ti.get('completed') else '○'
                                    AIEditMixin._ai_codex_events.append({
                                        '_kind': 'text', '_text': f'{done} {ti.get("text", "")}'})

                            elif item_type == 'error':
                                msg = item.get('message', '')
                                AIEditMixin._ai_codex_events.append({'_kind': 'text', '_text': f'Error: {msg}'})
                                AIEditMixin._ai_codex_raw_chunks.append(
                                    f"\x1b[31mError: {msg}\x1b[0m\r\n")

                        # ── Turn events ──
                        elif ev_type == 'turn.completed':
                            usage = event.get('usage', {})
                            if usage:
                                inp = usage.get('input_tokens', 0)
                                out = usage.get('output_tokens', 0)
                                AIEditMixin._ai_codex_raw_chunks.append(
                                    f"\x1b[90mTokens: {inp} in / {out} out\x1b[0m\r\n")

                        elif ev_type == 'turn.failed':
                            err = event.get('error', {}).get('message', 'Unknown error')
                            AIEditMixin._ai_codex_events.append({'_kind': 'text', '_text': f'Error: {err}'})
                            AIEditMixin._ai_codex_raw_chunks.append(
                                f"\x1b[31mError: {err}\x1b[0m\r\n")

                        elif ev_type == 'error':
                            msg = event.get('message', 'Stream error')
                            AIEditMixin._ai_codex_events.append({'_kind': 'text', '_text': f'Error: {msg}'})
                            AIEditMixin._ai_codex_raw_chunks.append(
                                f"\x1b[31m{msg}\x1b[0m\r\n")

                except Exception as e:
                    print(f"[AI EDIT] Reader error: {e}")

                proc.wait()
                AIEditMixin._ai_returncode = proc.returncode
                AIEditMixin._ai_done = True
                print(f"[AI EDIT] Process finished, rc={proc.returncode}, "
                      f"{len(AIEditMixin._ai_codex_events)} events")

            threading.Thread(target=_reader, daemon=True).start()
            return {'status': 'started', 'message': 'Codex is editing...', 'mode': 'json'}

        except Exception as e:
            print(f"[AI EDIT ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def ai_edit_poll(self):
        """Poll the Codex JSONL streaming output.

        Returns ``output`` (raw ANSI for xterm.js window mode)
        and ``filtered_output`` (formatted text for panel mode).
        """
        if AIEditMixin._ai_proc is None:
            return {'status': 'idle', 'output': '', 'filtered_output': '', 'done': True}

        # Drain raw chunks for xterm.js
        raw_chunks = AIEditMixin._ai_codex_raw_chunks
        AIEditMixin._ai_codex_raw_chunks = []
        raw_output = ''.join(raw_chunks)

        if not raw_output and not AIEditMixin._ai_done:
            return {'status': 'streaming', 'output': '', 'filtered_output': '',
                    'done': False, 'chars': 0}

        # Format ALL events for panel display (full replace)
        filtered = self._format_stream_events(AIEditMixin._ai_codex_events)

        if AIEditMixin._ai_done:
            code_file = AIEditMixin._ai_code_file
            original = AIEditMixin._ai_original_code
            edited_code = None

            # Strategy 1: Read modified file from workspace
            if code_file and os.path.exists(code_file):
                try:
                    with open(code_file, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    if file_content.strip() and file_content != original:
                        edited_code = file_content
                        print(f"[AI EDIT] Got modified scene.py ({len(edited_code)} chars)")
                    else:
                        print("[AI EDIT] scene.py unchanged")
                except Exception as e:
                    print(f"[AI EDIT] Read failed: {e}")

            # Strategy 2: Extract from agent_message text events
            if not edited_code:
                for ev in reversed(AIEditMixin._ai_codex_events):
                    if ev.get('_kind') == 'text':
                        extracted = self._extract_code_from_ai_response(ev.get('_text', ''))
                        if extracted:
                            edited_code = extracted
                            print(f"[AI EDIT] Extracted code from event ({len(edited_code)} chars)")
                            break

            if edited_code:
                return {
                    'status': 'success', 'output': raw_output,
                    'filtered_output': filtered,
                    'edited_code': edited_code, 'done': True, 'message': 'Done!'
                }
            else:
                return {
                    'status': 'error', 'output': raw_output,
                    'filtered_output': filtered,
                    'done': True,
                    'message': 'Codex finished but no code changes detected'
                }

        return {'status': 'streaming', 'output': raw_output,
                'filtered_output': filtered,
                'done': False, 'chars': len(filtered)}

    def ai_edit_cancel(self):
        """Cancel a running AI edit process and clean up workspace."""
        if AIEditMixin._ai_proc and not AIEditMixin._ai_done:
            try:
                AIEditMixin._ai_proc.kill()
                print("[AI EDIT] Process cancelled by user")
            except Exception:
                pass
        AIEditMixin._ai_proc = None
        AIEditMixin._ai_done = False
        AIEditMixin._ai_codex_events = []
        AIEditMixin._ai_codex_raw_chunks = []
        AIEditMixin._ai_returncode = None
        AIEditMixin._ai_original_code = ''
        workspace = AIEditMixin._ai_workspace
        if workspace and os.path.exists(workspace):
            try:
                shutil.rmtree(workspace, ignore_errors=True)
            except Exception:
                pass
        AIEditMixin._ai_workspace = None
        AIEditMixin._ai_code_file = None
        AIEditMixin._ai_prompt_file = None
        return {'status': 'cancelled'}

    def get_codex_models(self):
        """Return available models for Codex CLI."""
        return {
            'models': [
                {'id': 'gpt-5.4', 'display_name': 'GPT-5.4'},
                {'id': 'gpt-5.3-codex', 'display_name': 'GPT-5.3 Codex'},
                {'id': 'gpt-5.3-codex-spark', 'display_name': 'GPT-5.3 Codex Spark'},
                {'id': 'gpt-5.2-codex', 'display_name': 'GPT-5.2 Codex'},
                {'id': 'gpt-5.2', 'display_name': 'GPT-5.2'},
                {'id': 'gpt-5.1-codex-max', 'display_name': 'GPT-5.1 Codex Max'},
                {'id': 'gpt-5.1-codex-mini', 'display_name': 'GPT-5.1 Codex Mini'},
                {'id': 'gpt-5.1', 'display_name': 'GPT-5.1'},
                {'id': 'gpt-5-codex', 'display_name': 'GPT-5 Codex'},
                {'id': 'gpt-5-codex-mini', 'display_name': 'GPT-5 Codex Mini'},
                {'id': 'gpt-5-mini', 'display_name': 'GPT-5 Mini'},
                {'id': 'gpt-5-nano', 'display_name': 'GPT-5 Nano'},
                {'id': 'gpt-oss:120b', 'display_name': 'GPT-OSS 120B (Local)'},
                {'id': 'gpt-oss:20b', 'display_name': 'GPT-OSS 20B (Local)'},
            ]
        }

    # ══════════════════════════════════════════════════════════════════════
    # Inline AI Autocomplete (ghost text)
    # ══════════════════════════════════════════════════════════════════════
    _ai_complete_proc = None

    def ai_inline_complete(self, code_before, code_after):
        """Quick inline code completion using Claude CLI (haiku for speed).
        Returns {'status': 'success', 'completion': '...'} or error.
        """
        # Cancel any previous completion subprocess
        if AIEditMixin._ai_complete_proc and AIEditMixin._ai_complete_proc.poll() is None:
            try:
                AIEditMixin._ai_complete_proc.kill()
            except Exception:
                pass

        # Trim context to last 60 lines before cursor and 20 lines after
        before_lines = code_before.split('\n')
        after_lines = code_after.split('\n')
        trimmed_before = '\n'.join(before_lines[-60:])
        trimmed_after = '\n'.join(after_lines[:20])

        prompt = (
            "You are an inline code autocomplete engine for Manim (Python math animation library).\n"
            "Complete the code at the cursor position. Output ONLY the completion text — "
            "no explanation, no markdown fences, no repeating existing code.\n"
            "Keep it short (1-3 lines max). If unsure, output nothing.\n\n"
            f"Code before cursor:\n```\n{trimmed_before}\n```\n\n"
            f"Code after cursor:\n```\n{trimmed_after}\n```\n\n"
            "Completion:"
        )

        try:
            cmd = ['claude', '-p', prompt, '--output-format', 'text',
                   '--model', 'claude-haiku-4-5-20251001']
            env = _get_clean_env()
            for key in ('CLAUDECODE', 'CLAUDE_CODE'):
                env.pop(key, None)

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                env=env,
            )
            AIEditMixin._ai_complete_proc = proc
            stdout, _ = proc.communicate(timeout=30)
            AIEditMixin._ai_complete_proc = None

            completion = (stdout or '').strip()
            if not completion:
                return {'status': 'empty'}

            # Clean up: remove markdown fences if AI added them
            if completion.startswith('```'):
                lines = completion.split('\n')
                lines = [l for l in lines if not l.strip().startswith('```')]
                completion = '\n'.join(lines).strip()

            return {'status': 'success', 'completion': completion}
        except subprocess.TimeoutExpired:
            if AIEditMixin._ai_complete_proc:
                try:
                    AIEditMixin._ai_complete_proc.kill()
                except Exception:
                    pass
                AIEditMixin._ai_complete_proc = None
            return {'status': 'timeout'}
        except Exception as e:
            print(f"[AI COMPLETE] Error: {e}")
            return {'status': 'error', 'message': str(e)}

    # ══════════════════════════════════════════════════════════════════════
    # AI Agent (autonomous generate → render → screenshot → fix loop)
    # ══════════════════════════════════════════════════════════════════════

    _ai_agent_active = False
    _ai_agent_step = 'idle'
    _ai_agent_message = ''
    _ai_agent_code = ''
    _ai_agent_iteration = 0
    _ai_agent_max_iters = 5
    _ai_agent_description = ''
    _ai_agent_action = None       # dict for JS to execute
    _ai_agent_action_id = 0       # monotonic ID to avoid double-exec
    _ai_agent_ui_action = None    # visual cursor hint for JS
    _ai_agent_history = []
    _ai_agent_screenshots = []
    _ai_agent_feedback = None
    _ai_agent_feedback_event = None
    _ai_agent_cancel_flag = False
    _ai_agent_model = ''
    _ai_agent_stream_events = []  # live stream-json events from edit subprocess

    _ai_agent_provider = 'claude'  # 'claude' or 'codex'

    def ai_agent_start(self, description, max_iterations=5, model='', provider='claude'):
        """Start the autonomous AI agent workflow."""
        if AIEditMixin._ai_agent_active:
            return {'status': 'error', 'message': 'Agent already running'}
        AIEditMixin._ai_agent_model = (model or '').strip()
        AIEditMixin._ai_agent_provider = provider or 'claude'

        if provider == 'codex':
            check = self.check_codex_installed()
            if not check.get('installed'):
                return {'status': 'error', 'message': 'Codex CLI required for agent'}
        else:
            check = self.check_claude_code_installed()
            if not check.get('installed'):
                return {'status': 'error', 'message': 'Claude Code CLI required for agent'}

        # Reset state
        AIEditMixin._ai_agent_active = True
        AIEditMixin._ai_agent_step = 'generating'
        AIEditMixin._ai_agent_message = 'Starting...'
        AIEditMixin._ai_agent_code = ''
        AIEditMixin._ai_agent_iteration = 0
        AIEditMixin._ai_agent_max_iters = max_iterations
        AIEditMixin._ai_agent_description = description
        AIEditMixin._ai_agent_action = None
        AIEditMixin._ai_agent_action_id = 0
        AIEditMixin._ai_agent_ui_action = None
        AIEditMixin._ai_agent_history = []
        AIEditMixin._ai_agent_screenshots = []
        AIEditMixin._ai_agent_feedback = None
        AIEditMixin._ai_agent_feedback_event = threading.Event()
        AIEditMixin._ai_agent_cancel_flag = False
        # Reset session memory for fresh agent run
        AIEditMixin._ai_agent_session_id = None
        AIEditMixin._ai_agent_workspace = None
        AIEditMixin._ai_agent_first_edit = True

        t = threading.Thread(target=self._ai_agent_run,
                             args=(description, max_iterations), daemon=True)
        t.start()
        return {'status': 'started'}

    def _ai_agent_set(self, step, message, action=None, ui_action=None):
        """Update agent state."""
        AIEditMixin._ai_agent_step = step
        AIEditMixin._ai_agent_message = message
        if action:
            AIEditMixin._ai_agent_action_id += 1
            action['_id'] = AIEditMixin._ai_agent_action_id
        AIEditMixin._ai_agent_action = action
        AIEditMixin._ai_agent_ui_action = ui_action
        AIEditMixin._ai_agent_history.append({
            'step': step, 'message': message, 'time': time.time()
        })
        print(f"[AI AGENT] {step}: {message}")

    def _ai_agent_wait(self, timeout=180):
        """Block until JS sends feedback."""
        ev = AIEditMixin._ai_agent_feedback_event
        ev.clear()
        AIEditMixin._ai_agent_feedback = None
        ev.wait(timeout=timeout)
        return AIEditMixin._ai_agent_feedback

    def _ai_agent_edit(self, code, instruction):
        """Run AI CLI in a workspace to edit scene.py. Returns the edited code or None.
        Supports both Claude and Codex providers.
        Reuses workspace and session across iterations for memory.
        Streams output to _ai_agent_stream_events for live UI display."""
        if AIEditMixin._ai_agent_provider == 'codex':
            return self._ai_agent_edit_codex(code, instruction)
        try:
            # Reuse or create workspace
            if AIEditMixin._ai_agent_workspace and os.path.isdir(AIEditMixin._ai_agent_workspace):
                workspace = AIEditMixin._ai_agent_workspace
            else:
                _cleanup_old_workspaces()
                ts = int(time.time())
                workspace = os.path.join(_preview_dir, f'ai_agent_ws_{ts}')
                os.makedirs(workspace, exist_ok=True)
                _init_workspace_git(workspace)
                AIEditMixin._ai_agent_workspace = workspace
                AIEditMixin._ai_agent_session_id = str(uuid.uuid4())
                AIEditMixin._ai_agent_first_edit = True
                _link_assets(workspace)

            # Write scene.py
            code_file = os.path.join(workspace, 'scene.py')
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # Write CLAUDE.md (only on first edit — it doesn't change)
            if AIEditMixin._ai_agent_first_edit:
                md_path = os.path.join(workspace, 'CLAUDE.md')
                claude_md_content = (
                    "# Workspace Rules\n\n"
                    "Edit `scene.py` only. No explanations.\n\n"
                    "## CRITICAL: ALWAYS read scene.py FIRST before any edit.\n"
                    "Never guess file contents. Use Read tool to read it.\n\n"
                    "## NOT Allowed\n"
                    "- Do NOT run pip, python, manim, or any execution commands\n"
                    "- Do NOT create files other than `scene.py`\n\n"
                    "## Manim Context\n"
                    "- Always include `from manim import *`\n"
                    "- Must have a Scene class with `construct(self)` method\n"
                    "- Common: Text, MathTex, Circle, Square, Arrow, VGroup, "
                    "NumberPlane, SVGMobject, ImageMobject\n"
                    "- Animations: Write, FadeIn, FadeOut, Transform, "
                    "ReplacementTransform, Create, GrowFromCenter, MoveToTarget\n"
                    "- Use `self.play(...)` to animate, `self.wait()` to pause\n"
                    "- Position: `.to_edge()`, `.to_corner()`, `.next_to()`, "
                    "`.shift()`, `.move_to()`\n"
                    "- Colors: WHITE, YELLOW, BLUE, RED, GREEN, PURPLE, ORANGE\n"
                    "- Keep text readable (font_size=36+), don't overlap objects\n"
                )

                # List available assets
                if _assets_dir and os.path.isdir(_assets_dir):
                    try:
                        asset_files = [f for f in os.listdir(_assets_dir)
                                       if os.path.isfile(os.path.join(_assets_dir, f))]
                        if asset_files:
                            claude_md_content += (
                                "\n## Available Assets\n"
                                "These files are in the `./assets/` folder:\n"
                            )
                            for af in sorted(asset_files):
                                claude_md_content += f"- {af}\n"
                            claude_md_content += (
                                "\nUse relative path `./assets/filename` in code to reference them.\n"
                            )
                    except Exception:
                        pass

                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(claude_md_content)

            # Write instruction to file to avoid OS arg length limits
            instruction_file = os.path.join(workspace, '_instruction.txt')
            with open(instruction_file, 'w', encoding='utf-8') as f:
                f.write(instruction)

            # Build command with session support for token efficiency.
            # First edit: --session-id to create session.
            # Subsequent edits: --resume to reuse cached context (70-80% token savings).
            session_id = AIEditMixin._ai_agent_session_id
            cmd = [
                'claude', '-p', '--output-format', 'stream-json',
                '--verbose',
                '--allowedTools', 'Read,Write,Edit,Bash,Glob,Grep',
            ]
            if AIEditMixin._ai_agent_first_edit:
                cmd.extend(['--session-id', session_id])
            else:
                cmd.extend(['--resume', session_id])
            if AIEditMixin._ai_agent_model:
                cmd.extend(['--model', AIEditMixin._ai_agent_model])

            env = _get_clean_env()
            for key in ('CLAUDECODE', 'CLAUDE_CODE'):
                env.pop(key, None)

            session_flag = '--session-id' if AIEditMixin._ai_agent_first_edit else '--resume'
            print(f"[AI AGENT] Edit: claude -p (stdin, {len(instruction)} chars) "
                  f"{session_flag} {session_id[:8]}... --cwd {workspace}"
                  + (f" --model {AIEditMixin._ai_agent_model}" if AIEditMixin._ai_agent_model else ""))

            # Reset stream chunks for live display
            AIEditMixin._ai_agent_stream_events = []

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1,
                cwd=workspace, env=env,
            )

            # Write instruction via stdin to avoid arg length limits
            try:
                proc.stdin.write(instruction)
                proc.stdin.close()
            except Exception as e:
                print(f"[AI AGENT] stdin write error: {e}")

            # Mark first edit done so subsequent calls use --resume
            AIEditMixin._ai_agent_first_edit = False

            # Stream output — parse stream-json for live display
            result_text = ''
            try:
                for line in proc.stdout:
                    if AIEditMixin._ai_agent_cancel_flag:
                        proc.kill()
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        AIEditMixin._ai_agent_stream_events.append({'_kind': 'raw', '_text': line})
                        continue

                    ev_type = event.get('type', '')

                    if ev_type == 'result':
                        result_text = event.get('result', '')
                        cost = event.get('total_cost_usd')
                        dur = event.get('duration_ms')
                        if cost is not None:
                            AIEditMixin._ai_agent_stream_events.append({
                                '_kind': 'text',
                                '_text': f'Cost: ${cost:.4f}  Duration: {(dur or 0)/1000:.1f}s'
                            })
                        continue

                    if ev_type in ('system', 'rate_limit_event'):
                        continue

                    if ev_type == 'assistant':
                        for block in (event.get('message', {}).get('content') or []):
                            if not isinstance(block, dict):
                                continue
                            btype = block.get('type', '')
                            if btype == 'tool_use':
                                tool = block.get('name', '')
                                inp = block.get('input', {})
                                arg = ''
                                if isinstance(inp, dict):
                                    arg = (inp.get('file_path') or inp.get('path')
                                           or inp.get('command') or inp.get('query') or '')
                                    if isinstance(arg, str) and len(arg) > 60:
                                        arg = '...' + arg[-50:]
                                AIEditMixin._ai_agent_stream_events.append({
                                    '_kind': 'tool_use', '_tool': tool, '_arg': arg, '_input': inp})
                                content = inp.get('content', '') if isinstance(inp, dict) else ''
                                if content and tool in ('Write', 'Edit'):
                                    for i, cl in enumerate(content.split('\n'), 1):
                                        AIEditMixin._ai_agent_stream_events.append({
                                            '_kind': 'code_line', '_num': i, '_text': cl})
                            elif btype == 'text':
                                text = block.get('text', '').strip()
                                if text:
                                    AIEditMixin._ai_agent_stream_events.append({
                                        '_kind': 'text', '_text': text})
                        continue

                    if ev_type == 'user':
                        tr = event.get('tool_use_result', {})
                        if isinstance(tr, dict):
                            stdout_out = tr.get('stdout', '')
                            content = tr.get('content', '')
                            if stdout_out:
                                out_lines = stdout_out.strip().split('\n')
                                for ol in out_lines[:15]:
                                    AIEditMixin._ai_agent_stream_events.append({
                                        '_kind': 'result_line', '_text': ol})
                                if len(out_lines) > 15:
                                    AIEditMixin._ai_agent_stream_events.append({
                                        '_kind': 'collapsed', '_text': f'+{len(out_lines)-15} lines'})
                            elif isinstance(content, str) and content.strip():
                                short = content.strip()[:200]
                                AIEditMixin._ai_agent_stream_events.append({
                                    '_kind': 'result_line', '_text': short})
                        continue

            except Exception as e:
                print(f"[AI AGENT] stream read error: {e}")

            proc.wait()
            print(f"[AI AGENT] Claude edit done (rc={proc.returncode})")

            # Read the edited scene.py
            if os.path.exists(code_file):
                with open(code_file, 'r', encoding='utf-8') as f:
                    result = f.read().strip()
                if result and result != code.strip():
                    print(f"[AI AGENT] scene.py changed ({len(result)} chars)")
                    return result
                elif result:
                    print(f"[AI AGENT] scene.py unchanged, checking result text for code")

            # Fallback: try to extract code from result text
            if result_text:
                extracted = self._extract_code_from_ai_response(result_text.strip())
                if extracted:
                    print(f"[AI AGENT] Extracted code from result ({len(extracted)} chars)")
                    return extracted

            # If Claude failed (non-zero rc) and code unchanged, treat as error
            if proc.returncode != 0:
                print(f"[AI AGENT] Claude failed (rc={proc.returncode}), code unchanged")
                return None

            # Return the file content even if "unchanged" — it may be the generated code
            if os.path.exists(code_file):
                with open(code_file, 'r', encoding='utf-8') as f:
                    return f.read().strip() or None

            return None
        except Exception as e:
            print(f"[AI AGENT] edit error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _ai_agent_edit_codex(self, code, instruction):
        """Codex-based agent edit. Similar to Claude path but uses codex exec."""
        try:
            # Reuse or create workspace
            if AIEditMixin._ai_agent_workspace and os.path.isdir(AIEditMixin._ai_agent_workspace):
                workspace = AIEditMixin._ai_agent_workspace
            else:
                _cleanup_old_workspaces()
                ts = int(time.time())
                workspace = os.path.join(_preview_dir, f'ai_agent_ws_{ts}')
                os.makedirs(workspace, exist_ok=True)
                _init_workspace_git(workspace)
                AIEditMixin._ai_agent_workspace = workspace
                _link_assets(workspace)

            code_file = os.path.join(workspace, 'scene.py')
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # Write detailed AGENTS.md (only on first iteration)
            if not os.path.exists(os.path.join(workspace, 'AGENTS.md')):
                md_content = (
                    "# Workspace Rules\n\n"
                    "Edit `scene.py` only. No explanations.\n\n"
                    "## CRITICAL: ALWAYS read scene.py FIRST before any edit.\n"
                    "Never guess file contents. Use cat or shell to read it.\n\n"
                    "## NOT Allowed\n"
                    "- Do NOT run pip, python, manim, or any execution commands\n"
                    "- Do NOT create files other than `scene.py`\n\n"
                    "## Manim Context\n"
                    "- `scene.py` is a Manim (Python math animation library) file\n"
                    "- Always include `from manim import *`\n"
                    "- Must have a Scene class with `construct(self)` method\n"
                    "- Common: Text, MathTex, Circle, Square, Arrow, VGroup, "
                    "NumberPlane, SVGMobject, ImageMobject\n"
                    "- Animations: Write, FadeIn, FadeOut, Transform, "
                    "ReplacementTransform, Create, GrowFromCenter, MoveToTarget\n"
                    "- Use `self.play(...)` to animate, `self.wait()` to pause\n"
                    "- Position: `.to_edge()`, `.to_corner()`, `.next_to()`, "
                    "`.shift()`, `.move_to()`\n"
                    "- Colors: WHITE, YELLOW, BLUE, RED, GREEN, PURPLE, ORANGE\n"
                    "- Keep text readable (font_size=36+), don't overlap objects\n"
                )
                # List available assets
                if _assets_dir and os.path.isdir(_assets_dir):
                    try:
                        asset_files = [f for f in os.listdir(_assets_dir)
                                       if os.path.isfile(os.path.join(_assets_dir, f))]
                        if asset_files:
                            md_content += (
                                "\n## Available Assets\n"
                                "These files are in the `./assets/` folder:\n"
                            )
                            for af in sorted(asset_files):
                                md_content += f"- {af}\n"
                            md_content += (
                                "\nUse relative path `./assets/filename` in code "
                                "to reference them.\n"
                            )
                    except Exception:
                        pass

                for fname in ('AGENTS.md', 'CLAUDE.md'):
                    md_path = os.path.join(workspace, fname)
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)

            cmd = ['codex', 'exec', '-', '--full-auto',
                   '--skip-git-repo-check', '--json']
            if AIEditMixin._ai_agent_model:
                cmd.extend(['-m', AIEditMixin._ai_agent_model])

            env = _get_clean_env()
            AIEditMixin._ai_agent_stream_events = []

            print(f"[AI AGENT] Codex edit: {len(instruction)} chars instruction")
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, cwd=workspace, env=env,
            )
            try:
                proc.stdin.write(instruction)
                proc.stdin.close()
            except Exception as e:
                print(f"[AI AGENT] Codex stdin error: {e}")

            # Parse JSONL events for live display
            try:
                for line in proc.stdout:
                    if AIEditMixin._ai_agent_cancel_flag:
                        proc.kill()
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        AIEditMixin._ai_agent_stream_events.append(
                            {'_kind': 'raw', '_text': line})
                        continue

                    ev_type = event.get('type', '')
                    item = event.get('item', {})
                    item_type = item.get('type', '') if isinstance(item, dict) else ''

                    if ev_type in ('item.started', 'item.updated', 'item.completed'):
                        if item_type == 'command_execution':
                            cmd_text = item.get('command', '')
                            AIEditMixin._ai_agent_stream_events.append({
                                '_kind': 'tool_use', '_tool': 'Bash',
                                '_arg': cmd_text, '_input': item})
                            if ev_type == 'item.completed':
                                output = item.get('aggregated_output', '').strip()
                                if output:
                                    out_lines = output.split('\n')
                                    for ol in out_lines[:15]:
                                        AIEditMixin._ai_agent_stream_events.append({
                                            '_kind': 'result_line', '_text': ol})
                                    if len(out_lines) > 15:
                                        AIEditMixin._ai_agent_stream_events.append({
                                            '_kind': 'collapsed',
                                            '_text': f'+{len(out_lines)-15} lines'})
                                exit_code = item.get('exit_code')
                                if exit_code is not None and exit_code != 0:
                                    AIEditMixin._ai_agent_stream_events.append({
                                        '_kind': 'result_line',
                                        '_text': f'Exit code: {exit_code}'})

                        elif item_type == 'file_change':
                            for ch in item.get('changes', []):
                                path = ch.get('path', '')
                                kind = ch.get('kind', '')
                                tool = 'Write' if kind == 'add' else 'Edit'
                                AIEditMixin._ai_agent_stream_events.append({
                                    '_kind': 'tool_use', '_tool': tool,
                                    '_arg': path, '_input': ch})

                        elif item_type == 'agent_message':
                            text = item.get('text', '').strip()
                            if text:
                                AIEditMixin._ai_agent_stream_events.append({
                                    '_kind': 'text', '_text': text})

                        elif item_type == 'reasoning':
                            text = item.get('text', '').strip()
                            if text:
                                short = text[:150] + ('...' if len(text) > 150 else '')
                                AIEditMixin._ai_agent_stream_events.append({
                                    '_kind': 'text', '_text': short})

                        elif item_type == 'web_search':
                            query = item.get('query', '')
                            AIEditMixin._ai_agent_stream_events.append({
                                '_kind': 'tool_use', '_tool': 'WebSearch',
                                '_arg': query, '_input': item})

                        elif item_type == 'error':
                            msg = item.get('message', '')
                            AIEditMixin._ai_agent_stream_events.append({
                                '_kind': 'text', '_text': f'Error: {msg}'})
                            print(f"[AI AGENT] Codex error event: {msg}")

                    elif ev_type == 'turn.completed':
                        usage = event.get('usage', {})
                        if usage:
                            inp = usage.get('input_tokens', 0)
                            out = usage.get('output_tokens', 0)
                            AIEditMixin._ai_agent_stream_events.append({
                                '_kind': 'text',
                                '_text': f'Tokens: {inp} in / {out} out'})

                    elif ev_type == 'turn.failed':
                        err = event.get('error', {}).get('message', 'Unknown error')
                        AIEditMixin._ai_agent_stream_events.append({
                            '_kind': 'text', '_text': f'Turn failed: {err}'})
                        print(f"[AI AGENT] Codex turn failed: {err}")

            except Exception as e:
                print(f"[AI AGENT] Codex stream error: {e}")

            proc.wait()
            print(f"[AI AGENT] Codex edit done (rc={proc.returncode})")

            if os.path.exists(code_file):
                with open(code_file, 'r', encoding='utf-8') as f:
                    result = f.read().strip()
                if result and result != code.strip():
                    return result
                # Code unchanged — if codex failed (non-zero rc), treat as error
                if proc.returncode != 0:
                    print(f"[AI AGENT] Codex failed (rc={proc.returncode}), code unchanged")
                    return None
                # Code unchanged but rc=0 — codex chose not to change it
                return result or None
            return None
        except Exception as e:
            print(f"[AI AGENT] Codex edit error: {e}")
            return None

    def _ai_agent_review(self, prompt, screenshot_files=None):
        """Review call using the same provider as the agent.
        Codex agent → codex review (with -i images).
        Claude agent → claude review (with base64 images in prompt).
        """
        try:
            valid_imgs = [p for p in (screenshot_files or []) if os.path.isfile(p)]
            review_cwd = AIEditMixin._ai_agent_workspace or None

            if AIEditMixin._ai_agent_provider == 'codex':
                # ── Codex review: -i flag passes images natively ──
                cmd_list = ['codex', 'exec', '-', '--full-auto',
                            '--skip-git-repo-check', '--color', 'never']
                if AIEditMixin._ai_agent_model:
                    cmd_list.extend(['-m', AIEditMixin._ai_agent_model])
                for img_path in valid_imgs:
                    cmd_list.extend(['-i', img_path])

                env = _get_clean_env()
                print(f"[AI AGENT] Codex review: {len(prompt)} chars, "
                      f"{len(valid_imgs)} images via -i, cwd={review_cwd}")
                proc = subprocess.Popen(
                    cmd_list,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', errors='replace',
                    cwd=review_cwd, env=env,
                )
            else:
                # ── Claude review: let Claude read screenshot files from disk ──
                # Instead of embedding base64 (huge token cost), tell Claude
                # to use its Read tool to examine the JPEG files directly.
                cmd = ['claude', '-p', '--output-format', 'text',
                       '--allowedTools', 'Read,Glob']
                if AIEditMixin._ai_agent_model:
                    cmd.extend(['--model', AIEditMixin._ai_agent_model])

                # Tell Claude where the screenshot files are
                if valid_imgs:
                    # Use relative paths from workspace
                    rel_paths = []
                    for img_path in valid_imgs:
                        try:
                            rel = os.path.relpath(img_path, review_cwd)
                            rel_paths.append(rel)
                        except Exception:
                            rel_paths.append(img_path)
                    prompt += (
                        f"\n\nThere are {len(valid_imgs)} screenshot frames "
                        f"saved as JPEG files. Read each one using the Read tool:\n"
                    )
                    for rp in rel_paths:
                        prompt += f"- {rp}\n"
                    prompt += (
                        "\nYou MUST read ALL these image files to examine "
                        "every frame before giving your verdict.\n"
                    )

                env = _get_clean_env()
                for key in ('CLAUDECODE', 'CLAUDE_CODE'):
                    env.pop(key, None)

                print(f"[AI AGENT] Claude review: {len(prompt)} chars, "
                      f"{len(valid_imgs)} image files for Read tool, cwd={review_cwd}")
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', errors='replace',
                    cwd=review_cwd, env=env,
                )

            stdout, stderr = proc.communicate(input=prompt)
            result = (stdout or '').strip()
            if proc.returncode != 0 and not result:
                print(f"[AI AGENT] Review failed (rc={proc.returncode}): "
                      f"{(stderr or '')[:200]}")
            else:
                print(f"[AI AGENT] Review complete: {len(result)} chars "
                      f"(rc={proc.returncode})")
            return result if result else None
        except Exception as e:
            print(f"[AI AGENT] review error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _ai_agent_run(self, description, max_iterations):
        """Main agent loop (runs in thread). Never times out — loops until
        cancelled or the animation is correct."""
        try:
            # ── Step 1: Generate code via workspace ──
            self._ai_agent_set('generating', 'Creating Manim animation...')

            template = (
                "from manim import *\n\n"
                "class MyScene(Scene):\n"
                "    def construct(self):\n"
                "        pass\n"
            )
            instruction = (
                f"Read `scene.py` first, then edit it to create a "
                f"Manim animation for:\n\n"
                f"{description}\n\n"
                f"Replace the placeholder code with a complete, working "
                f"animation and write it back to scene.py.\n"
                f"Use smooth animations (Write, FadeIn, Transform, etc.) "
                f"and add self.wait() between animations.\n"
                f"Make sure text is readable, objects don't overlap, "
                f"and colors have good contrast against a black background."
            )
            code = self._ai_agent_edit(template, instruction)
            if not code or AIEditMixin._ai_agent_cancel_flag:
                self._ai_agent_set('error', 'Failed to generate code')
                AIEditMixin._ai_agent_active = False
                return

            AIEditMixin._ai_agent_code = code
            consecutive_errors = 0
            consecutive_edit_failures = 0

            # ── Loop forever until cancelled or satisfied ──
            it = 0
            while not AIEditMixin._ai_agent_cancel_flag:
                it += 1
                AIEditMixin._ai_agent_iteration = it

                # ── Safety: too many consecutive edit failures → stop ──
                if consecutive_edit_failures >= 5:
                    self._ai_agent_set('done',
                        'Stopping — AI edit failed too many times in a row')
                    AIEditMixin._ai_agent_active = False
                    return

                # ── Render preview ──
                self._ai_agent_set(
                    'rendering',
                    f'Rendering preview (attempt {it})...',
                    action={'type': 'set_code_and_preview', 'code': code},
                    ui_action={'type': 'click_button', 'target': 'previewBtn',
                               'label': 'Quick Preview'},
                )
                fb = self._ai_agent_wait(timeout=600)
                if AIEditMixin._ai_agent_cancel_flag:
                    break
                if not fb:
                    self._ai_agent_set('fixing', 'No response from render, retrying...')
                    time.sleep(2)
                    continue

                # ── Render failed → auto-debug ──
                if fb.get('type') == 'render_error':
                    err = fb.get('error', 'Unknown error')
                    consecutive_errors += 1
                    self._ai_agent_set(
                        'fixing',
                        f'Auto-fixing error (attempt {consecutive_errors}): {err[:100]}')
                    err_truncated = err[:1500] if len(err) > 1500 else err
                    fix_instruction = (
                        f"Read `scene.py` first. It has a render error:\n\n"
                        f"{err_truncated}\n\n"
                        f"Fix the bug and write the corrected code back to scene.py."
                    )
                    fixed = self._ai_agent_edit(code, fix_instruction)
                    if fixed and fixed.strip() != code.strip():
                        code = fixed
                        AIEditMixin._ai_agent_code = code
                        consecutive_edit_failures = 0
                    else:
                        consecutive_edit_failures += 1
                        print(f"[AI AGENT] Edit failed/unchanged "
                              f"({consecutive_edit_failures}/5)")
                    continue

                # ── Render succeeded ──
                if fb.get('type') == 'render_success':
                    consecutive_errors = 0

                    # ── Capture screenshots ──
                    self._ai_agent_set(
                        'capturing', 'Capturing 1 frame per second...',
                        action={'type': 'capture_screenshots'},
                        ui_action={'type': 'scrub_video'},
                    )
                    sfb = self._ai_agent_wait(timeout=60)
                    if AIEditMixin._ai_agent_cancel_flag:
                        break
                    shots = (sfb or {}).get('screenshots', [])
                    AIEditMixin._ai_agent_screenshots = shots

                    # ── Save ALL screenshots as files for review ──
                    workspace = AIEditMixin._ai_agent_workspace or _preview_dir
                    shots_dir = os.path.join(workspace, 'screenshots')
                    os.makedirs(shots_dir, exist_ok=True)
                    screenshot_files = []

                    for i, s in enumerate(shots):
                        data_url = s.get('dataUrl', '')
                        if not data_url or ',' not in data_url:
                            continue
                        try:
                            b64 = data_url.split(',', 1)[1]
                            img_bytes = base64.b64decode(b64)
                            fpath = os.path.join(shots_dir, f'frame_{i+1}.jpg')
                            with open(fpath, 'wb') as f:
                                f.write(img_bytes)
                            # Downscale to 960px wide to save ~75% image tokens
                            _downscale_image(fpath, max_width=960)
                            screenshot_files.append(fpath)
                        except Exception as e:
                            print(f"[AI AGENT] Screenshot save error: {e}")

                    # ── Review ──
                    self._ai_agent_set('analyzing',
                        f'Reviewing {len(screenshot_files)} frames...')

                    review_prompt = (
                        f"You are a visual QA reviewer for Manim animations.\n\n"
                        f"GOAL: \"{description}\"\n\n"
                        f"You MUST examine EVERY frame image carefully. "
                        f"There are {len(screenshot_files)} frames at 1 per second.\n\n"
                        f"Check each frame for these problems:\n"
                        f"1. DOESN'T MATCH GOAL — missing key elements that were "
                        f"requested, or showing wrong content entirely\n"
                        f"2. UNNATURAL/STRANGE — things that look weird or wrong, "
                        f"not how a proper math animation should look\n"
                        f"3. OVERLAPPING — objects or text piled on each other, "
                        f"making things unreadable\n"
                        f"4. OFF SCREEN — objects cut off at edges\n"
                        f"5. WRONG TEXT — typos, wrong words, wrong math, "
                        f"garbled or unreadable text\n"
                        f"6. DISCONNECTED — elements that should be connected "
                        f"look broken apart\n\n"
                        f"IGNORE: colors, fonts, spacing, timing, speed, style.\n\n"
                        f"IMPORTANT: If you find ANY of the above problems, "
                        f"you MUST say IMPROVE and describe what's wrong. "
                        f"Only say SATISFIED if there are ZERO problems.\n\n"
                        f"Reply:\n"
                        f"SATISFIED — if animation looks correct and natural\n"
                        f"IMPROVE: <what is wrong and needs fixing>"
                    )
                    review = self._ai_agent_review(review_prompt, screenshot_files)

                    # ── Review failed → skip review, continue loop ──
                    if not review:
                        review_retries = 0
                        while not review and review_retries < 2:
                            review_retries += 1
                            self._ai_agent_set('analyzing',
                                f'Review empty, retrying ({review_retries}/2)...')
                            time.sleep(2)
                            if AIEditMixin._ai_agent_cancel_flag:
                                break
                            review = self._ai_agent_review(review_prompt, screenshot_files)
                        if not review:
                            # Skip review — assume SATISFIED and finish
                            self._ai_agent_set('done',
                                'Animation rendered successfully!')
                            AIEditMixin._ai_agent_active = False
                            return

                    # ── Check verdict ──
                    print(f"[AI AGENT] Review result: {review[:300]}")
                    review_upper = review.upper()
                    if 'SATISFIED' in review_upper:
                        self._ai_agent_set('done',
                            'Animation complete!')
                        AIEditMixin._ai_agent_active = False
                        return

                    # ── Agent found issues → show what it found ──
                    tip = review
                    for prefix in ['IMPROVE:', 'improve:']:
                        if prefix in tip:
                            tip = tip.split(prefix, 1)[-1].strip()
                            break
                    # Show review findings in stream output
                    AIEditMixin._ai_agent_stream_events.append(
                        {'_kind': 'text', '_text': '─── Review Result ───'})
                    for line in tip.split('\n'):
                        line = line.strip()
                        if line:
                            AIEditMixin._ai_agent_stream_events.append(
                                {'_kind': 'text', '_text': line})
                    AIEditMixin._ai_agent_stream_events.append(
                        {'_kind': 'text', '_text': '─── Fixing... ───'})
                    self._ai_agent_set('fixing',
                        f'Found issue: {tip[:150]}')
                    # Give user time to read what was found
                    time.sleep(3)
                    tip_truncated = tip[:800] if len(tip) > 800 else tip
                    improve_instruction = (
                        f"Read `scene.py` first, then improve it based on this review:\n"
                        f"{tip_truncated}\n\n"
                        f"Apply the improvements and write the result back to scene.py."
                    )
                    improved = self._ai_agent_edit(code, improve_instruction)
                    if improved and improved.strip() != code.strip():
                        code = improved
                        AIEditMixin._ai_agent_code = code
                        consecutive_edit_failures = 0
                    else:
                        consecutive_edit_failures += 1
                        print(f"[AI AGENT] Improve failed/unchanged "
                              f"({consecutive_edit_failures}/5)")
                    # Loop continues — render again

                # ── Unknown feedback type → just continue ──
                else:
                    print(f"[AI AGENT] Unknown feedback type: {fb.get('type')}")
                    time.sleep(1)

            # Only reaches here if cancelled
            if AIEditMixin._ai_agent_cancel_flag:
                self._ai_agent_set('idle', 'Agent cancelled')
        except Exception as e:
            print(f"[AI AGENT] Error: {e}")
            self._ai_agent_set('error', str(e)[:200])
        finally:
            AIEditMixin._ai_agent_active = False

    def ai_agent_poll(self):
        """Poll agent state. Returns stream_output for live edit display."""
        # Format stream events for display (same format as non-agent Claude)
        stream_output = self._format_stream_events(
            AIEditMixin._ai_agent_stream_events) if AIEditMixin._ai_agent_stream_events else ''
        return {
            'active': AIEditMixin._ai_agent_active,
            'step': AIEditMixin._ai_agent_step,
            'message': AIEditMixin._ai_agent_message,
            'code': AIEditMixin._ai_agent_code,
            'iteration': AIEditMixin._ai_agent_iteration,
            'max_iterations': AIEditMixin._ai_agent_max_iters,
            'action': AIEditMixin._ai_agent_action,
            'ui_action': AIEditMixin._ai_agent_ui_action,
            'history': AIEditMixin._ai_agent_history[-20:],
            'screenshots': [{'time': s.get('time')} for s in AIEditMixin._ai_agent_screenshots],
            'stream_output': stream_output,
        }

    def ai_agent_feedback(self, feedback):
        """Receive feedback from JS (render result, screenshots, etc.)."""
        AIEditMixin._ai_agent_feedback = feedback
        if AIEditMixin._ai_agent_feedback_event:
            AIEditMixin._ai_agent_feedback_event.set()
        return {'status': 'ok'}

    def ai_agent_cancel(self):
        """Cancel running agent and reset session state."""
        AIEditMixin._ai_agent_cancel_flag = True
        if AIEditMixin._ai_agent_feedback_event:
            AIEditMixin._ai_agent_feedback_event.set()
        AIEditMixin._ai_agent_active = False
        AIEditMixin._ai_agent_step = 'idle'
        AIEditMixin._ai_agent_action = None
        # Reset session memory
        AIEditMixin._ai_agent_session_id = None
        AIEditMixin._ai_agent_workspace = None
        AIEditMixin._ai_agent_first_edit = True
        return {'status': 'cancelled'}

    @staticmethod
    def _extract_code_from_ai_response(raw):
        """Strip markdown fences, preamble, trailing explanations.
        Returns only the Python code, or None if response is not code."""
        text = raw.strip()
        if not text:
            return None

        # 1) Extract from ```python ... ``` fences
        fence_match = re.search(r'```(?:python)?\s*\n(.*?)```', text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
            return text if text else None

        # 2) Check if it looks like code
        code_indicators = [
            r'^\s*(from|import)\s+', r'^\s*class\s+\w+',
            r'^\s*def\s+\w+', r'^\s*self\.', r'^\s*#',
        ]
        has_code = any(re.search(pat, text, re.MULTILINE) for pat in code_indicators)
        if not has_code:
            return None

        # 3) Strip preamble
        lines = text.split('\n')
        start = 0
        preamble_patterns = [
            r'^here\s+(is|are)', r'^sure[,!.]',
            r'^i\'ve\s+(updated|modified|edited|fixed|changed)',
            r'^the\s+(updated|modified|edited|fixed|new)',
            r'^below\s+is', r'^this\s+(code|version|script)',
            r'^certainly', r'^of\s+course',
        ]
        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if not stripped:
                continue
            if any(re.match(p, stripped) for p in preamble_patterns):
                start = i + 1
                while start < len(lines) and not lines[start].strip():
                    start += 1
                continue
            break

        # 4) Strip postamble
        end = len(lines)
        postamble_patterns = [
            r'^(this|the|i|note|key|these)\s+(code|change|modif|update|add)',
            r'^let\s+me\s+know', r'^i\s+(hope|made|also|added)',
            r'^explanation', r'^changes?\s*(made|:)',
            r'^\*\*', r'^\d+\.\s+\*\*',
        ]
        for i in range(len(lines) - 1, start - 1, -1):
            stripped = lines[i].strip().lower()
            if not stripped:
                continue
            if any(re.match(p, stripped) for p in postamble_patterns):
                end = i
                while end > start and not lines[end - 1].strip():
                    end -= 1
                continue
            break

        cleaned = '\n'.join(lines[start:end]).strip()
        return cleaned if cleaned else None
