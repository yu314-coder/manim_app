// ManimStudioApp.swift — app entry. Only LaTeX/busytex is wired here.
// Python runtime + python-ios-lib SwiftPM products will be added back
// once we've validated which ones auto-link transitively from Manim.
import SwiftUI

@main
struct ManimStudioApp: App {
    init() {
        // Persistent crash log at Documents/Logs/manim_studio.log.
        // Visible in iOS Files app under "On My iPad / Manim Studio /
        // Logs/" so the user can read or share it after a crash. MUST
        // be installed first so signal handlers cover the rest of init.
        CrashLogger.shared.install()

        // Route offlinai_latex (manim's Tex/MathTex bridge) to busytex.
        setenv("OFFLINAI_LATEX_BACKEND", "busytex", 1)
        setenv("OFFLINAI_ENGINE",        "busytex", 1)
        setenv("OFFLINAI_LATEX_FORCE_BUSYTEX", "1", 1)
        setenv("OFFLINAI_LATEX_USE_PDFTEX",    "0", 1)

        DispatchQueue.main.async {
            BusytexEngine.shared.preload()
            LaTeXEngine.shared.initialize()
            // Set up the PTY pipes + write the banner immediately so
            // the terminal pane has visible content the instant it
            // mounts. Then start Python booting on its background
            // queue. By the time the user has navigated to Workspace
            // and looked at the terminal, the real
            //   mobile@iPad ~/Workspace %
            // prompt is usually already printed below the banner.
            PTYBridge.shared.setupIfNeeded()
            PythonRuntime.shared.ensureRuntimeReady()
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .commands { ManimStudioCommands() }
    }
}
