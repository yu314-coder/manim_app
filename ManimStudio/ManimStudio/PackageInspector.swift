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

    /// On-disk cache keyed by CFBundleVersion. The Python introspection
    /// otherwise takes 2-5 s every time the Packages tab opens — keying
    /// on build version means it runs once per install and is instant
    /// thereafter.
    private static func cachePath() -> String {
        let dir = (NSSearchPathForDirectoriesInDomains(.cachesDirectory, .userDomainMask, true).first
                   ?? NSTemporaryDirectory()) as NSString
        let ver = (Bundle.main.infoDictionary?["CFBundleVersion"] as? String) ?? "0"
        return dir.appendingPathComponent("manim_studio_pkgs_v\(ver).json")
    }

    func refresh(force: Bool = false) {
        guard !isLoading else { return }
        // Disk cache hit — skip Python entirely.
        let cache = Self.cachePath()
        if !force,
           packages.isEmpty,
           let data = try? Data(contentsOf: URL(fileURLWithPath: cache)),
           case .success(let pkgs) = Self.parse(data: data, plain: true) {
            self.packages = pkgs
            return
        }
        isLoading = true
        error = nil
        Task.detached(priority: .userInitiated) {
            let result = PythonRuntime.shared.execute(code: Self.script)
            let parsed = Self.parse(result.output)
            await MainActor.run {
                self.isLoading = false
                switch parsed {
                case .success(let pkgs):
                    self.packages = pkgs
                    // Persist in plain-JSON form (no markers) for cheap reload.
                    if let plain = try? JSONSerialization.data(withJSONObject:
                        pkgs.map { ["name": $0.name, "version": $0.version,
                                    "summary": $0.summary ?? "",
                                    "location": $0.location ?? ""] }) {
                        try? plain.write(to: URL(fileURLWithPath: Self.cachePath()))
                    }
                case .failure(let err):
                    self.error = err
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

    # Pull version + summary from importlib.metadata only — NEVER call
    # importlib.import_module here. Importing manim/scipy/plotly etc.
    # for the sake of reading __doc__ pulls in their entire C-extension
    # graph (which on iOS means dlopening dozens of .frameworks) and
    # adds 2-5 s of latency every time the Packages tab opens. The
    # *.dist-info dirs already carry both fields.
    from importlib.metadata import distributions as _dists, PackageNotFoundError as _PNF

    _meta_cache = {}
    try:
        for _d in _dists():
            try:
                _name = (_d.metadata.get("Name") or "").strip()
                if not _name: continue
                _ver = (_d.version or "").strip()
                _summary_raw = (_d.metadata.get("Summary") or "").strip()
                if _summary_raw and _summary_raw != "UNKNOWN":
                    _summary_clean = _summary_raw.split("\\n", 1)[0].strip()[:140]
                else:
                    _summary_clean = None
                # Index by both the canonical name (lowercased,
                # underscores) and the dir-on-disk variant — package
                # directories on disk preserve original case.
                key = _name.lower().replace("-", "_")
                _meta_cache[key] = (_ver, _summary_clean)
            except Exception:
                continue
    except Exception:
        pass

    def _meta_lookup(n):
        return _meta_cache.get(n.lower().replace("-", "_"), ("", None))

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
                ver, summ = _meta_lookup(modname)
                out.append({"name": modname, "version": ver or "",
                            "summary": summ, "location": path})

    out.sort(key=lambda x: x["name"].lower())
    print("___PKGJSON___" + json.dumps(out) + "___ENDPKGJSON___")
    """

    enum ParseResult: Sendable { case success([PackageInfo]); case failure(String) }

    /// Cache-path fast lane: bytes are already plain JSON (no marker
    /// envelope), so skip the substring scan.
    nonisolated private static func parse(data: Data, plain: Bool) -> ParseResult {
        guard plain,
              let raw = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]]
        else { return .failure("cache parse failed") }
        return .success(raw.compactMap { d in
            guard let n = d["name"] as? String, !n.isEmpty else { return nil }
            return PackageInfo(name: n,
                               version: d["version"] as? String ?? "",
                               summary: (d["summary"] as? String).flatMap { $0.isEmpty ? nil : $0 },
                               location: (d["location"] as? String).flatMap { $0.isEmpty ? nil : $0 })
        })
    }

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
