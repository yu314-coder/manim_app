"""ManimStudio's adjustments to the terminal shell.

The terminal runs offlinai_shell from python-ios-lib, the shell CodeBench
ships. ManimStudio bundles it as is (python-ios-lib isn't edited from this
repository) and fits it to this app at startup instead: PythonRuntime calls
install() once, before the REPL starts.

* Commands with no backend here are removed, so `help` doesn't list them and
  typing one isn't a wait for an error.
* Commands that need what iOS won't give an app (psutil's native half, a
  process to quit) are replaced.
* Commands that are broken on this build are patched in place.

Each step is applied on its own; one that fails is reported on stderr and the
rest still apply. install-python-stdlib.sh copies this file into the app's
python-metadata/ next to offlinai_shell.py.
"""

import builtins
import contextlib
import functools
import os
import re
import sys
import tempfile
import threading
import time

# The shell's colour codes, copied in install() so output matches.
BOLD = DIM = RED = GRN = YLW = CYN = RESET = ""

_shell = None  # the offlinai_shell module


def install(shell_module):
    global _shell, BOLD, DIM, RED, GRN, YLW, CYN, RESET
    _shell = shell_module
    BOLD, DIM, RED, GRN, YLW, CYN, RESET = (
        getattr(shell_module, name, "")
        for name in ("BOLD", "DIM", "RED", "GRN", "YLW", "CYN", "RESET"))
    for step in (_remove_unsupported, _replace_exit, _replace_top_and_ps,
                 _fix_documents_paths, _fix_missing_imports, _fix_debug, _fix_markdown,
                 _fix_http_fetch, _limit_git, _fit_test_libs, _fit_gpuz,
                 _rebrand_cpuz, _wrap_run_line, _fix_prompt_user):
        try:
            step()
        except Exception as e:
            sys.stderr.write(f"[manimstudio_shell] {step.__name__}: "
                             f"{type(e).__name__}: {e}\n")


def _wrap(name, make):
    """Replace builtin `name` with make(original), if the shell has it."""
    original = _shell.BUILTINS.get(name)
    if original is not None:
        _shell.BUILTINS[name] = make(original)


# ── Commands with no backend ──────────────────────────────────────────

# Command → what to tell someone who types it.
_UNSUPPORTED = {
    # pip: wheels with C extensions can't be built on the device, and the
    # app sandbox has no writable site-packages.
    **dict.fromkeys(("pip", "pip3", "pip-install", "pip-uninstall", "pip-list",
                     "pip-show", "pip-freeze", "pip-check"),
                    "packages come bundled with the app; there's no installer"),
    # ai: CodeBench's local-LLM assistant. offlinai_ai downloads a GGUF
    # model for a Swift LlamaRunner; ManimStudio ships neither. With it
    # gone, PTYBridge's AI mode never switches on either — only offlinai_ai
    # emits the marker that enables it.
    "ai": "there's no local AI model runner",
    # C, C++ and Fortran: the shell hands the source to CodeBench's Swift
    # compiler runtime over $TMPDIR/native_signals and waited 30 s for an
    # answer that never came.
    **dict.fromkeys(("cc", "gcc", "clang", "c++", "g++", "clang++",
                     "gfortran", "f77", "f90", "f95"),
                    "there's no C, C++ or Fortran compiler"),
    # swift: calls CodeBench's cb_swift_execute bridge.
    "swift": "there's no Swift interpreter",
    # debug-gui: steps through CodeBench's editor.
    "debug-gui": "use `debug` to step through a script with pdb",
}


def _remove_unsupported():
    for name in _UNSUPPORTED:
        _shell.BUILTINS.pop(name, None)


def _refuse_unsupported(line):
    """True (after saying why) if `line` runs a removed command. Without
    this, the line fell through to Python and failed with a NameError or
    SyntaxError. Lines that are valid Python (`cc = 5`) still run."""
    words = line.split()
    if not words or words[0] not in _UNSUPPORTED:
        return False
    if len(words) > 1:
        try:
            compile(line, "<shell>", "exec")
            return False
        except SyntaxError:
            pass
    print(f"{RED}{words[0]}:{RESET} not available in ManimStudio — "
          f"{_UNSUPPORTED[words[0]]}.")
    return True


# ── exit / quit ───────────────────────────────────────────────────────

