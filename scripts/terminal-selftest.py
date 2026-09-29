# terminal-selftest.py — run every ManimStudio terminal command once.
#
# Copy it into the app's Documents/Workspace (Files app, or on the Simulator
# `xcrun simctl get_app_container <udid> euleryu.ManimStudio data`), then in
# the ManimStudio terminal:
#     exec(open('terminal-selftest.py').read())
# Each case runs with a stdin of "q" lines and a timeout; the report goes to
# terminal-selftest.json next to it. On the Simulator numpy, scipy, manim and
# friends fail to import (no simulator builds), so check those on a device.
import os, sys, io, json, time, shutil, tempfile, threading, traceback, ctypes, base64
import zipfile, tarfile, gzip
import offlinai_shell as S

WS = os.getcwd()
OUT = os.path.join(WS, "terminal-selftest.json")
BOX = os.path.join(WS, "_selftest")
shutil.rmtree(BOX, ignore_errors=True)
os.makedirs(os.path.join(BOX, "sub", "deeper"), exist_ok=True)

def _w(name, text):
    with open(os.path.join(BOX, name), "w") as f:
        f.write(text)

_w("a.txt", "alpha\nbeta\ngamma\nbeta\nfoo bar\n")
_w("b.txt", "alpha\nBETA\ngamma\n")
_w("csv.txt", "x,1\ny,2\nz,3\n")
_w("sub/deeper/n.txt", "nested\n")
_w("gz_me.txt", "compress me\n")
_w("b64.txt", base64.b64encode(b"hello base64\n").decode() + "\n")
_w("t.py", "print('py-ok', 6*7)\n")
_w("t.js", "console.log('js-ok', 6*7);\n")
_w("t.c", '#include <stdio.h>\nint main(void){ printf("c-ok %d\\n", 6*7); return 0; }\n')
_w("t.cpp", '#include <iostream>\nint main(){ std::cout << "cpp-ok " << 6*7 << std::endl; return 0; }\n')
_w("t.f90", "program t\n  print *, 'f-ok', 6*7\nend program t\n")
_w("t.swift", 'print("swift-ok", 6*7)\n')
_w("t.tex", "\\documentclass{article}\n\\begin{document}\nHello $x^2$\n\\end{document}\n")
_w("p.tex", "Hello plain \\TeX.\n\\bye\n")
_w("t.md", "# Title\n\nSome *text* and `code`.\n")
_w("t.ipynb", json.dumps({"cells": [{"cell_type": "code", "source": ["print('nb-ok')"],
                                      "metadata": {}, "outputs": [], "execution_count": None}],
                          "metadata": {}, "nbformat": 4, "nbformat_minor": 5}))
_w("m.py", "from manim import *\nclass M(Scene):\n    def construct(self):\n        self.add(Dot())\n")
with open(os.path.join(BOX, "blob.bin"), "wb") as f:
    f.write(bytes(range(256)) * 16)
with zipfile.ZipFile(os.path.join(BOX, "z.zip"), "w") as z:
    z.writestr("inzip.txt", "zipped\n")
with tarfile.open(os.path.join(BOX, "t.tar"), "w") as t:
    t.add(os.path.join(BOX, "a.txt"), arcname="intar.txt")
with gzip.open(os.path.join(BOX, "g.txt.gz"), "wb") as g:
    g.write(b"gzipped\n")

