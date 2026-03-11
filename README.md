# 🎬 Manim Animation Studio

**Professional Desktop Environment for Creating Mathematical Animations**

A powerful, feature-rich desktop application for creating stunning mathematical animations using [Manim Community Edition](https://www.manim.community/). Built with Python, PyWebView, and modern web technologies.

![Version](https://img.shields.io/badge/version-1.1.2.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## ✨ Features

### 🎨 **Professional Code Editor**
- **Monaco Editor** (VS Code's editor) with full Python syntax highlighting
- **basedpyright IntelliSense** — real-time type checking, completions, hover docs, and diagnostics
- **Go-to-Definition** (F12), **Type Definition**, and **Find All References** (Shift+F12) via LSP
- **VS Code-quality signature help** — live parameter hints for Python builtins and all Manim classes
- **Static completions** for all Manim classes, animations, mobjects, colors, and constants (instant, no LSP required)
- **Scene Outline Panel** — tree view of all classes and methods with click-to-navigate
- **Editor Bookmarks** (Ctrl+Shift+K) — bookmark lines for quick navigation
- **Zen Mode** (F11) — distraction-free fullscreen editing
- **Drag-and-drop** .py files onto the editor to open them
- Line numbers, code folding, and multiple cursors
- Customizable font size and themes

### 🤖 **AI Edit Panel (Codex + Claude Code)**
- Send your code with a natural language prompt for intelligent edits
- **Claude Code (Beta)** — structured stream-json integration, no API key needed
- **OpenAI Codex CLI** — full JSONL streaming with `codex exec --json`
- **AI Agent Mode** — autonomous generate → render → screenshot → review → fix loop
  - Works with both Claude and Codex providers
  - Visual QA review examines every frame for issues
  - Auto-iterates until the animation looks correct
- **Continuous Chat** — multi-turn conversations with session memory (`--session-id` / `--resume`)
- **Token-Optimized** — AI reads files from disk instead of prompt embedding, session caching saves 70-80% on subsequent turns, screenshots downscaled to reduce image tokens
- **Image upload** — attach screenshots or reference images for the AI to understand your intent
- **Web Search** toggle — let the AI reference live web results while editing
- **Model selector** — pick from Claude Opus/Sonnet/Haiku, GPT-5.3 Codex, and more
- Side-by-side diff review — Accept or Reject changes with one click
- **Inline autocomplete** — ghost-text code completions powered by Claude Haiku
- Fix code errors directly from the diagnostics panel
- **Premium glass-morphism UI** with gradient buttons and slide-in panel

### 🎙️ **Auto Narration (Kokoro TTS)**
- Add `narrate("Your text here")` anywhere in your Manim code
- TTS audio is **automatically generated and merged** with the video on render or preview
- **Auto-subtitles (CC)** — WebVTT captions appear in the preview player
- Powered by **Kokoro ONNX** (82M params, ~310MB model, auto-downloaded on first use)
- Multiple voices — Heart, Bella, Nicole, Sarah, Adam, Michael, Emma, George
- Optional `narrate[kokoro]` package available in the setup wizard

### ⚡ **Dual Render Modes**
- **Quick Preview (F6)**: Fast, low-quality preview (480p, 15fps) for rapid iteration
- **Final Render (F5)**: High-quality output up to 8K resolution at 120fps
- GPU acceleration support (OpenGL renderer)
- Real-time progress tracking with live terminal output
- **Render History** — persistent log of all renders with replay, open, and delete

### 📁 **Integrated Asset Management**
- Drag & drop file uploads
- Support for videos, images, fonts, audio, and subtitles
- Built-in asset preview with media player
- Organized asset library with file metadata
- Easy access to custom fonts and media files

### 📦 **Visual Package Manager**
- Install Python packages with one click
- Check for package updates
- Uninstall packages safely
- View installed packages and versions
- Auto-detection of missing required packages on startup
- No terminal commands needed

### 🖥️ **Full-Featured Terminal**
- Real Windows cmd.exe integration with xterm.js
- Auto-activated virtual environment
- Copy/paste support (Ctrl+Shift+C/V)
- Persistent session across renders
- Color-coded output for better readability

### 🎯 **Smart Workflow Features**
- **Auto-save backups**: Never lose your work
- **Unsaved changes warning**: Prompted before opening a new file
- **File recovery**: Restore from auto-saved versions
- **Auto-open output folder**: Jump directly to saved renders
- **Live preview**: See your animation immediately after render
- **Screenshot save**: Save preview frames with a native Save As dialog
- **Settings persistence**: Your preferences are remembered
- **Command Palette** (Ctrl+Shift+P) — quick launcher for all actions

### 🌓 **Modern UI/UX**
- Dark/Light theme toggle
- **Manim Color Picker** — visual palette of all Manim color constants with one-click insert
- **Keyboard Shortcuts Modal** (Ctrl+/) — searchable reference of all shortcuts
- Responsive design with DPI awareness
- Glassmorphic design elements
- Smooth animations and transitions
- Collapsible render controls sidebar
- Toast notifications for all actions

---

## 📸 Screenshots

### Main Workspace
The main interface features a split view with Monaco code editor on the left and live preview on the right, with an integrated terminal at the bottom.

### Asset Manager
Browse, upload, and preview all your media files in one organized location with drag-and-drop support.

### Package Manager
Install and manage Python packages through an intuitive visual interface without touching the command line.

---

## 🚀 Getting Started

### Prerequisites

- **Windows 10/11** (64-bit)
- **Python 3.8+** installed and in PATH
- **4GB RAM minimum** (8GB recommended)
- **1GB free disk space**

### Installation

1. **Download the latest release**
   ```
   Download from GitHub Releases
   ```

2. **Extract the archive**
   ```
   Extract to your preferred location
   ```

3. **Run the application**
   ```
   Double-click app.exe (or python app.py from source)
   ```

4. **First-time setup** (automatic)
   - Virtual environment creation
   - Manim, manim-fonts, and basedpyright installation
   - LaTeX detection and setup
   - Assets folder initialization

### Building from Source

```bash
# Clone the repository
git clone https://github.com/yu314-coder/manim_app.git
cd manim_app

# Install host dependencies
pip install pywebview

# Run the application
python app.py
```

### Building Executable with Nuitka

```bash
# Activate build environment
python -m venv venv_nuitka
venv_nuitka\Scripts\activate

# Install Nuitka
pip install nuitka

# Build executable
python build_nuitka.py

# Output will be in dist_nuitka/
```

---

## 📖 Quick Start Guide

### Creating Your First Animation

1. **Launch Manim Studio**
   - The app opens with a default scene template

2. **Write Your Code**
   ```python
   from manim import *

   class MyScene(Scene):
       def construct(self):
           circle = Circle()
           self.play(Create(circle))
           self.wait()
   ```

3. **Preview (F6)**
   - Click "Preview" or press F6
   - Get a fast low-quality preview in seconds

4. **Final Render (F5)**
   - Click "Render" or press F5
   - Choose quality settings in the sidebar
   - Save your high-quality video when complete
   - **Output folder opens automatically** after saving

### Adding Narration

```python
from manim import *

class NarratedScene(Scene):
    def construct(self):
        narrate("Let me show you a circle.")
        circle = Circle(color=BLUE)
        self.play(Create(circle))
        narrate("Now let's transform it into a square.")
        self.play(Transform(circle, Square(color=RED)))
        self.wait()
```

Press **F6** or **F5** — TTS audio is generated and merged with the video automatically. Subtitles appear in the preview player.

### Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Render Animation | `F5` |
| Quick Preview | `F6` |
| Stop Render | `Esc` |
| Save File | `Ctrl + S` |
| New File | `Ctrl + N` |
| Open File | `Ctrl + O` |
| Command Palette | `Ctrl + Shift + P` |
| Keyboard Shortcuts | `Ctrl + /` |
| Zen Mode | `F11` |
| Toggle Bookmark | `Ctrl + Shift + K` |
| AI Edit Panel | `Ctrl + Shift + E` |
| Go to Definition | `F12` |
| Find All References | `Shift + F12` |
| Screenshot Preview | `Ctrl + Shift + S` |

---

## 🎨 Using Assets

### Adding Custom Fonts

1. **Upload Font**
   - Go to Assets tab
   - Drag & drop your .ttf or .otf file

2. **Use in Code**
   ```python
   from manim import *

   class CustomFontExample(Scene):
       def construct(self):
           register_font("YourFont.ttf")
           text = Text("Hello!", font="YourFont")
           self.play(Write(text))
   ```

### Adding Images/Videos

1. **Upload Media**
   - Drag files to Assets tab dropzone
   - Supported: MP4, PNG, JPG, SVG, GIF

2. **Use in Animation**
   ```python
   from manim import *

   class ImageExample(Scene):
       def construct(self):
           img = ImageMobject("myimage.png")
           self.play(FadeIn(img))
   ```

### Adding Audio

```python
from manim import *

class AudioExample(Scene):
    def construct(self):
        self.add_sound("music.mp3")
        circle = Circle()
        self.play(Create(circle))
```

---

## ⚙️ Configuration

### Render Settings

**Quality Presets:**
- **480p**: 854×480, 15fps (Fast preview)
- **720p**: 1280×720, 30fps (Standard HD)
- **1080p**: 1920×1080, 60fps (Full HD)
- **1440p**: 2560×1440, 60fps (2K)
- **4K**: 3840×2160, 60fps (Ultra HD)
- **8K**: 7680×4320, 60fps (Cinema quality)

**Output Formats:**
- MP4 (H.264 video)
- MOV (QuickTime)
- GIF (Animated)
- PNG (Image sequence)

### GPU Acceleration

Toggle GPU rendering in the header toolbar:
- **GPU: OFF** = Cairo renderer (CPU, compatible)
- **GPU: ON** = OpenGL renderer (GPU, faster but may have quirks)

### Editor Settings

Access via Settings (⚙️ icon):
- Font size (12-20px)
- Default save location
- Auto-save after render
- Auto-open output folder
- Manim cache settings

---

## 📂 File Structure

```
C:\Users\<you>\.manim_studio\
├── assets\              # Your uploaded files (fonts, images, audio)
├── lsp_workspace\       # basedpyright workspace (auto-managed)
├── media\               # Manim cache and temp files
├── render\              # High-quality render output (temporary)
├── preview\             # Quick preview output (temporary)
├── autosave\            # Auto-saved code backups
├── venvs\
│   └── manim_studio_default\  # Python virtual environment
└── settings.json        # Your app preferences
```

**Note:** Render outputs are temporary. Use the "Save" button after rendering to save them permanently to your chosen location. The output folder will open automatically in Windows Explorer after saving.

---

## 🐛 Troubleshooting

### Rendering Fails

**Problem:** Render shows errors in terminal

**Solutions:**
1. Check syntax errors (red underlines in editor)
2. Ensure all imported files exist in assets folder
3. Try Preview (F6) first to catch errors quickly
4. Check LaTeX status in System tab
5. Review terminal output for specific error messages

### Custom Fonts Not Working

**Problem:** Font doesn't appear in animation

**Solutions:**
1. Ensure font file is uploaded to Assets folder
2. Use `register_font("YourFont.ttf")` before using it
3. Reference font by name without extension: `font="YourFont"`
4. Check that font file is valid TrueType (.ttf) or OpenType (.otf)

### LaTeX Not Working

**Problem:** LaTeX formulas fail to render

**Solutions:**
1. Check LaTeX status indicator (header, right side)
2. Install MiKTeX or TeX Live if not present
3. Restart application after LaTeX installation
4. Use raw strings for LaTeX: `r"$\frac{1}{2}$"`

### IntelliSense Not Working

**Problem:** No type checking or smart completions from basedpyright

**Solutions:**
1. Wait ~2 seconds after the editor loads — IntelliSense starts in the background
2. Check that basedpyright is installed (Packages tab)
3. If missing, the app will prompt you to install it on startup
4. A "IntelliSense ready" toast appears when LSP is active

### Package Installation Fails

**Problem:** Cannot install Python packages

**Solutions:**
1. Check terminal output for specific error
2. Ensure package name is spelled correctly
3. Try installing via terminal manually
4. Check internet connection
5. Some packages may require system dependencies

### Video Won't Play in Preview

**Problem:** Preview panel shows no video after render

**Solutions:**
1. Check that render completed successfully (terminal logs)
2. Try refreshing Assets tab
3. Ensure video file exists and is not corrupted

---

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Report Bugs**: Open an issue with detailed reproduction steps
2. **Suggest Features**: Describe your use case and proposed solution
3. **Submit Pull Requests**: Fork, branch, code, test, and PR
4. **Improve Documentation**: Fix typos, add examples, clarify instructions

### Development Setup

```bash
# Clone and setup development environment
git clone https://github.com/yu314-coder/manim_app.git
cd manim_app

# Install host dependencies
pip install pywebview

# Run in development mode
python app.py
```

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **[Manim Community](https://www.manim.community/)** - The amazing animation engine
- **[Monaco Editor](https://microsoft.github.io/monaco-editor/)** - VS Code's powerful editor
- **[basedpyright](https://github.com/DetachHead/basedpyright)** - Python language server for IntelliSense
- **[OpenAI Codex CLI](https://github.com/openai/codex)** - OpenAI's AI coding agent
- **[Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx)** - Fast TTS with Kokoro and ONNX Runtime
- **[PyWebView](https://pywebview.flowrl.com/)** - Native Python desktop apps
- **[xterm.js](https://xtermjs.org/)** - Terminal emulator for the web
- **Font Awesome** - Beautiful icons

---

## 📞 Support

- **Documentation**: Check the built-in Help modal (? icon)
- **Issues**: [GitHub Issues](https://github.com/yu314-coder/manim_app/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yu314-coder/manim_app/discussions)
- **Manim Help**: [Manim Community Discord](https://discord.gg/manim)

---

## 🗺️ Roadmap

### Upcoming Features

- [ ] **Live Preview Mode**: See animations update in real-time as you type
- [ ] **Scene Browser**: Visual navigation between multiple scenes
- [ ] **Animation Templates**: Pre-built scenes for common use cases
- [ ] **Export Presets**: Save and reuse render configurations
- [ ] **macOS/Linux Support**: Cross-platform compatibility
- [ ] **Timeline Editor**: Visual animation timeline

---

## 📊 System Requirements

### Minimum

- **OS**: Windows 10 (64-bit)
- **CPU**: Dual-core 2.0 GHz
- **RAM**: 4GB
- **Storage**: 1GB free space
- **Display**: 1280×720

### Recommended

- **OS**: Windows 11 (64-bit)
- **CPU**: Quad-core 3.0 GHz
- **RAM**: 8GB+
- **GPU**: Dedicated graphics (for GPU rendering)
- **Storage**: 5GB free space (for cache)
- **Display**: 1920×1080 or higher

---

## 🎓 Learning Resources

### Manim Tutorials

- [Manim Community Docs](https://docs.manim.community/)
- [3Blue1Brown](https://www.youtube.com/c/3blue1brown) - Creator of Manim
- [Theorem of Beethoven](https://www.youtube.com/c/TheoremofBeethoven) - Manim tutorials
- [Manim Examples](https://docs.manim.community/en/stable/examples.html)

### Python Resources

- [Python Official Docs](https://docs.python.org/3/)
- [Real Python](https://realpython.com/)

---

## ⭐ Star History

If you find this project useful, please consider giving it a star on GitHub!

---

## 📝 Changelog

### v1.1.2.0 (Latest)
- ✨ **AI Agent Mode** — autonomous loop: generate code → render → capture screenshots → visual review → auto-fix → repeat until correct
- ✨ **Dual Agent Providers** — AI Agent works with both Claude Code and OpenAI Codex CLI, using the same provider for edit and review
- ✨ **Continuous Chat** — multi-turn conversations with session memory; Claude uses `--session-id` / `--resume` for context persistence
- ✨ **Token Optimization** — removed code embedding from all prompts (AI reads `scene.py` from disk), session caching saves 70-80% on repeated turns, screenshots downscaled to 960px for 4x fewer image tokens
- ✨ **Claude Agent Session Reuse** — first edit uses `--session-id`, subsequent edits use `--resume` so Claude remembers what it already tried
- ✨ **Screenshot Downscaling** — review frames auto-resized to 960px wide via Pillow (falls back gracefully if unavailable)
- ✨ **Claude Review via File Read** — Claude examines screenshot files from disk using its Read tool instead of base64 prompt embedding
- ✨ **Assets Folder Access** — AI workspaces get a junction/symlink to the assets folder; CLAUDE.md/AGENTS.md lists available asset files
- ✨ **Inline Autocomplete** — ghost-text code completions powered by Claude Haiku (fast, lightweight)
- ✨ **New Chat Button** — reset AI Edit session and start fresh without restarting the panel
- 🐛 Fixed Codex agent not working (cascading bugs: missing AGENTS.md, wrong CLI flags, no JSONL parsing)
- 🐛 Fixed Codex agent review using Claude instead of Codex — now each provider reviews with its own CLI
- 🐛 Fixed `--skip-git-repo-check` incorrectly added to Claude CLI calls (only valid for Codex)
- 🐛 Fixed `--image` flag used for Claude CLI (doesn't exist) — Claude now reads image files via Read tool
- 🐛 Fixed `--output-format stream-json` requiring `--verbose` flag for Claude agent edits
- 🐛 Fixed agent loop not continuing when review found bugs (edit failures, unchanged code, review errors)
- 🐛 Fixed review nitpicking minor issues — now focuses on real visual bugs (overlap, off-screen, wrong text, goal mismatch)
- 🐛 Fixed agent sending only 5 sampled frames — now sends ALL captured frames to review
- 🔧 Unified all 3 MD templates (non-agent, Claude agent, Codex agent) with consistent Manim context and "ALWAYS read scene.py FIRST" rule
- 🔧 Instructions piped via stdin (`-p` without arg) to avoid OS argument length limits
- 🔧 Review prompt no longer embeds code — reviewer only needs screenshots + goal description
- 🔧 Agent edit failure counter prevents infinite loops (stops after 5 consecutive failures)

### v1.1.1.0
- ✨ **Claude Code Integration (Beta)** — AI Edit now supports Claude Code via `claude -p --output-format stream-json`, no API key needed
- ✨ **Enhanced Streaming Output** — tool actions (Write, Read, Bash) render as styled blocks with icons, code lines get line-number gutters
- ✨ **AI Edit Beta Badge** — panel and window mode show "(Beta)" to indicate active development
- ✨ **Auto Narration (Kokoro TTS)** — `narrate("text")` calls generate TTS audio, auto-merged with video on render
- ✨ **Subtitles (CC)** — narrated videos get auto-generated WebVTT subtitles in the preview player
- ✨ **Kokoro model auto-download** — ~310MB TTS model downloaded automatically on first use
- ✨ **`narrate` PyPI package** — optional `narrate[kokoro]` for TTS support
- ✨ **Scene Outline Panel** — tree view of classes/methods with click-to-navigate
- ✨ **Command Palette** (Ctrl+Shift+P), **Shortcuts Modal** (Ctrl+/), **Zen Mode** (F11), **Bookmarks** (Ctrl+Shift+K)
- ✨ **Drag-and-drop** .py files onto the editor to open them
- ✨ **AI Edit Panel** — Codex + Claude Code, image upload, web search, model selector
- ✨ **Manim Color Picker**, **Go-to-Definition** (F12), **Find References** (Shift+F12)
- ✨ **Render History** — persistent log with replay, open, and delete
- ✨ **Screenshot Save** — save preview frames with native Save As dialog
- 🐛 Fixed WebSearch permission prompts getting stuck on numbered menu format
- 🐛 Fixed bundled EXE 404 for ai-edit-window.html (absolute path fix)
- 🐛 Fixed version mismatch, video preview via HTTP, CLI detection, subprocess piping, ANSI stripping
- 🔧 Refactored Claude Code from PTY-based to stream-json (removed winpty dependency)
- 🔧 Replaced hardcoded `C:\Windows` paths with `%SystemRoot%`
- 🔧 Added workspace instruction file (AGENTS.md) for reliable AI file editing

### v1.1.0.0
- ✨ **basedpyright IntelliSense** — real-time type checking, diagnostics, hover docs, and completions powered by a full LSP server
- ✨ **VS Code-quality signature help** — live parameter hints when typing `(` or `,` for all Python builtins and Manim classes
- ✨ **Rich per-parameter documentation** — typed labels, descriptions, default values, and code examples for 80+ functions
- ✨ **Missing packages auto-detection** — startup check notifies existing users of missing required packages with one-click install
- ✨ **basedpyright added to required packages** — automatically installed in new and existing environments
- 🐛 Fixed autosave messages incorrectly appearing in the terminal box
- 🐛 Added unsaved changes warning before opening a new file
- 🐛 Render status feedback ("Rendering...") shown immediately on render start
- 🔧 LSP workspace uses real on-disk directory so basedpyright resolves Manim imports correctly
- 🔧 Improved terminal polling rate for smoother output streaming

### v1.0.9.0
- ✨ **Auto-open output folder** after saving rendered files
- ✨ Improved render controls sidebar with chevron collapse icon
- 🎨 Enhanced toast notifications with comprehensive logging
- 🐛 Fixed async button handler for folder opening
- 🐛 Improved DPI awareness and responsive scaling
- 📖 Added comprehensive README documentation

### v1.0.8.0
- ✨ Added Package Manager with visual interface
- ✨ Drag & drop asset uploads
- 🐛 Fixed GPU toggle persistence
- 🐛 Fixed autosave recovery dialog
- 🎨 Improved responsive scaling and DPI awareness

### v1.0.7.0
- ✨ Added auto-save with backup recovery
- ✨ Integrated xterm.js terminal
- 🐛 Fixed LaTeX detection
- 🎨 Improved dark theme

### v1.0.6.0
- ✨ Initial public release
- 🎨 Professional UI with Monaco Editor
- ⚡ Dual render modes (Preview/Final)
- 📁 Asset management system

---

<div align="center">

**Made with ❤️ for the Manim Community**

[⬆ Back to Top](#-manim-animation-studio)

</div>
