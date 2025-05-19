# build_config.py
import os
import sys
from pathlib import Path

# Application metadata
APP_NAME = "Manim Animation Studio"
APP_VERSION = "3.5.0"
APP_AUTHOR = "Manim Studio Team"
APP_DESCRIPTION = "Professional mathematical animation software"
APP_IDENTIFIER = "yu314-coder.github.io"

# Build paths
BUILD_DIR = Path("build")
DIST_DIR = Path("dist")
INSTALLER_DIR = Path("installer")

# Dependencies that need special handling
HIDDEN_IMPORTS = [
    'manim',
    'numpy',
    'PIL',
    'cv2',
    'customtkinter',
    'jedi',
    'requests',
    'aiohttp',
    'tkinter',
    'matplotlib',
    'scipy',
    'sympy',
    'networkx'
]

# Data files to include
DATA_FILES = [
    ('assets', 'assets'),
    ('README.md', '.'),
    ('LICENSE', '.'),
]

# Excluded modules (to reduce size)
EXCLUDES = [
    'tkinter.test',
    'test',
    'unittest',
    'doctest',
    'pdb',
    'pydoc',
]