PID = os.getpid()
NET, SLOW, VSLOW = 45, 150, 300
# (command it covers, line to run, timeout seconds, working dir under BOX)
CASES = [
    ("help", "help", 20, ""), ("help", "help ls", 20, ""),
    ("pwd", "pwd", 20, ""), ("cd", "cd sub", 20, ""),
    ("ls", "ls", 20, ""), ("ls", "ls -lah sub", 20, ""),
    ("cat", "cat a.txt", 20, ""),
    ("head", "head -n 2 a.txt", 20, ""), ("tail", "tail -n 2 a.txt", 20, ""),
    ("mkdir", "mkdir -p newdir/inner", 20, ""), ("rm", "rm -r newdir", 20, ""),
    ("mkdir", "mkdir emptyd", 20, ""), ("rmdir", "rmdir emptyd", 20, ""),
    ("touch", "touch t1.txt", 20, ""), ("cp", "cp a.txt c.txt", 20, ""),
    ("mv", "mv c.txt d.txt", 20, ""),
    ("reveal", "reveal --copy a.txt ms_selftest_revealed.txt", 20, ""),
    ("echo", "echo hello world", 20, ""),
    ("export", "export MS_SELFTEST=42", 20, ""), ("env", "env", 20, ""),
    ("echo", "echo $MS_SELFTEST", 20, ""),
    ("which", "which ls", 20, ""), ("which", "which python", 20, ""),
    ("date", "date", 20, ""), ("uptime", "uptime", 20, ""),
    ("clear", "clear", 20, ""), ("cls", "cls", 20, ""),
    ("grep", "grep beta a.txt", 20, ""), ("grep", "grep -i BETA b.txt", 20, ""),
    ("find", "find . -name '*.txt'", 20, ""), ("tree", "tree", 20, ""),
    ("wc", "wc a.txt", 20, ""), ("history", "history", 20, ""),
    ("python", "python t.py", 30, ""), ("python", 'python -c "print(6*7)"', 30, ""),
    ("python3", "python3 --version", 30, ""),
    ("js", "js t.js", 30, ""), ("node", 'node -e "console.log(6*7)"', 30, ""),
    ("du", "du -s -h .", 20, ""), ("df", "df", 20, ""),
    ("ncdu", "ncdu .", 20, ""), ("stat", "stat a.txt", 20, ""),
    ("man", "man ls", 20, ""),
    ("cc", "cc t.c", 60, ""), ("gcc", "gcc t.c", 60, ""), ("clang", "clang t.c", 60, ""),
    ("c++", "c++ t.cpp", 60, ""), ("g++", "g++ t.cpp", 60, ""), ("clang++", "clang++ t.cpp", 60, ""),
    ("gfortran", "gfortran t.f90", 60, ""), ("f77", "f77 t.f90", 60, ""),
    ("f90", "f90 t.f90", 60, ""), ("f95", "f95 t.f90", 60, ""),
    ("swift", "swift t.swift", 60, ""),
    ("debug", "debug t.py", 30, ""),
    ("nb", "nb t.ipynb", 60, ""), ("ipynb", "ipynb t.ipynb", 60, ""),
    ("notebook", "notebook t.ipynb", 60, ""),
    ("repl", "repl", 30, ""), ("debug-gui", "debug-gui t.py", 30, ""),
    ("md", "md t.md", 30, ""), ("markdown", "markdown t.md", 30, ""),
    ("pdflatex", "pdflatex t.tex", 90, ""), ("latex", "latex t.tex", 90, ""),
    ("tex", "tex p.tex", 90, ""), ("pdftex", "pdftex p.tex", 90, ""),
    ("xelatex", "xelatex t.tex", 30, ""), ("latex-diagnose", "latex-diagnose", 60, ""),
    ("cpu-z", "cpu-z", SLOW, ""), ("cpuz", "cpuz", SLOW, ""),
    ("gpu-z", "gpu-z", SLOW, ""), ("gpuz", "gpuz", SLOW, ""),
    ("top", "top", 30, ""), ("htop", "htop", 30, ""),
    ("git", "git clone https://github.com/octocat/Hello-World.git hw", NET * 2, ""),
    ("git", "git status", 30, "hw"), ("git", "git log", 30, "hw"),
    ("ping", "ping -c 2 example.com", NET, ""),
    ("wget", "wget -q -O w.html https://example.com", NET, ""),
    ("curl", "curl -s https://example.com", NET, ""),
    ("curl", "curl -L -o c.html https://example.com", NET, ""),
    ("zip", "zip mine.zip a.txt b.txt", 20, ""),
    ("unzip", "unzip -l z.zip", 20, ""), ("unzip", "unzip -d uz z.zip", 20, ""),
    ("tar", "tar -tf t.tar", 20, ""), ("tar", "tar -cf mine.tar a.txt", 20, ""),
    ("tar", "tar -xf t.tar", 20, ""),
    ("7z", "7z l z.zip", 30, ""), ("7z", "7z x z.zip -o7x", 30, ""),
    ("extract", "extract z.zip -oex", 30, ""), ("unar", "unar t.tar -oua", 30, ""),
    ("binwalk", "binwalk blob.bin", 30, ""),
    ("simg2img", "simg2img nosuch.img out.img", 20, ""),
    ("gzip", "gzip gz_me.txt", 20, ""), ("gunzip", "gunzip g.txt.gz", 20, ""),
    ("manim", "manim -ql m.py M", VSLOW, ""),
    ("base64", "base64 a.txt", 20, ""), ("base64", "base64 -d b64.txt", 20, ""),
    ("sha256sum", "sha256sum a.txt", 20, ""), ("sha1sum", "sha1sum a.txt", 20, ""),
    ("md5sum", "md5sum a.txt", 20, ""),
    ("uname", "uname -a", 20, ""), ("whoami", "whoami", 20, ""),
    ("hostname", "hostname", 30, ""),
    ("sort", "sort a.txt", 20, ""), ("sort", "sort -r -u a.txt", 20, ""),
    ("uniq", "uniq -c a.txt", 20, ""), ("tr", "tr a-z A-Z", 20, ""),
    ("seq", "seq 1 5", 20, ""), ("seq", "seq 1 2 9", 20, ""),
    ("yes", "yes ok", 20, ""), ("sleep", "sleep 0.2", 20, ""),
    ("time", "time ls", 20, ""),
    ("crash-log", "crash-log --path", 20, ""), ("crashlog", "crashlog --tail 3", 20, ""),
    ("test_libs", "test_libs requests", 60, ""), ("test-libs", "test-libs", VSLOW, ""),
    ("nproc", "nproc", 20, ""), ("id", "id", 20, ""),
    ("basename", "basename /a/b/c.txt .txt", 20, ""), ("dirname", "dirname /a/b/c.txt", 20, ""),
    ("realpath", "realpath a.txt", 20, ""),
    ("file", "file a.txt blob.bin z.zip", 20, ""),
    ("mktemp", "mktemp", 20, ""), ("mktemp", "mktemp -d", 20, ""),
    ("nl", "nl a.txt", 20, ""), ("tac", "tac a.txt", 20, ""), ("rev", "rev a.txt", 20, ""),
    ("cut", "cut -d , -f 1 csv.txt", 20, ""), ("tee", "tee teeout.txt", 20, ""),
    ("diff", "diff a.txt b.txt", 20, ""),
    ("xxd", "xxd a.txt", 20, ""), ("hexdump", "hexdump a.txt", 20, ""),
    ("bc", "bc 2+3*4", 20, ""), ("cal", "cal", 20, ""), ("cal", "cal 2 2027", 20, ""),
    ("ps", "ps", 20, ""), ("kill", "kill", 20, ""), ("kill", f"kill -0 {PID}", 20, ""),
    ("watch", "watch -n 0.1 date", 25, ""),
    ("less", "less a.txt", 20, ""), ("more", "more a.txt", 20, ""),
    ("(python)", "print('fallthrough-ok', 1+1)", 20, ""),
    ("(python)", "import math; print(round(math.pi, 4))", 20, ""),
    ("(unknown)", "notacommand123", 20, ""),
    # ── round 2: the fixes ──
    ("exit", "exit", 20, ""), ("quit", "quit", 20, ""),
    ("(python)", 'python -c "exit()"', 20, ""), ("echo", "echo still-alive", 20, ""),
    ("echo", 'echo "$HOME" / $MS_SELFTEST / \'$HOME\' / ${MS_SELFTEST}x / $NOPE_UNSET.', 20, ""),
    ("cd", "cd /tmp", 20, ""),
    ("git", "git status", 20, ""), ("git", "git", 20, ""),
    ("cc", "cc t.c", 20, ""), ("(python)", "cc = 5; print('cc-var', cc)", 20, ""),
    ("js", 'js -e "[1,2,3].map(x => x * 2)"', 30, ""),
    ("js", 'js -e "globalThis.keep = 41"', 30, ""), ("js", 'js -e "keep + 1"', 30, ""),
    ("js", 'js -e "setTimeout(() => console.log(\'timer-ok\'), 50); \'sync-first\'"', 30, ""),
    ("js", 'js -e "Promise.resolve(5).then(v => console.log(\'promise\', v))"', 30, ""),
    ("js", 'js -e "const fs = require(\'fs\'); fs.writeFileSync(\'jsw.txt\', \'fs-ok\'); fs.readFileSync(\'jsw.txt\')"', 30, ""),
    ("js", 'js -e "require(\'path\').join(\'a\', \'../b\', \'c.txt\')"', 30, ""),
    ("js", 'js -e "throw new TypeError(\'boom\')"', 30, ""),
    ("js", 'js -e "fetch(\'https://example.com\').then(r => r.text()).then(t => console.log(\'fetched\', t.length))"', NET, ""),
    ("js", 'js -e "console.log({a: [1, {b: \'x\'}], m: new Map([[1, 2]])})"', 30, ""),
    ("node", 'node -e "process.exit(0)"', 30, ""), ("js", "js --reset", 30, ""),
    ("js", 'js -e "typeof keep"', 30, ""),
]
SKIPPED = {}