class _Quitter:
    """exit() / quit() for Python code. site's versions close sys.stdin
    before raising SystemExit; the shell reads every later command from
    that stdin, so these only raise."""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"Use {self.name}() or Ctrl-D (i.e. EOF) to exit"

    def __call__(self, code=None):
        raise SystemExit(code)


def _replace_exit():
    # CodeBench's exit / quit end the process with os._exit(), which here
    # would close ManimStudio itself.
    def exit_(sh, argv):
        """exit | quit  — the terminal is part of ManimStudio and stays open."""
        print(f"{DIM}The terminal stays open while ManimStudio runs — switch "
              f"tabs to leave it, or `clear` to wipe the screen.{RESET}")

    _shell.BUILTINS["exit"] = exit_
    _shell.BUILTINS["quit"] = exit_
    builtins.exit = _Quitter("exit")
    builtins.quit = _Quitter("quit")


# ── top, htop, ps ─────────────────────────────────────────────────────
#
# The shell's versions need psutil, whose native half python-ios-lib's App
# Store builds delete (_psutil_osx uses private API, ITMS-90338), so they
# printed "psutil not available". These read public sysctl and Mach task
# info instead. iOS apps can't see other processes, so they show
# ManimStudio's own.

_libc = None


def _c_library():
    global _libc
    if _libc is None:
        import ctypes
        import ctypes.util
        lib = ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib")
        lib.sysctlbyname.argtypes = [ctypes.c_char_p, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_size_t),
                                     ctypes.c_void_p, ctypes.c_size_t]
        lib.sysctlbyname.restype = ctypes.c_int
        lib.task_info.argtypes = [ctypes.c_uint32, ctypes.c_int,
                                  ctypes.c_void_p,
                                  ctypes.POINTER(ctypes.c_uint32)]
        lib.task_info.restype = ctypes.c_int
        _libc = lib
    return _libc


def _sysctl_str(name):
    try:
        import ctypes
        lib = _c_library()
        size = ctypes.c_size_t(0)
        if lib.sysctlbyname(name.encode(), None, ctypes.byref(size), None, 0) != 0 \
                or size.value == 0:
            return ""
        buf = ctypes.create_string_buffer(size.value)
        if lib.sysctlbyname(name.encode(), buf, ctypes.byref(size), None, 0) != 0:
            return ""
        return buf.value.decode("utf-8", "replace")
    except Exception:
        return ""


def _sysctl_u64(name):
    try:
        import ctypes
        value = ctypes.c_uint64(0)
        size = ctypes.c_size_t(8)
        if _c_library().sysctlbyname(name.encode(), ctypes.byref(value),
                                     ctypes.byref(size), None, 0) != 0:
            return 0
        return value.value
    except Exception:
        return 0


def _uptime_seconds():
    # kern.boottime is a struct timeval: 8-byte seconds + 8-byte microseconds.
    try:
        import ctypes
        import struct
        size = ctypes.c_size_t(16)
        buf = ctypes.create_string_buffer(16)
        if _c_library().sysctlbyname(b"kern.boottime", buf, ctypes.byref(size),
                                     None, 0) != 0:
            return 0
        sec, usec = struct.unpack_from("<qq", buf.raw, 0)
        return max(0, time.time() - sec - usec / 1e6)
    except Exception:
        return 0


def _footprint():
    """Memory charged to this process — phys_footprint, the figure jetsam
    and Xcode's memory gauge use — or 0. mach_task_self_ is a variable, so
    it's read, never called."""
    try:
        import ctypes
        import struct
        lib = _c_library()
        task = ctypes.c_uint32.in_dll(lib, "mach_task_self_").value
        words = (ctypes.c_uint32 * 128)()
        count = ctypes.c_uint32(len(words))
        if lib.task_info(task, 22, words, ctypes.byref(count)) != 0:  # TASK_VM_INFO
            return 0
        if count.value < 38:  # phys_footprint arrived in revision 1
            return 0
        return struct.unpack_from("<Q", bytes(words), 144)[0]
    except Exception:
        return 0


def _peak_rss():
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)  # bytes on Darwin
    except Exception:
        return 0


