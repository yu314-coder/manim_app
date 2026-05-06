"""AI Sketch (F-08)
===================

Generate 3 lightweight Manim draft scenes from a prompt and render each as
a ~3-second 240p loop. Used for rapid visual exploration before committing
to a real scene.

Flow:
    1. Call Claude CLI once with a prompt that asks for three ``Sketch0``,
       ``Sketch1``, ``Sketch2`` classes in a single file.
    2. Write the generated file to a temp workspace.
    3. Render each scene at 240p/15fps.
    4. Cache outputs under ``<preview_dir>/sketches/<session_id>/``.

v1 scope:
    - Sequential renders (not parallel); explicit TODO to wire into F-12
      dispatcher once that's mature.
    - Pure-text output parsing; no image references.
    - Fork copies the sketch code into a new file next to the current one.

Public entry points:

    generate(prompt, session_id=None) -> dict
    reroll(session_id, idx, prompt) -> dict
    fork(session_id, idx, dest_dir) -> dict
    latest_session() -> Optional[str]
"""

from __future__ import annotations

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


_LATEST_SESSION = {'id': None, 'base_dir': None, 'prompt': ''}
_LOCK = threading.Lock()

# Live state for the running generation job. Frontend polls
# ``sketch_status`` to update the modal incrementally.
_STATE = {
    'active': False,
    'step': 'idle',          # generating | rendering | done | error
    'message': '',
    'cards': [],             # filled in as each variant finishes
    'session_id': None,
    'error': None,
    'log': [],               # live stdout from claude / manim
}

_LOG_MAX = 400


def _log(line: str) -> None:
    """Append to the live log shown in the sketch modal."""
    line = (line or '').rstrip()
    if not line:
        return
    with _LOCK:
        _STATE['log'].append(line)
        if len(_STATE['log']) > _LOG_MAX:
            _STATE['log'] = _STATE['log'][-_LOG_MAX:]
    print(f'[SKETCH-LOG] {line[:200]}')


def sketch_status() -> dict:
    with _LOCK:
        return {
            'active': _STATE['active'],
            'step': _STATE['step'],
            'message': _STATE['message'],
            'cards': list(_STATE['cards']),
            'session_id': _STATE['session_id'],
            'error': _STATE['error'],
            'log': list(_STATE['log']),
        }


def _base_dir(preview_dir: str, session_id: str) -> str:
    p = os.path.join(preview_dir, 'sketches', session_id)
    os.makedirs(p, exist_ok=True)
    return p


_SKETCH_SYSTEM = """You are generating THREE visually distinct Manim draft scenes from the user's prompt. Output a single Python file containing exactly three classes named `Sketch0`, `Sketch1`, `Sketch2`, each a `Scene` subclass with a `construct(self)` method that runs for ~3 seconds. The three sketches should try visually different approaches. No narration. No external assets. No ValueTracker. Use the manim CE API. Output ONLY the .py file contents — no prose, no markdown fences."""