def _run_case(line, timeout, cwd):
    os.chdir(os.path.join(BOX, cwd) if cwd else BOX)
    r, w = os.pipe(); os.write(w, b"q\n" * 8); os.close(w)       # stdin: q lines, then EOF
    saved_in, saved_out, saved_err = os.dup(0), os.dup(1), os.dup(2)
    os.dup2(r, 0); os.close(r)
    tf = tempfile.TemporaryFile()
    os.dup2(tf.fileno(), 1); os.dup2(tf.fileno(), 2)
    py_out = io.TextIOWrapper(io.FileIO(os.dup(tf.fileno()), "wb"), encoding="utf-8",
                              errors="replace", write_through=True)
    py_in = io.TextIOWrapper(io.FileIO(os.dup(0), "rb"), encoding="utf-8", errors="replace")
    old = (sys.stdin, sys.stdout, sys.stderr)
    sys.stdin, sys.stdout, sys.stderr = py_in, py_out, py_out
    res = {"status": "running"}
    def target():
        try:
            S.run_line(line); res["status"] = "returned"
        except SystemExit as e:
            res["status"] = f"SystemExit({e.code})"
        except BaseException as e:
            res["status"] = "EXC"; res["tb"] = traceback.format_exc()[-2000:]
    t0 = time.time()
    th = threading.Thread(target=target, daemon=True); th.start(); th.join(timeout)
    if th.is_alive():
        res["status"] = "TIMEOUT"
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(th.ident),
                                                   ctypes.py_object(KeyboardInterrupt))
        th.join(3)
        if th.is_alive(): res["status"] = "TIMEOUT-STUCK"
    res["seconds"] = round(time.time() - t0, 2)
    try: py_out.flush()
    except Exception: pass
    sys.stdin, sys.stdout, sys.stderr = old
    os.dup2(saved_out, 1); os.dup2(saved_err, 2); os.dup2(saved_in, 0)
    for fd in (saved_in, saved_out, saved_err): os.close(fd)
    for f in (py_in, py_out):
        try: f.close()
        except Exception: pass
    tf.seek(0); out = tf.read().decode("utf-8", "replace"); tf.close()
    res["output"] = out if len(out) <= 3000 else out[:2200] + "\n…[truncated]…\n" + out[-700:]
    res["output_len"] = len(out)
    return res

results = []
t_all = time.time()
for i, (cmd, line, timeout, cwd) in enumerate(CASES, 1):
    r = _run_case(line, timeout, cwd)
    r.update({"covers": cmd, "line": line, "cwd": cwd})
    results.append(r)
    print(f"[{i:3}/{len(CASES)}] {r['status']:<13} {r['seconds']:>6}s  {line}", flush=True)

os.chdir(WS)
registered = sorted(S.BUILTINS)
covered = {c for c, *_ in CASES}
report = {
    "when": time.strftime("%Y-%m-%d %H:%M:%S"),
    "platform": sys.platform, "python": sys.version.split()[0],
    "shell_file": getattr(S, "__file__", ""),
    "registered": registered,
    "untested": [n for n in registered if n not in covered and n not in SKIPPED],
    "skipped": SKIPPED,
    "results": results,
    "total_seconds": round(time.time() - t_all, 1),
}
with open(OUT, "w") as f:
    json.dump(report, f, indent=1)
print(f"selftest done: {len(results)} cases in {report['total_seconds']}s -> {OUT}", flush=True)
