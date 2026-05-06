// AppState.swift — central observable state for the macOS app.
// One instance lives in @StateObject inside ManimStudio_macosApp
// and is passed down via @EnvironmentObject so any view can read
// the current source, render flags, output URL, log buffer, etc.
//
// Kept narrow on purpose — domain logic (subprocess spawning,
// file I/O, render pipeline) lives in RenderManager / PythonResolver
// / AssetsStore. AppState only carries the values the UI binds to.
import SwiftUI
import Combine

@MainActor
final class AppState: ObservableObject {
    // ── Editor buffer
    @Published var sourceCode: String = AppState.defaultScene
    @Published var openedFileURL: URL? = nil

    // ── Render state
    @Published var isRendering = false
    @Published var renderQuality: RenderQuality = .medium
    @Published var renderFPS: Int = 30
    @Published var renderFormat: RenderFormat = .mp4
    @Published var selectedScene: String = ""
    @Published var lastRenderURL: URL? = nil

    // ── Terminal / log buffer (cap to last ~64 KB so the NSTextView
    // doesn't degrade after long sessions).
    @Published var terminalText: String = ""
    private let terminalCap = 65_536

    // ── Sidebar nav
    @Published var sidebarSection: SidebarSection = .workspace

    // ── Settings
    @AppStorage("manim_macos_theme")        var themeMode: String = "dark"
    @AppStorage("manim_macos_editor_font")  var editorFontSize: Double = 13
    @AppStorage("manim_macos_terminal_font") var terminalFontSize: Double = 12

    // MARK: helpers

    func appendTerminal(_ s: String) {
        terminalText += s
        if terminalText.count > terminalCap {
            // Drop the oldest 25% so we don't ping-pong on every line.
            let drop = terminalText.count - (terminalCap * 3 / 4)
            terminalText = String(terminalText.dropFirst(drop))
        }
    }
    func clearTerminal() { terminalText = "" }

    /// Detected `class … (Scene)` names in the current buffer.
    var detectedScenes: [String] {
        // Lightweight regex; same shape as the iOS SceneDetector.
        let pattern = #"^\s*class\s+([A-Za-z_]\w*)\s*\([^)]*Scene[^)]*\)"#
        guard let re = try? NSRegularExpression(pattern: pattern,
                                                options: [.anchorsMatchLines])
        else { return [] }
        let ns = sourceCode as NSString
        return re.matches(in: sourceCode, range: NSRange(location: 0, length: ns.length))
            .compactMap { m in
                guard m.numberOfRanges > 1 else { return nil }
                return ns.substring(with: m.range(at: 1))
            }
    }

    // MARK: defaults

    private static let defaultScene = """
    from manim import *


    class Hello(Scene):
        def construct(self):
            title = Text("Hello, ManimStudio!").scale(0.9)
            self.play(Write(title))
            self.wait(0.5)
            self.play(title.animate.shift(UP * 0.5).set_color(BLUE))
            self.wait(1)
    """
}

// MARK: - small enums

enum RenderQuality: String, CaseIterable, Identifiable {
    case low, medium, high, production4K, production8K
    var id: String { rawValue }
    var label: String {
        switch self {
        case .low:           return "480p15"
        case .medium:        return "720p30"
        case .high:          return "1080p60"
        case .production4K:  return "2160p60 (4K)"
        case .production8K:  return "4320p60 (8K)"
        }
    }
    /// Manim CLI flag — `manim -ql / -qm / -qh / -qk / -qp`.
    var manimFlag: String {
        switch self {
        case .low:          return "-ql"
        case .medium:       return "-qm"
        case .high:         return "-qh"
        case .production4K: return "-qk"
        case .production8K: return "-qp"
        }
    }
}

enum RenderFormat: String, CaseIterable, Identifiable {
    case mp4, mov, gif, png
    var id: String { rawValue }
    var label: String { rawValue.uppercased() }
    /// Manim CLI flag — `--format mp4`.
    var manimArg: [String] { ["--format", rawValue] }
}

enum SidebarSection: String, CaseIterable, Identifiable {
    case workspace, assets, packages, history, settings
    var id: String { rawValue }
    var label: String {
        switch self {
        case .workspace: return "Workspace"
        case .assets:    return "Assets"
        case .packages:  return "Packages"
        case .history:   return "Render History"
        case .settings:  return "Settings"
        }
    }
    var icon: String {
        switch self {
        case .workspace: return "rectangle.split.2x1"
        case .assets:    return "folder"
        case .packages:  return "shippingbox"
        case .history:   return "clock.arrow.circlepath"
        case .settings:  return "gearshape"
        }
    }
}
