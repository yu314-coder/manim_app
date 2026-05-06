"""bootstrap_macos.py — entry point loaded by PythonHost.swift.

Boots the desktop app's `app` module on macOS by:

1. Applying platform shims (winpty / cmd.exe / Windows path quirks
   the Windows build assumes) BEFORE importing app — so app.py
   itself stays unmodified across platforms.
2. Importing `app` and instantiating its `App` class. The instance
   becomes module-level `api`, which PythonHost looks up by name
   for every JS `pywebview.api.<method>(*args)` call.
3. Skipping PyWebView's own window construction — we don't need it,
   the WKWebView shell handles the UI layer.

Why a separate file (rather than editing app.py): keeping
`PythonApp/app.py` byte-identical to `main`'s app.py means future
desktop updates merge cleanly. All macOS-isms live here.
"""
from __future__ import annotations

import os
import sys
import io
import platform
import traceback


# Module-level handle the Swift IPC dispatcher reads.
api: object | None = None


# ── Step 1. Platform shims ──────────────────────────────────────

def _install_pty_shim():
    """Replace `winpty` with a thin wrapper around `pty.openpty()`.

    The desktop app imports `winpty` for the integrated terminal.
    On macOS we provide a compatibility module that exposes the
    same `PtyProcess.spawn(...)` API but uses Apple's openpty +
    posix_spawn. Registered via sys.modules before app.py imports
    it, so the import succeeds without code changes.
    """
    if "winpty" in sys.modules:
        return
    try:
        import pty as _stdlib_pty
        import subprocess as _sp
        import select as _select
        import fcntl as _fcntl
        import termios as _termios
        import struct as _struct
    except Exception:
        return  # let the app fall back to its non-PTY path

    class _PtyProcess:
        def __init__(self, cmd, **kwargs):
            self._master, slave = _stdlib_pty.openpty()
            # Inherit child stdin/stdout/stderr from the slave end.
            argv = cmd if isinstance(cmd, (list, tuple)) else [cmd]
            self._proc = _sp.Popen(
                argv,
                stdin=slave, stdout=slave, stderr=slave,
                close_fds=True,
                preexec_fn=os.setsid,
                env=kwargs.get("env"),
                cwd=kwargs.get("cwd"))
            os.close(slave)

        @property
        def pid(self): return self._proc.pid
        def isalive(self): return self._proc.poll() is None

        def read(self, n=4096):
            r, _, _ = _select.select([self._master], [], [], 0.05)
            if not r:
                return b""
            try:
                return os.read(self._master, n)
            except OSError:
                return b""

        def write(self, data):
            if isinstance(data, str): data = data.encode("utf-8", "replace")
            return os.write(self._master, data)

        def setwinsize(self, rows, cols):
            try:
                _fcntl.ioctl(self._master, _termios.TIOCSWINSZ,
                             _struct.pack("HHHH", rows, cols, 0, 0))
            except OSError:
                pass

        def terminate(self, force=False):
            try:
                self._proc.terminate()
                if force:
                    self._proc.kill()
            except Exception:
                pass

        def close(self):
            try: os.close(self._master)
            except OSError: pass
            self.terminate(force=True)

        @classmethod
        def spawn(cls, cmd, **kwargs):
            return cls(cmd, **kwargs)

    _shim = type(sys)("winpty")
    _shim.PtyProcess = _PtyProcess
    sys.modules["winpty"] = _shim
    print("[bootstrap_macos] winpty shim installed (uses pty.openpty)",
          file=sys.stderr)


def _install_default_shell():
    """Make sure code paths that look up `cmd.exe` find an
    interactive `/bin/zsh -i` instead. The Windows build hardcodes
    `cmd.exe`/`COMSPEC` in a few subprocess.Popen sites.
    """
    os.environ.setdefault("COMSPEC", "/bin/zsh")
    os.environ.setdefault("SHELL",   "/bin/zsh")


def _install_pywebview_stub():
    """Provide a no-op `webview` module so app.py's
    `import webview` succeeds. The real PyWebView container is
    replaced by our WKWebView shell — we just need the import to
    not fail and the methods app.py calls (create_window, start,
    create_file_dialog, …) to be either no-ops or routed to native
    AppKit dialogs through the JS bridge.
    """
    if "webview" in sys.modules:
        return
    mod = type(sys)("webview")

    class _DummyWindow:
        title = "ManimStudio"
        def evaluate_js(self, js, callback=None):
            # Posting JS back to the WebView from Python — when
            # PythonHost.dispatch runs on its queue, it can't easily
            # call back into the WKWebView. The simplest path: stash
            # the JS into a queue Swift drains. For now no-op; we'll
            # wire the back-channel when the first feature needs it.
            return None
        def load_url(self, url): pass
        def destroy(self): pass

    def _create_window(*a, **kw):
        return _DummyWindow()

    def _start(*a, **kw): pass
    def _create_file_dialog(*a, **kw): return None

    # Match PyWebView's enum surface where app.py imports it.
    class _FileDialog:
        OPEN = 0
        OPEN_MULTIPLE = 1
        SAVE = 2
        FOLDER = 3

    mod.create_window = _create_window
    mod.start = _start
    mod.create_file_dialog = _create_file_dialog
    mod.FileDialog = _FileDialog
    mod.token = "macos"
    sys.modules["webview"] = mod
    print("[bootstrap_macos] webview stub installed", file=sys.stderr)


# ── Step 2. Boot ────────────────────────────────────────────────

def boot():
    """Top-level entry called by PythonHost after Py_Initialize.
    Idempotent.
    """
    global api
    if api is not None:
        return

    print(f"[bootstrap_macos] Python {platform.python_version()} on "
          f"{platform.machine()}/{platform.system()}", file=sys.stderr)

    # Order matters — shims must be in sys.modules BEFORE the app
    # module's `import winpty` / `import webview` runs.
    _install_pty_shim()
    _install_default_shell()
    _install_pywebview_stub()

    try:
        import app as _app  # noqa: F401  — main-branch app.py, unmodified
    except Exception:
        traceback.print_exc()
        return

    # The Windows app constructs a single API instance, usually as
    # part of `webview.create_window(js_api=App())`. Different
    # builds spell the class differently — try the common names.
    for cls_name in ("App", "Api", "ManimStudioApp", "ManimStudio"):
        cls = getattr(_app, cls_name, None)
        if cls is None: continue
        try:
            api = cls()
            print(f"[bootstrap_macos] api instance: app.{cls_name}",
                  file=sys.stderr)
            return
        except Exception:
            traceback.print_exc()

    # Fallback — expose the module itself so getattr() lookups still
    # find module-level functions like app.render_scene(...).
    api = _app
    print("[bootstrap_macos] api fallback: app module (no class found)",
          file=sys.stderr)
