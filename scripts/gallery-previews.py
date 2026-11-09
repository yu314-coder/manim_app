#!/usr/bin/env python3
"""The Gallery cards' looping videos, made from the templates themselves.

Each card in GalleryView.swift plays Resources/GalleryPreviews/<id>.mp4. They
used to come from a separate preview script and drifted from the code a card
loads (the Graph Traversal card showed a different graph). Now the video is a
render of the template's own code:

    scripts/gallery-previews.py extract <dir>
        writes each template's code to <dir>/<id>.py (scene name inside)
    render each <id>.py in ManimStudio at 1080p30 (Render, or the terminal's
        manim), and put the results in one folder as <id>.mp4
    scripts/gallery-previews.py install <dir>
        turns <dir>/<id>.mp4 into the 854x480 card videos (needs ffmpeg)
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
GALLERY = ROOT / "ManimStudio/ManimStudio/GalleryView.swift"
PREVIEWS = ROOT / "ManimStudio/ManimStudio/Resources/GalleryPreviews"


def templates():
    """(id, Python source) for every GalleryTemplate, from the Swift literal."""
    source = GALLERY.read_text(encoding="utf-8")
    for m in re.finditer(r'id: "(\w+)",.*?code: """\n(.*?)\n( *)"""', source, re.S):
        indent = m.group(3)
        lines = [line[len(indent):] if line.startswith(indent) else line
                 for line in m.group(2).split("\n")]
        # The Swift literal doubles each backslash.
        yield m.group(1), "\n".join(lines).replace("\\\\", "\\") + "\n"


def extract(out):
    out.mkdir(parents=True, exist_ok=True)
    for tid, code in templates():
        (out / f"{tid}.py").write_text(code, encoding="utf-8")
        print(f"{tid}.py")


def install(rendered):
    for tid, _ in templates():
        src = rendered / f"{tid}.mp4"
        if not src.exists():
            sys.exit(f"missing {src}")
        dst = PREVIEWS / f"{tid}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                        "-vf", "scale=854:480:flags=lanczos,fps=30",
                        "-c:v", "libx264", "-preset", "veryslow", "-crf", "26",
                        "-pix_fmt", "yuv420p", "-profile:v", "high",
                        "-movflags", "+faststart", "-an", str(dst)], check=True)
        print(f"{dst.name}  {dst.stat().st_size // 1024} KB")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("extract", "install"):
        sys.exit(__doc__)
    (extract if sys.argv[1] == "extract" else install)(pathlib.Path(sys.argv[2]))
