#!/usr/bin/env python3
"""Regenerate ManimStudio/ManimStudio/BundledPackages.swift — the list of
Python distributions whose CODE is actually bundled in ManimStudio.app.

Why a generator: the Packages tab reads this baked list instead of booting
Python + importlib.metadata at runtime (that pass took 2-5 s and janked the
tab). The set is fixed per build, so regenerate after a python-ios-lib pin
change.

IMPORTANT: it lists only distributions whose top-level package is actually
importable in the bundle — NOT every *.dist-info under python-metadata/
(those include CodeBench-only packages like flask/dash/torch whose metadata
ships but whose code does not).

Usage:
    # build the app once so app_packages/site-packages + python-metadata exist
    python3 scripts/gen-bundled-packages.py <path-to-ManimStudio.app>
"""
import os, glob, json, sys
from collections import Counter

CATEGORIES = {
    "Animation": {"manim","manimpango","pycairo","svgelements","skia-pathops",
                  "mapbox-earcut","isosurfaces","moderngl","moderngl-window",
                  "cairo-metal"},
    "Scientific": {"numpy","scipy","sympy","mpmath","networkx","scikit-learn"},
    "Plotting": {"matplotlib","plotly","narwhals","cycler","fonttools"},
    "Media": {"pillow","av","pydub","audioop-lts"},
    "Web / HTTP": {"requests","urllib3","certifi","idna","charset-normalizer",
                   "beautifulsoup4","soupsieve","jinja2","markupsafe","click",
                   "cloup","tornado"},
    "Data": {"jsonschema","jsonschema-specifications","referencing","rpds-py",
             "attrs","pyyaml","fsspec","filelock","regex"},
    "LaTeX": {"offlinai-latex"},
}

# Bundled libs whose dist-info has no top_level.txt (so the import→dist
# match misses them) or no metadata at all. name, version, summary.
MANUAL = {
    "pycairo": ("pycairo", "1.29.0",
                "Python bindings for the cairo 2D graphics library."),
    "fonttools": ("fonttools", "4.60.2",
                  "Font tooling; glyph-outline extraction powering Text() on iOS."),
    "scikit-learn": ("scikit-learn", "1.8.0",
                     "Machine-learning library (clustering, decomposition, …)."),
    "skia-pathops": ("skia-pathops", "0.9.2",
                     "Boolean ops on Bézier paths via Skia (Union/Difference/…)."),
    "audioop-lts": ("audioop-lts", "0.2.1",
                    "audioop standard-library replacement for Python 3.13+."),
    "offlinai-latex": ("offlinai_latex", "1.0.1",
                       "On-device LaTeX → SVG bridge (busytex) for MathTex/Tex."),
    "cairo-metal": ("cairo-metal", "0.1.0",
                    "Experimental Metal GPU backend for cairo (pycairo drop-in)."),
}

DENY = {"attr"}  # stray attr 0.3.2 — keep attrs instead


def categorize(n):
    n = n.lower()
    for c, s in CATEGORIES.items():
        if n in s:
            return c
    return "Utility"


def read_meta(di):
    name = ver = summ = ""
    p = os.path.join(di, "METADATA")
    if not os.path.exists(p):
        return None
    for line in open(p, encoding="utf-8", errors="replace"):
        if line.startswith("Name:") and not name:
            name = line.split(":", 1)[1].strip()
        elif line.startswith("Version:") and not ver:
            ver = line.split(":", 1)[1].strip()
        elif line.startswith("Summary:") and not summ:
            s = line.split(":", 1)[1].strip()
            summ = "" if s.upper() == "UNKNOWN" else s
        if name and ver and summ:
            break
    return (name, ver, summ) if name and ver else None


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    app = sys.argv[1]
    SP = os.path.join(app, "app_packages", "site-packages")
    META = os.path.join(app, "python-metadata")
    # extra dist-info source (vendor clone) for versions of pkgs whose
    # dist-info didn't ship into python-metadata
    VEND = os.path.join(os.path.dirname(__file__), "..", "_vendor",
                        "python-ios-lib", "app_packages", "site-packages")

    importable = set()
    for d in glob.glob(os.path.join(SP, "*")):
        b = os.path.basename(d)
        if b.endswith((".dist-info", ".egg-info", "__pycache__")):
            continue
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "__init__.py")):
            importable.add(b)
    for so in glob.glob(os.path.join(SP, "*.so")):
        importable.add(os.path.basename(so).split(".")[0])

    dists = {}
    for srcmeta in (META, VEND):
        for di in sorted(glob.glob(os.path.join(srcmeta, "*.dist-info"))):
            m = read_meta(di)
            if not m:
                continue
            name, ver, summ = m
            if name.lower() in DENY or name.lower() in dists:
                continue
            tl = os.path.join(di, "top_level.txt")
            prov = ({l.strip() for l in open(tl) if l.strip()}
                    if os.path.exists(tl) else {name.lower().replace("-", "_")})
            if prov & importable:
                if len(summ) > 150:
                    summ = summ[:147].rstrip() + "…"
                dists[name.lower()] = (name, ver, summ)

    for k, (n, v, s) in MANUAL.items():
        dists[k] = (n, v, s)

    out = [{"name": n, "version": v, "summary": s, "category": categorize(n)}
           for (n, v, s) in dists.values()]
    out.sort(key=lambda p: p["name"].lower())

    def esc(s):
        return (s or "").replace("\\", "\\\\").replace('"', '\\"')

    L = ["// BundledPackages.swift — GENERATED by scripts/gen-bundled-packages.py.",
         "// Do not edit by hand. Regenerate after changing the python-ios-lib pin.",
         "//",
         "// Lists ONLY the distributions whose code is actually bundled in",
         "// ManimStudio.app (importable top-level ∩ dist metadata) — not every",
         "// *.dist-info under python-metadata (those include CodeBench-only",
         "// packages whose metadata ships but whose code does not).",
         "//",
         "// Baked so the Packages tab is instant (no Python / importlib.metadata).",
         "",
         "import Foundation",
         "",
         "enum BundledPackages {",
         f"    /// {len(out)} distributions bundled at build time.",
         "    static let all: [PackageInfo] = ["]
    for p in out:
        s = f'"{esc(p["summary"])}"' if p["summary"] else "nil"
        L.append(f'        PackageInfo(name: "{esc(p["name"])}", '
                 f'version: "{esc(p["version"])}", summary: {s}, '
                 f'location: nil, category: "{esc(p["category"])}"),')
    L += ["    ]",
          "",
          "    /// Distinct categories in first-seen order.",
          "    static let categories: [String] = {",
          "        var seen = Set<String>(); var order: [String] = []",
          "        for p in all where !seen.contains(p.category ?? \"\") {",
          "            seen.insert(p.category ?? \"\"); order.append(p.category ?? \"\")",
          "        }",
          "        return order",
          "    }()",
          "}",
          ""]
    dst = os.path.abspath(os.path.join(os.path.dirname(__file__), "..",
                          "ManimStudio", "ManimStudio", "BundledPackages.swift"))
    open(dst, "w").write("\n".join(L))
    print(f"wrote {dst}  ({len(out)} packages)")
    for c, n in Counter(p["category"] for p in out).most_common():
        print(f"  {c}: {n}")


if __name__ == "__main__":
    main()
