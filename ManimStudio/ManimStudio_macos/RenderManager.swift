// RenderManager.swift — runs a manim render in a subprocess,
// streams stdout/stderr into AppState.terminalText, and resolves
// the produced .mp4 path on success.
//
// macOS Process pattern:
//   /usr/local/bin/python3.14 -m manim
//       <scene.py> <SceneName>
//       <quality flag>  -o <basename>  --format mp4 ...
//   PYTHONPATH = <App>.app/Contents/Resources/site-packages
//   cwd        = <writable temp dir per-render>
//
// We write the editor buffer to a temp .py file, invoke manim, and
// poll its stdout/stderr line-buffered through Pipe + readability
// handlers. Output is appended to AppState.terminalText on the
// main actor.
import Foundation

@MainActor
final class RenderManager {

    let app: AppState
    private var current: Process?

    init(app: AppState) { self.app = app }

    // MARK: trigger

    func renderFinal()  { run(quality: app.renderQuality, fps: app.renderFPS) }
    func renderPreview() { run(quality: .low, fps: 15) }

    func stop() {
        guard let p = current else { return }
        p.terminate()
        current = nil
    }

    // MARK: core

    private func run(quality: RenderQuality, fps: Int) {
        guard !app.isRendering else { return }
        // Prefer the per-app venv's python (created by the welcome
        // wizard via VenvManager) so renders use a pinned manim
        // instead of whatever happens to be on the user's PATH.
        // Fall back to host python if the venv isn't ready yet.
        guard let pyURL = VenvManager.venvPython ?? PythonResolver.pythonURL else {
            app.appendTerminal(
                "[render] no Python found. Open the welcome wizard from Help → " +
                "Set Up Environment, or install Python 3.14 (python.org / " +
                "`brew install python@3.14`).\n")
            return
        }

        // 1. Pick the scene to render.
        let sceneArg = app.selectedScene.isEmpty
            ? (app.detectedScenes.first ?? "")
            : app.selectedScene
        if sceneArg.isEmpty {
            app.appendTerminal(
                "[render] no Scene class found in the editor buffer.\n")
            return
        }

        // 2. Stage the source + output under
        //    Documents/ManimStudio/Renders/manim_<id>/
        // (same path HistoryView walks). Persistent so the user can
        // find the .mp4 across launches; runDir is deleted only when
        // they hit "Clear all" in History.
        let runID  = UUID().uuidString.prefix(8)
        let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask).first!
        let rendersRoot = docs.appendingPathComponent(
            "ManimStudio/Renders", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: rendersRoot, withIntermediateDirectories: true)
        let runDir = rendersRoot
            .appendingPathComponent("manim_\(runID)", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: runDir, withIntermediateDirectories: true)
        let sourceURL = runDir.appendingPathComponent("scene.py")
        do {
            try app.sourceCode.write(to: sourceURL, atomically: true, encoding: .utf8)
        } catch {
            app.appendTerminal("[render] failed to stage scene.py: \(error)\n")
            return
        }

        // 3. Compose the manim command.
        let outputDir = runDir.appendingPathComponent("output", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: outputDir, withIntermediateDirectories: true)

        var args: [String] = [
            "-m", "manim", "render",
            quality.manimFlag,
            "--fps", String(fps),
            "--media_dir", outputDir.path,
        ]
        args.append(contentsOf: app.renderFormat.manimArg)
        args.append(sourceURL.path)
        args.append(sceneArg)

        // 4. Launch.
        let proc = Process()
        proc.executableURL = pyURL
        proc.arguments = args
        proc.currentDirectoryURL = runDir

        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"]            = PythonResolver.pythonPath
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"]      = "1"
        env["MANIM_DISABLE_RENDERER_CACHE"] = "1"
        proc.environment = env

        let stdout = Pipe(); let stderr = Pipe()
        proc.standardOutput = stdout
        proc.standardError  = stderr
        attachReader(stdout)
        attachReader(stderr)

        proc.terminationHandler = { [weak self] p in
            Task { @MainActor [weak self] in
                self?.finished(in: outputDir, exit: p.terminationStatus)
            }
        }

        let invocation = ([pyURL.path] + args).joined(separator: " ")
        app.appendTerminal("\n[render] \(invocation)\n")
        app.isRendering = true
        do {
            try proc.run()
            current = proc
        } catch {
            app.appendTerminal("[render] failed to launch: \(error)\n")
            app.isRendering = false
        }
    }

    // MARK: pipes → terminal

    private func attachReader(_ pipe: Pipe) {
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { return }
            let s = String(data: data, encoding: .utf8) ?? ""
            Task { @MainActor [weak self] in
                self?.app.appendTerminal(s)
            }
        }
    }

    // MARK: finish

    private func finished(in outputDir: URL, exit: Int32) {
        // Drain pipes one last time + detach handlers so they don't
        // hold a strong ref to self and leak the Process.
        if let p = current {
            (p.standardOutput as? Pipe)?.fileHandleForReading.readabilityHandler = nil
            (p.standardError  as? Pipe)?.fileHandleForReading.readabilityHandler = nil
        }
        current = nil

        if exit == 0 {
            // Walk outputDir for the most recently produced video file.
            let exts: Set<String> = ["mp4", "mov", "gif", "png"]
            if let walker = FileManager.default.enumerator(
                at: outputDir,
                includingPropertiesForKeys: [.contentModificationDateKey, .isRegularFileKey])
            {
                var best: (URL, Date)?
                for case let url as URL in walker {
                    let v = try? url.resourceValues(forKeys: [
                        .isRegularFileKey, .contentModificationDateKey])
                    guard v?.isRegularFile == true,
                          exts.contains(url.pathExtension.lowercased())
                    else { continue }
                    let m = v?.contentModificationDate ?? .distantPast
                    if best == nil || m > best!.1 { best = (url, m) }
                }
                if let url = best?.0 {
                    app.lastRenderURL = url
                    app.appendTerminal("[render] complete → \(url.path)\n")
                } else {
                    app.appendTerminal("[render] exited 0 but no video file found\n")
                }
            }
        } else {
            app.appendTerminal("[render] exited with status \(exit)\n")
        }
        app.isRendering = false
    }
}
