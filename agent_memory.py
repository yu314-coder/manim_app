"""Agent Memory (F-09)
=====================

Per-project style memory for the AI Edit agent.

Each project directory (the directory containing the currently open scene file)
gets a `.manim_studio/style.md` file. Its contents are prepended as a system
preamble to every AI Edit turn, so the AI remembers the user's conventions
across sessions.

Layout on disk:

    <project_dir>/.manim_studio/
        style.md          # user-editable markdown; prepended to every prompt
        proposals.json    # pending memory update proposals (auto-learned)

If the user has no file open, we fall back to a global memory at
    ~/.manim_studio/global_memory/style.md

so the feature still works in "untitled" mode.

Public surface:

    AgentMemory.resolve_dir(current_file_path) -> str   # .manim_studio dir
    AgentMemory.load(current_file_path) -> str          # preamble (budgeted)
    AgentMemory.read_raw(current_file_path) -> dict     # {style_md, path, proposals}
    AgentMemory.write_style(current_file_path, content) # overwrite style.md
    AgentMemory.propose_update(current_file_path, last_user_prompt,
                                last_response_text, turn_index) -> dict|None
    AgentMemory.list_proposals(current_file_path) -> list
    AgentMemory.accept_proposal(current_file_path, proposal_id)
    AgentMemory.dismiss_proposal(current_file_path, proposal_id)
    AgentMemory.strip_ignore_marker(prompt) -> (prompt, should_skip)

Design notes:
- Token budget for the preamble is ~400 tokens (~1600 chars). If style.md is
  bigger, we truncate with a marker so the user knows content was elided.
- Proposal detection is a pure-heuristic keyword matcher (no LLM call). It
  catches obvious correction patterns ("not X, use Y", "too slow", "should be",
  etc.) and proposes saving the user's correction as a style rule verbatim.
  The user decides whether to accept.
- Every write goes through a single helper so on-disk format stays consistent.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Optional


# Maximum characters of style.md to inject as preamble (~400 tokens).
_PREAMBLE_CHAR_BUDGET = 1600

# Prefix a prompt with this token to skip the preamble for a single turn.
_IGNORE_MARKER = '#ignore-style'

# Patterns that indicate the user is correcting the AI's previous output.
# Kept deliberately narrow to avoid false positives.
_CORRECTION_PATTERNS = [
    re.compile(r'\b(no|not)\s+(that|this|like\s+that|what\s+i\s+(wanted|meant|asked))\b', re.I),
    re.compile(r'\b(use|make\s+it|prefer|set)\s+\w+\s+(not|instead\s+of|rather\s+than)\b', re.I),
    re.compile(r'\binstead\s+of\b', re.I),
    re.compile(r'\brather\s+than\b', re.I),
    re.compile(r'\btoo\s+(slow|fast|short|long|big|small|bright|dark|thick|thin|bold)\b', re.I),
    re.compile(r'\bshould\s+(be|have|use)\b', re.I),
    re.compile(r"\b(that\'s|that\s+is)\s+(wrong|incorrect|not\s+right)\b", re.I),
    re.compile(r'\b(always|never)\s+use\b', re.I),
    re.compile(r'\bmake\s+(sure|it)\b.*\b(always|never)\b', re.I),
    re.compile(r'\b(stop|don\'t|do\s+not)\s+\w+ing\b', re.I),
]

# Style.md default scaffold created on first use.
_DEFAULT_STYLE_MD = """---
# Style memory for the AI Edit agent.
# This file is prepended to every AI prompt. Keep it concise.
version: 1
---

## Conventions
<!-- Add style preferences here. Examples:
- Always use `ValueTracker` for smooth transitions
- Prefer `FadeIn` over `Write` for text
- Default runtime: 2.0 seconds
- Color palette: BLUE_D, YELLOW_E, RED_C
-->

