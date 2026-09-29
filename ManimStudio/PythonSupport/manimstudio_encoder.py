"""Keeps a render's video going when iOS takes the hardware encoder away.

ManimStudio encodes with VideoToolbox, Apple's hardware H.264/HEVC encoder.
iOS invalidates a hardware encoding session whenever the app moves between
the foreground and the background; ffmpeg's own videotoolboxenc.c says so
("On iOS, the VT session is invalidated when the APP switches from
foreground to background and vice versa"). The frames the session held at
that moment come back as errors, ffmpeg's encoder stays failed from then on,
and the render used to stop with "the video encoder stopped". Whether a
background app may open a new hardware session at all isn't documented.

With this module, a failed hardware encode splits the animation's clip
instead of ending the render:

* the frames already written stay in the clip, which is closed as usual;
* the rest of the animation goes to a new clip: a fresh hardware encoder
  where iOS allows one, the software encoder where it doesn't;
* the frames the failed encoder swallowed are sent again, so the video keeps
  its length and stays in step with any sound.

When the scene's clips are combined and no longer share one encoding, they
are re-encoded into a single file first: with the hardware encoder when it
is available, in software (mpeg4) when it isn't. MPEG-4 Part 2 stops at
8190 pixels, and nothing Apple devices play is encoded in software above
that, so a bigger render waits for the hardware encoder, which comes back
when the app returns to the foreground.

A render whose encoder never fails is untouched: nothing here changes a clip
until an encode has failed, and combining without a split is manim's own.

ManimStudio's code, installed by the render wrapper in PythonRuntime.swift.
python-ios-lib's manim is left as it is.
"""

import os
import time

__all__ = ["install", "software_codec"]

#: The encoders a failure is recovered from. Everything else fails as before.
HARDWARE = ("h264_videotoolbox", "hevc_videotoolbox")

#: MPEG-4 Part 2 stores width and height in 13 bits; MPEG-2 in 14. Even
#: sizes only, as yuv420p needs.
MPEG4_MAX = 8190
MPEG2_MAX = 16382

#: The software encoders run at a fixed quantiser rather than a bitrate:
#: -q:v 2 in ffmpeg terms (global_quality = q * FF_QP2LAMBDA). That keeps
#: manim's flat colours and thin lines clean at any size, where a fixed
#: bitrate would starve 8K and waste bytes at 480p.
_QUALITY = str(2 * 118)

#: A clip may be split this often before its encoder failure is final.
MAX_SPLITS = 24

#: How long a render that needs the hardware encoder waits between tries.
WAIT_SECONDS = 2.0


def _log(message):
    print(f"[manim] {message}", flush=True)


def software_codec(width, height):
    """(encoder, options, pixel format, extension) for a software clip.

    mpeg4 is what the rest of the app already uses as its software encoder,
    and Photos takes it. MPEG-2 and JPEG frames are only ever intermediate:
    a clip in either is re-encoded before anyone sees it.
    """
    options = {"flags": "+qscale", "global_quality": _QUALITY}
    if width <= MPEG4_MAX and height <= MPEG4_MAX:
        return "mpeg4", options, "yuv420p", ".mp4"
    if width <= MPEG2_MAX and height <= MPEG2_MAX:
        return "mpeg2video", options, "yuv420p", ".mov"
    return "mjpeg", options, "yuvj420p", ".mov"


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _codec_name(stream):
    try:
        return stream.codec_context.name
    except Exception:
        return ""


class _Clip:
    """The clip being written: frames handed to its encoder and packets back.

    VideoToolbox returns a packet a frame or two after the frame went in, so
    `sent - muxed` is what a failed session took down with it.
    """

    __slots__ = ("sent", "muxed", "software")

    def __init__(self, software=False):
        self.sent = 0
        self.muxed = 0
        self.software = software


