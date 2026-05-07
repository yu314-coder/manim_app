# 🎬 Manim Animation Studio

**Professional Desktop Environment for Creating Mathematical Animations**

A powerful, feature-rich desktop application for creating stunning mathematical animations using [Manim Community Edition](https://www.manim.community/). Built with Python, PyWebView, and modern web technologies.

![Version](https://img.shields.io/badge/version-1.1.3.0-blue)
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

### 🖥️ **CLI & MCP Server (Codex Plugin)**
- **Same EXE, dual mode** — double-click for GUI, run from terminal for CLI
- `ManimStudio render scene.py --quality 1080p --width 1920 --height 1080 --fps 60` — headless render
- `ManimStudio validate scene.py` — syntax check and scene class detection
- `ManimStudio presets` — list all quality presets with resolutions
- `ManimStudio mcp` — start MCP server (stdio) for **OpenAI Codex** integration
- **Full resolution control** — quality presets (120p–8K) plus custom `--width` / `--height` override
- **MCP tools exposed**: `render_manim_animation`, `check_render_status`, `validate_scene`, `list_quality_presets`
- Uses the same `manim_studio_default` venv as the GUI — no separate setup
- Register in Codex: add `[mcp_servers.ManimStudio]` to `~/.codex/config.toml`

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

### CLI Usage

The same executable (or `python app.py`) works as both GUI and CLI:

```bash
# Headless render with quality preset
ManimStudio.exe render scene.py --quality 1080p --fps 60

# Render with custom resolution (overrides preset width/height)
ManimStudio.exe render scene.py --quality 720p --width 800 --height 600 --fps 24

# Render to a specific output directory
ManimStudio.exe render scene.py -q 4K -o C:\renders\my_video

# Validate code without rendering
ManimStudio.exe validate scene.py

# List all quality presets
ManimStudio.exe presets

# Start MCP server for Codex integration
ManimStudio.exe mcp
```

From source, replace `ManimStudio.exe` with `python app.py`:

```bash
python app.py render scene.py --quality 720p --width 1280 --height 720
python app.py mcp
```

### Codex MCP Integration

Register ManimStudio as an MCP server in `~/.codex/config.toml`:

```toml
# If using the compiled EXE:
[mcp_servers.ManimStudio]
command = "C:\\path\\to\\ManimStudio.exe"
args = ["mcp"]

# If running from source:
[mcp_servers.ManimStudio]
command = "python"
args = ["C:\\path\\to\\app.py", "mcp"]
```

Once registered, Codex can call these MCP tools:

| Tool | Description |
|------|-------------|
| `render_manim_animation` | Render Manim code with quality/width/height/fps/format controls |
| `check_render_status` | Check if a render output file exists |
| `validate_scene` | Syntax check + scene class name extraction |
| `list_quality_presets` | List all presets with their default resolutions |

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

**Quality Presets** (GUI, CLI `--quality`, and MCP `quality` param):

| Preset | Resolution | Default FPS | CLI Flag |
|--------|-----------|------------|----------|
| 120p | 214×120 | 15 | `-q 120p` |
| 240p | 426×240 | 15 | `-q 240p` |
| 480p | 854×480 | 15 | `-q 480p` |
| 720p | 1280×720 | 30 | `-q 720p` |
| 1080p | 1920×1080 | 60 | `-q 1080p` |
| 1440p | 2560×1440 | 60 | `-q 1440p` |
| 4K | 3840×2160 | 60 | `-q 4K` |
| 8K | 7680×4320 | 60 | `-q 8K` |

Use `--width` / `--height` (CLI) or `width` / `height` (MCP) to override the preset resolution.

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
manim_app/                    # Source / EXE directory
├── app.py                    # Main app (GUI + CLI dispatcher)
├── cli.py                    # CLI & MCP server (headless render)
├── ai_edit.py                # AI Edit module (Claude + Codex)
├── narration_addon.py        # Kokoro TTS narration
├── build_nuitka.py           # Nuitka build script
├── prompts/                  # AI prompt templates (.md)
└── web/                      # Frontend (HTML/CSS/JS)

C:\Users\<you>\.manim_studio\   # User data directory
├── assets\              # Your uploaded files (fonts, images, audio)
├── lsp_workspace\       # basedpyright workspace (auto-managed)
├── media\               # Manim cache and temp files
├── render\              # High-quality render output (temporary)
├── preview\             # Quick preview output (temporary)
├── autosave\            # Auto-saved code backups
├── venvs\
│   └── manim_studio_default\  # Python virtual environment (shared by GUI & CLI)
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

- [x] **CLI & MCP Server**: Headless render + Codex plugin via MCP tools
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

### v1.1.3.0 (Latest)

**New features:**
- ✨ **F-09 Agent Memory** — per-project `style.md` auto-injected as a system preamble on every AI edit/agent turn. Editable via the 🧠 brain icon in the AI Edit panel header. Heuristic detects user corrections (e.g. "no, use BLUE instead of RED") and proposes memory updates with one-click accept/dismiss. Prefix `#ignore-style` on a single message to skip the preamble for that turn.
- ✨ **F-03 Visual Diff** — pHashes every rendered frame, diffs against the baseline render, opens an A/B review modal when drift > 1%. Accept (promotes new baseline), Revert, Block per render. Keyboard shortcuts `J/K` next/prev flagged frame, `A` accept, `R` revert, `B` block.
- ✨ **Multi-scene combined render** — files with 2+ Scene classes pop a picker. Tick checkboxes + "Render selected" runs ONE manim subprocess with all scene names as positional args, then ffmpeg `-f concat -c copy` stitches the outputs into one standalone `combined_*.mp4`.
- ✨ **Scene picker modal** — auto-shows when rendering/previewing a file with multiple Scene subclasses. Single-click a row to render just that scene; checkboxes + "Render selected" for batch; "Select all" button for one-click full-file render.
- ✨ **CJK auto-template** — files with Chinese / Japanese / Korean characters inside `MathTex(...)` / `Tex(...)` get the xelatex + `ctex` template auto-injected. Works around Manim 0.20.1's `tempconfig({})` clearing `_tex_template` between scenes by subclassing `MathTex`/`Tex` to bake `tex_template=ctex` into every constructor.
- ✨ **Auto-discovery of AI models** — Claude models auto-detected by scanning `~/.claude/projects/*/*.jsonl` session history; Codex models pulled from the authoritative `~/.codex/models_cache.json` cache (with full metadata: slug, display name, reasoning levels, speed tiers, visibility). New models that OpenAI / Anthropic ship surface in the dropdown automatically — no Manim Studio update required. Discovered models appear under a "Discovered" tier with an orange 🔍 magnifier icon to distinguish from hardcoded defaults.
- ✨ **Claude 4.7 family** — Opus 4.7, Sonnet 4.7, Haiku 4.7 are now the default tier for edit / agent / autocomplete / review / complex tasks. 4.6 and 4.5 remain selectable under a "(previous)" suffix. Fallback chain: Opus 4.7 → Sonnet 4.7 → Haiku 4.7 → Haiku 4.5.
- ✨ **AST-based scene detection** — fixed the long-standing "only first scene detected" bug. `extract_scene_name` now uses Python's `ast` module to find every Scene subclass, handling tricky base-class shapes (`typing.Generic[T]`, metaclass parents, mixed bases). Backward-compatible regex fallback for files in the middle of an edit.
- ✨ **`list_scenes` MCP tool** — Codex can list every Scene-subclass class in a Manim file (name, line, parent) before invoking `render_manim_animation`.

**Bug fixes:**
- 🐛 **Multi-scene render no longer wipes preview folder** between iterations. Was a per-scene loop that called `clear_preview_folder()` between scenes; the previous scene's temp file got deleted before manim could read it. Now a single subprocess + ffmpeg concat.
- 🐛 **Agent waits for in-flight preview** before firing its own. Was hanging forever when `quickPreview()` got silently rejected by `if (job.running) return`. Now polls `job.running` to clear (up to 5min) before triggering, plus a 10-min safety timeout that synthesises `render_error` to break out of `_ai_agent_wait` cleanly.
- 🐛 **Preview-folder race condition fixed** — double-clicking Preview rapidly wiped the in-flight previous render's temp `.py` (`FileNotFoundError: temp_preview_*.py not found`). `clear_preview_folder()` now skips files modified in the last 60 seconds.
- 🐛 **LaTeX errors no longer truncated** — error capture used to grab only 3 lines / 200 chars, hiding the actual root cause. Now scans up to 40 traceback lines, stops at the closing `ErrorType:` line, returns up to 2000 chars to the UI, and dumps the full content to backend stdout.
- 🐛 **Memory modal no longer overlapped by preview video** — Chromium's GPU video compositor painted over HTML regardless of z-index. Modal now sets `visibility:hidden` on the `<video>` element while open (full GPU-layer removal), plus `transform: translateZ(0); isolation: isolate` on the modal itself as defense-in-depth.

**Removed from toolbar UI** (backends remain on disk for future re-introduction):
- 🗑️ F-08 AI Sketches button (the `sketch_*` API methods are still available via pywebview)
- 🗑️ F-04 Inspector button + side dock
- 🗑️ F-01 Timeline dock + toolbar button
- 🗑️ F-12 Render Farm sidebar toggle + progress modal
- 🗑️ Narration Voice & Speed sidebar selector (narration itself still works; localStorage-driven)

### v1.1.2.0
- ✨ **CLI Mode** — same EXE works as headless CLI: `ManimStudio render scene.py --quality 1080p --width 1920 --height 1080 --fps 60`
- ✨ **MCP Server for Codex** — `ManimStudio mcp` exposes render/validate/presets as MCP tools over stdio; register in `~/.codex/config.toml` and Codex can render Manim animations directly
- ✨ **Full Resolution Control** — CLI and MCP support all quality presets (120p–8K) plus custom `--width`/`--height` override
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
- ✨ **Persistent Chat History** — AI chat sessions auto-saved to disk (`~/.manim_studio/chat_history/`); browse, resume, or delete past sessions from the history dropdown
- ✨ **AI-Friendly GUI** — `aria-label`, `data-testid`, `aria-live` attributes on all interactive elements; hidden app state indicator (`#appStateIndicator`) exposes render/AI/file state for computer-control agents (Claude Code Desktop, Codex)
- ✨ **Faster Startup** — disk-cached dependency checks (1-hour TTL) skip subprocess calls on repeat launches; Python and LaTeX checks run in parallel threads; `shutil.which()` fast path for LaTeX
- ✨ **Editor Skeleton UI** — CSS shimmer placeholder shown while Monaco editor loads for improved perceived startup speed
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
- 🔧 Build: console mode changed from `disable` to `attach` so the EXE works as both GUI and CLI
- 🔧 Build: removed `--force-stdout-spec`/`--force-stderr-spec` (they broke CLI/MCP stdio)
- 🔒 **Security: Shell injection fix** — Codex CLI commands converted from `shell=True` string interpolation to safe list-based `subprocess.Popen` (prevents model name / image path injection)
- 🔒 **Security: Path traversal fix** — `upload_file_content` now strips directory components with `os.path.basename()` (prevents writing files outside assets folder)
- 🔒 **Security: XSS fix in asset display** — `displayAssets()` now escapes `file.name` and `file.path` via `escapeHtml()` before innerHTML insertion
- 🔒 **Security: XSS fix in package manager** — PyPI search results and installed package list now escape all metadata (`pkg.name`, `pkg.version`, `pkg.summary`, update warnings) before rendering

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
