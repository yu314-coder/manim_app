"""
Narration — Local TTS using Kokoro ONNX (built-in feature).

Adds narrate("...") call support to Manim code.
Parses these comments, generates speech with Kokoro TTS,
and merges the audio with the rendered video via ffmpeg.

Engine packages (kokoro-onnx, soundfile, onnxruntime) are installed
automatically via the global missing-packages check at startup.
"""
import os
import sys
import subprocess
import re
import json
import time
import threading
import shutil

# ── Module-level refs injected by init_narration() ──
_preview_dir = None
_get_clean_env = None
_venv_dir = None
_models_dir = None


def init_narration(preview_dir, get_clean_env_func, venv_dir, user_data_dir):
    """Initialise module-level dependencies (called once from app.py)."""
    global _preview_dir, _get_clean_env, _venv_dir, _models_dir
    _preview_dir = preview_dir
    _get_clean_env = get_clean_env_func
    _venv_dir = venv_dir
    _models_dir = os.path.join(user_data_dir, 'narration', 'models')
    os.makedirs(_models_dir, exist_ok=True)


def _get_venv_python():
    """Return the venv Python executable path."""
    if os.name == 'nt':
        python = os.path.join(_venv_dir, 'Scripts', 'python.exe')
    else:
        python = os.path.join(_venv_dir, 'bin', 'python')
    return python if os.path.exists(python) else None


# ── Helper script executed inside the venv to generate all TTS segments ──
# Loads the Kokoro model once, processes every segment, streams progress to stdout.
_TTS_GENERATE_SCRIPT = r'''
import sys, json, os, urllib.request

data = json.loads(sys.stdin.read())
segments   = data["segments"]
voice      = data.get("voice", "af_heart")
speed      = data.get("speed", 1.0)
output_dir = data["output_dir"]
models_dir = data.get("models_dir", "")

# ── Load Kokoro ONNX ──
try:
    import kokoro_onnx, soundfile as sf, numpy as np
except ImportError as e:
    print(json.dumps({"fatal": f"Missing package: {e}"}), flush=True)
    sys.exit(1)

model_path  = os.path.join(models_dir, "kokoro-v1.0.onnx")
voices_path = os.path.join(models_dir, "voices-v1.0.bin")

# Auto-download model files if missing
_BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
for fname, fpath in [("kokoro-v1.0.onnx", model_path), ("voices-v1.0.bin", voices_path)]:
    if not os.path.isfile(fpath):
        url = f"{_BASE_URL}/{fname}"
        print(json.dumps({"info": f"Downloading {fname}..."}), flush=True)
        try:
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            urllib.request.urlretrieve(url, fpath)
            size_mb = os.path.getsize(fpath) / (1024 * 1024)
            print(json.dumps({"info": f"Downloaded {fname} ({size_mb:.1f} MB)"}), flush=True)
        except Exception as dl_err:
            print(json.dumps({"fatal": f"Failed to download {fname}: {dl_err}"}), flush=True)
            sys.exit(1)

try:
    kokoro = kokoro_onnx.Kokoro(model_path, voices_path)
except Exception as load_err:
    print(json.dumps({"fatal": f"Cannot load Kokoro model: {load_err}"}), flush=True)
    sys.exit(1)

results = []
for i, seg in enumerate(segments):
    audio_path = os.path.join(output_dir, f"segment_{i:03d}.wav")
    try:
        samples, sr = kokoro.create(seg["text"], voice=voice, speed=speed)
        sf.write(audio_path, samples, sr)
        duration = round(len(samples) / sr, 3)
        entry = {"index": i, "audio_path": audio_path, "duration": duration, "status": "ok"}
    except Exception as exc:
        entry = {"index": i, "status": "error", "message": str(exc)}
    results.append(entry)
    print(json.dumps({"progress": i + 1, "total": len(segments), "segment": entry}), flush=True)

print(json.dumps({"done": True, "results": results}), flush=True)
'''