def _call_claude_for_sketches(prompt: str, timeout: int = 120) -> Optional[str]:
    """Stream a Claude CLI call so the sketch modal can show live progress.
    Uses --output-format stream-json (same as AI Edit) for line-by-line
    text deltas; falls back to plain text mode if streaming fails."""
    import json as _json
    combined = f"{_SKETCH_SYSTEM}\n\nUser prompt:\n{prompt}"
    _log(f"Calling Claude (prompt {len(combined)} chars, timeout {timeout}s)…")
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            ['claude', '-p', combined,
             '--output-format', 'stream-json', '--verbose'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
        )
    except FileNotFoundError:
        _log("ERROR: claude CLI not found on PATH")
        return None
    except Exception as e:
        _log(f"ERROR: claude spawn failed: {e}")
        return None

    text_parts = []
    deadline = t0 + timeout
    try:
        for line in proc.stdout or []:
            if time.time() > deadline:
                _log(f"Claude timed out after {timeout}s — killing process")
                proc.kill()
                return None
            line = line.strip()
            if not line:
                continue
            # stream-json emits one JSON event per line. We mainly want
            # `assistant` deltas (text) and `result` (final content).
            try:
                event = _json.loads(line)
            except Exception:
                # Not JSON — probably a usage banner or raw text. Show it.
                _log(line[:240])
                text_parts.append(line)
                continue

            t = event.get('type', '')
            if t == 'assistant':
                # Could be a tool-call or text message. Collect text.
                msg = event.get('message') or {}
                content = msg.get('content') or []
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        chunk = block.get('text', '')
                        if chunk:
                            text_parts.append(chunk)
                            for ln in chunk.split('\n')[:6]:
                                _log(ln[:240])
            elif t == 'result':
                # Final consolidated result. Prefer this over deltas if
                # both arrive.
                final = event.get('result')
                if isinstance(final, str) and final:
                    text_parts = [final]
            elif t == 'system':
                # Brief lifecycle messages — show concisely.
                sub = event.get('subtype') or event.get('event') or ''
                if sub:
                    _log(f"[claude] {sub}")
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        _log("Claude wait timeout")
    except Exception as e:
        _log(f"Claude reader error: {e}")

    dt = time.time() - t0
    text = ''.join(text_parts).strip()
    if not text:
        _log(f"Claude finished in {dt:.1f}s but produced no text")
        return None
    _log(f"Claude finished — {len(text)} chars in {dt:.1f}s")
    # Strip any accidental markdown fences.
    m = re.search(r'```(?:python)?\s*(.+?)```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    return text or None


def _render_scene(scene_file: str, scene_name: str, out_dir: str,
                  manim_cmd: list) -> Optional[str]:
    os.makedirs(out_dir, exist_ok=True)
    cmd = list(manim_cmd) + [
        '-ql', '--fps', '15',
        '--output_file', f'{scene_name}.mp4',
        '--media_dir', out_dir,
        '--disable_caching',
        scene_file, scene_name,
    ]
    _log(f"manim render {scene_name}…")
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
        )
        deadline = time.time() + 180
        last_pct = -1
        for line in proc.stdout or []:
            if time.time() > deadline:
                _log(f"render {scene_name} timed out — killing")
                proc.kill()
                return None
            line = line.strip()
            if not line:
                continue
            # Manim's progress bars come back as long lines with % markers;
            # only post a few key milestones so we don't spam the log.
            m = re.search(r'(\d+)\s*%', line)
            if m:
                pct = int(m.group(1))
                if pct - last_pct >= 25 or pct == 100:
                    _log(f"  {scene_name} {pct}%")
                    last_pct = pct
                continue
            if 'Rendered' in line or 'error' in line.lower() or 'traceback' in line.lower():
                _log(f"  {line[:240]}")
        rc = proc.wait(timeout=5)
        if rc != 0:
            _log(f"render {scene_name} failed rc={rc}")
            return None
    except subprocess.TimeoutExpired:
        _log(f"render {scene_name} timed out")
        return None
    except Exception as e:
        _log(f"render {scene_name} error: {e}")
        return None
    for root, _, files in os.walk(out_dir):
        for f in files:
            if f.endswith('.mp4') and scene_name in f:
                return os.path.join(root, f)
    return None


def generate(preview_dir: str, prompt: str,
             manim_cmd: Optional[list] = None,
             session_id: Optional[str] = None) -> dict:
    """Kick off generation in a background thread and return immediately.

    The frontend polls ``sketch_status()`` every ~500ms to update the modal:
        step='generating'  → "Calling Claude…"
        step='rendering'   → "Rendering Sketch{i}…" with cards filling in
        step='done'        → final cards
        step='error'       → message set
    """
    if not prompt or not prompt.strip():
        return {'status': 'error', 'message': 'empty prompt'}
    with _LOCK:
        if _STATE['active']:
            return {'status': 'busy',
                    'message': 'A sketch generation is already running'}

    manim_cmd = manim_cmd or ['manim']
    session_id = session_id or f'sk_{uuid.uuid4().hex[:10]}'
    base = _base_dir(preview_dir, session_id)
    with _LOCK:
        _LATEST_SESSION.update({'id': session_id, 'base_dir': base, 'prompt': prompt})
        _STATE.update({
            'active': True, 'step': 'generating',
            'message': 'Calling Claude to generate 3 variants…',
            'cards': [{'placeholder': f'Variant {chr(65+i)} — pending'}
                      for i in range(3)],
            'session_id': session_id, 'error': None,
        })

    def _worker():
        try:
            source = _call_claude_for_sketches(prompt)
            if not source:
                with _LOCK:
                    _STATE.update({
                        'active': False, 'step': 'error',
                        'message': 'AI generation failed (check claude CLI / network)',
                        'error': 'no source',
                    })
                return

            # Patch missing classes with stubs so at least partial output renders.
            if not all(f'class Sketch{i}' in source for i in range(3)):
                for i in range(3):
                    if f'class Sketch{i}' not in source:
                        source += (f"\n\nclass Sketch{i}(Scene):\n"
                                   f"    def construct(self):\n"
                                   f"        self.add(Text('Sketch {i} failed to generate'))\n"
                                   f"        self.wait(3)\n")

            scene_file = os.path.join(base, 'sketches.py')
            with open(scene_file, 'w', encoding='utf-8') as f:
                f.write(source)

            with _LOCK:
                _STATE.update({'step': 'rendering',
                                'message': 'Rendering Sketch0/1/2…'})

            for i in range(3):
                name = f'Sketch{i}'
                out_dir = os.path.join(base, f'render_{i}')
                with _LOCK:
                    _STATE['message'] = f'Rendering {name} (variant {chr(65+i)})…'
                print(f'[SKETCH] Rendering {name}…')
                vid = _render_scene(scene_file, name, out_dir, manim_cmd)
                if vid:
                    card = {'video': 'file:///' + vid.replace('\\', '/'),
                            'scene': name, 'source_file': scene_file, 'idx': i}
                    print(f'[SKETCH] {name} rendered → {vid}')
                else:
                    card = {'placeholder': f'{name} render failed',
                            'scene': name, 'source_file': scene_file, 'idx': i}
                    print(f'[SKETCH] {name} render failed')
                with _LOCK:
                    if i < len(_STATE['cards']):
                        _STATE['cards'][i] = card
                    else:
                        _STATE['cards'].append(card)

            with _LOCK:
                _STATE.update({
                    'active': False, 'step': 'done',
                    'message': f'{sum(1 for c in _STATE["cards"] if c.get("video"))}/3 variants ready',
                })
        except Exception as e:
            import traceback
            traceback.print_exc()
            with _LOCK:
                _STATE.update({
                    'active': False, 'step': 'error',
                    'message': str(e), 'error': str(e),
                })

    threading.Thread(target=_worker, daemon=True).start()
    return {'status': 'started', 'session_id': session_id}


