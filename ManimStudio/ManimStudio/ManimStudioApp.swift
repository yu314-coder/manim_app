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

        // LaTeX backend selection — match CodeBench's behaviour.
        //
        // We previously forced every MathTex call through busytex/xelatex so
        // that complex macros (\underbrace, \boxed, CJK, matrix/align
        // environments) would render correctly. The side-effect: xelatex
        // strictly enforces \frac{}{} having exactly two arguments, which
        // collides with a long-standing Manim quirk in
        // `_break_up_by_substrings`: it splits every TeX string on `{{` /
        // `}}` (substring isolation markers) and rejoins the pieces with
        // dvisvgm `\special{...}` markers + a space. When `}}` arises
        // naturally inside an expression — e.g. `\frac{p_{i|j}}{2n}`, where
        // one `}` closes `p_{i|j` and the other closes the numerator —
        // those two braces get eaten and never restored. After
        // `offlinai_latex` strips the specials, xelatex sees
        // `\frac{p_{i|j {2n}}}` (one argument, no denominator) and fails.
        //
        // CodeBench doesn't set any of these env vars, so its routing
        // condition is `(has_cjk OR has_special_macro) AND NOT disabled`.
        // CJK-bearing expressions still go to busytex; simple Latin math
        // like `\frac{p_{i|j}}{2n}` falls through to SwiftMath, which
        // tolerates the Manim mangling. Match that here.
        //
        // To force busytex back on for debugging, set
        // OFFLINAI_LATEX_FORCE_BUSYTEX=1 from your Python script.

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