def _fmt_bytes(n):
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def _fmt_uptime(s):
    s = int(s)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _top(sh, argv):
    """top | htop  — device and ManimStudio process stats (one snapshot)."""
    import platform
    import socket
    times = os.times()
    total_ram = _sysctl_u64("hw.memsize")
    ncpu = _sysctl_u64("hw.ncpu") or _sysctl_u64("hw.activecpu")
    machine = _sysctl_str("hw.machine") or platform.machine() or "—"
    try:
        host = socket.gethostname() or "device"
    except Exception:
        host = "device"
    uptime = _uptime_seconds()
    footprint, peak = _footprint(), _peak_rss()

    print(f"{BOLD}ManimStudio · top{RESET}  {DIM}{host} ({machine}){RESET}")
    print(f"{DIM}OS{RESET}         {platform.platform()}")
    if uptime > 0:
        print(f"{DIM}Uptime{RESET}     {_fmt_uptime(uptime)}")
    if ncpu:
        print(f"{DIM}CPUs{RESET}       {ncpu}")
    if total_ram:
        print(f"{DIM}RAM total{RESET}  {_fmt_bytes(total_ram)}")
    print("")
    print(f"{BOLD}This process{RESET}")
    print(f"{DIM}PID{RESET}        {os.getpid()}")
    if footprint:
        print(f"{DIM}Memory{RESET}     {GRN}{_fmt_bytes(footprint)}{RESET}")
    if peak:
        print(f"{DIM}RSS peak{RESET}   {GRN}{_fmt_bytes(peak)}{RESET}")
    print(f"{DIM}CPU time{RESET}   {CYN}user {times.user:.2f}s · sys "
          f"{times.system:.2f}s (total {times.user + times.system:.2f}s){RESET}")
    print(f"{DIM}Threads{RESET}    {threading.active_count()} Python")


def _ps(sh, argv):
    """ps  — ManimStudio's process and its Python threads.

    iOS apps can't see other processes, so this lists the one running the
    editor, the renders and this terminal."""
    times = os.times()
    minutes, seconds = divmod(times.user + times.system, 60)
    memory = _footprint() or _peak_rss()
    print(f"{BOLD}{'PID':>7}  {'TIME':>9}  {'MEM':>10}  COMMAND{RESET}")
    print(f"{os.getpid():>7}  {int(minutes):>3}:{seconds:05.2f}  "
          f"{_fmt_bytes(memory) if memory else '—':>10}  ManimStudio")
    threads = threading.enumerate()
    current = threading.current_thread()
    print(f"\n{BOLD}Python threads ({len(threads)}){RESET}")
    for thread in threads:
        notes = [n for n, on in (("this shell", thread is current),
                                  ("daemon", thread.daemon)) if on]
        print(f"  {thread.native_id or '?':>8}  {thread.name}"
              + (f"  {DIM}({', '.join(notes)}){RESET}" if notes else ""))


def _replace_top_and_ps():
    _shell.BUILTINS["top"] = _top
    _shell.BUILTINS["htop"] = _top
    _shell.BUILTINS["ps"] = _ps


# ── Documents paths ───────────────────────────────────────────────────
#
# PythonRuntime points HOME at Documents, so `~` is writable for user code.
# The shell was written for iOS's own HOME, the container root, and spells
# the Documents folder "~/Documents" — here that's Documents/Documents.

@contextlib.contextmanager
def _container_home():
    """HOME as iOS sets it, for shell code that says ~/Documents."""
    home = os.environ.get("HOME", "").rstrip("/")
    if os.path.basename(home) != "Documents":
        yield
        return
    os.environ["HOME"] = os.path.dirname(home)
    try:
        yield
    finally:
        os.environ["HOME"] = home


def _fix_documents_paths():
    # The shell starts in ~/Documents/Workspace when that exists, and
    # `reveal` created it (Documents/Documents/Workspace), so after one
    # reveal the terminal opened in that nested folder instead of the
    # Workspace PythonRuntime had just moved it to.
    home = os.path.expanduser("~")
    workspace = os.path.join(home, "Workspace")
    try:
        if os.path.samefile(os.getcwd(), os.path.join(home, "Documents", "Workspace")) \
                and os.path.isdir(workspace):
            os.chdir(workspace)
    except OSError:
        pass

    # reveal copies into ~/Documents/Workspace: the Workspace the Files app
    # shows, not a nested one.
    def make(original):
        @functools.wraps(original)
        def reveal(sh, argv):
            with _container_home():
                return original(sh, argv)
        return reveal
    _wrap("reveal", make)


