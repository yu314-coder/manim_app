// PackageInspector.swift — walks sys.path for python-ios-lib_*.bundle siblings,
// imports each top-level package, reads __version__/__doc__, returns JSON.
import Foundation
import Combine

struct PackageInfo: Identifiable, Hashable {
    var id: String { name }
    let name: String
    let version: String
    let summary: String?
    let location: String?
}

@MainActor
final class PackageInspector: ObservableObject {
    @Published var packages: [PackageInfo] = []
    @Published var isLoading = false
    @Published var error: String?

    func refresh() {
        guard !isLoading else { return }
        isLoading = true
        error = nil
        Task.detached(priority: .userInitiated) {
            let result = PythonRuntime.shared.execute(code: Self.script)
            let parsed = Self.parse(result.output)
            await MainActor.run {
                self.isLoading = false
                switch parsed {
                case .success(let pkgs): self.packages = pkgs
                case .failure(let err):  self.error = err
                }
            }
        }
    }

    nonisolated private static let script: String = """
    import io, json, os, sys, importlib, contextlib

    SKIP = {"__pycache__", "lib-dynload", "site-packages", "encodings", "tests",
            "test", "bin", "include", "share", "lib", "ffmpeg", "build",
            "Headers", "Resources"}

    _stdout_capture = io.StringIO()
    _stderr_capture = io.StringIO()
    out, seen = [], set()

    # Two install layouts in play:
    #   - SwiftPM resource bundles: <App>.app/python-ios-lib_*.bundle/
    #   - BeeWare consolidated: <App>.app/app_packages/site-packages/
    # install-python-stdlib.sh Step 9 deletes the bundles after merging
    # them into app_packages/site-packages — match either form.
    scan_paths = [p for p in sys.path if p and (
        ("python-ios-lib_" in p and p.endswith(".bundle")) or
        ("app_packages/site-packages" in p) or
        ("python-metadata" in p)
    )]
    docs = os.path.expanduser("~/Documents/site-packages")
    if os.path.isdir(docs):
        scan_paths.append(docs)

    def _is_pkg(d):
        try: e = os.listdir(d)
        except Exception: return False
        return ("__init__.py" in e) or ("__init__.pyc" in e)

    def _meta_ver(n):
        try:
            from importlib.metadata import version as _v
            return _v(n)
        except Exception: return ""

    def _attr_ver(n):
        try:
            m = importlib.import_module(n)
            for a in ("__version__", "version", "VERSION"):
                v = getattr(m, a, None)
                if isinstance(v, str): return v
                if isinstance(v, tuple): return ".".join(str(x) for x in v)
        except Exception: pass
        return ""

    def _summary(n):
        try:
            m = importlib.import_module(n)
            d = (m.__doc__ or "").strip()
            if d:
                return d.split("\\n", 1)[0].strip()[:140]
        except Exception: pass
        return None

    with contextlib.redirect_stdout(_stdout_capture), \\
         contextlib.redirect_stderr(_stderr_capture):
        for path in scan_paths:
            if not path or not os.path.isdir(path): continue
            try: entries = sorted(os.listdir(path))
            except Exception: continue
            for name in entries:
                if name in SKIP or name.startswith(("_", ".")): continue
                full = os.path.join(path, name)
                modname = None
                if os.path.isdir(full) and _is_pkg(full): modname = name
                elif name.endswith(".py"): modname = name[:-3]
                else: continue
                if modname in seen: continue
                seen.add(modname)
                ver = _meta_ver(modname) or _attr_ver(modname)
                out.append({"name": modname, "version": ver or "",
                            "summary": _summary(modname), "location": path})

    out.sort(key=lambda x: x["name"].lower())
    print("___PKGJSON___" + json.dumps(out) + "___ENDPKGJSON___")
    """

    enum ParseResult: Sendable { case success([PackageInfo]); case failure(String) }

    nonisolated private static func parse(_ output: String) -> ParseResult {
        guard let s = output.range(of: "___PKGJSON___"),
              let e = output.range(of: "___ENDPKGJSON___",
                                   range: s.upperBound..<output.endIndex) else {
            return .failure("No package list emitted. Output: \(output.prefix(400))")
        }
        let json = String(output[s.upperBound..<e.lowerBound])
        guard let data = json.data(using: .utf8) else {
            return .failure("Bad UTF-8 in JSON")
        }
        do {
            let raw = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
            return .success(raw.compactMap { d in
                guard let n = d["name"] as? String, !n.isEmpty else { return nil }
                return PackageInfo(name: n,
                                   version: d["version"] as? String ?? "",
                                   summary: d["summary"] as? String,
                                   location: d["location"] as? String)
            })
        } catch {
            return .failure("JSON decode failed: \(error.localizedDescription)")
        }
    }
}