def install(SceneFileWriter, *, hardware_codec=None, on_phase=None,
            check_cancel=None, on_progress=None):
    """Patch SceneFileWriter so a failed hardware encode splits the clip.

    hardware_codec(width, height) -> (encoder, mp4 tag or None): the encoder
        a fresh hardware clip and the final re-encode use. Defaults to the
        encoder of the clip that failed, or H.264.
    on_phase(name): told "waiting" while a render waits for the hardware
        encoder, and "finishing" when it has it back.
    check_cancel(): raises to stop a render that is waiting.
    on_progress(frames): told how many frames a re-encode has written so
        far, every 30 — it writes no render frames, and can take minutes.
    """
    if getattr(SceneFileWriter, "_ms_encoder_installed", False):
        return
    SceneFileWriter._ms_encoder_installed = True

    import av
    from manim import config
    from manim.scene import scene_file_writer as _sfw

    def _rate():
        return _sfw.to_av_frame_rate(config.frame_rate)

    def _hardware_options():
        # What open_partial_movie_stream gives VideoToolbox: encode each
        # frame as it arrives, keyframe every second.
        return {"realtime": "1", "g": str(max(int(config.frame_rate), 1))}

    def _pick_hardware(width, height, fallback="h264_videotoolbox"):
        if hardware_codec is not None:
            try:
                codec, tag = hardware_codec(width, height)
                if codec in HARDWARE:
                    return codec, tag
            except Exception:
                pass
        return fallback, ("hvc1" if fallback.startswith("hevc") else None)

    def _open(path, codec, options, pix_fmt="yuv420p", tag=None):
        """An output container with one video stream, its encoder opened.

        avcodec_open2 normally runs at the first frame; opening it here makes
        an encoder that can't run fail now, while nothing depends on it.
        """
        container = av.open(path, mode="w")
        try:
            stream = container.add_stream(codec, rate=_rate(), options=options)
            stream.width = config.pixel_width
            stream.height = config.pixel_height
            stream.pix_fmt = pix_fmt
            if tag and codec.startswith("hevc"):
                # ffmpeg writes HEVC as hev1, which AVFoundation won't play.
                try:
                    stream.codec_tag = tag
                except Exception:
                    pass
            stream.codec_context.open()
        except BaseException:
            try:
                container.close()
            except Exception:
                pass
            _remove(path)
            raise
        return container, stream

    def _clip(writer):
        clip = getattr(writer, "_ms_clip", None)
        if clip is None:
            clip = writer._ms_clip = _Clip()
        return clip

    # ── Splitting a clip ─────────────────────────────────────────────

    def _split(writer, error):
        """Move the rest of the animation to a new clip after `error`.

        Returns how many frames the failed encoder swallowed, to send again,
        or None when the failure can't be recovered from here.
        """
        clip = _clip(writer)
        codec = _codec_name(writer.video_stream)
        if codec not in HARDWARE or clip.software:
            return None
        base = str(writer.partial_movie_file_path)
        segments = writer._ms_segments.setdefault(base, [])
        if len(segments) >= MAX_SPLITS:
            return None
        lost = max(clip.sent - clip.muxed, 0)
        reason = f"{type(error).__name__}: {error}"
        # What the failed encoder muxed is a valid clip once closed. Don't
        # flush it: a failed session only returns the error again.
        try:
            writer.video_container.close()
        except Exception:
            pass
        # PyAV creates the file with its first packet, so an encoder that
        # failed on its first frame leaves none, and manim touches every
        # clip path after combining. An empty file stands in; combining
        # skips it.
        if not os.path.exists(base):
            try:
                open(base, "ab").close()
            except OSError:
                pass

        stem, ext = os.path.splitext(base)
        width, height = config.pixel_width, config.pixel_height
        animation = getattr(getattr(writer, "renderer", None), "num_plays", "?")
        opened = None
        if clip.sent:
            # This session worked until now, so it was most likely
            # invalidated by a switch between foreground and background. A
            # new one works wherever iOS allows hardware encoding.
            path = f"{stem}.ms{len(segments) + 1}{ext}"
            try:
                opened = _open(path, codec, _hardware_options(),
                               tag=_pick_hardware(width, height, codec)[1])
                software = False
                _log(f"the hardware encoder stopped during animation "
                     f"{animation} ({reason}); continuing in a new clip")
            except Exception as retry_error:
                reason = f"{type(retry_error).__name__}: {retry_error}"
        if opened is None:
            sw_codec, options, pix_fmt, sw_ext = software_codec(width, height)
            path = f"{stem}.ms{len(segments) + 1}{sw_ext}"
            try:
                opened = _open(path, sw_codec, options, pix_fmt)
            except Exception as sw_error:
                _log(f"the software encoder couldn't take over "
                     f"({type(sw_error).__name__}: {sw_error})")
                return None
            software = True
            _log(f"hardware video encoding isn't available for animation "
                 f"{animation} ({reason}) — iOS doesn't always allow it "
                 f"while ManimStudio is in the background. Continuing with "
                 f"the software encoder ({sw_codec}).")
        writer.video_container, writer.video_stream = opened
        segments.append(path)
        writer._ms_clip = _Clip(software=software)
        return lost

    _orig_open = SceneFileWriter.open_partial_movie_stream

    def open_partial_movie_stream(self, *args, **kwargs):
        if not hasattr(self, "_ms_segments"):
            # Clip path -> the clips its animation continued in, in order.
            self._ms_segments = {}
        self._ms_clip = _Clip()
        return _orig_open(self, *args, **kwargs)

    def encode_and_write_frame(self, frame, num_frames):
        # manim's own loop, plus the split. A frame that failed is sent
        # again to the new clip, followed by one copy for each frame the
        # failed encoder swallowed, which holds the picture for those
        # frames rather than shortening the video.
        remaining = int(num_frames)
        while remaining > 0:
            clip = _clip(self)
            av_frame = av.VideoFrame.from_ndarray(frame, format="rgba")
            try:
                packets = self.video_stream.encode(av_frame)
                for packet in packets:
                    self.video_container.mux(packet)
            except Exception as error:
                lost = _split(self, error)
                if lost is None:
                    raise
                remaining += lost
                continue
            clip.sent += 1
            clip.muxed += len(packets)
            remaining -= 1

    SceneFileWriter.open_partial_movie_stream = open_partial_movie_stream
    SceneFileWriter.encode_and_write_frame = encode_and_write_frame

    # ── Combining ────────────────────────────────────────────────────

    def _has_video(path):
        try:
            if os.path.getsize(path) == 0:
                return False
            with av.open(path) as container:
                if not container.streams.video:
                    return False
                stream = container.streams.video[0]
                if stream.frames:
                    return True
                return any(packet.size for packet in container.demux(stream))
        except Exception:
            return False

    def _encoding(path):
        # Clips can be joined packet for packet only if they match here —
        # including the parameter sets, which the joined file takes from
        # its first clip.
        with av.open(path) as container:
            context = container.streams.video[0].codec_context
            return (context.name, context.width, context.height,
                    context.format.name if context.format else "",
                    bytes(context.extradata or b""))

    def _frames_of(paths):
        for path in paths:
            with av.open(path) as container:
                for frame in container.decode(video=0):
                    yield frame

    class _HardwareLost(Exception):
        pass

    def _write_joined(paths, out_path, codec, options, pix_fmt, tag):
        container, stream = _open(out_path, codec, options, pix_fmt, tag)
        hardware = codec in HARDWARE
        count = 0
        try:
            for frame in _frames_of(paths):
                frame.pts = count
                frame.time_base = stream.codec_context.time_base
                try:
                    for packet in stream.encode(frame):
                        container.mux(packet)
                except Exception as error:
                    if hardware:
                        raise _HardwareLost(error) from error
                    raise
                count += 1
                if on_progress is not None and count % 30 == 0:
                    on_progress(count)
            try:
                for packet in stream.encode():
                    container.mux(packet)
            except Exception as error:
                if hardware:
                    raise _HardwareLost(error) from error
                raise
        finally:
            container.close()
        return count

    def _join(writer, paths):
        """Re-encode clips in different encodings into one file."""
        width, height = config.pixel_width, config.pixel_height
        folder = os.path.dirname(str(paths[0]))
        waiting = False
        while True:
            codec, tag = _pick_hardware(width, height)
            out_path = os.path.join(folder, "ms_joined.mp4")
            try:
                count = _write_joined(paths, out_path, codec,
                                      _hardware_options(), "yuv420p", tag)
                if waiting and on_phase is not None:
                    on_phase("finishing")
                _log(f"joined {len(paths)} clips into one video "
                     f"({count} frames, {codec})")
                return out_path
            except Exception as error:
                _remove(out_path)
                hardware_error = f"{type(error).__name__}: {error}"
            sw_codec, options, pix_fmt, ext = software_codec(width, height)
            if sw_codec == "mpeg4":
                out_path = os.path.join(folder, "ms_joined" + ext)
                count = _write_joined(paths, out_path, sw_codec, options,
                                      pix_fmt, None)
                _log(f"joined {len(paths)} clips into one video with the "
                     f"software encoder ({count} frames; hardware: "
                     f"{hardware_error})")
                return out_path
            # Too big for mpeg4. Wait for the hardware encoder to come
            # back, which it does when ManimStudio is in the foreground.
            if not waiting:
                waiting = True
                if on_phase is not None:
                    on_phase("waiting")
                _log(f"a {width}×{height} video needs the hardware encoder, "
                     f"which isn't available right now ({hardware_error}). "
                     f"It will be written when you return to ManimStudio.")
            if check_cancel is not None:
                check_cancel()
            time.sleep(WAIT_SECONDS)

    _orig_combine = SceneFileWriter.combine_files

    def combine_files(self, input_files, output_file, *args, **kwargs):
        segments = getattr(self, "_ms_segments", None)
        if not segments:
            return _orig_combine(self, input_files, output_file, *args, **kwargs)
        # A clip whose encoder failed on its first frame holds nothing;
        # the animation is in the clips that continued it.
        paths = []
        for path in input_files:
            for clip_path in [str(path)] + segments.get(str(path), []):
                if _has_video(clip_path):
                    paths.append(clip_path)
        if not paths:
            raise RuntimeError("the render wrote no video frames")
        if len({_encoding(path) for path in paths}) == 1:
            return _orig_combine(self, paths, output_file, *args, **kwargs)
        joined = _join(self, paths)
        try:
            return _orig_combine(self, [joined], output_file, *args, **kwargs)
        finally:
            _remove(joined)

    SceneFileWriter.combine_files = combine_files