# ── Names the shell uses without importing ────────────────────────────

def _fix_missing_imports():
    # `nb` / `notebook` / `ipynb` stopped with "name 'tempfile' is not
    # defined", and `cd /tmp` would too: those paths use a module-level
    # `tempfile` the shell never imports.
    if not hasattr(_shell, "tempfile"):
        _shell.tempfile = tempfile


# ── debug ─────────────────────────────────────────────────────────────

def _pdb_with_runscript():
    """`debug` runs the script with Pdb._runscript, which Python 3.11 folded
    into Pdb._run, so it failed with AttributeError. This supplies one with
    _run's steps, except that the script gets its own namespace: _run
    empties the real __main__, which here holds the app's interpreter state."""
    import pdb
    if hasattr(pdb.Pdb, "_runscript"):
        return

    def _runscript(self, filename):
        filename = os.path.abspath(filename)
        with open(filename, "rb") as f:
            code = compile(f.read(), filename, "exec")
        namespace = {"__name__": "__main__", "__file__": filename,
                     "__builtins__": builtins}
        # Stop on the script's first line, not inside the exec machinery.
        self._wait_for_mainpyfile = True
        self._user_requested_quit = False
        self.mainpyfile = self.canonic(filename)
        self.run(code, namespace, namespace)

    pdb.Pdb._runscript = _runscript


def _fix_debug():
    def make(original):
        @functools.wraps(original)
        def debug(sh, argv):
            _pdb_with_runscript()
            return original(sh, argv)
        return debug
    _wrap("debug", make)


# ── md / nb ───────────────────────────────────────────────────────────

def _markdown_without_linkify():
    """md and nb render with markdown-it's "gfm-like" preset, which turns
    linkify on. linkify-it-py isn't bundled, so rendering stopped with
    "Linkify enabled but not installed": the shell leaves the option out
    when linkify-it is missing, but then the preset's own True stands."""
    try:
        import linkify_it  # noqa: F401
        return
    except ImportError:
        pass
    from markdown_it import main
    for preset in main._PRESETS.values():
        preset.get("options", {})["linkify"] = False


def _fix_markdown():
    def make(original):
        @functools.wraps(original)
        def render(sh, argv):
            _markdown_without_linkify()
            return original(sh, argv)
        return render
    for name in ("md", "markdown", "nb", "notebook", "ipynb"):
        _wrap(name, make)


# ── curl / wget ───────────────────────────────────────────────────────

