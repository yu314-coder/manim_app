#!/usr/bin/env python3
"""Simplified build script for Manim Studio.

This script compiles ``app.py`` using Nuitka. A working LaTeX installation
is required and will be checked before building. The result is a single-file
executable by default.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys

REQUIRED_PACKAGES = [
    "manim",
    "customtkinter",
    "PIL",
    "numpy",
    "cv2",
    "matplotlib",
    "jedi",
    "psutil",
]


def check_latex_installed() -> bool:
    """Return ``True`` if a LaTeX executable is available and working."""
    latex_cmd = shutil.which("latex") or shutil.which("pdflatex")
    if not latex_cmd:
        print("❌ LaTeX executable not found in PATH. Install MiKTeX or TeX Live.")
        return False
    try:
        subprocess.run([latex_cmd, "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as exc:
        print(f"❌ LaTeX detected at {latex_cmd} but failed to run: {exc}")
        return False
    print(f"✅ LaTeX detected at: {latex_cmd}")
    return True


def check_requirements() -> bool:
    """Ensure all Python package requirements are met."""
    missing: list[str] = []
    for pkg in REQUIRED_PACKAGES:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    if missing:
        print("❌ Missing packages:", " ".join(missing))
        print("Install them with: pip install " + " ".join(missing))
        return False
    return True


def build(onefile: bool = True, jobs: int | None = None) -> Path | None:
    """Build the executable and return its path on success."""
    if not check_latex_installed() or not check_requirements():
        return None

    if jobs is None:
        jobs = max(1, multiprocessing.cpu_count() - 1)

    output_dir = Path("dist")
    if output_dir.exists():
        shutil.rmtree(output_dir)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile" if onefile else "--standalone",
        "--windows-disable-console",
        "--enable-plugin=tk-inter",
        f"--output-dir={output_dir}",
        f"--jobs={jobs}",
        "app.py",
    ]

    logging.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("✅ Build completed")
        try:
            return next(output_dir.glob("app.*"))
        except StopIteration:
            return None
    print(f"❌ Build failed with code {result.returncode}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Manim Studio executable")
    parser.add_argument("--jobs", type=int, help="Number of compilation threads")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Create a directory build instead of a single file",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    exe = build(onefile=not args.standalone, jobs=args.jobs)
    if exe:
        print(f"Executable created at: {exe}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
