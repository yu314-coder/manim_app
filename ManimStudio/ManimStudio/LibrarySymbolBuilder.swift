// LibrarySymbolBuilder.swift — supplies Monaco's completion provider with
// a `{ module: { name: kind } }` symbol index for the bundled libraries
// (manim, numpy, scipy, sympy, …) that it merges into its hardcoded base
// completions.
//
// The index is PRE-GENERATED offline by scripts/gen-library-symbols.py and
// shipped as Resources/LibrarySymbols.json, so the editor gets full library
// completions the instant it loads — zero Python, zero on-device
// introspection. (That introspection used to run a one-time multi-second
// `import manim/numpy/scipy/…` pass on device, which janked whatever screen
// triggered it.) The bundled set is fixed per build, exactly like
// BundledPackages — regenerate the JSON after a python-ios-lib pin bump.
import Foundation

@MainActor
final class LibrarySymbolBuilder {
    static let shared = LibrarySymbolBuilder()

    /// In-memory cache of the bundled JSON, read once on first request.
    private var payloadJSON: String?

    /// Hand Monaco the baked symbol index. Reads the bundled JSON on the
    /// first call (a ~60 KB resource read, negligible) and serves it from
    /// memory thereafter. `completion` receives nil only if the resource is
    /// somehow absent from the bundle, in which case Monaco keeps just its
    /// hardcoded manim/Python completions.
    func loadIfCached(completion: @escaping (String?) -> Void) {
        if let cached = payloadJSON { completion(cached); return }
        if let bundled = Self.bundledSymbolsJSON() {
            payloadJSON = bundled
            completion(bundled)
        } else {
            completion(nil)
        }
    }

    /// The pre-generated symbol index shipped in the app bundle
    /// (Resources/LibrarySymbols.json).
    nonisolated static func bundledSymbolsJSON() -> String? {
        let url = Bundle.main.url(forResource: "LibrarySymbols", withExtension: "json")
            ?? Bundle.main.url(forResource: "LibrarySymbols", withExtension: "json",
                               subdirectory: "Resources")
        guard let url else { return nil }
        return try? String(contentsOf: url, encoding: .utf8)
    }
}