class NarrationMixin:
    """Mixin providing narration / TTS pywebview API methods.

    ManimAPI inherits this so every method is callable from JS
    via ``pywebview.api.<method>()``.
    """

    # ── Generation state ──
    _narr_proc = None
    _narr_generating = False
    _narr_progress = 0
    _narr_total = 0
    _narr_error = None
    _narr_output_buf = ''
    _narr_info = ''            # current info/download status message
    _narr_audio_dir = None
    _narr_segments = []       # [{index, audio_path, duration}, ...]
    _narr_texts = []          # original text for each segment (for subtitles)
    _narr_final_audio = None  # path to concatenated WAV
    _narr_subtitles_vtt = None  # path to generated WebVTT file
    _narr_done = False

    # ------------------------------------------------------------------ #
    #  Engine check (Kokoro)
    # ------------------------------------------------------------------ #

    def check_narration_engine(self):
        """Check if Kokoro TTS engine is installed in the app venv."""
        python = _get_venv_python()
        if not python:
            return {'installed': False, 'message': 'Python venv not found'}
        try:
            result = subprocess.run(
                [python, '-c', 'import kokoro_onnx; import soundfile; print("ok")'],
                capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=15, env=_get_clean_env()
            )
            if result.returncode == 0 and 'ok' in result.stdout:
                return {'installed': True}
            msg = (result.stderr or result.stdout or '').strip()[:300]
            return {'installed': False, 'message': msg or 'kokoro-onnx not found'}
        except Exception as e:
            return {'installed': False, 'message': str(e)}

    # ------------------------------------------------------------------ #
    #  Voices
    # ------------------------------------------------------------------ #

    def get_narration_voices(self):
        """Return available Kokoro TTS voices."""
        return {
            'voices': [
                {'id': 'af_heart',   'name': 'Heart (Female, Warm)'},
                {'id': 'af_bella',   'name': 'Bella (Female, Clear)'},
                {'id': 'af_nicole',  'name': 'Nicole (Female, Pro)'},
                {'id': 'af_sarah',   'name': 'Sarah (Female, Soft)'},
                {'id': 'af_sky',     'name': 'Sky (Female, Bright)'},
                {'id': 'am_adam',    'name': 'Adam (Male, Deep)'},
                {'id': 'am_michael', 'name': 'Michael (Male, Natural)'},
                {'id': 'bf_emma',    'name': 'Emma (British Female)'},
                {'id': 'bm_george',  'name': 'George (British Male)'},
            ]
        }

    # ------------------------------------------------------------------ #
    #  Parse narrate() calls
    # ------------------------------------------------------------------ #

    def parse_narrate_comments(self, code):
        """Parse ``narrate("...")`` calls from Manim code.

        Returns ``{segments: [{line, text}], count: int}``.
        """
        pattern = r'@?narrate\(\s*["\'](.+?)["\']\s*\)'
        results = []
        for i, line in enumerate(code.split('\n'), 1):
            m = re.search(pattern, line)
            if m:
                results.append({'line': i, 'text': m.group(1)})
        return {'status': 'success', 'segments': results, 'count': len(results)}

    # ------------------------------------------------------------------ #
    #  Generate TTS audio
    # ------------------------------------------------------------------ #

    def generate_narration(self, code, voice='af_heart', speed=1.0):
        """Generate TTS audio for all ``narrate("...")`` calls in *code*.

        Spawns a subprocess in the app venv that loads Kokoro once and
        processes every segment.  Poll with ``narration_poll()``.
        """
        if NarrationMixin._narr_generating:
            return {'status': 'error', 'message': 'Already generating'}

        # Parse narration comments
        parsed = self.parse_narrate_comments(code)
        segments = parsed['segments']
        if not segments:
            return {'status': 'error',
                    'message': 'No narrate() calls found in code'}

        # Check engine
        engine = self.check_narration_engine()
        if not engine.get('installed'):
            return {'status': 'error',
                    'message': 'Kokoro TTS not installed. Restart the app to install missing packages.'}

        python = _get_venv_python()
        if not python:
            return {'status': 'error', 'message': 'Python venv not found'}

        # Setup output dir
        ts = int(time.time())
        audio_dir = os.path.join(_preview_dir, f'narration_{ts}')
        os.makedirs(audio_dir, exist_ok=True)

        # Reset state
        NarrationMixin._narr_generating = True
        NarrationMixin._narr_progress = 0
        NarrationMixin._narr_total = len(segments)
        NarrationMixin._narr_error = None
        NarrationMixin._narr_info = ''
        NarrationMixin._narr_output_buf = ''
        NarrationMixin._narr_audio_dir = audio_dir
        NarrationMixin._narr_segments = []
        NarrationMixin._narr_texts = [s['text'] for s in segments]
        NarrationMixin._narr_final_audio = None
        NarrationMixin._narr_done = False

        # Write the helper script to the audio dir
        script_path = os.path.join(audio_dir, '_generate.py')
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(_TTS_GENERATE_SCRIPT)

        # Build input JSON
        input_data = json.dumps({
            'segments': segments,
            'voice': voice,
            'speed': speed,
            'output_dir': audio_dir,
            'models_dir': _models_dir
        })

        print(f"[NARRATION] Generating {len(segments)} segments, voice={voice}, speed={speed}")

        try:
            NarrationMixin._narr_proc = subprocess.Popen(
                [python, script_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace',
                bufsize=1, env=_get_clean_env(), cwd=audio_dir
            )
            # Feed input JSON via stdin
            try:
                NarrationMixin._narr_proc.stdin.write(input_data)
                NarrationMixin._narr_proc.stdin.close()
            except Exception as e:
                print(f"[NARRATION] stdin write error: {e}")

            def _reader():
                proc = NarrationMixin._narr_proc
                try:
                    for line in proc.stdout:
                        NarrationMixin._narr_output_buf += line
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if 'fatal' in msg:
                            NarrationMixin._narr_error = msg['fatal']
                            break
                        if 'info' in msg:
                            NarrationMixin._narr_info = msg['info']
                            print(f"[NARRATION] {msg['info']}")
                            continue
                        if 'progress' in msg:
                            NarrationMixin._narr_progress = msg['progress']
                            seg = msg.get('segment')
                            if seg and seg.get('status') == 'ok':
                                NarrationMixin._narr_segments.append(seg)
                        if msg.get('done'):
                            break
                except Exception as e:
                    NarrationMixin._narr_error = str(e)

                proc.wait()
                NarrationMixin._narr_done = True
                NarrationMixin._narr_generating = False

                # Concatenate segment WAVs into one file
                if NarrationMixin._narr_segments and not NarrationMixin._narr_error:
                    try:
                        _concatenate_audio(
                            NarrationMixin._narr_segments, audio_dir)
                    except Exception as e:
                        print(f"[NARRATION] Concat error: {e}")

                    # Generate WebVTT subtitles
                    try:
                        _generate_subtitles_vtt(
                            NarrationMixin._narr_segments,
                            NarrationMixin._narr_texts,
                            audio_dir)
                    except Exception as e:
                        print(f"[NARRATION] VTT error: {e}")

                print(f"[NARRATION] Done. {len(NarrationMixin._narr_segments)} segments, "
                      f"error={NarrationMixin._narr_error}")

            threading.Thread(target=_reader, daemon=True).start()
            return {'status': 'started', 'total': len(segments),
                    'message': 'Generating narration...'}

        except Exception as e:
            NarrationMixin._narr_generating = False
            print(f"[NARRATION ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def narration_poll(self):
        """Poll narration generation progress."""
        if NarrationMixin._narr_proc is None:
            return {'status': 'idle', 'done': True}

        if NarrationMixin._narr_done:
            if NarrationMixin._narr_error:
                return {
                    'status': 'error',
                    'done': True,
                    'message': NarrationMixin._narr_error,
                    'progress': NarrationMixin._narr_progress,
                    'total': NarrationMixin._narr_total
                }
            segments = NarrationMixin._narr_segments
            total_dur = sum(s.get('duration', 0) for s in segments)
            return {
                'status': 'success',
                'done': True,
                'progress': NarrationMixin._narr_total,
                'total': NarrationMixin._narr_total,
                'segments': segments,
                'total_duration': round(total_dur, 2),
                'final_audio': NarrationMixin._narr_final_audio,
                'message': f'Done! {len(segments)} segments, {total_dur:.1f}s total'
            }

        # Still running
        info = NarrationMixin._narr_info
        if info:
            msg = info
        elif NarrationMixin._narr_progress > 0:
            msg = f'Generating... ({NarrationMixin._narr_progress}/{NarrationMixin._narr_total})'
        else:
            msg = 'Loading Kokoro model...'
        return {
            'status': 'generating',
            'done': False,
            'progress': NarrationMixin._narr_progress,
            'total': NarrationMixin._narr_total,
            'message': msg
        }

    def narration_cancel(self):
        """Cancel a running narration generation."""
        if NarrationMixin._narr_proc and not NarrationMixin._narr_done:
            try:
                NarrationMixin._narr_proc.kill()
                print("[NARRATION] Cancelled by user")
            except Exception:
                pass
        NarrationMixin._narr_proc = None
        NarrationMixin._narr_generating = False
        NarrationMixin._narr_done = False
        NarrationMixin._narr_progress = 0
        NarrationMixin._narr_output_buf = ''
        NarrationMixin._narr_error = None
        NarrationMixin._narr_info = ''
        # Clean up audio dir
        audio_dir = NarrationMixin._narr_audio_dir
        if audio_dir and os.path.exists(audio_dir):
            try:
                shutil.rmtree(audio_dir, ignore_errors=True)
            except Exception:
                pass
        NarrationMixin._narr_audio_dir = None
        NarrationMixin._narr_segments = []
        NarrationMixin._narr_texts = []
        NarrationMixin._narr_final_audio = None
        NarrationMixin._narr_subtitles_vtt = None
        return {'status': 'cancelled'}

    # ------------------------------------------------------------------ #
    #  Merge audio + video
    # ------------------------------------------------------------------ #

    def merge_narration_video(self, video_path, output_path=''):
        """Merge the generated narration audio with a rendered video.

        Uses ffmpeg (already required by Manim).
        Returns the path to the narrated video.
        """
        final_audio = NarrationMixin._narr_final_audio
        if not final_audio or not os.path.isfile(final_audio):
            return {'status': 'error',
                    'message': 'No narration audio. Generate narration first.'}
        if not video_path or not os.path.isfile(video_path):
            return {'status': 'error',
                    'message': f'Video file not found: {video_path}'}

        if not output_path:
            base, ext = os.path.splitext(video_path)
            output_path = f"{base}_narrated{ext}"

        # ffmpeg: overlay audio on video, keep video codec, encode audio as AAC
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', final_audio,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_path
        ]
        print(f"[NARRATION] Merging: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=120, env=_get_clean_env()
            )
            if result.returncode == 0 and os.path.isfile(output_path):
                size_kb = os.path.getsize(output_path) / 1024
                print(f"[NARRATION] Merged: {output_path} ({size_kb:.0f} KB)")
                return {
                    'status': 'success',
                    'output_path': output_path,
                    'message': f'Narrated video saved ({size_kb:.0f} KB)'
                }
            err = (result.stderr or result.stdout or '')[:500]
            return {'status': 'error', 'message': f'ffmpeg failed: {err}'}
        except FileNotFoundError:
            return {'status': 'error',
                    'message': 'ffmpeg not found. It is required by Manim — check your PATH.'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def get_narration_status(self):
        """Return current narration state summary (for UI sync on panel open)."""
        return {
            'generating': NarrationMixin._narr_generating,
            'progress': NarrationMixin._narr_progress,
            'total': NarrationMixin._narr_total,
            'done': NarrationMixin._narr_done,
            'error': NarrationMixin._narr_error,
            'segment_count': len(NarrationMixin._narr_segments),
            'final_audio': NarrationMixin._narr_final_audio,
            'total_duration': round(
                sum(s.get('duration', 0) for s in NarrationMixin._narr_segments), 2)
        }

    def get_narration_subtitles(self):
        """Return WebVTT subtitle content for the current narration."""
        vtt_path = NarrationMixin._narr_subtitles_vtt
        if not vtt_path or not os.path.isfile(vtt_path):
            return {'status': 'error', 'message': 'No subtitles available'}
        try:
            with open(vtt_path, 'r', encoding='utf-8') as f:
                return {'status': 'success', 'vtt': f.read()}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


# ── Helper: concatenate segment WAVs into one file with gaps ──

def _concatenate_audio(segments, audio_dir, gap_seconds=0.5):
    """Concatenate segment WAV files with silence gaps between them.

    Uses ffmpeg concat demuxer (avoids needing numpy/soundfile in the
    main process).  Result is saved as ``narration_full.wav``.
    """
    # Build ffmpeg concat list
    list_path = os.path.join(audio_dir, 'concat_list.txt')
    silence_path = os.path.join(audio_dir, 'silence.wav')
    output_path = os.path.join(audio_dir, 'narration_full.wav')

    # Generate a short silence file
    subprocess.run([
        'ffmpeg', '-y', '-f', 'lavfi',
        '-i', f'anullsrc=r=24000:cl=mono:d={gap_seconds}',
        silence_path
    ], capture_output=True, timeout=10)

    with open(list_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments):
            ap = seg.get('audio_path', '')
            if ap and os.path.isfile(ap):
                f.write(f"file '{ap}'\n")
                # Add silence gap after each segment except the last
                if i < len(segments) - 1 and os.path.isfile(silence_path):
                    f.write(f"file '{silence_path}'\n")

    result = subprocess.run([
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
        '-i', list_path, '-c', 'copy', output_path
    ], capture_output=True, text=True, encoding='utf-8',
       errors='replace', timeout=60)

    if result.returncode == 0 and os.path.isfile(output_path):
        NarrationMixin._narr_final_audio = output_path
        print(f"[NARRATION] Concatenated audio: {output_path}")
    else:
        print(f"[NARRATION] Concat ffmpeg failed: {result.stderr[:300]}")


def _generate_subtitles_vtt(segments, texts, audio_dir, gap_seconds=0.5):
    """Generate a WebVTT subtitle file from narration segments.

    Timing matches the concatenated audio (segment durations + silence gaps).
    """
    vtt_path = os.path.join(audio_dir, 'subtitles.vtt')
    lines = ['WEBVTT', '']

    current_time = 0.0
    for i, seg in enumerate(segments):
        duration = seg.get('duration', 0)
        if duration <= 0:
            continue
        text = texts[i] if i < len(texts) else ''
        if not text:
            continue

        start = current_time
        end = current_time + duration

        lines.append(str(i + 1))
        lines.append(f'{_format_vtt_time(start)} --> {_format_vtt_time(end)}')
        lines.append(text)
        lines.append('')

        # Advance by segment duration + gap (except after last segment)
        current_time = end
        if i < len(segments) - 1:
            current_time += gap_seconds

    with open(vtt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    NarrationMixin._narr_subtitles_vtt = vtt_path
    print(f"[NARRATION] Subtitles: {vtt_path}")


def _format_vtt_time(seconds):
    """Format seconds as HH:MM:SS.mmm for WebVTT."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f'{hours:02d}:{minutes:02d}:{secs:06.3f}'
