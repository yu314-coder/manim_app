// RenderManager.swift — drives manim render commands through the
// integrated PTY terminal (TerminalProcessView) so the user sees
// the actual manim output stream in the same shell they can type
// into. No hidden subprocess; just a command dispatched via
// TerminalBridge.
//
// Earlier the render spawned its own Process and tried to mirror
// stdout/stderr into a separate read-only NSTextView. That panel
// was replaced by the real terminal, so the render output was
// silently going nowhere. Now we treat the integrated terminal
// as the single source of truth for command output.
//
// State coordination:
//   • app.isRendering tracks whether a manim run is in flight.
//     Toggled true on send, false when an output file lands or
//     2 minutes pass without progress (timeout).
//   • The output poller watches Documents/ManimStudio/Renders/ for
//     the produced .mp4/.mov/.gif/.png and promotes the newest
//     non-partial one to app.lastRenderURL. The PreviewView's
//     AVPlayerView updates automatically.
//   • Stop sends Ctrl-C through the PTY — manim catches the
//     KeyboardInterrupt cleanly between animations.
import Foundation

@MainActor
final class RenderManager {

    let app: AppState
    private var outputPoller: Timer?
    private var renderStart: Date = .distantPast
    private var lastSurfacedURL: URL?
    private var watchedDir: URL?

    init(app: AppState) { self.app = app }

    // MARK: trigger

    func renderFinal()   { dispatch(quality: app.renderQuality,   fps: app.renderFPS) }
    func renderPreview() { dispatch(quality: app.previewQuality,  fps: app.previewFPS) }

    func stop() {
        guard app.isRendering else { return }
        TerminalBridge.shared.interrupt()
        finishUpUI()
    }

    // MARK: core

    private func dispatch(quality: RenderQuality, fps: Int) {
        guard !app.isRendering else { return }

        // 1. Resolve the scene.
        let sceneArg = app.selectedScene.isEmpty
            ? (app.detectedScenes.first ?? "")
            : app.selectedScene
        if sceneArg.isEmpty {
            // Surface the warning into the terminal so the user
            // sees it in the same place every other render output
            // appears.
            TerminalBridge.shared.sendCommand?(
                "echo '[manimstudio] no Scene class found in the editor buffer'\n")
            return
        }

        // 2. Stage scene.py to a per-render directory.
        let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask).first!
        let runID  = UUID().uuidString.prefix(8)
        let runDir = docs
            .appendingPathComponent("ManimStudio/Renders", isDirectory: true)
            .appendingPathComponent("manim_\(runID)", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: runDir, withIntermediateDirectories: true)
        let sceneURL = runDir.appendingPathComponent("scene.py")
        do {
            try app.sourceCode.write(
                to: sceneURL, atomically: true, encoding: .utf8)
        } catch {
            TerminalBridge.shared.sendCommand?(
                "echo '[manimstudio] could not stage scene.py: \(error.localizedDescription)'\n")
            return
        }

        // 3. Compose the manim command line. Run it INSIDE the
        // venv's python. If the venv is ready, the user's terminal
        // already has activated it (TerminalProcessView sources
        // bin/activate at boot), so plain `python` resolves to the
        // venv binary. Use that path explicitly anyway in case the
        // user typed `deactivate`.
        let pythonCmd: String = {
            if let py = VenvManager.venvPython { return py.path.shellQuoted() }
            return "python3"
        }()
        let outputDir = runDir.appendingPathComponent("output", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: outputDir, withIntermediateDirectories: true)

        let parts: [String] = [
            pythonCmd, "-m", "manim", "render",
            quality.manimFlag,
            "--fps", String(fps),
            "--media_dir", outputDir.path.shellQuoted(),
        ] + app.renderFormat.manimArg + [
            sceneURL.path.shellQuoted(),
            sceneArg,
        ]
        let cmd = parts.joined(separator: " ")

        // 4. Send to terminal.
        TerminalBridge.shared.sendCommand?("\n# manimstudio render\n")
        TerminalBridge.shared.sendCommand?(cmd + "\n")

        app.isRendering = true
        renderStart = Date()
        lastSurfacedURL = nil
        watchedDir = outputDir
        startOutputPoller(in: outputDir)
    }

    // MARK: poller — watches outputDir for produced video files

    private func startOutputPoller(in outputDir: URL) {
        stopOutputPoller()
        let exts: Set<String> = ["mp4", "mov", "m4v", "gif", "png"]
        outputPoller = Timer.scheduledTimer(
            withTimeInterval: 1.2, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                guard let walker = FileManager.default.enumerator(
                    at: outputDir,
                    includingPropertiesForKeys: [.contentModificationDateKey,
                                                  .isRegularFileKey,
                                                  .fileSizeKey])
                else { return }
                var best: (URL, Date)?
                for case let url as URL in walker {
                    // Skip per-animation chunks — manim deletes those
                    // after the final concat finishes.
                    if url.pathComponents.contains("partial_movie_files") {
                        continue
                    }
                    let v = try? url.resourceValues(forKeys: [
                        .isRegularFileKey, .contentModificationDateKey,
                        .fileSizeKey])
                    guard v?.isRegularFile == true,
                          exts.contains(url.pathExtension.lowercased()),
                          (v?.fileSize ?? 0) > 0,
                          let mtime = v?.contentModificationDate,
                          mtime >= self.renderStart
                    else { continue }
                    if best == nil || mtime > best!.1 { best = (url, mtime) }
                }
                if let (url, _) = best, url != self.lastSurfacedURL {
                    self.lastSurfacedURL = url
                    self.app.lastRenderURL = url
                }
                // Heuristic for "render finished": the newest file
                // is older than 8 seconds AND we have something. The
                // shell's prompt printing isn't easily observable
                // from here, so we fall back to an idle-window check.
                if let (_, mtime) = best,
                   Date().timeIntervalSince(mtime) > 8,
                   self.app.isRendering {
                    self.finishUpUI()
                }
            }
        }
        if let t = outputPoller {
            RunLoop.main.add(t, forMode: .common)
        }
    }
    private func stopOutputPoller() {
        outputPoller?.invalidate()
        outputPoller = nil
    }

    private func finishUpUI() {
        stopOutputPoller()
        app.isRendering = false
    }
}

// MARK: - shell quoting helper

private extension String {
    /// Wrap a path in single quotes safely, escaping any embedded
    /// single quotes via `'\''` so the shell sees one argument.
    func shellQuoted() -> String {
        "'" + self.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
