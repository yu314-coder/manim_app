"""Visual Diff (F-03)
=====================

Hash every frame of every render; compare successive renders; flag drift.

Layout:

    <user_data>/.manim_studio/renders/
        <render_id>/
            meta.json      # {video_path, created_at, scene_file, status, baseline_id}
            frames.json    # {"hashes": ["<hex64>", ...], "fps": 30}
            thumbs/        # low-res preview frames for the A/B scrubber

Public surface (functions — no class state):

    record_render(render_id, video_path, scene_file) -> dict
    diff_against_baseline(render_id, baseline_id=None) -> dict
        returns {drift_per_frame, flagged, flagged_count, mean_drift,
                 total_frames, threshold, auto_accepted}
    list_renders(limit=40) -> list[dict]
    accept(render_id) -> dict       # promotes render to current baseline
    revert(render_id) -> dict       # marks render as rejected
    block(render_id) -> dict        # marks render as permanently blocked
    get_frame_thumb(render_id, frame_idx) -> absolute path or None

pHash implementation is pure-Python (no imagehash dep) — uses OpenCV if
available (cv2 is already in the narration pipeline), else falls back to
PIL. Both are commonly installed with Manim.
"""

from __future__ import annotations

import json
import os
import struct
import time
import uuid
from typing import Optional


_DIFF_THRESHOLD = 0.01  # Fraction of 64-bit pHash that must differ to flag.
_MAX_RENDERS = 40       # Prune oldest render records beyond this count.
_THUMB_WIDTH = 320      # Thumbnail width (px) for the A/B scrubber.


def _root() -> str:
    base = os.path.join(os.path.expanduser('~'), '.manim_studio', 'renders')
    os.makedirs(base, exist_ok=True)
    return base


def _record_dir(render_id: str) -> str:
    d = os.path.join(_root(), render_id)
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, 'thumbs'), exist_ok=True)
    return d


def _current_baseline_path() -> str:
    return os.path.join(_root(), 'baseline.txt')


def _get_current_baseline() -> Optional[str]:
    p = _current_baseline_path()
    if not os.path.isfile(p):
        return None
    try:
        with open(p, 'r') as f:
            return f.read().strip() or None
    except OSError:
        return None


def _set_current_baseline(render_id: str) -> None:
    try:
        with open(_current_baseline_path(), 'w') as f:
            f.write(render_id)
    except OSError as e:
        print(f"[VISUAL DIFF] baseline write failed: {e}")


# ---------- pHash ----------

def _hash_frame_np(img_gray_small):
    """64-bit perceptual hash from an 8x8 DCT-free grayscale crop (ahash
    variant — faster than DCT pHash and plenty accurate for UI diffs).
    Accepts a numpy 2D array of shape (8, 8) in uint8.
    Returns hex string."""
    mean = img_gray_small.mean()
    bits = (img_gray_small >= mean).flatten()
    val = 0
    for b in bits:
        val = (val << 1) | int(bool(b))
    return f'{val:016x}'


def _try_hash_via_cv2(video_path: str):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    hashes = []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
            hashes.append(_hash_frame_np(small))
    finally:
        cap.release()
    return {'hashes': hashes, 'fps': fps}


def _try_hash_via_pil(video_path: str):
    """Fallback: decode via imageio-ffmpeg if cv2 is missing. Slow but works."""
    try:
        import imageio.v3 as iio
        from PIL import Image
        import numpy as np
    except ImportError:
        return None
    try:
        hashes = []
        meta = iio.immeta(video_path, exclude_applied=False)
        fps = meta.get('fps', 30.0) if isinstance(meta, dict) else 30.0
        for frame in iio.imiter(video_path):
            img = Image.fromarray(frame).convert('L').resize((8, 8))
            arr = np.asarray(img, dtype=np.float32)
            hashes.append(_hash_frame_np(arr))
        return {'hashes': hashes, 'fps': fps}
    except Exception as e:
        print(f"[VISUAL DIFF] PIL fallback failed: {e}")
        return None