## Learned Preferences
<!-- Auto-populated when you accept proposed memory updates. -->
"""

# Header under which accepted proposals get appended.
_LEARNED_HEADER = '## Learned Preferences'


class AgentMemory:
    """Per-project style memory. All methods are classmethods; no state is
    kept in memory — every call reads/writes through disk."""

    # Short-lived in-process cache so the hot path (preamble injection)
    # doesn't stat the disk on every turn. Keyed by project_dir.
    _cache: dict = {}
    _cache_mtime: dict = {}

    # ---------- Project dir resolution ----------

    @classmethod
    def resolve_dir(cls, current_file_path: Optional[str]) -> str:
        """Return the absolute path to the project's `.manim_studio/` directory.
        Creates it if missing. Falls back to a global directory if no file is
        open."""
        if current_file_path and os.path.isfile(current_file_path):
            base = os.path.dirname(os.path.abspath(current_file_path))
        else:
            base = os.path.join(os.path.expanduser('~'),
                                '.manim_studio', 'global_memory')
        proj = os.path.join(base, '.manim_studio')
        try:
            os.makedirs(proj, exist_ok=True)
        except OSError as e:
            print(f"[AGENT MEMORY] mkdir failed: {e}")
        return proj

    @classmethod
    def _style_path(cls, current_file_path: Optional[str]) -> str:
        return os.path.join(cls.resolve_dir(current_file_path), 'style.md')

    @classmethod
    def _proposals_path(cls, current_file_path: Optional[str]) -> str:
        return os.path.join(cls.resolve_dir(current_file_path), 'proposals.json')

    # ---------- Preamble generation (hot path) ----------

    @classmethod
    def load(cls, current_file_path: Optional[str]) -> str:
        """Return the compiled preamble string to prepend to an AI prompt.
        Empty string if no meaningful memory exists."""
        path = cls._style_path(current_file_path)
        if not os.path.isfile(path):
            return ''

        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return ''

        # Cache: skip re-read if file hasn't changed.
        if cls._cache_mtime.get(path) == mtime:
            return cls._cache.get(path, '')

        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except OSError as e:
            print(f"[AGENT MEMORY] read failed: {e}")
            return ''

        compiled = cls._compile_preamble(raw)
        cls._cache[path] = compiled
        cls._cache_mtime[path] = mtime
        return compiled

    @staticmethod
    def _compile_preamble(raw_md: str) -> str:
        """Strip YAML frontmatter, collapse comment-only sections, truncate
        to the char budget, and wrap in a clear delimiter."""
        body = raw_md

        # Strip leading YAML frontmatter (between --- fences).
        if body.startswith('---'):
            end = body.find('\n---', 3)
            if end != -1:
                body = body[end + 4:].lstrip('\n')

        # Remove HTML comment blocks (example scaffolding).
        body = re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL).strip()

        # If there's nothing left but section headers, no memory exists.
        non_header_lines = [
            ln for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith('#')
        ]
        if not non_header_lines:
            return ''

        if len(body) > _PREAMBLE_CHAR_BUDGET:
            body = body[:_PREAMBLE_CHAR_BUDGET].rstrip() + '\n…[memory truncated]'

        return (
            '## Style Memory (project conventions — obey these)\n'
            + body.strip()
            + '\n\n---\n\n'
        )

    # ---------- Raw read / write (for the UI panel) ----------

    @classmethod
    def read_raw(cls, current_file_path: Optional[str]) -> dict:
        """Return {style_md, path, proposals, project_dir} for the UI.
        Creates a default style.md scaffold on first read so the user has
        something to edit."""
        path = cls._style_path(current_file_path)
        if not os.path.isfile(path):
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(_DEFAULT_STYLE_MD)
            except OSError as e:
                print(f"[AGENT MEMORY] create default failed: {e}")

        content = ''
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError:
            pass

        return {
            'style_md': content,
            'path': path,
            'project_dir': cls.resolve_dir(current_file_path),
            'proposals': cls.list_proposals(current_file_path),
        }

    @classmethod
    def write_style(cls, current_file_path: Optional[str], content: str) -> dict:
        """Overwrite style.md. Returns {ok, path, error?}."""
        path = cls._style_path(current_file_path)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content or '')
            # Invalidate cache.
            cls._cache.pop(path, None)
            cls._cache_mtime.pop(path, None)
            return {'ok': True, 'path': path}
        except OSError as e:
            return {'ok': False, 'error': str(e)}

    # ---------- Proposal heuristic ----------

    @classmethod
    def propose_update(cls, current_file_path: Optional[str],
                       last_user_prompt: str,
                       last_response_text: str = '',
                       turn_index: int = 0) -> Optional[dict]:
        """Heuristic: detect whether the user's prompt is a correction of
        the previous AI turn. If so, stage a pending proposal and return it.
        Returns None if no correction signal is detected.

        turn_index: 0 means this is the first turn in the session — we skip
        proposals on first turns since there's nothing being corrected."""
        if turn_index < 1:
            return None
        if not last_user_prompt:
            return None
        text = last_user_prompt.strip()
        # Skip the ignore marker itself from triggering.
        if text.startswith(_IGNORE_MARKER):
            return None
        # Short prompts with correction keywords are the strongest signal.
        # Long prompts are usually fresh requests, not corrections.
        if len(text) > 300:
            return None
        matched = None
        for pat in _CORRECTION_PATTERNS:
            m = pat.search(text)
            if m:
                matched = m.group(0)
                break
        if not matched:
            return None

        proposal = {
            'id': uuid.uuid4().hex[:12],
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'trigger': matched,
            'correction_text': text,
            'suggested_rule': cls._format_rule(text),
            'turn_index': turn_index,
        }
        cls._append_proposal(current_file_path, proposal)
        return proposal

    @staticmethod
    def _format_rule(correction_text: str) -> str:
        """Turn the raw correction into a one-line style rule.
        V1: the correction text IS the rule. Strip trailing punctuation and
        cap length. Future: feed through an LLM for cleaner phrasing."""
        rule = correction_text.strip().rstrip('.?!')
        # Collapse whitespace/newlines.
        rule = re.sub(r'\s+', ' ', rule)
        if len(rule) > 180:
            rule = rule[:177].rstrip() + '…'
        return rule

    @classmethod
    def _append_proposal(cls, current_file_path: Optional[str],
                         proposal: dict) -> None:
        path = cls._proposals_path(current_file_path)
        data = {'proposals': []}
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.loads(f.read()) or {'proposals': []}
            except (OSError, json.JSONDecodeError):
                data = {'proposals': []}
        data.setdefault('proposals', []).append(proposal)
        # Cap at 50 pending proposals to avoid unbounded growth.
        data['proposals'] = data['proposals'][-50:]
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(data, indent=2))
        except OSError as e:
            print(f"[AGENT MEMORY] save proposal failed: {e}")

    @classmethod
    def list_proposals(cls, current_file_path: Optional[str]) -> list:
        path = cls._proposals_path(current_file_path)
        if not os.path.isfile(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return (json.loads(f.read()) or {}).get('proposals', [])
        except (OSError, json.JSONDecodeError):
            return []

    @classmethod
    def _save_proposals(cls, current_file_path: Optional[str],
                        proposals: list) -> None:
        path = cls._proposals_path(current_file_path)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(json.dumps({'proposals': proposals}, indent=2))
        except OSError as e:
            print(f"[AGENT MEMORY] save proposals failed: {e}")

    @classmethod
    def accept_proposal(cls, current_file_path: Optional[str],
                        proposal_id: str) -> dict:
        """Append the proposal's rule to style.md under 'Learned Preferences'
        and remove it from the pending list. Returns {ok, error?}."""
        proposals = cls.list_proposals(current_file_path)
        target = next((p for p in proposals if p.get('id') == proposal_id), None)
        if not target:
            return {'ok': False, 'error': 'proposal not found'}

        style_path = cls._style_path(current_file_path)
        try:
            if os.path.isfile(style_path):
                with open(style_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                content = _DEFAULT_STYLE_MD
        except OSError as e:
            return {'ok': False, 'error': f'read failed: {e}'}

        rule_line = f"- {target['suggested_rule']}  " \
                    f"<!-- added {target['created_at']} -->"

        if _LEARNED_HEADER in content:
            # Insert the rule right after the header (before any comment
            # scaffolding or existing bullets).
            content = content.replace(
                _LEARNED_HEADER,
                _LEARNED_HEADER + '\n' + rule_line,
                1,
            )
        else:
            if not content.endswith('\n'):
                content += '\n'
            content += f'\n{_LEARNED_HEADER}\n{rule_line}\n'

        write_result = cls.write_style(current_file_path, content)
        if not write_result.get('ok'):
            return write_result

        remaining = [p for p in proposals if p.get('id') != proposal_id]
        cls._save_proposals(current_file_path, remaining)
        return {'ok': True, 'rule': rule_line}

    @classmethod
    def dismiss_proposal(cls, current_file_path: Optional[str],
                         proposal_id: str) -> dict:
        proposals = cls.list_proposals(current_file_path)
        remaining = [p for p in proposals if p.get('id') != proposal_id]
        if len(remaining) == len(proposals):
            return {'ok': False, 'error': 'proposal not found'}
        cls._save_proposals(current_file_path, remaining)
        return {'ok': True}

    # ---------- Ignore marker ----------

    @classmethod
    def strip_ignore_marker(cls, prompt: str) -> tuple:
        """If the prompt starts with `#ignore-style`, strip it and return
        (clean_prompt, True). Otherwise return (prompt, False)."""
        if not prompt:
            return prompt, False
        stripped = prompt.lstrip()
        if stripped.startswith(_IGNORE_MARKER):
            return stripped[len(_IGNORE_MARKER):].lstrip(), True
        return prompt, False
