"""
AI Edit Module — OpenAI Codex + Claude Code integration.
Provides AIEditMixin class that ManimAPI inherits from.

Claude Code uses ``claude -p --output-format stream-json`` for clean
structured streaming output.  No PTY, no ANSI stripping, no permission
prompt auto-accept needed.

Improvements inspired by Claude Code internal architecture:
- Stall watchdog: kill hung CLI after STALL_TIMEOUT_S of silence
- Per-turn cost/token tracking with cache hit display
- Auto-retry on CLI failure with exponential backoff
- Session token estimation with context window warnings
- Agent render parallelism: overlap screenshot saving with parse
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
import traceback

# ── Module-level refs injected by init_ai_edit() ──
_preview_dir = None
_get_clean_env = None
_assets_dir = None
_venv_python = None  # Path to venv Python for subprocess tasks

# ── Streaming robustness constants (inspired by Claude Code internals) ──
STALL_TIMEOUT_S = 90       # Kill hung CLI after 90s of no output (non-agent mode only)
STALL_WARNING_S = 45       # Log warning after 45s of silence (non-agent mode only)
RETRY_BASE_DELAY_S = 2     # Exponential backoff base delay (non-agent retries)
RETRY_MAX_ATTEMPTS = 2     # Max retry attempts (non-agent mode)

# ── Context window estimation ──
# Claude's context: 200k tokens. Warn at 70%, force new session at 90%.
CONTEXT_WINDOW_TOKENS = 200_000
CONTEXT_WARN_RATIO = 0.70
CONTEXT_CRITICAL_RATIO = 0.90
# Rough estimation: ~4 chars per token for code/English mixed content
CHARS_PER_TOKEN = 4


_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts')


# ═══════════════════════════════════════════════════════════════
#  Model Registry (inspired by Claude Code utils/model/)
#  Capabilities, pricing, aliases, smart defaults, fallback chain
# ═══════════════════════════════════════════════════════════════

class ModelRegistry:
    """Central registry for all supported AI models with capabilities,
    pricing, aliases, and fallback logic.

    Inspired by Claude Code's model.ts / modelCost.ts / context.ts.
    """

    # ── Model definitions ──
    # id → {display, provider, family, aliases, context, max_output,
    #        thinking, effort, fast, cost_input, cost_output, tier}
    MODELS = {
        # ── Claude (via Claude Code CLI) ──
        'claude-opus-4-6': {
            'display': 'Claude Opus 4.6',
            'provider': 'claude',
            'family': 'opus',
            'aliases': ['opus', 'opus-4-6', 'opus4.6', 'best'],
            'context': 200_000,
            'context_1m': True,
            'max_output': 128_000,
            'thinking': 'adaptive',
            'effort': True,
            'fast_mode': True,
            'cost_input': 5.0,    # $ per 1M tokens
            'cost_output': 25.0,
            'tier': 'premium',
            'recommended_for': ['complex_edits', 'agent', 'review'],
        },
        'claude-sonnet-4-6': {
            'display': 'Claude Sonnet 4.6',
            'provider': 'claude',
            'family': 'sonnet',
            'aliases': ['sonnet', 'sonnet-4-6', 'sonnet4.6'],
            'context': 200_000,
            'context_1m': True,
            'max_output': 64_000,
            'thinking': 'adaptive',
            'effort': True,
            'fast_mode': False,
            'cost_input': 3.0,
            'cost_output': 15.0,
            'tier': 'standard',
            'recommended_for': ['edits', 'balanced'],
        },
        'claude-haiku-4-5-20251001': {
            'display': 'Claude Haiku 4.5',
            'provider': 'claude',
            'family': 'haiku',
            'aliases': ['haiku', 'haiku-4-5', 'haiku4.5', 'fast', 'cheap'],
            'context': 200_000,
            'context_1m': False,
            'max_output': 64_000,
            'thinking': 'budget',
            'effort': False,
            'fast_mode': False,
            'cost_input': 1.0,
            'cost_output': 5.0,
            'tier': 'economy',
            'recommended_for': ['autocomplete', 'quick_fix', 'review'],
        },
        'claude-sonnet-4-5': {
            'display': 'Claude Sonnet 4.5',
            'provider': 'claude',
            'family': 'sonnet',
            'aliases': ['sonnet-4-5', 'sonnet4.5'],
            'context': 200_000,
            'context_1m': True,
            'max_output': 64_000,
            'thinking': 'budget',
            'effort': False,
            'fast_mode': False,
            'cost_input': 3.0,
            'cost_output': 15.0,
            'tier': 'standard',
            'recommended_for': ['edits'],
        },
        'claude-opus-4-5': {
            'display': 'Claude Opus 4.5',
            'provider': 'claude',
            'family': 'opus',
            'aliases': ['opus-4-5', 'opus4.5'],
            'context': 200_000,
            'context_1m': True,
            'max_output': 64_000,
            'thinking': 'budget',
            'effort': False,
            'fast_mode': False,
            'cost_input': 5.0,
            'cost_output': 25.0,
            'tier': 'premium',
            'recommended_for': ['complex_edits'],
        },
        # ── Codex (via Codex CLI) ──
        'gpt-5.4': {
            'display': 'GPT-5.4',
            'provider': 'codex',
            'family': 'gpt5',
            'aliases': ['gpt5.4'],
            'context': 200_000,
            'context_1m': False,
            'max_output': 32_000,
            'thinking': 'auto',
            'effort': False,
            'fast_mode': False,
            'cost_input': 0, 'cost_output': 0,
            'tier': 'standard',
            'recommended_for': ['edits'],
        },
        'gpt-5.3-codex': {
            'display': 'GPT-5.3 Codex',
            'provider': 'codex',
            'family': 'gpt5',
            'aliases': ['codex', 'gpt5.3'],
            'context': 200_000,
            'context_1m': False,
            'max_output': 32_000,
            'thinking': 'auto',
            'effort': False,
            'fast_mode': False,
            'cost_input': 0, 'cost_output': 0,
            'tier': 'standard',
            'recommended_for': ['edits', 'agent'],
        },
    }

    # ── Fallback chains (model → fallback when rate-limited/error) ──
    FALLBACK = {
        'claude-opus-4-6': 'claude-sonnet-4-6',
        'claude-opus-4-5': 'claude-sonnet-4-5',
        'claude-sonnet-4-6': 'claude-haiku-4-5-20251001',
        'claude-sonnet-4-5': 'claude-haiku-4-5-20251001',
        'gpt-5.4': 'gpt-5.3-codex',
    }

    # ── Smart defaults per task type ──
    TASK_DEFAULTS = {
        'edit': 'claude-sonnet-4-6',       # Balanced for code edits
        'agent': 'claude-sonnet-4-6',      # Agent loop (many turns)
        'autocomplete': 'claude-haiku-4-5-20251001',  # Fast completions
        'review': 'claude-haiku-4-5-20251001',         # Screenshot review
        'complex': 'claude-opus-4-6',      # Complex generation
    }

    # ── Legacy model migrations ──
    MIGRATIONS = {
        'claude-sonnet-4-5-20250514': 'claude-sonnet-4-5',
        'claude-sonnet-4-5-20250929': 'claude-sonnet-4-5',
        'claude-opus-4-5-20251101': 'claude-opus-4-5',
        'claude-opus-4-1-20250805': 'claude-opus-4-6',
        'claude-opus-4-20250514': 'claude-opus-4-6',
        'claude-sonnet-4-20250514': 'claude-sonnet-4-6',
        'claude-3-7-sonnet-20250219': 'claude-sonnet-4-6',
        'claude-3-5-sonnet-20241022': 'claude-sonnet-4-6',
        'claude-3-5-haiku-20241022': 'claude-haiku-4-5-20251001',
    }

    @classmethod
    def resolve(cls, model_input, task='edit'):
        """Resolve a model string (alias, legacy ID, or full ID) to a
        canonical model ID. Falls back to task default if empty/unknown.

        Priority: exact ID > alias > migration > task default.
        Returns (model_id, was_migrated).
        """
        if not model_input or not model_input.strip():
            default = cls.TASK_DEFAULTS.get(task, 'claude-sonnet-4-6')
            return default, False

        raw = model_input.strip()
        lower = raw.lower()

        # Exact match
        if raw in cls.MODELS:
            return raw, False

        # Alias match
        for model_id, info in cls.MODELS.items():
            if lower in [a.lower() for a in info.get('aliases', [])]:
                return model_id, False

        # Legacy migration
        if raw in cls.MIGRATIONS:
            new_id = cls.MIGRATIONS[raw]
            print(f"[MODEL] Migrated {raw} → {new_id}")
            return new_id, True

        # Unknown model — pass through (user may have a custom model)
        return raw, False

    @classmethod
    def get_fallback(cls, model_id):
        """Get fallback model for when primary is rate-limited/unavailable."""
        return cls.FALLBACK.get(model_id)

    @classmethod
    def get_info(cls, model_id):
        """Get full model info dict, or None if unknown."""
        return cls.MODELS.get(model_id)

    @classmethod
    def get_provider(cls, model_id):
        """Get provider ('claude' or 'codex') for a model."""
        info = cls.MODELS.get(model_id)
        return info['provider'] if info else 'claude'

    @classmethod
    def get_context_window(cls, model_id):
        """Get context window size in tokens."""
        info = cls.MODELS.get(model_id)
        return info['context'] if info else 200_000

    @classmethod
    def estimate_cost(cls, model_id, input_tokens, output_tokens,
                      cache_read=0, cache_creation=0):
        """Estimate cost in USD for a given token usage."""
        info = cls.MODELS.get(model_id)
        if not info:
            return 0.0
        ci = info['cost_input'] / 1_000_000
        co = info['cost_output'] / 1_000_000
        # Cache: reads cost 0.1x, writes cost 1.25x
        uncached_input = input_tokens - cache_read - cache_creation
        cost = (uncached_input * ci
                + cache_read * ci * 0.1
                + cache_creation * ci * 1.25
                + output_tokens * co)
        return round(cost, 6)

    @classmethod
    def list_for_provider(cls, provider):
        """List all models for a given provider, sorted by tier."""
        tier_order = {'premium': 0, 'standard': 1, 'economy': 2}
        models = [
            {'id': mid, **info}
            for mid, info in cls.MODELS.items()
            if info['provider'] == provider
        ]
        models.sort(key=lambda m: tier_order.get(m.get('tier', 'standard'), 9))
        return models

    @classmethod
    def list_all(cls):
        """List all models grouped by provider."""
        return {
            'claude': cls.list_for_provider('claude'),
            'codex': cls.list_for_provider('codex'),
        }

# Prompt cache — loaded once from prompts/ folder
_prompt_cache = {}


def _load_prompt(filename):
    """Load a prompt template from the prompts/ folder. Cached after first read."""
    if filename in _prompt_cache:
        return _prompt_cache[filename]
    fpath = os.path.join(_PROMPTS_DIR, filename)
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        _prompt_cache[filename] = content
        return content
    except Exception as e:
        print(f"[AI EDIT] Failed to load prompt {filename}: {e}")
        return ''


def _load_prompt_section(filename, section):
    """Load a specific ## section from a prompt file.
    E.g. _load_prompt_section('claude_agent.md', 'Fix') returns the
    text under '## Fix' up to the next '## ' or end of file."""
    content = _load_prompt(filename)
    if not content:
        return ''
    marker = f'## {section}'
    start = content.find(marker)
    if start == -1:
        return ''
    start += len(marker)
    # Skip to next line after the header
    nl = content.find('\n', start)
    if nl == -1:
        return content[start:].strip()
    start = nl + 1
    # Find next section or end
    next_section = content.find('\n## ', start)
    if next_section == -1:
        return content[start:].strip()
    return content[start:next_section].strip()


def _append_assets_list(md_content):
    """Append available assets list to MD content if assets exist."""
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
                    "\nOnly read and use assets that are referenced in `scene.py`.\n"
                    "Use relative path `./assets/filename` in code.\n"
                )
        except Exception:
            pass
    return md_content


def init_ai_edit(preview_dir, get_clean_env_func, assets_dir=None, venv_dir=None):
    """Initialise module-level dependencies (called once from app.py)."""
    global _preview_dir, _get_clean_env, _assets_dir, _venv_python
    _preview_dir = preview_dir
    _get_clean_env = get_clean_env_func
    _assets_dir = assets_dir
    if venv_dir:
        if os.name == 'nt':
            _venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
        else:
            _venv_python = os.path.join(venv_dir, 'bin', 'python')
        if not os.path.exists(_venv_python):
            _venv_python = None
    # Initialize persistent storage systems
    RenderMemory.init()
    ChatHistory.init()


# ═══════════════════════════════════════════════════════════════
#  Render Memory — persist successful patterns & known fixes
#  Inspired by Claude Code's memdir system (200 lines / 25KB cap)
# ═══════════════════════════════════════════════════════════════

class RenderMemory:
    """Persistent memory of render outcomes — successes, errors, and fixes.
    Stored at ~/.manim_studio/render_memory.md. Injected into AI workspace
    context so the model learns from past attempts."""

    MAX_LINES = 200
    MAX_BYTES = 25_000
    _path = None

    @classmethod
    def init(cls):
        user_data = os.path.join(os.path.expanduser('~'), '.manim_studio')
        cls._path = os.path.join(user_data, 'render_memory.md')
        if not os.path.exists(cls._path):
            try:
                os.makedirs(user_data, exist_ok=True)
                with open(cls._path, 'w', encoding='utf-8') as f:
                    f.write("# Render Memory\n"
                            "Past render outcomes — the AI reads this "
                            "to avoid repeating mistakes.\n\n")
            except Exception as e:
                print(f"[RENDER MEMORY] Init error: {e}")

    @classmethod
    def record_success(cls, scene_name, goal, duration_s, pattern_note=''):
        """Record a successful render for future reference."""
        if not cls._path:
            return
        ts = time.strftime('%Y-%m-%d %H:%M')
        entry = f"## [{ts}] {scene_name} — SUCCESS\n"
        if goal:
            entry += f"- Goal: {goal[:200]}\n"
        entry += f"- Render: {duration_s:.1f}s\n"
        if pattern_note:
            entry += f"- Key pattern: {pattern_note[:300]}\n"
        entry += "---\n\n"
        cls._append(entry)

    @classmethod
    def record_error(cls, scene_name, goal, error, fix=''):
        """Record a render error (and optional fix) for future reference."""
        if not cls._path:
            return
        ts = time.strftime('%Y-%m-%d %H:%M')
        entry = f"## [{ts}] {scene_name} — ERROR\n"
        if goal:
            entry += f"- Goal: {goal[:200]}\n"
        entry += f"- Error: {error[:400]}\n"
        if fix:
            entry += f"- Fix: {fix[:300]}\n"
        entry += "---\n\n"
        cls._append(entry)

    @classmethod
    def record_agent_outcome(cls, scene_name, goal, iterations,
                             satisfied, final_tip=''):
        """Record an agent loop outcome."""
        if not cls._path:
            return
        ts = time.strftime('%Y-%m-%d %H:%M')
        status = 'SATISFIED' if satisfied else 'UNSATISFIED'
        entry = f"## [{ts}] {scene_name} — Agent {status}\n"
        if goal:
            entry += f"- Goal: {goal[:200]}\n"
        entry += f"- Iterations: {iterations}\n"
        if final_tip:
            entry += f"- Note: {final_tip[:300]}\n"
        entry += "---\n\n"
        cls._append(entry)

    @classmethod
    def _append(cls, entry):
        """Append entry, truncating oldest entries if limits exceeded."""
        try:
            with open(cls._path, 'r', encoding='utf-8') as f:
                content = f.read()
            content += entry

            # Truncate: keep header + newest entries within limits
            lines = content.split('\n')
            while (len(lines) > cls.MAX_LINES
                   or len('\n'.join(lines).encode('utf-8')) > cls.MAX_BYTES):
                # Find first entry boundary (## [...]) after header and remove it
                for i in range(3, len(lines)):
                    if lines[i].startswith('## ['):
                        # Find end of this entry (next ## or ---)
                        end = i + 1
                        while end < len(lines) and not lines[end].startswith('## ['):
                            end += 1
                        lines = lines[:i] + lines[end:]
                        break
                else:
                    break  # No more entries to remove

            with open(cls._path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception as e:
            print(f"[RENDER MEMORY] Write error: {e}")

    @classmethod
    def get_context(cls, max_lines=50):
        """Get recent memory entries for injection into AI workspace context."""
        if not cls._path or not os.path.exists(cls._path):
            return ''
        try:
            with open(cls._path, 'r', encoding='utf-8') as f:
                content = f.read()
            lines = content.strip().split('\n')
            if len(lines) <= 3:
                return ''  # Only header, no entries
            # Take the last max_lines lines (most recent entries)
            recent = lines[-max_lines:] if len(lines) > max_lines else lines
            return '\n'.join(recent)
        except Exception:
            return ''


# ═══════════════════════════════════════════════════════════════
#  Chat History — persistent conversation sessions per file
#  Saved to ~/.manim_studio/chat_history/ as JSON
# ═══════════════════════════════════════════════════════════════

class ChatHistory:
    """Persistent chat session storage. Each session is a JSON file
    containing user prompts, AI responses, model info, and cost data.
    Sessions are associated with the file being edited."""

    MAX_SESSIONS = 50  # Auto-prune oldest beyond this
    _dir = None

    @classmethod
    def init(cls):
        user_data = os.path.join(os.path.expanduser('~'), '.manim_studio')
        cls._dir = os.path.join(user_data, 'chat_history')
        os.makedirs(cls._dir, exist_ok=True)

    @classmethod
    def save_turn(cls, session_id, file_path, model, prompt, response_text,
                  code_after=None, cost_usd=0.0, tokens=None):
        """Append a turn (user prompt + AI response) to the session file."""
        if not cls._dir or not session_id:
            return
        try:
            path = os.path.join(cls._dir, f'{session_id}.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    session = json.loads(f.read())
            else:
                session = {
                    'session_id': session_id,
                    'file_path': file_path or '',
                    'file_name': os.path.basename(file_path) if file_path else 'untitled',
                    'model': model or '',
                    'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'turns': [],
                    'total_cost_usd': 0.0,
                }

            turn = {
                'prompt': (prompt or '')[:2000],
                'response': (response_text or '')[:3000],
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'cost_usd': round(cost_usd, 4),
                'tokens': tokens or {},
            }
            if code_after:
                turn['code_preview'] = code_after[:500]

            session['turns'].append(turn)
            session['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
            session['total_cost_usd'] = round(
                sum(t.get('cost_usd', 0) for t in session['turns']), 4)
            session['model'] = model or session.get('model', '')

            with open(path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(session, indent=2))
            cls._prune()
        except Exception as e:
            print(f"[CHAT HISTORY] Save error: {e}")

    @classmethod
    def list_sessions(cls, limit=30):
        """Return recent sessions sorted by last update, most recent first."""
        if not cls._dir or not os.path.isdir(cls._dir):
            return []
        sessions = []
        try:
            for fname in os.listdir(cls._dir):
                if not fname.endswith('.json'):
                    continue
                fpath = os.path.join(cls._dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.loads(f.read())
                    turns = data.get('turns', [])
                    last_prompt = turns[-1]['prompt'][:80] if turns else ''
                    sessions.append({
                        'session_id': data.get('session_id', fname[:-5]),
                        'file_name': data.get('file_name', 'untitled'),
                        'file_path': data.get('file_path', ''),
                        'model': data.get('model', ''),
                        'turn_count': len(turns),
                        'total_cost_usd': data.get('total_cost_usd', 0),
                        'updated_at': data.get('updated_at', ''),
                        'created_at': data.get('created_at', ''),
                        'last_prompt': last_prompt,
                    })
                except Exception:
                    continue
            sessions.sort(key=lambda s: s.get('updated_at', ''), reverse=True)
            return sessions[:limit]
        except Exception as e:
            print(f"[CHAT HISTORY] List error: {e}")
            return []

    @classmethod
    def load_session(cls, session_id):
        """Load full session data by ID."""
        if not cls._dir:
            return None
        path = os.path.join(cls._dir, f'{session_id}.json')
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.loads(f.read())
        except Exception as e:
            print(f"[CHAT HISTORY] Load error: {e}")
            return None

    @classmethod
    def delete_session(cls, session_id):
        """Delete a session file."""
        if not cls._dir:
            return
        path = os.path.join(cls._dir, f'{session_id}.json')
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"[CHAT HISTORY] Deleted: {session_id[:8]}")
        except Exception as e:
            print(f"[CHAT HISTORY] Delete error: {e}")

    @classmethod
    def build_context_summary(cls, session_id, max_turns=10):
        """Build a text summary of a previous session for injecting into
        a new Claude session as context (so the AI remembers prior work)."""
        data = cls.load_session(session_id)
        if not data or not data.get('turns'):
            return ''
        turns = data['turns'][-max_turns:]
        parts = [f"# Previous conversation ({data.get('file_name', 'unknown')})"]
        for t in turns:
            parts.append(f"\nUser: {t['prompt']}")
            resp = t.get('response', '')
            if resp:
                parts.append(f"Assistant: {resp[:500]}")
        return '\n'.join(parts)

    @classmethod
    def _prune(cls):
        """Remove oldest sessions beyond MAX_SESSIONS."""
        if not cls._dir:
            return
        try:
            files = []
            for fname in os.listdir(cls._dir):
                if fname.endswith('.json'):
                    fpath = os.path.join(cls._dir, fname)
                    files.append((os.path.getmtime(fpath), fpath))
            if len(files) > cls.MAX_SESSIONS:
                files.sort()
                for _, fpath in files[:len(files) - cls.MAX_SESSIONS]:
                    os.remove(fpath)
        except Exception:
            pass


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


_PDF_MAX_TEXT_CHARS = 40_000  # ~10K tokens — keep PDF text manageable for AI

def _extract_pdf_text(pdf_path, max_pages=50):
    """Extract text from a PDF file and save as a companion .txt file.
    Returns the path to the .txt file, or None on failure.
    Tries: in-process library → venv subprocess → pdftotext CLI."""
    txt_path = pdf_path.rsplit('.', 1)[0] + '_content.txt'

    # Strategy 1: Try pypdf / PyPDF2 in-process
    for mod_name in ('pypdf', 'PyPDF2'):
        try:
            PdfReader = __import__(mod_name, fromlist=['PdfReader']).PdfReader
            reader = PdfReader(pdf_path)
            parts = []
            for i, page in enumerate(reader.pages[:max_pages], 1):
                text = page.extract_text() or ''
                if text.strip():
                    parts.append(f"--- Page {i} ---\n{text.strip()}")
            if parts:
                content = '\n\n'.join(parts)
                if len(reader.pages) > max_pages:
                    content += f"\n\n[... truncated at {max_pages}/{len(reader.pages)} pages]"
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"[AI EDIT] PDF extracted ({mod_name}): {os.path.basename(pdf_path)} "
                      f"-> {len(parts)} pages, {len(content)} chars")
                break
        except ImportError:
            continue
        except Exception as e:
            print(f"[AI EDIT] PDF {mod_name} failed: {e}")

    # Strategy 2: venv Python subprocess (has PyPDF2/pypdf installed)
    if not os.path.exists(txt_path) and _venv_python and os.path.exists(_venv_python):
        try:
            script = (
                "import sys, json\n"
                "pdf_path, max_p = sys.argv[1], int(sys.argv[2])\n"
                "try:\n"
                "    from pypdf import PdfReader\n"
                "except ImportError:\n"
                "    from PyPDF2 import PdfReader\n"
                "reader = PdfReader(pdf_path)\n"
                "parts = []\n"
                "for i, page in enumerate(reader.pages[:max_p], 1):\n"
                "    text = page.extract_text() or ''\n"
                "    if text.strip():\n"
                "        parts.append(f'--- Page {i} ---\\n' + text.strip())\n"
                "print(json.dumps({'pages': len(parts), 'text': '\\n\\n'.join(parts)}))\n"
            )
            result = subprocess.run(
                [_venv_python, '-c', script, pdf_path, str(max_pages)],
                capture_output=True, text=True, timeout=30,
                encoding='utf-8', errors='replace'
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout.strip())
                if data.get('text'):
                    with open(txt_path, 'w', encoding='utf-8') as f:
                        f.write(data['text'])
                    print(f"[AI EDIT] PDF extracted (venv): {os.path.basename(pdf_path)} "
                          f"-> {data['pages']} pages")
            elif result.stderr:
                print(f"[AI EDIT] PDF venv failed: {result.stderr.strip()[:200]}")
        except Exception as e:
            print(f"[AI EDIT] PDF venv extraction failed: {e}")

    # Strategy 3: pdftotext CLI (poppler-utils)
    if not os.path.exists(txt_path):
        try:
            result = subprocess.run(
                ['pdftotext', '-layout', pdf_path, txt_path],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and os.path.exists(txt_path):
                if os.path.getsize(txt_path) > 0:
                    print(f"[AI EDIT] PDF extracted (pdftotext): {os.path.basename(pdf_path)} "
                          f"-> {os.path.getsize(txt_path)} bytes")
                else:
                    os.remove(txt_path)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[AI EDIT] pdftotext failed: {e}")

    if not os.path.exists(txt_path):
        print(f"[AI EDIT] PDF extraction failed for {os.path.basename(pdf_path)}. "
              f"Install in venv: pip install pypdf")
        return None

    # Truncate if too large to keep AI context manageable
    try:
        with open(txt_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        if len(content) > _PDF_MAX_TEXT_CHARS:
            truncated = content[:_PDF_MAX_TEXT_CHARS]
            truncated += f"\n\n[... truncated at {_PDF_MAX_TEXT_CHARS} chars, " \
                         f"original was {len(content)} chars]"
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(truncated)
            print(f"[AI EDIT] PDF text truncated: {len(content)} -> {_PDF_MAX_TEXT_CHARS} chars")
    except Exception:
        pass
    return txt_path


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

    # ── Session token tracking (inspired by Claude Code cost-tracker) ──
    _ai_session_tokens = {          # Accumulated across turns
        'input': 0, 'output': 0,
        'cache_read': 0, 'cache_creation': 0,
        'total_cost_usd': 0.0,
        'turn_count': 0,
    }
    _ai_session_estimated_ctx = 0   # Rough char-based context estimate
    _ai_stall_last_event = 0.0     # Timestamp of last streaming event

    # ── Streaming preview (inspired by Claude Code StreamingToolExecutor) ──
    # Detect Write/Edit to scene.py mid-stream and offer early preview
    _ai_claude_early_code = None    # Code available before stream finishes
    _ai_claude_early_code_at = 0.0  # Timestamp when early code was detected

    # ── Chat history tracking (for persistent sessions) ──
    _ai_current_prompt = ''         # Current turn's user prompt
    _ai_current_model = ''          # Current turn's model
    _ai_resume_context = ''         # Previous session context to inject on resume

    # ── Image upload for AI context ──

    def ai_edit_save_image(self, filename, data_url):
        """Save a base64 data URL file (image or PDF) to a temp directory for AI context.
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
        """Return available Claude models with capabilities and pricing."""
        models = ModelRegistry.list_for_provider('claude')
        return {
            'models': [
                {
                    'id': m['id'],
                    'display_name': m['display'],
                    'family': m.get('family', ''),
                    'tier': m.get('tier', 'standard'),
                    'cost': f"${m['cost_input']}/{m['cost_output']} per Mtok",
                    'context': m.get('context', 200_000),
                    'thinking': m.get('thinking', ''),
                    'recommended_for': m.get('recommended_for', []),
                }
                for m in models
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
            pdf_names = [n for n in names if n.lower().endswith('.pdf')]
            img_names = [n for n in names if not n.lower().endswith('.pdf')]
            parts = []
            if img_names:
                parts.append(
                    f"Reference images in `images/` folder: {', '.join(img_names)}. "
                    f"Read every image first — describe ALL text, layout, colors, "
                    f"shapes, math exactly. Then use that to code.")
            if pdf_names:
                # Check which PDFs have extracted text companions
                extracted = []
                raw_only = []
                for n, p in zip(pdf_names, [p for p in image_paths if os.path.basename(p).lower().endswith('.pdf')]):
                    txt = p.rsplit('.', 1)[0] + '_content.txt'
                    if os.path.exists(txt):
                        extracted.append((n, os.path.basename(txt)))
                    else:
                        raw_only.append(n)
                if extracted:
                    txt_list = ', '.join(t for _, t in extracted)
                    parts.append(
                        f"Reference PDFs in `images/` folder: {', '.join(n for n, _ in extracted)}. "
                        f"Text extracted to: {txt_list}. "
                        f"Read the _content.txt file(s) for the full text. "
                        f"Then use that content to code.")
                if raw_only:
                    parts.append(
                        f"Reference PDFs in `images/` folder: {', '.join(raw_only)}. "
                        f"Read each PDF using pages parameter (e.g. pages='1-10') in small chunks. "
                        f"Extract ALL relevant content, formulas, and structure. Then use that to code.")
            image_hint = "\n\n" + " ".join(parts)

        # Load from prompts/ folder (claude and codex share the same non-agent prompt)
        prompt_file = 'claude_non_agent.md'
        if has_selection:
            tpl = _load_prompt_section(prompt_file, 'With Selection')
            if tpl:
                result = (tpl
                    .replace('{{SEL_START}}', str(selection_start))
                    .replace('{{SEL_END}}', str(selection_end))
                    .replace('{{SELECTED_CODE}}', selected_code)
                    .replace('{{PROMPT}}', prompt))
                return result + search_hint + image_hint
        else:
            tpl = _load_prompt_section(prompt_file, 'Without Selection')
            if tpl:
                result = tpl.replace('{{PROMPT}}', prompt)
                return result + image_hint + search_hint

        # Fallback if prompt file missing
        return f"Read `scene.py` first, then edit it.\nInstruction: {prompt}{image_hint}{search_hint}"

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
        if not code or not code.strip():
            print("[AI EDIT] WARNING: _setup_ai_workspace received empty code")
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code or '')

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
                    # Auto-extract text from PDFs so AI can read them reliably
                    if dest.lower().endswith('.pdf'):
                        _extract_pdf_text(dest)

        # CLAUDE.md / AGENTS.md — loaded from prompts/ folder
        md_content = _load_prompt('workspace_claude.md')
        if not md_content:
            md_content = "# Workspace Rules\nEdit scene.py only. Read it first.\n"
        md_content = _append_assets_list(md_content)

        # Inject render memory context (past successes/errors)
        memory_ctx = RenderMemory.get_context(max_lines=30)
        if memory_ctx:
            md_content += (
                "\n## Render History (learn from past attempts)\n"
                + memory_ctx + "\n"
            )

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

            raw_model = (model or '').strip()
            use_model, migrated = ModelRegistry.resolve(raw_model, task='edit')
            # Only pass model flag if user explicitly chose one
            if not raw_model:
                use_model = ''
            model_info = ModelRegistry.get_info(use_model) if use_model else None

            print(f"[AI CLAUDE] Starting Claude Code edit (stream-json)...")
            print(f"[AI CLAUDE] Prompt: {prompt}")
            if use_model:
                cost_str = (f" (${model_info['cost_input']}/{model_info['cost_output']} per Mtok)"
                            if model_info else '')
                migrated_str = f" [migrated from {raw_model}]" if migrated else ''
                print(f"[AI CLAUDE] Model: {use_model}{cost_str}{migrated_str}")

            # ── Auto-compact: if context is near limit, start fresh session ──
            est_tokens = AIEditMixin._ai_session_estimated_ctx
            if (est_tokens > CONTEXT_WINDOW_TOKENS * CONTEXT_CRITICAL_RATIO
                    and AIEditMixin._ai_chat_session_id):
                old_sid = (AIEditMixin._ai_chat_session_id or '')[:8]
                AIEditMixin._ai_chat_session_id = str(uuid.uuid4())
                AIEditMixin._ai_chat_first_message = True
                # Reset token tracking but keep cumulative cost
                old_cost = AIEditMixin._ai_session_tokens['total_cost_usd']
                AIEditMixin._ai_session_tokens = {
                    'input': 0, 'output': 0,
                    'cache_read': 0, 'cache_creation': 0,
                    'total_cost_usd': old_cost, 'turn_count': 0,
                }
                AIEditMixin._ai_session_estimated_ctx = 0
                msg = (f"Auto-compact: session context was near limit "
                       f"(~{est_tokens//1000}k tokens). "
                       f"Started fresh session to avoid errors.")
                print(f"[AI CLAUDE] {msg} (old={old_sid}...)")
                AIEditMixin._ai_claude_raw_chunks.append(
                    f"\x1b[33m{msg}\x1b[0m\r\n")
                AIEditMixin._ai_claude_events.append({
                    '_kind': 'text', '_text': msg})

            # Guard: if code is empty, try to get it from app state
            if not code or not code.strip():
                try:
                    code_res = self.get_code()
                    if isinstance(code_res, dict):
                        code = code_res.get('code', '') or ''
                    print(f"[AI CLAUDE] Code param was empty, "
                          f"fetched from editor: {len(code)} chars")
                except Exception:
                    pass
            if not code or not code.strip():
                print("[AI CLAUDE] WARNING: code is empty — scene.py will be blank")

            # Continuous chat: reuse workspace and session
            # Check that the workspace directory still exists (it may have
            # been cleaned up by _cleanup_old_workspaces or deleted externally)
            if (AIEditMixin._ai_chat_session_id
                    and AIEditMixin._ai_chat_workspace
                    and os.path.isdir(AIEditMixin._ai_chat_workspace)):
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
                # Workspace missing or first message — create fresh
                if AIEditMixin._ai_chat_workspace and not os.path.isdir(AIEditMixin._ai_chat_workspace):
                    print(f"[AI CLAUDE] Workspace was deleted, creating new one")
                workspace, code_file, image_paths = self._setup_ai_workspace(code, image_paths or [])
                AIEditMixin._ai_chat_session_id = str(uuid.uuid4())
                AIEditMixin._ai_chat_workspace = workspace
                AIEditMixin._ai_chat_first_message = True

            instruction = self._build_ai_instruction(
                prompt, selected_code, selection_start, selection_end, search, image_paths)

            # Inject previous session context on resume
            if AIEditMixin._ai_resume_context:
                instruction = (AIEditMixin._ai_resume_context
                               + "\n\n---\nNow continue with the new request:\n\n"
                               + instruction)
                AIEditMixin._ai_resume_context = ''  # Only inject once

            # Reset streaming state (not session state)
            AIEditMixin._ai_claude_events = []
            AIEditMixin._ai_claude_raw_chunks = []
            AIEditMixin._ai_claude_done = False
            AIEditMixin._ai_claude_workspace = workspace
            AIEditMixin._ai_claude_code_file = code_file
            AIEditMixin._ai_claude_original_code = code
            AIEditMixin._ai_claude_result_text = ''
            AIEditMixin._ai_claude_early_code = None
            AIEditMixin._ai_claude_early_code_at = 0.0

            # Track for chat history persistence
            AIEditMixin._ai_current_prompt = prompt
            AIEditMixin._ai_current_model = use_model

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
            # Includes stall watchdog and per-turn cost/token tracking.
            def _reader():
                AIEditMixin._ai_stall_last_event = time.time()
                # Mutable container so watchdog can set warned=True
                stall_state = {'warned': False}

                # Start stall watchdog thread
                def _watchdog():
                    while not AIEditMixin._ai_claude_done:
                        time.sleep(5)
                        elapsed = time.time() - AIEditMixin._ai_stall_last_event
                        if elapsed > STALL_TIMEOUT_S:
                            print(f"[AI CLAUDE] Stall watchdog: no output for "
                                  f"{elapsed:.0f}s — killing process")
                            # Kill whichever proc is currently active
                            cur = AIEditMixin._ai_claude_proc
                            if cur:
                                try:
                                    cur.kill()
                                except Exception:
                                    pass
                            AIEditMixin._ai_claude_events.append({
                                '_kind': 'text',
                                '_text': f'Stream stalled ({int(elapsed)}s), process killed'
                            })
                            AIEditMixin._ai_claude_raw_chunks.append(
                                f"\x1b[31mStream stalled ({int(elapsed)}s), "
                                f"process killed\x1b[0m\r\n")
                            AIEditMixin._ai_claude_done = True
                            return
                        elif elapsed > STALL_WARNING_S and not stall_state['warned']:
                            stall_state['warned'] = True
                            print(f"[AI CLAUDE] Stall warning: no output for {elapsed:.0f}s")
                            AIEditMixin._ai_claude_raw_chunks.append(
                                f"\x1b[33mWaiting for response ({int(elapsed)}s)...\x1b[0m\r\n")
                threading.Thread(target=_watchdog, daemon=True).start()

                try:
                    for line in proc.stdout:
                        AIEditMixin._ai_stall_last_event = time.time()
                        stall_state['warned'] = False
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

                        # Final result — extract cost + token usage
                        # Note: 'result' field can be a dict in newer CLI versions
                        if ev_type == 'result':
                            raw_result = event.get('result', '')
                            if isinstance(raw_result, dict):
                                raw_result = raw_result.get('text', '') or json.dumps(raw_result)
                            AIEditMixin._ai_claude_result_text = str(raw_result)
                            cost = event.get('total_cost_usd')
                            dur = event.get('duration_ms')
                            rt = AIEditMixin._ai_claude_result_text

                            # ── Per-turn token tracking ──
                            usage = event.get('usage', {})
                            inp_tok = usage.get('input_tokens', 0)
                            out_tok = usage.get('output_tokens', 0)
                            cache_read = usage.get('cache_read_input_tokens', 0)
                            cache_create = usage.get('cache_creation_input_tokens', 0)

                            st = AIEditMixin._ai_session_tokens
                            st['input'] += inp_tok
                            st['output'] += out_tok
                            st['cache_read'] += cache_read
                            st['cache_creation'] += cache_create
                            st['turn_count'] += 1
                            if cost is not None:
                                st['total_cost_usd'] += cost

                            # Estimate context size from accumulated tokens
                            AIEditMixin._ai_session_estimated_ctx = (
                                st['input'] + st['output'])

                            if rt:
                                AIEditMixin._ai_claude_events.append({'_kind': 'text', '_text': rt})
                                AIEditMixin._ai_claude_raw_chunks.append(
                                    f"\r\n\x1b[32m{rt}\x1b[0m\r\n")

                            # ── Display cost + cache stats ──
                            cost_parts = []
                            if cost is not None:
                                cost_parts.append(f"${cost:.4f}")
                            if dur is not None:
                                cost_parts.append(f"{dur/1000:.1f}s")
                            if inp_tok or out_tok:
                                cost_parts.append(f"{inp_tok}→{out_tok} tok")
                            if cache_read:
                                pct = (cache_read / max(inp_tok, 1)) * 100
                                cost_parts.append(f"cache:{pct:.0f}%")
                            if cost_parts:
                                summary = '  '.join(cost_parts)
                                AIEditMixin._ai_claude_raw_chunks.append(
                                    f"\x1b[90m{summary}\x1b[0m\r\n")
                                AIEditMixin._ai_claude_events.append({
                                    '_kind': 'text', '_text': summary})

                            # ── Context window warning ──
                            est_tokens = AIEditMixin._ai_session_estimated_ctx
                            if est_tokens > CONTEXT_WINDOW_TOKENS * CONTEXT_CRITICAL_RATIO:
                                warn = (f"⚠ Session near context limit "
                                        f"(~{est_tokens//1000}k/{CONTEXT_WINDOW_TOKENS//1000}k). "
                                        f"Start a New Chat to avoid errors.")
                                AIEditMixin._ai_claude_raw_chunks.append(
                                    f"\x1b[31m{warn}\x1b[0m\r\n")
                                AIEditMixin._ai_claude_events.append({
                                    '_kind': 'text', '_text': warn})
                            elif est_tokens > CONTEXT_WINDOW_TOKENS * CONTEXT_WARN_RATIO:
                                warn = (f"Context growing large "
                                        f"(~{est_tokens//1000}k/{CONTEXT_WINDOW_TOKENS//1000}k). "
                                        f"Consider starting a New Chat soon.")
                                AIEditMixin._ai_claude_raw_chunks.append(
                                    f"\x1b[33m{warn}\x1b[0m\r\n")

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
                        # Streaming preview: after each tool result, check if
                        # scene.py was modified. If so, offer it for early
                        # preview while AI continues working.
                        if ev_type == 'user':
                            code_file = AIEditMixin._ai_claude_code_file
                            if code_file and os.path.exists(code_file):
                                try:
                                    with open(code_file, 'r', encoding='utf-8') as _f:
                                        current = _f.read()
                                    orig = AIEditMixin._ai_claude_original_code
                                    if (current.strip()
                                            and current != orig
                                            and current != (AIEditMixin._ai_claude_early_code or '')):
                                        AIEditMixin._ai_claude_early_code = current
                                        AIEditMixin._ai_claude_early_code_at = time.time()
                                        print(f"[AI CLAUDE] Early code detected "
                                              f"({len(current)} chars)")
                                except Exception:
                                    pass

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
                rc = proc.returncode
                print(f"[AI CLAUDE] Process finished, rc={rc}")

                # ── Auto-retry on failure (inspired by Claude Code withRetry) ──
                if rc != 0 and not AIEditMixin._ai_claude_events:
                    retry_attempt = getattr(AIEditMixin, '_ai_claude_retry_attempt', 0)
                    if retry_attempt < RETRY_MAX_ATTEMPTS:
                        delay = RETRY_BASE_DELAY_S * (2 ** retry_attempt)
                        AIEditMixin._ai_claude_retry_attempt = retry_attempt + 1
                        msg = (f"Claude exited with error (rc={rc}), "
                               f"retrying in {delay}s "
                               f"(attempt {retry_attempt + 1}/{RETRY_MAX_ATTEMPTS})...")
                        print(f"[AI CLAUDE] {msg}")
                        AIEditMixin._ai_claude_raw_chunks.append(
                            f"\x1b[33m{msg}\x1b[0m\r\n")
                        AIEditMixin._ai_claude_events.append({
                            '_kind': 'text', '_text': msg})
                        time.sleep(delay)

                        # Relaunch the same command
                        try:
                            retry_proc = subprocess.Popen(
                                cmd_parts,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='replace',
                                bufsize=1, cwd=workspace, env=env
                            )
                            AIEditMixin._ai_claude_proc = retry_proc
                            AIEditMixin._ai_stall_last_event = time.time()
                            # Recurse into reader loop for retry
                            for line in retry_proc.stdout:
                                AIEditMixin._ai_stall_last_event = time.time()
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    event = json.loads(line)
                                except json.JSONDecodeError:
                                    AIEditMixin._ai_claude_events.append(
                                        {'_kind': 'raw', '_text': line})
                                    AIEditMixin._ai_claude_raw_chunks.append(
                                        line + '\r\n')
                                    continue
                                ev_type = event.get('type', '')
                                if ev_type == 'result':
                                    raw_r = event.get('result', '')
                                    if isinstance(raw_r, dict):
                                        raw_r = raw_r.get('text', '') or json.dumps(raw_r)
                                    AIEditMixin._ai_claude_result_text = str(raw_r)
                                    rt = AIEditMixin._ai_claude_result_text
                                    if rt:
                                        AIEditMixin._ai_claude_events.append(
                                            {'_kind': 'text', '_text': rt})
                                        AIEditMixin._ai_claude_raw_chunks.append(
                                            f"\r\n\x1b[32m{rt}\x1b[0m\r\n")
                                    cost = event.get('total_cost_usd')
                                    if cost is not None:
                                        AIEditMixin._ai_claude_raw_chunks.append(
                                            f"\x1b[90mRetry cost: ${cost:.4f}\x1b[0m\r\n")
                                        AIEditMixin._ai_session_tokens[
                                            'total_cost_usd'] += cost
                                    continue
                                # Pass through all other events
                                if ev_type == 'assistant':
                                    for block in (event.get('message', {}).get(
                                            'content') or []):
                                        if isinstance(block, dict):
                                            btype = block.get('type', '')
                                            if btype == 'text':
                                                text = block.get('text', '').strip()
                                                if text:
                                                    AIEditMixin._ai_claude_events.append(
                                                        {'_kind': 'text', '_text': text})
                                                    AIEditMixin._ai_claude_raw_chunks.append(
                                                        text + '\r\n')
                            retry_proc.wait()
                            rc = retry_proc.returncode
                            print(f"[AI CLAUDE] Retry finished, rc={rc}")
                        except Exception as e:
                            print(f"[AI CLAUDE] Retry error: {e}")
                    else:
                        AIEditMixin._ai_claude_events.append({
                            '_kind': 'text',
                            '_text': f'Claude Code exited with error (rc={rc})'
                        })
                elif rc != 0:
                    AIEditMixin._ai_claude_events.append({
                        '_kind': 'text',
                        '_text': f'Claude Code exited with error (rc={rc})'
                    })

                # Reset retry counter on success
                AIEditMixin._ai_claude_retry_attempt = 0

                # ── Save turn to persistent chat history ──
                try:
                    formatted = AIEditMixin._format_stream_events(
                        AIEditMixin._ai_claude_events)
                    st = AIEditMixin._ai_session_tokens
                    code_after = None
                    cf = AIEditMixin._ai_claude_code_file
                    if cf and os.path.exists(cf):
                        with open(cf, 'r', encoding='utf-8') as _f:
                            code_after = _f.read()
                    ChatHistory.save_turn(
                        session_id=AIEditMixin._ai_chat_session_id,
                        file_path='',
                        model=AIEditMixin._ai_current_model,
                        prompt=AIEditMixin._ai_current_prompt,
                        response_text=formatted,
                        code_after=code_after,
                        cost_usd=st.get('total_cost_usd', 0),
                        tokens={'input': st.get('input', 0),
                                'output': st.get('output', 0)},
                    )
                except Exception as _e:
                    print(f"[CHAT HISTORY] Auto-save failed: {_e}")

                AIEditMixin._ai_claude_done = True

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

        # Include session stats for frontend display
        st = AIEditMixin._ai_session_tokens
        session_info = None
        if st['turn_count'] > 0:
            session_info = {
                'turns': st['turn_count'],
                'total_input': st['input'],
                'total_output': st['output'],
                'cache_read': st['cache_read'],
                'total_cost': round(st['total_cost_usd'], 4),
                'est_context_pct': min(100, round(
                    (AIEditMixin._ai_session_estimated_ctx
                     / CONTEXT_WINDOW_TOKENS) * 100)),
            }

        # Include early code for streaming preview
        early = AIEditMixin._ai_claude_early_code
        early_info = None
        if early:
            early_info = {
                'code': early,
                'detected_at': AIEditMixin._ai_claude_early_code_at,
            }

        return {'status': 'streaming', 'output': raw_output,
                'filtered_output': filtered,
                'done': False, 'chars': len(raw_output),
                'session': session_info,
                'early_preview': early_info}

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
        # Reset session token tracking
        AIEditMixin._ai_session_tokens = {
            'input': 0, 'output': 0,
            'cache_read': 0, 'cache_creation': 0,
            'total_cost_usd': 0.0, 'turn_count': 0,
        }
        AIEditMixin._ai_session_estimated_ctx = 0
        print("[AI CLAUDE] Chat session reset (tokens cleared)")
        return {'status': 'ok'}

    # ── Chat History API ──

    def ai_edit_list_sessions(self):
        """Return recent chat sessions for the history dropdown."""
        sessions = ChatHistory.list_sessions(limit=30)
        return {'status': 'ok', 'sessions': sessions}

    def ai_edit_load_session(self, session_id):
        """Load a previous chat session's conversation for display."""
        data = ChatHistory.load_session(session_id)
        if not data:
            return {'status': 'error', 'message': 'Session not found'}
        return {'status': 'ok', 'session': data}

    def ai_edit_delete_session(self, session_id):
        """Delete a chat session from history."""
        ChatHistory.delete_session(session_id)
        return {'status': 'ok'}

    def ai_edit_resume_session(self, session_id):
        """Resume a previous chat session. Injects context summary into
        a new Claude session so the AI remembers the prior conversation."""
        data = ChatHistory.load_session(session_id)
        if not data:
            return {'status': 'error', 'message': 'Session not found'}
        # Set session state so next ai_edit_claude_start uses this context
        AIEditMixin._ai_chat_session_id = session_id
        AIEditMixin._ai_chat_first_message = True
        # Store context summary to inject in the next CLAUDE.md
        AIEditMixin._ai_resume_context = ChatHistory.build_context_summary(
            session_id, max_turns=8)
        return {
            'status': 'ok',
            'session': data,
            'message': f"Resumed session ({len(data.get('turns', []))} turns)"
        }

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
        models = ModelRegistry.list_for_provider('codex')
        # Include models from registry + extra Codex models not in registry
        extra = [
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
        result = [
            {'id': m['id'], 'display_name': m['display'],
             'tier': m.get('tier', 'standard')}
            for m in models
        ]
        result.extend(extra)
        return {'models': result}

    def resolve_model(self, model_input, task='edit'):
        """Resolve a model alias/legacy ID to canonical ID.
        Exposed as API so frontend can resolve before sending."""
        model_id, migrated = ModelRegistry.resolve(model_input, task)
        info = ModelRegistry.get_info(model_id)
        return {
            'model_id': model_id,
            'migrated': migrated,
            'display': info['display'] if info else model_id,
            'provider': info['provider'] if info else 'claude',
            'tier': info.get('tier', 'standard') if info else 'standard',
            'cost': (f"${info['cost_input']}/{info['cost_output']} per Mtok"
                     if info else 'unknown'),
        }

    def get_model_info(self, model_id):
        """Get full model capabilities and pricing."""
        info = ModelRegistry.get_info(model_id)
        if not info:
            return {'status': 'error', 'message': f'Unknown model: {model_id}'}
        return {'status': 'success', **info}

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
            autocomplete_model, _ = ModelRegistry.resolve('', task='autocomplete')
            cmd = ['claude', '-p', prompt, '--output-format', 'text',
                   '--model', autocomplete_model]
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
    _ai_agent_image_paths = []    # user-uploaded reference images

    def ai_agent_start(self, description, max_iterations=5, model='', provider='claude', image_paths=None, code=''):
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
        AIEditMixin._ai_agent_image_paths = image_paths or []
        # Reset session memory for fresh agent run
        AIEditMixin._ai_agent_session_id = None
        AIEditMixin._ai_agent_workspace = None
        AIEditMixin._ai_agent_first_edit = True
        # Reset agent session token tracking
        AIEditMixin._ai_session_tokens = {
            'input': 0, 'output': 0,
            'cache_read': 0, 'cache_creation': 0,
            'total_cost_usd': 0.0, 'turn_count': 0,
        }
        AIEditMixin._ai_session_estimated_ctx = 0

        t = threading.Thread(target=self._ai_agent_run,
                             args=(description, max_iterations, code), daemon=True)
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
        # Ensure code/instruction are strings (guard against dict from JS)
        if not isinstance(code, str):
            code = str(code) if code else ''
        if not isinstance(instruction, str):
            instruction = str(instruction) if instruction else ''
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

                # Copy user-uploaded reference files (images + PDFs) into workspace
                if AIEditMixin._ai_agent_image_paths:
                    img_ws_dir = os.path.join(workspace, 'images')
                    os.makedirs(img_ws_dir, exist_ok=True)
                    for ip in AIEditMixin._ai_agent_image_paths:
                        if os.path.isfile(ip):
                            dest = os.path.join(img_ws_dir, os.path.basename(ip))
                            shutil.copy2(ip, dest)
                            print(f"[AI AGENT] Copied file: {os.path.basename(ip)}")
                            if dest.lower().endswith('.pdf'):
                                _extract_pdf_text(dest)

            # Write scene.py — guard against empty code
            code_file = os.path.join(workspace, 'scene.py')
            if not code or not code.strip():
                # Try to get code from app state
                try:
                    code_res = self.get_code()
                    if isinstance(code_res, dict) and code_res.get('code'):
                        code = code_res['code']
                        print(f"[AI AGENT] Code was empty, fetched from editor: "
                              f"{len(code)} chars")
                except Exception:
                    pass
            if not code or not code.strip():
                print("[AI AGENT] WARNING: writing empty scene.py to workspace")
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code or '')

            # Write CLAUDE.md (only on first edit — it doesn't change)
            if AIEditMixin._ai_agent_first_edit:
                md_path = os.path.join(workspace, 'CLAUDE.md')
                claude_md_content = _load_prompt('workspace_claude.md')
                if not claude_md_content:
                    claude_md_content = "# Workspace Rules\nEdit scene.py only. Read it first.\n"
                claude_md_content = _append_assets_list(claude_md_content)
                # Inject render memory (past successes/errors)
                memory_ctx = RenderMemory.get_context(max_lines=30)
                if memory_ctx:
                    claude_md_content += (
                        "\n## Render History (learn from past attempts)\n"
                        + memory_ctx + "\n"
                    )
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
                stderr=subprocess.PIPE,
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

            # Background stderr reader — captures errors for diagnostics
            _stderr_lines = []
            def _read_stderr():
                try:
                    for line in proc.stderr:
                        line = line.rstrip()
                        if line:
                            _stderr_lines.append(line)
                            print(f"[AI AGENT] stderr: {line[:200]}")
                except Exception:
                    pass
            threading.Thread(target=_read_stderr, daemon=True).start()

            # Mark first edit done so subsequent calls use --resume
            AIEditMixin._ai_agent_first_edit = False

            # Stream output — parse stream-json for live display
            # Includes stall watchdog to detect hung processes.
            result_text = ''
            last_event_time = time.time()
            _raw_line_count = 0

            def _agent_stream_parse(proc_stream):
                """Parse stream-json lines from a process. Returns result_text."""
                nonlocal last_event_time, _raw_line_count
                _result_text = ''
                try:
                    for line in proc_stream:
                        last_event_time = time.time()
                        _raw_line_count += 1
                        if _raw_line_count <= 3:
                            print(f"[AI AGENT] raw[{_raw_line_count}]: {line.strip()[:150]}")
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

                        if ev_type == 'result':
                            raw_r = event.get('result', '')
                            if isinstance(raw_r, dict):
                                raw_r = raw_r.get('text', '') or json.dumps(raw_r)
                            _result_text = str(raw_r)
                            cost = event.get('total_cost_usd')
                            dur = event.get('duration_ms')
                            # Track tokens for agent session
                            usage = event.get('usage', {})
                            inp_tok = usage.get('input_tokens', 0)
                            out_tok = usage.get('output_tokens', 0)
                            cache_read = usage.get('cache_read_input_tokens', 0)
                            cost_parts = []
                            if cost is not None:
                                cost_parts.append(f"${cost:.4f}")
                            if dur is not None:
                                cost_parts.append(f"{dur/1000:.1f}s")
                            if inp_tok or out_tok:
                                cost_parts.append(f"{inp_tok}→{out_tok} tok")
                            if cache_read and inp_tok:
                                cost_parts.append(
                                    f"cache:{cache_read/max(inp_tok,1)*100:.0f}%")
                            if cost_parts:
                                AIEditMixin._ai_agent_stream_events.append({
                                    '_kind': 'text',
                                    '_text': '  '.join(cost_parts)})
                            continue

                        if ev_type in ('system', 'rate_limit_event'):
                            continue

                        if ev_type == 'assistant':
                            for block in (event.get('message', {}).get(
                                    'content') or []):
                                if not isinstance(block, dict):
                                    continue
                                btype = block.get('type', '')
                                if btype == 'tool_use':
                                    tool = block.get('name', '')
                                    inp = block.get('input', {})
                                    arg = ''
                                    if isinstance(inp, dict):
                                        arg = (inp.get('file_path')
                                               or inp.get('path')
                                               or inp.get('command')
                                               or inp.get('query') or '')
                                        if isinstance(arg, str) and len(arg) > 60:
                                            arg = '...' + arg[-50:]
                                    AIEditMixin._ai_agent_stream_events.append({
                                        '_kind': 'tool_use', '_tool': tool,
                                        '_arg': arg, '_input': inp})
                                    content = (inp.get('content', '')
                                               if isinstance(inp, dict) else '')
                                    if content and tool in ('Write', 'Edit'):
                                        for i, cl in enumerate(
                                                content.split('\n'), 1):
                                            AIEditMixin._ai_agent_stream_events.append(
                                                {'_kind': 'code_line',
                                                 '_num': i, '_text': cl})
                                elif btype == 'text':
                                    text = block.get('text', '').strip()
                                    if text:
                                        AIEditMixin._ai_agent_stream_events.append(
                                            {'_kind': 'text', '_text': text})
                            continue

                        if ev_type == 'user':
                            tr = event.get('tool_use_result', {})
                            if isinstance(tr, dict):
                                stdout_out = tr.get('stdout', '')
                                content = tr.get('content', '')
                                if stdout_out:
                                    out_lines = stdout_out.strip().split('\n')
                                    for ol in out_lines[:15]:
                                        AIEditMixin._ai_agent_stream_events.append(
                                            {'_kind': 'result_line', '_text': ol})
                                    if len(out_lines) > 15:
                                        AIEditMixin._ai_agent_stream_events.append({
                                            '_kind': 'collapsed',
                                            '_text': f'+{len(out_lines)-15} lines'})
                                elif isinstance(content, str) and content.strip():
                                    short = content.strip()[:200]
                                    AIEditMixin._ai_agent_stream_events.append(
                                        {'_kind': 'result_line', '_text': short})
                            continue

                except Exception as e:
                    print(f"[AI AGENT] stream read error: {e}")
                return _result_text

            # No stall watchdog for agent edits — Claude may think for
            # minutes on complex tasks (PDF reading, code generation).
            # The user can cancel manually via the stop button.

            result_text = _agent_stream_parse(proc.stdout)
            proc.wait()

            # ── Diagnostics on failure ──
            if proc.returncode != 0:
                print(f"[AI AGENT] Claude exit rc={proc.returncode}, "
                      f"stdout_lines={_raw_line_count}, stderr_lines={len(_stderr_lines)}")
                if _stderr_lines:
                    for sl in _stderr_lines[:10]:
                        print(f"[AI AGENT] stderr: {sl[:300]}")

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

                # Copy user-uploaded reference files (images + PDFs) into workspace
                if AIEditMixin._ai_agent_image_paths:
                    img_ws_dir = os.path.join(workspace, 'images')
                    os.makedirs(img_ws_dir, exist_ok=True)
                    for ip in AIEditMixin._ai_agent_image_paths:
                        if os.path.isfile(ip):
                            dest = os.path.join(img_ws_dir, os.path.basename(ip))
                            shutil.copy2(ip, dest)
                            print(f"[AI AGENT] Copied file: {os.path.basename(ip)}")
                            if dest.lower().endswith('.pdf'):
                                _extract_pdf_text(dest)

            code_file = os.path.join(workspace, 'scene.py')
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # Write AGENTS.md + CLAUDE.md (only on first iteration)
            if not os.path.exists(os.path.join(workspace, 'AGENTS.md')):
                md_content = _load_prompt('workspace_codex.md')
                if not md_content:
                    md_content = "# Workspace Rules\nEdit scene.py only. Read it first.\n"
                md_content = _append_assets_list(md_content)
                for fname in ('AGENTS.md', 'CLAUDE.md'):
                    md_path = os.path.join(workspace, fname)
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)

            cmd = ['codex', 'exec', '-', '--full-auto',
                   '--skip-git-repo-check', '--json']
            if AIEditMixin._ai_agent_model:
                cmd.extend(['-m', AIEditMixin._ai_agent_model])
            # Pass user-uploaded reference images via -i flag
            if AIEditMixin._ai_agent_image_paths:
                img_ws_dir = os.path.join(workspace, 'images')
                if os.path.isdir(img_ws_dir):
                    for fname in os.listdir(img_ws_dir):
                        fpath = os.path.join(img_ws_dir, fname)
                        if os.path.isfile(fpath):
                            cmd.extend(['-i', fpath])

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

    def _ai_agent_run(self, description, max_iterations, code=''):
        """Main agent loop (runs in thread). Never times out — loops until
        cancelled or the animation is correct."""
        try:
            # Ensure code is a string (JS may send dict/object)
            if not isinstance(code, str):
                code = str(code) if code else ''

            # ── Step 1: Generate code via workspace ──
            self._ai_agent_set('generating', 'Creating Manim animation...')

            # Use the actual editor code; fall back to empty template only if blank
            template = code.strip() if code and code.strip() else (
                "from manim import *\n\n"
                "class MyScene(Scene):\n"
                "    def construct(self):\n"
                "        pass\n"
            )
            # Build file hint if user uploaded reference images/PDFs
            image_hint = ''
            if AIEditMixin._ai_agent_image_paths:
                all_names = [os.path.basename(ip)
                             for ip in AIEditMixin._ai_agent_image_paths
                             if os.path.isfile(ip)]
                if all_names:
                    pdf_names = [n for n in all_names if n.lower().endswith('.pdf')]
                    img_names = [n for n in all_names if not n.lower().endswith('.pdf')]
                    parts = []
                    if img_names:
                        parts.append(
                            f"Reference images in `images/` folder: {', '.join(img_names)}. "
                            f"Read every image first — describe ALL text, layout, colors, "
                            f"shapes, math exactly. Then use that to code.")
                    if pdf_names:
                        # Check which PDFs have extracted text companions
                        ws = AIEditMixin._ai_agent_workspace or ''
                        img_dir = os.path.join(ws, 'images') if ws else ''
                        extracted, raw_only = [], []
                        for n in pdf_names:
                            txt_file = os.path.join(img_dir, n.rsplit('.', 1)[0] + '_content.txt')
                            if img_dir and os.path.exists(txt_file):
                                extracted.append((n, os.path.basename(txt_file)))
                            else:
                                raw_only.append(n)
                        if extracted:
                            txt_list = ', '.join(t for _, t in extracted)
                            parts.append(
                                f"Reference PDFs in `images/` folder: {', '.join(n for n, _ in extracted)}. "
                                f"Text extracted to: {txt_list}. "
                                f"Read the _content.txt file(s) for the full text. "
                                f"Then use that content to code.")
                        if raw_only:
                            parts.append(
                                f"Reference PDFs in `images/` folder: {', '.join(raw_only)}. "
                                f"Read each PDF using pages parameter (e.g. pages='1-10') in small chunks. "
                                f"Extract ALL relevant content, formulas, and structure. Then use that to code.")
                    image_hint = "\n\n" + " ".join(parts)

            # Load Generate prompt from file
            agent_prompt_file = ('codex_agent.md' if AIEditMixin._ai_agent_provider == 'codex'
                                 else 'claude_agent.md')
            tpl = _load_prompt_section(agent_prompt_file, 'Generate')
            if tpl:
                instruction = tpl.replace('{{DESCRIPTION}}', description) + image_hint
            else:
                instruction = (
                    f"Create a Manim animation for:\n\n{description}{image_hint}\n\n"
                    f"Write the complete animation code to scene.py."
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

                # ── Auto-compact: reset session when context grows too large ──
                # Inspired by Claude Code's auto-compaction. Since we use the
                # CLI (not API), we can't do server-side compaction — instead
                # we start a fresh session with a new --session-id, carrying
                # over only the current code and goal.
                est_tokens = AIEditMixin._ai_session_estimated_ctx
                if est_tokens > CONTEXT_WINDOW_TOKENS * CONTEXT_CRITICAL_RATIO:
                    old_sid = (AIEditMixin._ai_agent_session_id or '')[:8]
                    AIEditMixin._ai_agent_session_id = str(uuid.uuid4())
                    AIEditMixin._ai_agent_first_edit = True
                    AIEditMixin._ai_session_tokens = {
                        'input': 0, 'output': 0,
                        'cache_read': 0, 'cache_creation': 0,
                        'total_cost_usd': AIEditMixin._ai_session_tokens[
                            'total_cost_usd'],  # keep cumulative cost
                        'turn_count': 0,
                    }
                    AIEditMixin._ai_session_estimated_ctx = 0
                    msg = (f"Session context full (~{est_tokens//1000}k tokens). "
                           f"Auto-compacting: new session started.")
                    print(f"[AI AGENT] {msg} (old={old_sid}...)")
                    AIEditMixin._ai_agent_stream_events.append({
                        '_kind': 'text', '_text': msg})
                    self._ai_agent_set('fixing', msg)

                # ── Safety: too many consecutive edit failures → stop ──
                if consecutive_edit_failures >= 5:
                    self._ai_agent_set('done',
                        'Stopping — AI edit failed too many times in a row')
                    RenderMemory.record_agent_outcome(
                        scene_name='AgentScene',
                        goal=description,
                        iterations=it,
                        satisfied=False,
                        final_tip='Stopped after 5 consecutive edit failures')
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
                # Wait indefinitely for render — user can cancel via stop button
                fb = None
                while not fb and not AIEditMixin._ai_agent_cancel_flag:
                    fb = self._ai_agent_wait(timeout=30)
                if AIEditMixin._ai_agent_cancel_flag:
                    break

                # ── Render failed → auto-debug ──
                if fb.get('type') == 'render_error':
                    err = fb.get('error', 'Unknown error')
                    consecutive_errors += 1
                    # Record error in render memory
                    RenderMemory.record_error(
                        scene_name='AgentScene',
                        goal=description,
                        error=err[:400])
                    self._ai_agent_set(
                        'fixing',
                        f'Auto-fixing error (attempt {consecutive_errors}): {err[:100]}')
                    err_truncated = err[:1500] if len(err) > 1500 else err
                    tpl_fix = _load_prompt_section(agent_prompt_file, 'Fix')
                    if tpl_fix:
                        fix_instruction = tpl_fix.replace('{{ERROR}}', err_truncated)
                    else:
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
                    # Parallelized: decode + write + downscale runs in a
                    # thread pool (inspired by Claude Code's concurrent
                    # read-only tool execution).
                    workspace = AIEditMixin._ai_agent_workspace or _preview_dir
                    shots_dir = os.path.join(workspace, 'screenshots')
                    os.makedirs(shots_dir, exist_ok=True)

                    def _save_shot(idx_shot):
                        idx, s = idx_shot
                        data_url = s.get('dataUrl', '')
                        if not data_url or ',' not in data_url:
                            return None
                        try:
                            b64 = data_url.split(',', 1)[1]
                            img_bytes = base64.b64decode(b64)
                            fpath = os.path.join(shots_dir, f'frame_{idx+1}.jpg')
                            with open(fpath, 'wb') as f:
                                f.write(img_bytes)
                            _downscale_image(fpath, max_width=960)
                            return fpath
                        except Exception as e:
                            print(f"[AI AGENT] Screenshot save error: {e}")
                            return None

                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=min(8, len(shots) or 1)) as pool:
                        results = list(pool.map(_save_shot, enumerate(shots)))
                    screenshot_files = [r for r in results if r]

                    # ── Review ──
                    self._ai_agent_set('analyzing',
                        f'Reviewing {len(screenshot_files)} frames...')

                    tpl_review = _load_prompt_section(agent_prompt_file, 'Review')
                    if tpl_review:
                        review_prompt = (tpl_review
                            .replace('{{DESCRIPTION}}', description)
                            .replace('{{NUM_FRAMES}}', str(len(screenshot_files))))
                    else:
                        review_prompt = (
                            f"You are a visual QA reviewer for Manim animations.\n\n"
                            f"GOAL: \"{description}\"\n\n"
                            f"Examine all {len(screenshot_files)} frames.\n"
                            f"Reply SATISFIED or IMPROVE: <what is wrong>"
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
                        # Record success in render memory
                        RenderMemory.record_agent_outcome(
                            scene_name='AgentScene',
                            goal=description,
                            iterations=it,
                            satisfied=True)
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
                    tpl_improve = _load_prompt_section(agent_prompt_file, 'Improve')
                    if tpl_improve:
                        improve_instruction = tpl_improve.replace('{{REVIEW_FEEDBACK}}', tip_truncated)
                    else:
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

        # Session stats
        st = AIEditMixin._ai_session_tokens
        session_info = None
        if st['turn_count'] > 0:
            session_info = {
                'turns': st['turn_count'],
                'total_cost': round(st['total_cost_usd'], 4),
                'est_context_pct': min(100, round(
                    (AIEditMixin._ai_session_estimated_ctx
                     / CONTEXT_WINDOW_TOKENS) * 100)),
            }

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
            'session': session_info,
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