def _http_fetch(method, url, headers, data, follow, out_path, silent, max_show=4096):
    """Shared HTTP transport for wget / curl. Returns exit code.

    The shell's version read the whole body into memory before showing
    4 KB of it, twice over (bytes, then text): `curl` on a large file — a
    model download, say — peaked at 4.4x the file size and could take the
    app down. This one streams: to disk with -o / -O as before, and to the
    screen it reads only what it shows."""
    try:
        import requests
    except ImportError:
        print(f"{RED}http:{RESET} `requests` not available")
        return 1
    try:
        r = requests.request(method.upper(), url, headers=headers, data=data,
                             allow_redirects=follow, stream=True, timeout=30)
    except requests.RequestException as e:
        print(f"{RED}http:{RESET} {e}")
        return 1
    with r:
        if out_path:
            if not silent:
                print(f"{DIM}{r.status_code} {r.reason}  "
                      f"{r.headers.get('content-length', '?')} bytes{RESET}")
            written = 0
            try:
                with open(os.path.expanduser(out_path), "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)
            except OSError as e:
                print(f"{RED}http:{RESET} cannot write {out_path}: {e}")
                return 1
            except requests.RequestException as e:
                print(f"{RED}http:{RESET} {e}")
                return 1
            if not silent:
                print(f"  saved {_fmt_bytes(written)} → {out_path}")
        else:
            head = bytearray()
            try:
                for chunk in r.iter_content(chunk_size=16 * 1024):
                    head += chunk
                    if len(head) > max_show:
                        break
            except requests.RequestException as e:
                print(f"{RED}http:{RESET} {e}")
                return 1
            complete = len(head) <= max_show
            if not silent:
                size = (len(head) if complete
                        else r.headers.get("content-length") or f"more than {max_show}")
                print(f"{DIM}{r.status_code} {r.reason}  {size} bytes{RESET}")
            shown = bytes(head[:max_show])
            if b"\x00" in shown:
                print(f"{DIM}(binary data — use -o FILE to save it){RESET}")
            else:
                charset = requests.utils.get_encoding_from_headers(r.headers)
                content_type = r.headers.get("content-type", "")
                if "charset" not in content_type.lower():
                    charset = "utf-8"
                try:
                    text = shown.decode(charset or "utf-8", errors="replace")
                except LookupError:
                    text = shown.decode("utf-8", errors="replace")
                sys.stdout.write(text)
                if not complete:
                    print(f"\n{DIM}… truncated after {max_show} bytes "
                          f"(use -o FILE to save the rest){RESET}")
                elif not text.endswith("\n"):
                    sys.stdout.write("\n")
    return 0 if r.status_code < 400 else 1


def _fix_http_fetch():
    _shell._http_fetch = _http_fetch


# ── git ───────────────────────────────────────────────────────────────

def _limit_git():
    # Only `clone` is built in: it downloads the repository snapshot (a
    # zipball) without .git history. Every other subcommand needs dulwich,
    # which the shell tries to pip-install, and there's no pip here.
    def make(original):
        def git(sh, argv):
            """git clone <url> [dir]  — download a repository's files.

            Fetches the snapshot GitHub, GitLab, Bitbucket, Codeberg and Gitea
            serve as a zip: the files, without .git history. Other git
            subcommands aren't available in ManimStudio."""
            sub = argv[0] if argv else ""
            if sub == "clone":
                return original(sh, argv)
            if sub and sub != "help" and not _shell._is_help_tok(sub):
                print(f"{RED}git {sub}:{RESET} not available in ManimStudio — only "
                      f"`git clone` is, and it downloads the files without the "
                      f".git history.")
                return
            print("usage: git clone <url> [dir]")
            print(f"{DIM}  Downloads the repository's files (GitHub, GitLab, Bitbucket, "
                  f"Codeberg, Gitea), without .git history.{RESET}")
        return git
    _wrap("git", make)


# ── test-libs ─────────────────────────────────────────────────────────

# Libraries test_libs checks that ManimStudio has never shipped: CodeBench's
# ML stack and its LLM assistant.
_NOT_SHIPPED = {"torch", "tokenizers", "transformers", "huggingface_hub",
                "safetensors", "offlinai_ai"}


def _skip_psutil():
    # top and ps don't need it (see _replace_top_and_ps).
    return "SKIP: native module not shipped (App Store)"


def _process_probe():
    """test_libs' per-library memory / CPU columns, without psutil."""
    ncpu = os.cpu_count() or 1
    last = [time.perf_counter(), sum(os.times()[:2])]

    def snapshot():
        now, cpu = time.perf_counter(), sum(os.times()[:2])
        wall = now - last[0]
        percent = (cpu - last[1]) / wall * 100 if wall > 0 else 0.0
        last[:] = [now, cpu]
        memory = _footprint()
        if not memory:
            return None
        return {"rss": memory, "cpu": percent,
                "thr": threading.active_count(), "ncpu": ncpu}
    return snapshot


def _fit_test_libs():
    # The command imports test_libs, which ManimStudio now bundles
    # (install-python-stdlib.sh). Its list includes libraries ManimStudio
    # doesn't ship, and psutil, which can't import without its native
    # half; those would only ever read as failures.
    def make(original):
        def test_libs(sh, argv):
            """test-libs [name|category…]  — smoke-test the bundled libraries.

            Imports each library ManimStudio ships, makes one cheap call, and
            prints PASS / FAIL / SKIP per library with timing and memory. Name
            libraries or categories to run just those:
                test-libs numpy manim
                test-libs viz media
            Categories: numerical, viz, media, web, util, manim-dep, custom."""
            import importlib
            sys.modules.pop("test_libs", None)
            try:
                tl = importlib.import_module("test_libs")
            except ImportError as e:
                print(f"{RED}test-libs:{RESET} can't import test_libs: {e}")
                return
            tl.TESTS[:] = [(cat, name, _skip_psutil if name == "psutil" else fn)
                           for cat, name, fn in tl.TESTS if name not in _NOT_SHIPPED]
            tl._make_process_probe = _process_probe
            try:
                rc = tl.main(["test-libs"] + list(argv))
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else (1 if e.code else 0)
            except KeyboardInterrupt:
                print(f"\n{YLW}^C{RESET} (test run aborted; partial results above)")
                return
            if rc:
                print(f"{YLW}test-libs exited with code {rc}{RESET}")
        return test_libs
    _wrap("test-libs", make)
    _wrap("test_libs", make)


# ── gpu-z / cpu-z ─────────────────────────────────────────────────────

class _RewritingStream:
    def __init__(self, stream, replacements):
        self._stream = stream
        self._replacements = replacements

    def write(self, text):
        if isinstance(text, str):
            for old, new in self._replacements:
                text = text.replace(old, new)
        return self._stream.write(text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


@contextlib.contextmanager
def _rewriting_stdout(*replacements):
    # These commands write their header with sys.stdout.write, which the
    # CodeBench → ManimStudio rename on print() doesn't see.
    saved = sys.stdout
    sys.stdout = _RewritingStream(saved, replacements)
    try:
        yield
    finally:
        sys.stdout = saved


def _fit_gpuz():
    # The benchmark half needs torch and CodeBench's Metal bridge, so after
    # the device table it failed on the torch import. Show the table only,
    # which is what `gpu-z -i` does.
    def make(original):
        def gpuz(sh, argv):
            """gpu-z  — Metal GPU information: device, family, memory."""
            with _rewriting_stdout(
                    ("CodeBench edition — Metal device + live benchmark", "Metal device"),
                    ("CodeBench edition", "ManimStudio edition")):
                return original(sh, [a for a in argv if a != "-i"] + ["-i"])
        return gpuz
    _wrap("gpu-z", make)
    _wrap("gpuz", make)


def _rebrand_cpuz():
    def make(original):
        @functools.wraps(original)
        def cpuz(sh, argv):
            with _rewriting_stdout(("CodeBench edition", "ManimStudio edition")):
                return original(sh, argv)
        return cpuz
    _wrap("cpu-z", make)
    _wrap("cpuz", make)


# ── Command lines: $VAR expansion, removed commands ───────────────────

_VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")


def _expand(line):
    """Expand $NAME and ${NAME} from the environment the way sh does: not
    inside single quotes or after a backslash; unset names expand to
    nothing. Outside double quotes the value is quoted, so it stays one
    word."""
    import shlex
    out = []
    i, single, double = 0, False, False
    while i < len(line):
        ch = line[i]
        if ch == "\\" and not single:
            out.append(line[i:i + 2])
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif ch == "$" and not single:
            m = _VARIABLE.match(line, i)
            if m:
                value = os.environ.get(m.group(1) or m.group(2), "")
                if double:
                    out.append(value.replace("\\", "\\\\").replace('"', '\\"'))
                else:
                    out.append(shlex.quote(value) if value else "")
                i = m.end()
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _wrap_run_line():
    # The shell tokenizes with shlex, which doesn't expand variables, so
    # `echo $HOME` printed "$HOME". Lines for shell commands are expanded
    # first; anything else is Python and is left alone. Removed commands
    # are answered here too (see _refuse_unsupported).
    shell_class = _shell.Shell
    run_line = shell_class.run_line

    @functools.wraps(run_line)
    def adjusted_run_line(self, line):
        if not self.pending:
            if _refuse_unsupported(line):
                return
            if "$" in line:
                words = line.split(maxsplit=1)
                head = words[0] if words else ""
                head = self.aliases.get(head, head).split(maxsplit=1)[0] if head else ""
                if head in _shell.BUILTINS:
                    line = _expand(line)
        return run_line(self, line)

    shell_class.run_line = adjusted_run_line


# ── Prompt ────────────────────────────────────────────────────────────

def _fix_prompt_user():
    # The prompt read "codebench@<host>": the shell's fallback when USER and
    # LOGNAME are unset, as they are in an iOS app. Use the name `whoami`
    # prints instead.
    sh = getattr(_shell, "shell", None)
    if sh is None or getattr(sh, "user", None) != "codebench":
        return
    try:
        import getpass
        sh.user = getpass.getuser() or "mobile"
    except Exception:
        sh.user = "mobile"
