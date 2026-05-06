// PythonResolver.swift — finds a Python interpreter capable of
// running `python -m manim render scene.py SceneName`. Search
// order: bundle-relative → /usr/local/bin → /opt/homebrew/bin
// → $PATH. Caches the result for the app's lifetime since the
// interpreter location doesn't change at runtime.
//
// We deliberately don't embed a launcher binary here (that would
// require building one from BeeWare's framework slice via dlopen +
// PyMain_BytesMain). The host Python is fast, well-known to the
// user, and lets RenderManager hand the user clear error messages
// when something on their setup is wrong.
import Foundation

enum PythonResolver {

    /// Resolved interpreter path for the current launch.
    static let pythonURL: URL? = {
        let fm = FileManager.default
        for candidate in candidateURLs {
            if fm.isExecutableFile(atPath: candidate.path) {
                return candidate
            }
        }
        return whichOnPath("python3.14")
            ?? whichOnPath("python3.13")
            ?? whichOnPath("python3.12")
            ?? whichOnPath("python3")
    }()

    /// Path to the bundled site-packages tree (manim, numpy, scipy,
    /// kokoro-onnx, …) installed by `install-python-macos.sh`.
    static let bundledSitePackages: URL? = {
        let url = Bundle.main.resourceURL?
            .appendingPathComponent("site-packages", isDirectory: true)
        if let url, FileManager.default.fileExists(atPath: url.path) {
            return url
        }
        return nil
    }()

    /// Compose `PYTHONPATH` so subprocess Python finds the bundled
    /// packages first, then any user-installed system packages.
    static var pythonPath: String {
        var components: [String] = []
        if let s = bundledSitePackages?.path { components.append(s) }
        if let existing = ProcessInfo.processInfo.environment["PYTHONPATH"] {
            components.append(existing)
        }
        return components.joined(separator: ":")
    }

    // MARK: - private

    private static let candidateURLs: [URL] = [
        // Future: a launcher binary we build from BeeWare's framework.
        // For now we look for python.org / Homebrew / system installs.
        URL(fileURLWithPath: "/usr/local/bin/python3.14"),
        URL(fileURLWithPath: "/opt/homebrew/bin/python3.14"),
        URL(fileURLWithPath: "/usr/local/bin/python3.13"),
        URL(fileURLWithPath: "/opt/homebrew/bin/python3.13"),
        URL(fileURLWithPath: "/usr/local/bin/python3.12"),
        URL(fileURLWithPath: "/opt/homebrew/bin/python3.12"),
        URL(fileURLWithPath: "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14"),
    ]

    private static func whichOnPath(_ name: String) -> URL? {
        guard let env = ProcessInfo.processInfo.environment["PATH"] else { return nil }
        for dir in env.split(separator: ":") {
            let url = URL(fileURLWithPath: String(dir))
                .appendingPathComponent(name)
            if FileManager.default.isExecutableFile(atPath: url.path) {
                return url
            }
        }
        return nil
    }
}
