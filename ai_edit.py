"""
AI Edit Module — Claude Code + OpenAI Codex integration.
Provides AIEditMixin class that ManimAPI inherits from.
"""
import os
import subprocess
import time
import re

# ── Module-level refs injected by init_ai_edit() ──
_preview_dir = None
_get_clean_env = None


def init_ai_edit(preview_dir, get_clean_env_func):
    """Initialise module-level dependencies (called once from app.py)."""
    global _preview_dir, _get_clean_env
    _preview_dir = preview_dir
    _get_clean_env = get_clean_env_func


class AIEditMixin:
    """Mixin providing all AI-edit pywebview API methods.

    ManimAPI inherits this so every method is callable from JS
    via ``pywebview.api.<method>()``.
    """

    def check_claude_code_installed(self):
        """Check if Claude Code CLI is installed.
        Uses 'claude --help' with shell=True so Windows can find .cmd wrappers.
        """
        try:
            result = subprocess.run(
                'claude --help',
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10,
                shell=True,
                env=_get_clean_env()
            )
            output = (result.stdout or '').strip() + (result.stderr or '').strip()
            # If we got any meaningful output, the CLI is installed
            if output and ('claude' in output.lower() or 'usage' in output.lower()
                          or 'anthropic' in output.lower() or len(output) > 20):
                print(f"[CLAUDE CODE] Found (help output: {len(output)} chars)")
                return {
                    'status': 'success',
                    'installed': True,
                    'version': 'installed'
                }
            else:
                print(f"[CLAUDE CODE] Not detected (rc={result.returncode}, output={output[:100]})")
                return {
                    'status': 'success',
                    'installed': False,
                    'message': 'Claude Code not found'
                }
        except FileNotFoundError:
            print("[CLAUDE CODE] Not installed (command not found)")
            return {
                'status': 'success',
                'installed': False,
                'message': 'Claude Code not installed. Install with: npm install -g @anthropic-ai/claude-code'
            }
        except Exception as e:
            print(f"[CLAUDE CODE ERROR] {e}")
            return {
                'status': 'error',
                'message': str(e),
                'installed': False
            }

    # ── Cached model list ──
    _cached_models = None

    @staticmethod
    def _model_id_to_display(model_id):
        """Convert a model ID like 'claude-sonnet-4-6' → 'Sonnet 4.6'."""
        s = model_id.strip()
        # Remove 'claude-' prefix
        s = re.sub(r'^claude-', '', s)
        # Remove dated suffix like -20250514 or -20251001
        s = re.sub(r'-\d{8}$', '', s)
        # Parse family-major-minor  e.g. 'sonnet-4-6', 'opus-4-6', 'haiku-4-5'
        m = re.match(r'([a-z]+)-(\d+)-(\d+)', s)
        if m:
            family = m.group(1).capitalize()
            return f"{family} {m.group(2)}.{m.group(3)}"
        # Alias like 'sonnet', 'opus', 'haiku'
        m2 = re.match(r'([a-z]+)-(\d+)-(\d+)', s)
        if not m2:
            return s.capitalize()
        return s

    def get_claude_models(self):
        """Return {current_model, models: [{id, display_name}]}.

        Fetches available models from:
          1. Anthropic API  (if ANTHROPIC_API_KEY is set)
          2. ~/.claude.json  usage history (models the user actually used)
          3. Known current model aliases as fallback

        Also returns the currently configured model from settings.
        """
        import json as _json

        home_dir = os.path.expanduser('~')
        project_dir = os.path.dirname(os.path.abspath(__file__))

        # ── 1. Detect current configured model from settings ──
        current_model = ''
        if os.name == 'nt':
            managed = os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'),
                                   'ClaudeCode', 'managed-settings.json')
        else:
            managed = '/etc/claude-code/managed-settings.json'

        settings_paths = [
            managed,
            os.path.join(project_dir, '.claude', 'settings.local.json'),
            os.path.join(project_dir, '.claude', 'settings.json'),
            os.path.join(home_dir, '.claude', 'settings.json'),
        ]
        for path in settings_paths:
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = _json.load(f)
                    val = data.get('model')
                    if val:
                        current_model = str(val)
                        break
                except Exception:
                    pass
        if not current_model:
            current_model = os.environ.get('ANTHROPIC_MODEL', '')

        # ── 2. Return cache if available ──
        if AIEditMixin._cached_models is not None:
            return {'current_model': current_model, 'models': AIEditMixin._cached_models}

        fetched_models = []

        # ── 3. Read usage history from ~/.claude.json ──
        usage_model_ids = set()
        claude_json = os.path.join(home_dir, '.claude.json')
        if os.path.isfile(claude_json):
            try:
                with open(claude_json, 'r', encoding='utf-8') as f:
                    cj = _json.load(f)
                projects = cj.get('projects', {})
                for pkey, pval in projects.items():
                    if isinstance(pval, dict):
                        usage = pval.get('lastModelUsage', {})
                        if isinstance(usage, dict):
                            for mid in usage.keys():
                                if mid and 'claude' in mid:
                                    usage_model_ids.add(mid)
            except Exception as e:
                print(f"[AI MODELS] Failed to read .claude.json: {e}")

        # ── 4. Merge: API results + usage history ──
        seen_ids = {m['id'] for m in fetched_models}
        for mid in usage_model_ids:
            if mid not in seen_ids:
                fetched_models.append({
                    'id': mid,
                    'display_name': self._model_id_to_display(mid)
                })
                seen_ids.add(mid)

        # ── 5. Deduplicate: keep only the latest version per family ──
        # Group by family (sonnet, opus, haiku)
        family_map = {}  # family → {version_tuple: model_info}
        other_models = []
        for m in fetched_models:
            mid = m['id']
            match = re.match(r'claude-([a-z]+)-(\d+)-(\d+)', mid)
            if match:
                family = match.group(1)
                ver = (int(match.group(2)), int(match.group(3)))
                if family not in family_map or ver > family_map[family][0]:
                    family_map[family] = (ver, m)
            else:
                other_models.append(m)

        # Build final list: latest per family, sorted by relevance
        final_models = []
        family_order = ['sonnet', 'opus', 'haiku']
        for fam in family_order:
            if fam in family_map:
                final_models.append(family_map[fam][1])
        # Add any families not in the default order
        for fam, (ver, m) in family_map.items():
            if fam not in family_order:
                final_models.append(m)

        # If nothing was found at all, provide known defaults
        if not final_models:
            final_models = [
                {'id': 'claude-sonnet-4-6', 'display_name': 'Sonnet 4.6'},
                {'id': 'claude-opus-4-6', 'display_name': 'Opus 4.6'},
                {'id': 'claude-haiku-4-5', 'display_name': 'Haiku 4.5'},
                {'id': 'sonnet', 'display_name': 'Sonnet (latest)'},
                {'id': 'opus', 'display_name': 'Opus (latest)'},
                {'id': 'haiku', 'display_name': 'Haiku (latest)'},
            ]

        AIEditMixin._cached_models = final_models
        return {'current_model': current_model, 'models': final_models}

    # ── Streaming AI edit state ──
    _ai_proc = None           # subprocess.Popen
    _ai_output_buf = ''       # accumulated stdout+stderr (merged)
    _ai_done = False
    _ai_returncode = None
    _ai_workspace = None      # isolated temp workspace directory
    _ai_code_file = None      # path to scene.py inside workspace
    _ai_prompt_file = None    # path to instruction file inside workspace
    _ai_original_code = ''    # original code for comparison
    _ai_codex_provider = False  # True when current edit is via Codex CLI

    def ai_edit_code(self, code, prompt, model='', search=False,
                     selected_code='', selection_start=0, selection_end=0):
        """Start a real Claude Code agent edit in an isolated workspace.
        Claude Code runs with Read/Write/Edit tools and up to 10 turns,
        working in a temp directory with a copy of the code.
        Use ai_edit_poll() to read live output and the final result.

        Args:
            code:            The full source code.
            prompt:          The instruction for Claude.
            model:           Optional model alias (e.g. 'sonnet', 'opus', 'haiku').
            search:          If True, enable WebSearch tool (--allowedTools).
            selected_code:   If non-empty, only this portion should be edited.
            selection_start: 1-based start line of the selection.
            selection_end:   1-based end line of the selection.
        """
        import threading

        # If a previous process is still running, kill it
        self.ai_edit_cancel()

        try:
            check_result = self.check_claude_code_installed()
            if not check_result.get('installed', False):
                return {
                    'status': 'error',
                    'message': 'Claude Code not installed. Install it with: npm install -g @anthropic-ai/claude-code'
                }

            has_selection = bool(selected_code and selected_code.strip())

            print(f"[AI EDIT] Starting Claude Code agent edit...")
            print(f"[AI EDIT] Prompt: {prompt}")
            print(f"[AI EDIT] Selection: {'lines ' + str(selection_start) + '-' + str(selection_end) if has_selection else 'whole file'}")
            if model:
                print(f"[AI EDIT] Model: {model}")

            # ── Create isolated workspace (acts as a lightweight sandbox) ──
            ts = int(time.time())
            workspace = os.path.join(_preview_dir, f'ai_workspace_{ts}')
            os.makedirs(workspace, exist_ok=True)

            # Copy code into the workspace as scene.py
            code_file = os.path.join(workspace, 'scene.py')
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # ── Create CLAUDE.md — Claude Code auto-reads this on startup ──
            claude_md = os.path.join(workspace, 'CLAUDE.md')
            with open(claude_md, 'w', encoding='utf-8') as f:
                f.write(
                    "# Workspace Rules\n\n"
                    "You are a **code editor**. Your only job is to edit `scene.py`.\n\n"
                    "## Workflow\n"
                    "1. Read `scene.py` with the Read tool\n"
                    "2. Apply the requested changes using the Edit or Write tool\n"
                    "3. Done — do NOT explain, do NOT create new files\n\n"
                    "## Important\n"
                    "- Always modify `scene.py` directly — never just describe changes\n"
                    "- Use the Edit tool for targeted changes or Write tool for full rewrites\n"
                    "- Keep all existing code that wasn't asked to change\n"
                    "- This is a Manim (animation library) Python file\n"
                )

            print(f"[AI EDIT] Workspace: {workspace}")
            print(f"[AI EDIT] Code file: {code_file} ({len(code)} chars)")

            # ── Build the instruction prompt ──
            search_hint = ("\nUse WebSearch to look up any documentation, APIs, "
                           "or examples you need to complete this task." if search else "")
            if has_selection:
                instruction = (
                    f"Edit scene.py — ONLY lines {selection_start}-{selection_end}.\n\n"
                    f"Selected code (lines {selection_start}-{selection_end}):\n"
                    f"```\n{selected_code}\n```\n\n"
                    f"Instruction: {prompt}{search_hint}"
                )
            else:
                instruction = (
                    f"Edit scene.py according to this instruction: {prompt}{search_hint}"
                )

            # Write instruction to a file (avoids Windows cmd.exe quoting issues)
            prompt_file = os.path.join(workspace, 'instruction.txt')
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(instruction)

            # ── Write system prompt file (avoids cmd.exe quoting issues) ──
            sys_prompt_file = os.path.join(workspace, 'system_prompt.txt')
            with open(sys_prompt_file, 'w', encoding='utf-8') as f:
                f.write(
                    "You are a code editor. Your ONLY task is to edit scene.py.\n"
                    "ALWAYS use the Edit or Write tool to modify scene.py directly.\n"
                    "Never just describe changes - apply them to the file.\n"
                    "Do not create new files. Do not run commands.\n"
                    "After editing, you are done."
                )

            # ── Build command — real Claude Code with full tool access ──
            # --dangerously-skip-permissions: needed for non-interactive tool use
            # --no-session-persistence:       don't save sessions to disk
            # --append-system-prompt-file:    reinforces editing behavior
            # shell=True: needed on Windows to find .cmd wrappers from npm
            # stdin=PIPE: feed instruction directly (reliable cross-platform)
            model_flag = f' --model "{model}"' if model else ''
            # --allowedTools WebSearch: auto-approve web search without prompts
            search_flag = ' --allowedTools "WebSearch,WebFetch"' if search else ''
            command = (
                f'claude -p'
                f' --dangerously-skip-permissions'
                f' --no-session-persistence'
                f'{model_flag}'
                f'{search_flag}'
                f' --output-format text'
                f' --append-system-prompt-file "{sys_prompt_file}"'
            )

            # Reset state
            AIEditMixin._ai_output_buf = ''
            AIEditMixin._ai_done = False
            AIEditMixin._ai_returncode = None
            AIEditMixin._ai_workspace = workspace
            AIEditMixin._ai_code_file = code_file
            AIEditMixin._ai_prompt_file = prompt_file
            AIEditMixin._ai_original_code = code

            # Start the subprocess
            env = _get_clean_env()
            # Remove CLAUDECODE env var so claude CLI doesn't reject nested launch
            env.pop('CLAUDECODE', None)
            env.pop('CLAUDE_CODE_ENTRYPOINT', None)

            print(f"[AI EDIT] Command: {command}")
            AIEditMixin._ai_proc = subprocess.Popen(
                command,
                shell=True,              # Needed to find .cmd on Windows
                stdin=subprocess.PIPE,   # Feed instruction via stdin
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=workspace,
                env=env
            )

            # Write instruction to stdin then close it
            try:
                AIEditMixin._ai_proc.stdin.write(instruction)
                AIEditMixin._ai_proc.stdin.close()
            except Exception as e:
                print(f"[AI EDIT] Failed to write stdin: {e}")

            # Background thread reads combined stdout+stderr for live streaming display
            def _reader():
                proc = AIEditMixin._ai_proc
                try:
                    while True:
                        ch = proc.stdout.read(1)
                        if ch == '':
                            break  # EOF
                        AIEditMixin._ai_output_buf += ch
                except Exception as e:
                    print(f"[AI EDIT] Reader error: {e}")

                proc.wait()
                AIEditMixin._ai_returncode = proc.returncode
                AIEditMixin._ai_done = True
                print(f"[AI EDIT] Process finished, code={proc.returncode}, {len(AIEditMixin._ai_output_buf)} chars")

            t = threading.Thread(target=_reader, daemon=True)
            t.start()

            return {'status': 'started', 'message': 'Claude is editing...'}

        except Exception as e:
            print(f"[AI EDIT ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def ai_edit_poll(self):
        """Poll the streaming AI edit.  Returns current output and status.
        Call repeatedly from JS (e.g. every 300ms) to update the UI live.

        When done, reads the modified file from the workspace (Claude Code
        edits the file directly using its Write/Edit tools).  Falls back to
        extracting code from text output if the file wasn't modified.
        """
        import shutil
        import re as _re

        if AIEditMixin._ai_proc is None:
            return {'status': 'idle', 'output': '', 'done': True}

        # Strip ANSI escape codes from output (Codex CLI uses colored output)
        raw_output = AIEditMixin._ai_output_buf
        output = _re.sub(r'\x1b\[[0-9;]*m', '', raw_output)

        if AIEditMixin._ai_done:
            code_file = AIEditMixin._ai_code_file
            workspace = AIEditMixin._ai_workspace
            original  = AIEditMixin._ai_original_code

            edited_code = None

            # Log workspace contents for debugging
            if workspace and os.path.exists(workspace):
                try:
                    ws_files = os.listdir(workspace)
                    print(f"[AI EDIT] Workspace files after edit: {ws_files}")
                except Exception:
                    pass

            # ── Strategy 1: Read the modified file from workspace ──
            # Claude Code uses Write/Edit tools to modify scene.py directly
            if code_file and os.path.exists(code_file):
                try:
                    with open(code_file, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    # Only use if the file was actually changed
                    if file_content.strip() and file_content != original:
                        edited_code = file_content
                        print(f"[AI EDIT] Strategy 1: Got modified scene.py ({len(edited_code)} chars)")
                    else:
                        print(f"[AI EDIT] Strategy 1: scene.py unchanged ({len(file_content)} chars)")
                except Exception as e:
                    print(f"[AI EDIT] Strategy 1 failed: {e}")

            # ── Strategy 2: Extract code from text output (fallback) ──
            if not edited_code and output.strip():
                extracted = self._extract_code_from_ai_response(output.strip())
                if extracted:
                    edited_code = extracted
                    print(f"[AI EDIT] Strategy 2: Extracted code from text output ({len(edited_code)} chars)")
                else:
                    print(f"[AI EDIT] Strategy 2: Text output is not code ({len(output)} chars): {output[:200]}")

            # ── Clean up workspace ──
            if workspace and os.path.exists(workspace):
                try:
                    shutil.rmtree(workspace, ignore_errors=True)
                    print(f"[AI EDIT] Cleaned up workspace: {workspace}")
                except Exception:
                    pass

            if edited_code:
                return {
                    'status': 'success',
                    'output': output,
                    'edited_code': edited_code,
                    'done': True,
                    'message': 'Done!'
                }
            else:
                provider_name = 'Codex' if AIEditMixin._ai_codex_provider else 'Claude Code'
                err = output or f'Unknown error (no output from {provider_name})'
                return {
                    'status': 'error',
                    'output': output,
                    'done': True,
                    'message': f'{provider_name} error: {err[:500]}'
                }

        # Still running — return partial output
        return {
            'status': 'streaming',
            'output': output,
            'done': False,
            'chars': len(output)
        }

    def ai_edit_cancel(self):
        """Cancel a running AI edit process and clean up workspace."""
        import shutil

        if AIEditMixin._ai_proc and not AIEditMixin._ai_done:
            try:
                AIEditMixin._ai_proc.kill()
                print("[AI EDIT] Process cancelled by user")
            except Exception:
                pass
        AIEditMixin._ai_proc = None
        AIEditMixin._ai_done = False
        AIEditMixin._ai_output_buf = ''
        AIEditMixin._ai_returncode = None
        AIEditMixin._ai_original_code = ''
        AIEditMixin._ai_codex_provider = False
        # Clean up workspace directory
        workspace = AIEditMixin._ai_workspace
        if workspace and os.path.exists(workspace):
            try:
                shutil.rmtree(workspace, ignore_errors=True)
                print(f"[AI EDIT] Cleaned up workspace: {workspace}")
            except Exception:
                pass
        AIEditMixin._ai_workspace = None
        AIEditMixin._ai_code_file = None
        AIEditMixin._ai_prompt_file = None
        return {'status': 'cancelled'}

    # ── OpenAI Codex CLI ─────────────────────────────────────────────────

    def check_codex_installed(self):
        """Check if OpenAI Codex CLI is installed (npm i -g @openai/codex).
        Uses 'codex --help' with shell=True so Windows can find .cmd wrappers.
        """
        try:
            result = subprocess.run(
                'codex --help',
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10,
                shell=True,
                env=_get_clean_env()
            )
            output = (result.stdout or '').strip() + (result.stderr or '').strip()
            # If we got any meaningful output, the CLI is installed
            if output and ('codex' in output.lower() or 'usage' in output.lower()
                          or 'openai' in output.lower() or len(output) > 20):
                print(f"[CODEX CLI] Found (help output: {len(output)} chars)")
                return {'status': 'success', 'installed': True, 'version': 'installed'}
            else:
                print(f"[CODEX CLI] Not detected (rc={result.returncode}, output={output[:100]})")
                return {'status': 'success', 'installed': False,
                        'message': 'Codex CLI not found'}
        except FileNotFoundError:
            print("[CODEX CLI] Not installed (command not found)")
            return {'status': 'success', 'installed': False,
                    'message': 'Codex CLI not installed. Install with: npm install -g @openai/codex'}
        except Exception as e:
            print(f"[CODEX CLI ERROR] {e}")
            return {'status': 'error', 'message': str(e), 'installed': False}

    def ai_edit_codex(self, code, prompt, model='', search=False,
                      selected_code='', selection_start=0, selection_end=0):
        """Start an AI edit using the OpenAI Codex CLI (codex exec).
        Works like Claude Code: edits scene.py in an isolated workspace.
        Reuses ai_edit_poll() for polling — same workspace/file strategy.

        Args:
            code:            Full source code.
            prompt:          The instruction for the AI.
            model:           Codex model (e.g. 'o4-mini', 'gpt-4.1', 'codex-mini').
            search:          If True, enable live web search (--search flag).
            selected_code:   If non-empty, only this portion should be edited.
            selection_start: 1-based start line of the selection.
            selection_end:   1-based end line of the selection.
        """
        import threading

        self.ai_edit_cancel()

        try:
            check_result = self.check_codex_installed()
            if not check_result.get('installed', False):
                return {
                    'status': 'error',
                    'message': 'Codex CLI not installed. Install it with: npm install -g @openai/codex'
                }

            has_selection = bool(selected_code and selected_code.strip())
            use_model = (model or '').strip()

            print(f"[AI EDIT CODEX] Starting Codex CLI edit...")
            print(f"[AI EDIT CODEX] Prompt: {prompt}")
            print(f"[AI EDIT CODEX] Selection: {'lines ' + str(selection_start) + '-' + str(selection_end) if has_selection else 'whole file'}")
            if use_model:
                print(f"[AI EDIT CODEX] Model: {use_model}")
            if search:
                print(f"[AI EDIT CODEX] Web search: enabled (live)")

            # ── Create isolated workspace ──
            ts = int(time.time())
            workspace = os.path.join(_preview_dir, f'ai_workspace_codex_{ts}')
            os.makedirs(workspace, exist_ok=True)

            # Copy code into workspace as scene.py
            code_file = os.path.join(workspace, 'scene.py')
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # ── Create AGENTS.md — Codex CLI auto-reads this on startup ──
            agents_md = os.path.join(workspace, 'AGENTS.md')
            with open(agents_md, 'w', encoding='utf-8') as f:
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

            print(f"[AI EDIT CODEX] Workspace: {workspace}")
            print(f"[AI EDIT CODEX] Code file: {code_file} ({len(code)} chars)")

            # ── Build the instruction ──
            search_hint = ("\nUse web search to look up any documentation, APIs, "
                           "or examples you need to complete this task." if search else "")
            if has_selection:
                instruction = (
                    f"Edit the file `scene.py` in this directory.\n"
                    f"ONLY modify lines {selection_start}-{selection_end}.\n\n"
                    f"Selected code (lines {selection_start}-{selection_end}):\n"
                    f"```python\n{selected_code}\n```\n\n"
                    f"Instruction: {prompt}\n\n"
                    f"Read scene.py, apply the changes, and write it back. "
                    f"Keep all existing code that wasn't asked to change.{search_hint}"
                )
            else:
                instruction = (
                    f"Edit the file `scene.py` in this directory.\n\n"
                    f"Instruction: {prompt}\n\n"
                    f"Read scene.py, apply the changes, and write it back. "
                    f"Keep all existing code that wasn't asked to change. "
                    f"This is a Manim (Python math animation library) file.{search_hint}"
                )

            # Save instruction for reference
            prompt_file = os.path.join(workspace, 'instruction.txt')
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(instruction)

            # ── Build command ──
            # codex exec - : read prompt from stdin (we feed via PIPE)
            # --yolo:         bypass all approval prompts (non-interactive)
            # -m / --model:   select model
            # -c key=val:     config override (web_search for live search)
            # shell=True:     needed on Windows to find .cmd wrappers from npm
            # NOTE: --search is NOT valid for `codex exec`, use -c instead
            model_flag = f' -m "{use_model}"' if use_model else ''
            search_flag = ' -c web_search=live' if search else ''
            command = f'codex exec - --yolo{model_flag}{search_flag}'

            # Reset state — reuse same fields as Claude Code
            AIEditMixin._ai_output_buf = ''
            AIEditMixin._ai_done = False
            AIEditMixin._ai_returncode = None
            AIEditMixin._ai_workspace = workspace
            AIEditMixin._ai_code_file = code_file
            AIEditMixin._ai_prompt_file = prompt_file
            AIEditMixin._ai_original_code = code
            AIEditMixin._ai_codex_provider = True

            # Start the subprocess — feed instruction via stdin PIPE
            env = _get_clean_env()

            print(f"[AI EDIT CODEX] Command: {command}")
            AIEditMixin._ai_proc = subprocess.Popen(
                command,
                shell=True,              # Needed to find .cmd on Windows
                stdin=subprocess.PIPE,   # Feed instruction via stdin
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=workspace,
                env=env
            )

            # Write instruction to stdin then close it
            try:
                AIEditMixin._ai_proc.stdin.write(instruction)
                AIEditMixin._ai_proc.stdin.close()
            except Exception as e:
                print(f"[AI EDIT CODEX] Failed to write stdin: {e}")

            # Background thread reads output for live streaming display
            def _reader():
                proc = AIEditMixin._ai_proc
                try:
                    while True:
                        ch = proc.stdout.read(1)
                        if ch == '':
                            break  # EOF
                        AIEditMixin._ai_output_buf += ch
                except Exception as e:
                    print(f"[AI EDIT CODEX] Reader error: {e}")

                proc.wait()
                AIEditMixin._ai_returncode = proc.returncode
                AIEditMixin._ai_done = True
                print(f"[AI EDIT CODEX] Process finished, code={proc.returncode}, {len(AIEditMixin._ai_output_buf)} chars")

            t = threading.Thread(target=_reader, daemon=True)
            t.start()

            return {'status': 'started', 'message': 'Codex is editing...'}

        except Exception as e:
            print(f"[AI EDIT CODEX ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def get_codex_models(self):
        """Return a static list of models available for Codex CLI.
        Includes ChatGPT-authenticated models and API-available models.
        """
        return {
            'models': [
                # ── Latest / Recommended ──
                {'id': 'gpt-5.3-codex', 'display_name': 'GPT-5.3 Codex'},
                {'id': 'gpt-5.3-codex-spark', 'display_name': 'GPT-5.3 Codex Spark'},
                {'id': 'gpt-5.2-codex', 'display_name': 'GPT-5.2 Codex'},
                {'id': 'gpt-5.2', 'display_name': 'GPT-5.2'},
                # ── GPT-5.1 series ──
                {'id': 'gpt-5.1-codex-max', 'display_name': 'GPT-5.1 Codex Max'},
                {'id': 'gpt-5.1-codex-mini', 'display_name': 'GPT-5.1 Codex Mini'},
                {'id': 'gpt-5.1', 'display_name': 'GPT-5.1'},
                # ── GPT-5 series ──
                {'id': 'gpt-5-codex', 'display_name': 'GPT-5 Codex'},
                {'id': 'gpt-5-codex-mini', 'display_name': 'GPT-5 Codex Mini'},
                {'id': 'gpt-5-mini', 'display_name': 'GPT-5 Mini'},
                {'id': 'gpt-5-nano', 'display_name': 'GPT-5 Nano'},
                # ── Open Source (via Ollama / local) ──
                {'id': 'gpt-oss:120b', 'display_name': 'GPT-OSS 120B (Local)'},
                {'id': 'gpt-oss:20b', 'display_name': 'GPT-OSS 20B (Local)'},
            ]
        }

    @staticmethod
    def _extract_code_from_ai_response(raw):
        """Strip markdown fences, 'Here is...' preamble, trailing explanations.
        Returns only the Python code, or None if response is not code."""
        text = raw.strip()

        if not text:
            return None

        # 1) If wrapped in ```python ... ``` or ``` ... ```, extract the content
        fence_match = re.search(r'```(?:python)?\s*\n(.*?)```', text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
            return text if text else None

        # 2) Quick sanity check: does the response look like code at all?
        #    If it has common Python patterns it's likely code
        code_indicators = [
            r'^\s*(from|import)\s+',
            r'^\s*class\s+\w+',
            r'^\s*def\s+\w+',
            r'^\s*self\.',
            r'^\s*#',
        ]
        has_code = any(
            re.search(pat, text, re.MULTILINE)
            for pat in code_indicators
        )
        if not has_code:
            # Response doesn't contain any Python code — likely conversational text
            print(f"[AI EDIT] Response doesn't look like code, raw length={len(text)}")
            return None

        # 3) Strip common preamble lines
        lines = text.split('\n')
        start = 0
        preamble_patterns = [
            r'^here\s+(is|are)',
            r'^sure[,!.]',
            r'^i\'ve\s+(updated|modified|edited|fixed|changed)',
            r'^the\s+(updated|modified|edited|fixed|new)',
            r'^below\s+is',
            r'^this\s+(code|version|script)',
            r'^certainly',
            r'^of\s+course',
            r'^it\s+looks\s+like',
            r'^i\s+need',
            r'^please\s+',
            r'^in\s+the\s+meantime',
            r'^could\s+you',
        ]
        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if not stripped:
                continue
            if any(re.match(p, stripped) for p in preamble_patterns):
                start = i + 1
                # Skip blank lines after preamble
                while start < len(lines) and not lines[start].strip():
                    start += 1
                continue
            break

        # 4) Strip common postamble from the end
        end = len(lines)
        postamble_patterns = [
            r'^(this|the|i|note|key|these)\s+(code|change|modif|update|add|version|script|fix)',
            r'^let\s+me\s+know',
            r'^i\s+(hope|made|also|added)',
            r'^explanation',
            r'^changes?\s*(made|:)',
            r'^what\s+(i|this)',
            r'^\*\*',
            r'^\d+\.\s+\*\*',
            r'^please\s+approve',
        ]
        for i in range(len(lines) - 1, start - 1, -1):
            stripped = lines[i].strip().lower()
            if not stripped:
                continue
            if any(re.match(p, stripped) for p in postamble_patterns):
                end = i
                # Also skip blank lines before postamble
                while end > start and not lines[end - 1].strip():
                    end -= 1
                continue
            break

        cleaned = '\n'.join(lines[start:end]).strip()
        return cleaned if cleaned else None
