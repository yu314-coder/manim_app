// LaTeXProbe.swift — sniffs $PATH (and the standard MacTeX install
// dir /Library/TeX/texbin, which isn't on the GUI PATH by default
// on macOS) for pdflatex / latex / xelatex / lualatex.
//
// Manim invokes `latex` or `pdflatex` to compile Tex / MathTex
// mobjects and even plain `Text(...)` on some versions; without a
// LaTeX install the render fails with the cryptic "latex error
// converting to dvi" message. The header chip uses this probe to
// surface a one-click install hint.
//
// Probing is cheap (a handful of stat() calls). We re-run on
// every header appear so the chip flips green the moment the user
// finishes installing BasicTeX without needing to restart the app.
import Foundation
import SwiftUI
import Combine

// Class-level @MainActor dropped — Swift 6's ObservableObject
// synthesis can't reconcile @MainActor with the nonisolated
// objectWillChange requirement. SwiftUI views call this from the
// main actor, so @Published mutations happen there.
final class LaTeXProbe: ObservableObject {
    static let shared = LaTeXProbe()
    private init() {}

    enum Status: Equatable {
        case unknown
        case missing
        case found(name: String, path: URL)

        var isReady: Bool {
            if case .found = self { return true }
            return false
        }
    }

    @Published private(set) var status: Status = .unknown

    /// Probes asynchronously; publishes the result on the main actor.
    /// Safe to call repeatedly — each call overwrites the result.
    func probe() {
        Task.detached(priority: .userInitiated) {
            let result = Self.findFirst()
            await MainActor.run {
                self.status = result
            }
        }
    }

    // MARK: - search

    /// Order matters — manim prefers pdflatex when available, falls
    /// back to latex (DVI), then the Unicode-aware engines.
    private nonisolated static let candidates = ["pdflatex", "latex", "xelatex", "lualatex"]

    /// Search dirs in this order:
    ///   1. $PATH (whatever the spawning shell exported)
    ///   2. Standard MacTeX/BasicTeX symlink location
    ///      (/Library/TeX/texbin) — this is NOT on $PATH for GUI apps
    ///      because launchd doesn't source ~/.zshrc / /etc/paths
    ///   3. Apple Silicon Homebrew bin (in case mactex was kegless)
    ///   4. Intel Homebrew bin
    private nonisolated static var searchDirs: [String] {
        var dirs: [String] = []
        if let path = ProcessInfo.processInfo.environment["PATH"] {
            dirs.append(contentsOf: path.split(separator: ":").map(String.init))
        }
        dirs.append("/Library/TeX/texbin")
        dirs.append("/opt/homebrew/bin")
        dirs.append("/usr/local/bin")
        // De-dup while preserving order.
        var seen = Set<String>()
        return dirs.filter { seen.insert($0).inserted }
    }

    private nonisolated static func findFirst() -> Status {
        for name in candidates {
            for dir in searchDirs {
                let url = URL(fileURLWithPath: dir).appendingPathComponent(name)
                if FileManager.default.isExecutableFile(atPath: url.path) {
                    return .found(name: name, path: url)
                }
            }
        }
        return .missing
    }
}