def reroll(preview_dir: str, idx: int, prompt: str,
           manim_cmd: Optional[list] = None) -> dict:
    """Re-generate and re-render just ONE variant. Uses the current session
    ID so the card slot is preserved."""
    if _LATEST_SESSION['id'] is None:
        return generate(preview_dir, prompt, manim_cmd=manim_cmd)
    # Simplest: re-run the full generation with a slightly tweaked prompt
    # and swap only the requested slot. Over-generating is wasteful but
    # v1-honest; TODO: per-class prompts once we have partial rerendering.
    alt_prompt = f"{prompt}\n\n(Previous Sketch{idx} was rejected — try a visually different approach for Sketch{idx}.)"
    res = generate(preview_dir, alt_prompt,
                   manim_cmd=manim_cmd, session_id=_LATEST_SESSION['id'])
    if res.get('status') != 'ok':
        return res
    card = res['cards'][idx] if idx < len(res.get('cards', [])) else None
    return {'status': 'ok', 'card': card}


def fork(idx: int, dest_dir: str, base_name: Optional[str] = None) -> dict:
    """Copy the generated sketches.py into the user's project directory and
    return the new file path."""
    if _LATEST_SESSION['id'] is None:
        return {'status': 'error', 'message': 'no active sketch session'}
    src = os.path.join(_LATEST_SESSION['base_dir'], 'sketches.py')
    if not os.path.isfile(src):
        return {'status': 'error', 'message': 'sketch source missing'}
    if not dest_dir or not os.path.isdir(dest_dir):
        return {'status': 'error', 'message': 'no destination directory'}
    slug = re.sub(r'[^\w]+', '_',
                  (base_name or _LATEST_SESSION['prompt'] or 'sketch'))[:40].strip('_').lower()
    letter = chr(ord('a') + idx) if 0 <= idx < 26 else str(idx)
    target = os.path.join(dest_dir, f'{slug}_{letter}.py')
    # Extract only the requested Sketch class plus imports into the target.
    try:
        with open(src, 'r', encoding='utf-8') as f:
            source = f.read()
    except OSError as e:
        return {'status': 'error', 'message': str(e)}

    # Find everything up to the first `class Sketch0` — that's the imports
    # header we keep verbatim.
    first_class = source.find('class Sketch0')
    header = source[:first_class] if first_class > 0 else 'from manim import *\n\n'

    # Extract the requested sketch class by walking forward to the next
    # `class ` at indentation 0.
    import_end = header
    start = source.find(f'class Sketch{idx}')
    if start < 0:
        return {'status': 'error', 'message': f'Sketch{idx} not found in source'}
    next_class = re.search(r'\nclass Sketch\d', source[start + 1:])
    end = start + 1 + next_class.start() if next_class else len(source)
    body = source[start:end]
    # Rename the class to something nicer.
    body = body.replace(f'class Sketch{idx}', f'class {slug.title().replace("_", "")}', 1)
    try:
        with open(target, 'w', encoding='utf-8') as f:
            f.write(import_end + body)
    except OSError as e:
        return {'status': 'error', 'message': str(e)}
    return {'status': 'ok', 'file': target}


def latest_session() -> Optional[str]:
    return _LATEST_SESSION['id']
