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

# ── Module-level refs injected by init_ai_edit() ──
_preview_dir = None
_get_clean_env = None


def init_ai_edit(preview_dir, get_clean_env_func):
    """Initialise module-level dependencies (called once from app.py)."""
    global _preview_dir, _get_clean_env
    _preview_dir = preview_dir
    _get_clean_env = get_clean_env_func


def _cleanup_old_workspaces(max_age=3600):
    """Remove ai_workspace_* and ai_images dirs older than max_age seconds."""
    if not _preview_dir or not os.path.isdir(_preview_dir):
        return
    now = time.time()
    for name in os.listdir(_preview_dir):
        if not (name.startswith('ai_workspace_') or name == 'ai_images'):
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
        """Build the instruction string used by both Codex and Claude."""
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
                f"Read scene.py, apply the changes, and write it back. "
                f"Keep all existing code that wasn't asked to change."
                f"{search_hint}{image_hint}"
            )
        else:
            return (
                f"Edit the file `scene.py` in this directory.\n\n"
                f"Instruction: {prompt}\n\n"
                f"Read scene.py, apply the changes, and write it back. "
                f"Keep all existing code that wasn't asked to change. "
                f"This is a Manim (Python math animation library) file."
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

        code_file = os.path.join(workspace, 'scene.py')
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code)

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
        for fname in ('AGENTS.md', 'CLAUDE.md'):
            md_path = os.path.join(workspace, fname)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(
                    "# Workspace Rules\n\n"
                    "You are a **code editor**. Your only job is to edit `scene.py` in this directory.\n\n"
                    "## Workflow\n"
                    "1. Read `scene.py` using shell commands\n"
                    "2. Apply the requested changes\n"
                    "3. Write the modified content back to `scene.py`\n"
                    "4. Done\n\n"
                    "## Allowed\n"
                    "- Reading files (Get-Content, cat, etc.)\n"
                    "- Writing/editing files (Set-Content, patch, etc.)\n"
                    "- Listing directory contents\n\n"
                    "## NOT Allowed\n"
                    "- Do NOT run pip, python, manim, or any build/execution commands\n"
                    "- Do NOT create any files other than editing `scene.py`\n"
                    "- Do NOT give explanations — just edit the file\n\n"
                    "## Context\n"
                    "- `scene.py` is a Manim (Python math animation library) file\n"
                    "- Keep all existing code that wasn't asked to change\n"
                )

        return workspace, code_file, copied_images

    def ai_edit_claude_start(self, code, prompt, model='', search=False,
                             selected_code='', selection_start=0, selection_end=0,
                             image_paths=None):
        """Start Claude Code via ``claude -p --output-format stream-json``.
        Poll with ai_edit_claude_poll().
        """
        # Cancel any running session first
        self.ai_edit_cancel()
        self.ai_edit_claude_cancel()

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

            workspace, code_file, image_paths = self._setup_ai_workspace(code, image_paths or [])
            instruction = self._build_ai_instruction(
                prompt, selected_code, selection_start, selection_end, search, image_paths)

            # Reset state
            AIEditMixin._ai_claude_events = []
            AIEditMixin._ai_claude_raw_chunks = []
            AIEditMixin._ai_claude_done = False
            AIEditMixin._ai_claude_workspace = workspace
            AIEditMixin._ai_claude_code_file = code_file
            AIEditMixin._ai_claude_original_code = code
            AIEditMixin._ai_claude_result_text = ''

            # Build command
            cmd_parts = [
                'claude', '-p', instruction,
                '--output-format', 'stream-json',
                '--verbose',
                '--allowedTools', 'Read,Write,Edit,Bash,Glob,Grep,WebSearch,WebFetch',
            ]
            if use_model:
                cmd_parts.extend(['--model', use_model])

            print(f"[AI CLAUDE] Command: claude -p <{len(instruction)} chars> "
                  f"--output-format stream-json --allowedTools Read,Write,Edit,Bash,Glob,Grep,WebSearch,WebFetch"
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
        """Kill Claude Code process and clean up."""
        proc = AIEditMixin._ai_claude_proc
        if proc:
            try:
                proc.kill()
                print("[AI CLAUDE] Process cancelled")
            except Exception:
                pass
            AIEditMixin._ai_claude_proc = None

        workspace = AIEditMixin._ai_claude_workspace
        if workspace and os.path.exists(workspace):
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

            # ── Build command (shell=True needed for .cmd wrapper on Windows) ──
            cmd_parts = 'codex exec - --yolo --json'
            if use_model:
                cmd_parts += f' -m "{use_model}"'
            if search:
                cmd_parts += ' -c web_search=live'
            if image_paths:
                for ip in image_paths:
                    cmd_parts += f' --image "{ip}"'

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
            print(f"[AI EDIT] Command: codex exec - --yolo --json"
                  + (f" -m {use_model}" if use_model else ""))

            proc = subprocess.Popen(
                cmd_parts,
                shell=True,
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