def _extract_thumbs_cv2(video_path: str, out_dir: str, every_n: int = 1) -> int:
    try:
        import cv2
    except ImportError:
        return 0
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0
    count = 0
    idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % every_n == 0:
                h, w = frame.shape[:2]
                if w > _THUMB_WIDTH:
                    new_h = int(h * _THUMB_WIDTH / w)
                    frame = cv2.resize(frame, (_THUMB_WIDTH, new_h))
                out_path = os.path.join(out_dir, f'{idx:05d}.jpg')
                cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                count += 1
            idx += 1
    finally:
        cap.release()
    return count


# ---------- Hamming diff ----------

def _hamming(a_hex: str, b_hex: str) -> int:
    try:
        return bin(int(a_hex, 16) ^ int(b_hex, 16)).count('1')
    except ValueError:
        return 64


def _drift_ratio(a_hex: str, b_hex: str) -> float:
    return _hamming(a_hex, b_hex) / 64.0


# ---------- Public API ----------

def record_render(render_id: str, video_path: str,
                  scene_file: str = '') -> dict:
    """Hash all frames of a completed render and persist metadata. Returns
    {ok, frames, path}. Safe to call in a background thread after a render
    finishes."""
    if not render_id:
        render_id = uuid.uuid4().hex[:12]
    d = _record_dir(render_id)

    hash_result = _try_hash_via_cv2(video_path) or _try_hash_via_pil(video_path)
    if not hash_result:
        return {'ok': False, 'error': 'No frame decoder available (install opencv-python or imageio)'}

    try:
        with open(os.path.join(d, 'frames.json'), 'w') as f:
            json.dump(hash_result, f)
    except OSError as e:
        return {'ok': False, 'error': f'frames.json write failed: {e}'}

    meta = {
        'render_id': render_id,
        'video_path': os.path.abspath(video_path),
        'scene_file': scene_file or '',
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'status': 'pending',
        'frame_count': len(hash_result['hashes']),
    }
    try:
        with open(os.path.join(d, 'meta.json'), 'w') as f:
            json.dump(meta, f, indent=2)
    except OSError as e:
        print(f"[VISUAL DIFF] meta write failed: {e}")

    # Extract thumbnails lazily, sampling up to 60 frames to keep disk low.
    try:
        total = len(hash_result['hashes'])
        step = max(1, total // 60)
        _extract_thumbs_cv2(video_path, os.path.join(d, 'thumbs'), every_n=step)
    except Exception as e:
        print(f"[VISUAL DIFF] thumb extraction failed: {e}")

    _prune_old_records()
    return {'ok': True, 'render_id': render_id, 'frames': len(hash_result['hashes'])}


def diff_against_baseline(render_id: str,
                          baseline_id: Optional[str] = None,
                          threshold: float = _DIFF_THRESHOLD) -> dict:
    """Compare this render's pHashes against the baseline. Returns drift
    array, list of flagged frame indices, and auto-promote decision."""
    if baseline_id is None:
        baseline_id = _get_current_baseline()

    cur_path = os.path.join(_root(), render_id, 'frames.json')
    if not os.path.isfile(cur_path):
        return {'ok': False, 'error': 'render frames missing'}
    try:
        with open(cur_path, 'r') as f:
            cur = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {'ok': False, 'error': f'frames read failed: {e}'}

    cur_hashes = cur.get('hashes', [])

    if not baseline_id or baseline_id == render_id:
        # First render — nothing to compare against. Auto-accept.
        return {
            'ok': True,
            'baseline_id': None,
            'drift_per_frame': [0.0] * len(cur_hashes),
            'flagged': [],
            'flagged_count': 0,
            'mean_drift': 0.0,
            'total_frames': len(cur_hashes),
            'threshold': threshold,
            'auto_accepted': True,
            'reason': 'first_render',
        }

    base_path = os.path.join(_root(), baseline_id, 'frames.json')
    if not os.path.isfile(base_path):
        return {
            'ok': True,
            'baseline_id': None,
            'drift_per_frame': [0.0] * len(cur_hashes),
            'flagged': [],
            'flagged_count': 0,
            'mean_drift': 0.0,
            'total_frames': len(cur_hashes),
            'threshold': threshold,
            'auto_accepted': True,
            'reason': 'baseline_missing',
        }
    try:
        with open(base_path, 'r') as f:
            base = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {'ok': False, 'error': 'baseline read failed'}

    base_hashes = base.get('hashes', [])
    n = max(len(cur_hashes), len(base_hashes))
    drift = []
    flagged = []
    for i in range(n):
        a = cur_hashes[i] if i < len(cur_hashes) else '0' * 16
        b = base_hashes[i] if i < len(base_hashes) else '0' * 16
        d = _drift_ratio(a, b)
        drift.append(round(d, 4))
        if d > threshold:
            flagged.append(i)

    mean_drift = round(sum(drift) / n, 4) if n else 0.0
    auto_accepted = (mean_drift <= threshold) and (not flagged)

    return {
        'ok': True,
        'baseline_id': baseline_id,
        'drift_per_frame': drift,
        'flagged': flagged,
        'flagged_count': len(flagged),
        'mean_drift': mean_drift,
        'total_frames': n,
        'threshold': threshold,
        'auto_accepted': auto_accepted,
    }


def list_renders(limit: int = 40) -> list:
    """Return recent renders newest-first with their current status."""
    root = _root()
    entries = []
    try:
        for name in os.listdir(root):
            d = os.path.join(root, name)
            meta_p = os.path.join(d, 'meta.json')
            if not os.path.isfile(meta_p):
                continue
            try:
                with open(meta_p, 'r') as f:
                    entries.append(json.load(f))
            except (OSError, json.JSONDecodeError):
                continue
    except OSError:
        return []
    entries.sort(key=lambda m: m.get('created_at', ''), reverse=True)
    current_baseline = _get_current_baseline()
    for e in entries:
        e['is_baseline'] = (e.get('render_id') == current_baseline)
    return entries[:limit]


def _set_status(render_id: str, status: str) -> dict:
    meta_p = os.path.join(_root(), render_id, 'meta.json')
    if not os.path.isfile(meta_p):
        return {'ok': False, 'error': 'render not found'}
    try:
        with open(meta_p, 'r') as f:
            meta = json.load(f)
        meta['status'] = status
        meta['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        with open(meta_p, 'w') as f:
            json.dump(meta, f, indent=2)
        return {'ok': True, 'status': status}
    except (OSError, json.JSONDecodeError) as e:
        return {'ok': False, 'error': str(e)}


def accept(render_id: str) -> dict:
    """Mark render as accepted and promote it to the current baseline."""
    res = _set_status(render_id, 'accepted')
    if res.get('ok'):
        _set_current_baseline(render_id)
    return res


def revert(render_id: str) -> dict:
    return _set_status(render_id, 'reverted')


def block(render_id: str) -> dict:
    return _set_status(render_id, 'blocked')


def get_frame_thumb(render_id: str, frame_idx: int) -> Optional[str]:
    """Return absolute path to the nearest cached thumb for this frame index."""
    d = os.path.join(_root(), render_id, 'thumbs')
    if not os.path.isdir(d):
        return None
    try:
        files = sorted(os.listdir(d))
    except OSError:
        return None
    # Pick the file with the closest frame index encoded in its name.
    best = None
    best_delta = 10 ** 9
    for f in files:
        if not f.endswith('.jpg'):
            continue
        try:
            idx = int(f.split('.')[0])
        except ValueError:
            continue
        delta = abs(idx - frame_idx)
        if delta < best_delta:
            best_delta = delta
            best = os.path.join(d, f)
    return best


def _prune_old_records() -> None:
    """Keep only the most recent MAX_RENDERS records on disk."""
    root = _root()
    try:
        items = []
        for name in os.listdir(root):
            d = os.path.join(root, name)
            if not os.path.isdir(d):
                continue
            meta_p = os.path.join(d, 'meta.json')
            if not os.path.isfile(meta_p):
                continue
            try:
                items.append((os.path.getmtime(meta_p), name))
            except OSError:
                continue
        items.sort(reverse=True)
        baseline = _get_current_baseline()
        for _, name in items[_MAX_RENDERS:]:
            if name == baseline:
                continue
            try:
                _rmtree(os.path.join(root, name))
            except Exception:
                pass
    except OSError:
        pass


def _rmtree(path: str) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)
