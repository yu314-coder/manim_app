#!/usr/bin/env python3
"""Generate Resources/LibrarySymbols.json — the editor's library
auto-completion index, BAKED so the app needs zero runtime Python
introspection for it (the same idea as scripts/gen-bundled-packages.py).

Background
----------
Monaco's completion provider merges a `{ module: { name: kind } }` map into
its hardcoded base symbols. That map used to be produced on-device by
LibrarySymbolBuilder importing every bundled package and calling dir() — a
one-time multi-second Python pass that janked whatever screen triggered it.
This script produces the SAME map offline so it can ship in the bundle and
load instantly (no Python, no jank).

How it works
------------
Imports every top-level package installed in the CURRENT environment and
records dir() classified into Monaco CompletionItemKind ints — byte-for-byte
the logic the device used. Run it in a venv that has the libraries
ManimStudio bundles installed. Python-level symbol *names* are stable across
minor versions and identical between the macOS and iOS builds of a package,
so a host venv is a faithful source even though the shipped binaries are
iphoneos.

Usage
-----
    python3 -m venv /tmp/symgen && source /tmp/symgen/bin/activate
    pip install numpy scipy matplotlib scikit-learn networkx sympy mpmath \
        requests beautifulsoup4 plotly pillow jinja2 click rich pygments \
        fonttools pydub svgelements manim==0.20.1   # manim needs cairo/pango
    python3 scripts/gen-library-symbols.py
"""
import io, json, os, sys, importlib, contextlib, inspect, site, sysconfig

# Mirrors LibrarySymbolBuilder.script's SKIP, plus host build-tooling that
# isn't part of the app bundle (pip/setuptools/venv scaffolding).
SKIP = {
    "__pycache__", "lib-dynload", "site-packages", "encodings", "tests",
    "test", "bin", "include", "share", "lib", "ffmpeg", "build", "Headers",
    "Resources",
    # Known-crashy on iOS — excluded on device, so exclude here too for parity.
    "moderngl", "moderngl_window", "pyglet", "watchdog", "screeninfo",
    # Host-only build/packaging tooling — never shipped in the app.
    "pip", "setuptools", "wheel", "pkg_resources", "_distutils_hack",
    "easy_install", "_virtualenv", "virtualenv", "_yaml",
}

# Monaco CompletionItemKind values (monaco.languages.CompletionItemKind).
K_FUNCTION = 1
K_VARIABLE = 4
K_CLASS    = 6
K_MODULE   = 8
K_CONSTANT = 14


def kind_of(obj):
    if inspect.ismodule(obj):
        return K_MODULE
    if inspect.isclass(obj):
        return K_CLASS
    if callable(obj):
        return K_FUNCTION
    return K_CONSTANT


def site_dirs():
    dirs = set()
    try:
        dirs.update(site.getsitepackages())
    except Exception:
        pass
    for key in ("purelib", "platlib"):
        try:
            dirs.add(sysconfig.get_paths()[key])
        except Exception:
            pass
    return [d for d in dirs if d and os.path.isdir(d)]


import glob


def bundle_allowlist():
    """Top-level import names ACTUALLY shipped in ManimStudio.app.

    Without this, the host venv's macOS-only dependencies (pyobjc:
    AppKit/Cocoa/Foundation/objc, dragged in by matplotlib's macosx
    backend, plus Cython/glm) pollute the index with symbols the iOS app
    can't import. Reading the built .app's app_packages/site-packages —
    the same source gen-bundled-packages.py uses — restricts the index to
    exactly the bundled set. Returns an empty set if no .app is found, in
    which case the caller indexes everything (and you should pass a path).
    """
    roots = []
    if len(sys.argv) > 1:
        roots.append(os.path.join(sys.argv[1], "app_packages", "site-packages"))
    for dd in ("/Volumes/D/xcode/DerivedData",
               os.path.expanduser("~/Library/Developer/Xcode/DerivedData")):
        roots += sorted(glob.glob(os.path.join(
            dd, "ManimStudio-*/Build/Products/*-iphoneos/"
            "ManimStudio.app/app_packages/site-packages")))
    roots.append(os.path.join(os.path.dirname(__file__), "..", "_vendor",
                 "python-ios-lib", "app_packages", "site-packages"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        names = set()
        for n in os.listdir(root):
            if n.startswith((".", "_")) or n.endswith((".dist-info", ".egg-info", ".pth")):
                continue
            full = os.path.join(root, n)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, "__init__.py")):
                names.add(n)
            elif n.endswith(".py"):
                names.add(n[:-3])
            elif n.endswith(".so"):
                names.add(n.split(".")[0])
        if names:
            print(f"allowlist from {root}  ({len(names)} importable top-levels)")
            return names
    print("WARNING: no ManimStudio.app found — indexing ALL installed "
          "packages (pass the .app path as argv[1] to filter to the bundle)")
    return set()


def main():
    allow = bundle_allowlist()
    modules = {}
    sink = io.StringIO()
    for path in sorted(site_dirs()):
        try:
            entries = sorted(os.listdir(path))
        except Exception:
            continue
        for name in entries:
            if name in SKIP or name.startswith(("_", ".")):
                continue
            full = os.path.join(path, name)
            modname = None
            if os.path.isdir(full):
                if os.path.exists(os.path.join(full, "__init__.py")):
                    modname = name
            elif name.endswith(".py"):
                modname = name[:-3]
            elif name.endswith((".so", ".pyd")):
                modname = name.split(".")[0]
            if not modname or modname in modules or modname in SKIP:
                continue
            # Restrict to what ManimStudio.app actually bundles (drops
            # host-only pyobjc/Cython/etc.). If no allowlist was found,
            # index everything.
            if allow and modname not in allow:
                continue
            try:
                with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                    m = importlib.import_module(modname)
            except BaseException:
                # Some C extensions hard-exit; a plain `continue` is the
                # best we can do — they're excluded via SKIP where known.
                continue
            attrs = {}
            names = [n for n in dir(m) if not n.startswith("_")][:400]
            for n in names:
                try:
                    attrs[n] = kind_of(getattr(m, n))
                except Exception:
                    attrs[n] = K_VARIABLE
            if attrs:
                modules[modname] = attrs

    payload = {"modules": modules}
    dst = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..",
        "ManimStudio", "ManimStudio", "Resources", "LibrarySymbols.json"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"), sort_keys=True)

    total_syms = sum(len(v) for v in modules.values())
    size_kb = os.path.getsize(dst) / 1024
    print(f"wrote {dst}")
    print(f"  modules: {len(modules)}   symbols: {total_syms}   size: {size_kb:.0f} KB")
    for name in sorted(modules, key=lambda k: -len(modules[k]))[:25]:
        print(f"    {name:18} {len(modules[name])}")


if __name__ == "__main__":
    main()
