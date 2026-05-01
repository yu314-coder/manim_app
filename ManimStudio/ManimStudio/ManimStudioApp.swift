// ManimStudioApp.swift — app entry. Only LaTeX/busytex is wired here.
// Python runtime + python-ios-lib SwiftPM products will be added back
// once we've validated which ones auto-link transitively from Manim.
import SwiftUI

@main
struct ManimStudioApp: App {
    init() {
        // Route offlinai_latex (manim's Tex/MathTex bridge) to busytex.
        setenv("OFFLINAI_LATEX_BACKEND", "busytex", 1)
        setenv("OFFLINAI_ENGINE",        "busytex", 1)
        setenv("OFFLINAI_LATEX_FORCE_BUSYTEX", "1", 1)
        setenv("OFFLINAI_LATEX_USE_PDFTEX",    "0", 1)

        DispatchQueue.main.async {
            BusytexEngine.shared.preload()
            LaTeXEngine.shared.initialize()
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
