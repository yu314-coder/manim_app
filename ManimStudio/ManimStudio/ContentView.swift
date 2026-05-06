// ContentView.swift — top-level app shell.
import SwiftUI
import UniformTypeIdentifiers
import Photos

struct ContentView: View {
    @State private var selectedTab: AppTab = .workspace
    @AppStorage("manim_source") private var sourceCode: String = """
    from manim import *

    class HelloManim(Scene):
        def construct(self):
            title = Text("Hello, ManimStudio!").scale(0.9)
            self.play(Write(title))
            self.wait(0.5)
            self.play(title.animate.shift(UP*0.5).set_color(BLUE))
            self.wait(1)
    """
    @State private var isRendering = false
    @State private var renderedVideoURL: URL? = nil
    /// Timer that walks Documents/ToolOutputs/ during a render and
    /// promotes the newest produced .mp4/.gif/.png to
    /// `renderedVideoURL` so the preview pane shows partial movie
    /// segments mid-render instead of staying empty until the
    /// terminal handler fires (which can be minutes on a 1080p run).
    @State private var renderOutputPoller: Timer? = nil
    @State private var renderStartedAt: Date = .distantPast
    @State private var renderSurfacedURLs: Set<URL> = []
    @State private var selectedScene: String = ""
    @State private var confirmNew = false
    @State private var showOpener  = false
    @State private var showSaver   = false
    @State private var saveDoc: PythonSourceDoc? = nil
    @State private var renderCompleteURL: URL? = nil   // shows export sheet
    /// Forwarded down to EditorPane so we can paint render-error
    /// markers when a render fails. Reset on each render start.
    @State private var renderErrorMarkers: [MonacoEditorView.EditorMarker] = []

    private var detectedScenes: [String] {
        SceneDetector.detect(in: sourceCode)
    }

    var body: some View {
        VStack(spacing: 0) {
            HeaderView(
                isRendering: $isRendering,
                selectedScene: $selectedScene,
                detectedScenes: detectedScenes,
                onRender:  { triggerRender(quick: false) },
                onPreview: { triggerRender(quick: true) },
                onStop:    { stopRender() },
                onNew:     { confirmNew = true },
                onOpen:    { showOpener = true },
                onSave:    {
                    saveDoc = PythonSourceDoc(text: sourceCode)
                    showSaver = true
                }
            )
            TabBarView(selection: $selectedTab)

            Group {
                switch selectedTab {
                case .workspace:
                    WorkspaceView(
                        sourceCode: $sourceCode,
                        isRendering: $isRendering,
                        renderedVideoURL: $renderedVideoURL
                    )
                case .system:   SystemView()
                case .assets:   AssetsView()
                case .packages: PackagesView()
                case .history:  HistoryView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Theme.bgPrimary.ignoresSafeArea())
        .preferredColorScheme(.dark)
        .onChange(of: detectedScenes) { _, scenes in
            if !selectedScene.isEmpty && !scenes.contains(selectedScene) {
                selectedScene = ""
            }
        }
        // ── Menu-bar (Magic Keyboard) wiring. Each notification is
        // posted by ManimStudioCommands when the user picks a menu
        // item or hits its accelerator. We observe at ContentView
        // level for app-wide actions; editor-local actions are
        // observed inside EditorPane.
        .onReceive(NotificationCenter.default.publisher(for: .menuFileNew))    { _ in confirmNew = true }
        .onReceive(NotificationCenter.default.publisher(for: .menuFileOpen))   { _ in showOpener = true }
        .onReceive(NotificationCenter.default.publisher(for: .menuFileSave))   { _ in
            saveDoc = PythonSourceDoc(text: sourceCode); showSaver = true
        }
        .onReceive(NotificationCenter.default.publisher(for: .menuRenderRender))  { _ in triggerRender(quick: false) }
        .onReceive(NotificationCenter.default.publisher(for: .menuRenderPreview)) { _ in triggerRender(quick: true) }
        .onReceive(NotificationCenter.default.publisher(for: .menuRenderStop))    { _ in stopRender() }
        .onReceive(NotificationCenter.default.publisher(for: .menuRenderGPU))     { _ in
            let cur = UserDefaults.standard.object(forKey: "manim_gpu_on") as? Bool ?? true
            UserDefaults.standard.set(!cur, forKey: "manim_gpu_on")
        }
        .onReceive(NotificationCenter.default.publisher(for: .menuRenderClearOutputs)) { _ in
            // Reuse the SettingsSheet helper via direct file ops here
            // (avoids dragging the sheet open just to clear).
            if let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first,
               let entries = try? FileManager.default.contentsOfDirectory(
                    at: docs.appendingPathComponent("ToolOutputs"),
                    includingPropertiesForKeys: nil) {
                for u in entries { try? FileManager.default.removeItem(at: u) }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .menuViewTab)) { note in
            if let raw = (note.userInfo?["tab"] as? String),
               let tab = AppTab(rawValue: raw) {
                selectedTab = tab
            }
        }
        .confirmationDialog("Start a new file?", isPresented: $confirmNew, titleVisibility: .visible) {
            Button("Discard current code", role: .destructive) {
                sourceCode = ""; selectedScene = ""
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Your current code will be cleared. Save first if you need it.")
        }
        .background(
            DocumentPicker(
                isPresented: $showOpener,
                contentTypes: [.pythonScript, .plainText, .sourceCode, .text],
                allowsMultiple: false
            ) { urls in
                guard let url = urls.first else { return }
                let scope = url.startAccessingSecurityScopedResource()
                defer { if scope { url.stopAccessingSecurityScopedResource() } }
                if let s = try? String(contentsOf: url, encoding: .utf8) {
                    sourceCode = s
                    selectedScene = ""
                }
            }
        )
        .fileExporter(isPresented: $showSaver,
                      document: saveDoc,
                      contentType: .pythonScript,
                      defaultFilename: "scene") { _ in }
        .sheet(item: Binding(
            get: { renderCompleteURL.map { RenderedItem(url: $0) } },
            set: { renderCompleteURL = $0?.url }
        )) { item in
            RenderCompleteSheet(videoURL: item.url) {
                renderCompleteURL = nil
            }
        }
    }

    private func triggerRender(quick: Bool) {
        guard !isRendering else { return }
        // Clear stale error markers before each render so the editor
        // gutter reflects only the current run's outcome.
        renderErrorMarkers = []
        NotificationCenter.default.post(name: .editorClearMarkers, object: nil)
        isRendering = true
        renderStartedAt = Date()
        renderSurfacedURLs.removeAll()
        startRenderOutputPoller()
        // Keep the render going if the user switches apps or locks the
        // screen mid-render. iOS gives backgrounded apps ~30 s by
        // default; beginBackgroundTask extends that to a few minutes
        // for active "finishing" work — long enough for typical manim
        // renders. The token is released in logStream_done / stopRender.
        BackgroundTaskGuard.shared.begin(label: quick ? "preview" : "render")
        let label = quick ? "preview" : "render"
        let target = selectedScene.isEmpty ? "all scenes" : selectedScene
        // Render output flows into the live terminal automatically because
        // PythonRuntime redirects sys.stdout/stderr through PTYBridge's pipe.
        // We just write a header banner so the user sees where the run started.
        let banner = "\n\u{1b}[1;36m[\(label)]\u{1b}[0m starting at " +
                     "\(Date().formatted(date: .omitted, time: .standard)) — target: \(target)\r\n"
        banner.withCString { cs in
            _ = Darwin.write(PTYBridge.shared.stdoutPipeWriteFD, cs, strlen(cs))
        }
        setenv("OFFLINAI_MANIM_QUALITY", quick ? "low_quality" : "high_quality", 1)
        // GPU toggle (header bolt button): when off, force software
        // x264 encode; when on, allow manim's default h264_videotoolbox
        // hardware path. Persisted via @AppStorage("manim_gpu_on").
        let gpuOn = UserDefaults.standard.object(forKey: "manim_gpu_on") as? Bool ?? true
        setenv("OFFLINAI_MANIM_GPU", gpuOn ? "1" : "0", 1)

        let code = sourceCode
        let scene: String? = selectedScene.isEmpty ? nil : selectedScene
        // Plain GCD, NOT Task.detached. The polling loop inside execute()
        // blocks on DispatchSemaphore.wait — that ties up a cooperative
        // thread for the whole render. Two renders in a row exhaust the
        // cooperative pool → MainActor messaging stalls → buttons stop
        // responding. Plain GCD has its own dedicated worker threads.
        DispatchQueue.global(qos: .userInitiated).async {
            // onOutput is intentionally a no-op for terminal display.
            // The wrapper's _StreamWriter tees stdout/stderr directly to
            // PTYBridge.stdoutPipeWriteFD via os.write(), so SwiftTerm
            // already shows live output as Python prints it. Feeding via
            // TerminalAppender too would duplicate every line. We still
            // pass the closure (rather than nil) to keep PythonRuntime
            // in streaming mode — that triggers the file-poll loop which
            // is the canonical signal for "Python finished" + ensures
            // result.output is captured.
            let result = PythonRuntime.shared.execute(
                code: code,
                targetScene: scene,
                onOutput: { _ in /* PTY-tee handles terminal display */ }
            )
            DispatchQueue.main.async {
                self.logStream_done(label: label, result: result)
            }
        }
    }

    private func logStream_done(label: String, result: PythonRuntime.ExecutionResult) {
        stopRenderOutputPoller()
        // Path resolution priority:
        //   1. result.imagePath — what the wrapper script wrote to
        //      __codebench_plot_path. Usually populated.
        //   2. fallback walk — Documents/ToolOutputs/manim_*/videos/
        //      */<scene>.mp4 — the newest non-partial mp4 since the
        //      render started. Covers cases where the wrapper failed
        //      to set the global but manim DID produce the file.
        let imgPath: String? = {
            if let p = result.imagePath, FileManager.default.fileExists(atPath: p) {
                return p
            }
            return Self.findFinalRenderURL(after: renderStartedAt)?.path
        }()
        if let img = imgPath {
            let url = URL(fileURLWithPath: img)
            renderedVideoURL = url

            // Manim writes one `uncached_NNNNN.mp4` per animation into
            // <run>/videos/<res>/partial_movie_files/<scene>/, then
            // concatenates them into the final <scene>.mp4. The
            // partials are no longer useful once the concat finishes
            // — and they're huge: a 30-animation 1080p render leaves
            // ~500 MB of partials in Documents. Tear them out as soon
            // as we've confirmed the final file exists. Best-effort:
            // any failure is silent so a permission glitch doesn't
            // block the success path.
            cleanupPartials(finalVideo: url)

            let done = "\n\u{1b}[1;32m[\(label)]\u{1b}[0m output: \(img)\r\n"
            done.withCString { cs in
                _ = Darwin.write(PTYBridge.shared.stdoutPipeWriteFD, cs, strlen(cs))
            }
            // Auto-present an export sheet so the user can save the
            // finished render to Files / Photos / share via AirDrop /
            // Mail without first navigating to the History tab. The
            // file is already in Documents/ToolOutputs/ either way —
            // this is a "save as / share" convenience, not a required
            // step. Skipped for Preview renders so quick iteration
            // loops aren't interrupted by a sheet popping up every time.
            if label == "render" {
                renderCompleteURL = url
            }
        }
        // If no final video exists, the render likely raised — parse
        // the captured output for `File "<string>", line N` markers
        // pointing at the user's source.
        if result.imagePath == nil || result.imagePath?.isEmpty == true
            || (result.imagePath.flatMap { FileManager.default.fileExists(atPath: $0) ? $0 : nil }) == nil {
            let markers = Self.parseTracebackMarkers(in: result.output)
            if !markers.isEmpty {
                NotificationCenter.default.post(
                    name: .editorSetMarkers, object: nil,
                    userInfo: ["markers": markers])
            }
        }
        isRendering = false
        BackgroundTaskGuard.shared.end()
    }

    /// Pull `File "<string>", line N` (and similar) out of a Python
    /// traceback. `<string>` is the wrapper's tag for the user's
    /// source — `<offlinai-python-tool>` and module-qualified files
    /// are skipped because they point at our wrapper or library code.
    /// The final non-trace line of the captured output is used as
    /// the marker message (typically the exception type + reason).
    static func parseTracebackMarkers(in output: String) -> [MonacoEditorView.EditorMarker] {
        guard !output.isEmpty else { return [] }
        // Last line (excluding empties) — usually "NameError: name 'x'
        // is not defined" or similar.
        let lines = output.split(separator: "\n", omittingEmptySubsequences: false)
        var lastError = ""
        for line in lines.reversed() {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { continue }
            if trimmed.contains(": ") || trimmed.contains("Error") {
                lastError = trimmed
                break
            }
        }
        // Match File "<string>", line 7, in ...
        let regex = try? NSRegularExpression(
            pattern: #"File\s+"<string>",\s+line\s+(\d+)"#,
            options: [])
        guard let r = regex else { return [] }
        var seen = Set<Int>()
        var markers: [MonacoEditorView.EditorMarker] = []
        for line in lines {
            let s = String(line)
            let range = NSRange(s.startIndex..., in: s)
            for m in r.matches(in: s, options: [], range: range) {
                if m.numberOfRanges < 2 { continue }
                if let lineRange = Range(m.range(at: 1), in: s),
                   let n = Int(s[lineRange]),
                   !seen.contains(n) {
                    seen.insert(n)
                    markers.append(.init(line: n, column: 1,
                                          message: lastError.isEmpty ? "Render error here" : lastError))
                }
            }
        }
        return markers
    }

    /// Walk up from the final video URL to the per-render root and
    /// remove every `partial_movie_files/` subtree underneath. Manim's
    /// directory layout is:
    ///   ToolOutputs/manim_<hash>/videos/<resolution>/<scene>.mp4
    ///   ToolOutputs/manim_<hash>/videos/<resolution>/partial_movie_files/<scene>/uncached_*.mp4
    /// We resolve the `videos/<resolution>/` parent of the final mp4
    /// and delete its `partial_movie_files` if present. Defensive in
    /// case the layout changes — falls back to a recursive search
    /// inside the run root.
    private func cleanupPartials(finalVideo: URL) {
        let fm = FileManager.default
        let resolutionDir = finalVideo.deletingLastPathComponent()    // .../videos/<res>/
        let direct = resolutionDir.appendingPathComponent("partial_movie_files",
                                                          isDirectory: true)
        if fm.fileExists(atPath: direct.path) {
            try? fm.removeItem(at: direct)
            return
        }
        // Fallback: search up to <res>/'s parent (the manim_<hash>/
        // run dir) for any partial_movie_files dirs and prune them.
        let runRoot = resolutionDir.deletingLastPathComponent()         // .../manim_<hash>/
                                  .deletingLastPathComponent()          // .../videos/  (same)
        if let walker = fm.enumerator(at: runRoot,
                                      includingPropertiesForKeys: [.isDirectoryKey]) {
            for case let url as URL in walker
                where url.lastPathComponent == "partial_movie_files" {
                try? fm.removeItem(at: url)
                walker.skipDescendants()
            }
        }
    }

    private func stopRender() {
        guard isRendering else { return }
        // Equivalent to typing Ctrl-C in the terminal — manim catches the
        // KeyboardInterrupt between animations and aborts cleanly.
        PTYBridge.shared.send(data: [0x03])
        PythonRuntime.shared.interruptPythonMainThread()
        BackgroundTaskGuard.shared.end()
        stopRenderOutputPoller()
    }

    // MARK: live-preview polling

    /// Walks Documents/ToolOutputs/ every ~1.5 s while a render is
    /// running, looking for any .mp4/.gif/.png/.webm that's been
    /// modified since the render began. Promotes the newest one to
    /// `renderedVideoURL` so the preview pane updates with each
    /// partial movie file as manim writes them, instead of staying
    /// empty for the entire 5-10 minutes a 1080p high-quality render
    /// can take. The PreviewPane re-loads its AVPlayer when the URL
    /// changes, so the user sees real-time render progress.
    private func startRenderOutputPoller() {
        stopRenderOutputPoller()
        guard let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask).first
        else { return }
        let outputs = docs.appendingPathComponent("ToolOutputs",
                                                   isDirectory: true)
        renderOutputPoller = Timer.scheduledTimer(
            withTimeInterval: 1.5, repeats: true) { _ in
            DispatchQueue.main.async {
                self.scanForFreshOutput(under: outputs)
            }
        }
        if let t = renderOutputPoller {
            RunLoop.main.add(t, forMode: .common)
        }
    }

    private func stopRenderOutputPoller() {
        renderOutputPoller?.invalidate()
        renderOutputPoller = nil
    }

    /// Static fallback — walk Documents/ToolOutputs/ for the newest
    /// non-partial mp4/.gif/.png modified after `start`. Used when
    /// result.imagePath is empty so the user still sees their video
    /// even if the wrapper script's global lookup misfired.
    static func findFinalRenderURL(after start: Date) -> URL? {
        guard let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask).first
        else { return nil }
        let outputs = docs.appendingPathComponent("ToolOutputs", isDirectory: true)
        guard let walker = FileManager.default.enumerator(
            at: outputs,
            includingPropertiesForKeys: [.contentModificationDateKey,
                                          .isRegularFileKey,
                                          .fileSizeKey],
            options: [.skipsHiddenFiles])
        else { return nil }
        let exts: Set<String> = ["mp4", "mov", "m4v", "webm", "gif", "png"]
        var best: (URL, Date)?
        for case let url as URL in walker {
            if url.pathComponents.contains("partial_movie_files") { continue }
            let v = try? url.resourceValues(forKeys: [
                .isRegularFileKey, .contentModificationDateKey, .fileSizeKey])
            guard v?.isRegularFile == true,
                  exts.contains(url.pathExtension.lowercased()),
                  (v?.fileSize ?? 0) > 0,
                  let mtime = v?.contentModificationDate,
                  mtime >= start
            else { continue }
            if best == nil || mtime > best!.1 { best = (url, mtime) }
        }
        return best?.0
    }

    private func scanForFreshOutput(under outputs: URL) {
        let exts: Set<String> = ["mp4", "mov", "m4v", "webm", "gif", "png"]
        guard let walker = FileManager.default.enumerator(
            at: outputs,
            includingPropertiesForKeys: [.contentModificationDateKey,
                                          .isRegularFileKey,
                                          .fileSizeKey],
            options: [.skipsHiddenFiles])
        else { return }
        var best: (URL, Date)?
        for case let url as URL in walker {
            // CRITICAL: skip files inside partial_movie_files/ — those
            // are per-animation chunks manim deletes once the final
            // concat finishes (cleanupPartials() runs on success).
            // If we set renderedVideoURL to a partial, AVPlayer then
            // points at a deleted file and shows nothing. Keep the
            // poller restricted to the final video tree:
            //   <run>/videos/<res>/<scene>.mp4
            if url.pathComponents.contains("partial_movie_files") { continue }
            let v = try? url.resourceValues(forKeys: [
                .isRegularFileKey, .contentModificationDateKey, .fileSizeKey])
            guard v?.isRegularFile == true,
                  exts.contains(url.pathExtension.lowercased()),
                  // Ignore zero-byte placeholders manim creates
                  // before encoding starts.
                  (v?.fileSize ?? 0) > 0,
                  let mtime = v?.contentModificationDate,
                  // Only consider files newer than the render start —
                  // skip leftovers from previous runs.
                  mtime >= renderStartedAt
            else { continue }
            if best == nil || mtime > best!.1 { best = (url, mtime) }
        }
        if let (url, _) = best, !renderSurfacedURLs.contains(url) {
            renderSurfacedURLs.insert(url)
            renderedVideoURL = url
        }
    }
}

#Preview { ContentView() }

// MARK: - File document for Save (.py)

struct PythonSourceDoc: FileDocument {
    static var readableContentTypes: [UTType] { [.pythonScript, .plainText] }
    static var writableContentTypes: [UTType] { [.pythonScript] }
    var text: String
    init(text: String) { self.text = text }
    init(configuration: ReadConfiguration) throws {
        let data = configuration.file.regularFileContents ?? Data()
        text = String(data: data, encoding: .utf8) ?? ""
    }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: Data(text.utf8))
    }
}

extension UTType {
    /// public.python-script — declared by the system on iOS 14+.
    static var pythonScript: UTType {
        UTType("public.python-script") ?? .plainText
    }
}

// MARK: - Render-complete export sheet
//
// Pops up after a Final render finishes. Gives the user every
// reasonable destination in one place: pick a folder via the iOS
// document picker, save to Photos, or share via the system activity
// sheet (AirDrop, Mail, Messages, …). The original file stays put in
// Documents/ToolOutputs/ regardless of what they choose — this is a
// copy-out flow, not a move.

private struct RenderedItem: Identifiable {
    let url: URL
    var id: URL { url }
}

private struct RenderCompleteSheet: View {
    let videoURL: URL
    var onDismiss: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var showExporter = false
    @State private var showShare    = false
    @State private var saveStatus: String? = nil

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                // Preview thumbnail strip
                VStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 44))
                        .foregroundStyle(.green)
                    Text("Render complete")
                        .font(.system(size: 18, weight: .semibold))
                    Text(videoURL.lastPathComponent)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1).truncationMode(.middle)
                    Text(fileSize)
                        .font(.system(size: 11))
                        .foregroundStyle(.tertiary)
                }
                .padding(.top, 12)

                Divider()

                VStack(spacing: 10) {
                    actionButton("Save to Files…",
                                 icon: "folder.badge.plus",
                                 tint: .blue) {
                        showExporter = true
                    }
                    actionButton("Save to Photos",
                                 icon: "photo.on.rectangle.angled",
                                 tint: .pink) {
                        saveToPhotos()
                    }
                    actionButton("Share…",
                                 icon: "square.and.arrow.up",
                                 tint: .indigo) {
                        showShare = true
                    }
                }
                .padding(.horizontal, 12)

                if let status = saveStatus {
                    Text(status)
                        .font(.system(size: 12))
                        .foregroundStyle(status.hasPrefix("✓") ? .green : .red)
                        .padding(.top, 4)
                }

                Spacer()

                Text("The original copy stays in\nDocuments/ToolOutputs/.")
                    .font(.system(size: 11))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.tertiary)
                    .padding(.bottom, 8)
            }
            .padding(.horizontal, 16)
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss(); onDismiss() }
                }
            }
            .fileExporter(isPresented: $showExporter,
                          document: VideoFileDoc(url: videoURL),
                          contentType: contentType,
                          defaultFilename: videoURL.deletingPathExtension().lastPathComponent) { result in
                switch result {
                case .success:
                    saveStatus = "✓ Saved to Files"
                    autoDismiss()
                case .failure(let err):
                    // .userCancelled shouldn't surface as an error.
                    if (err as NSError).code != NSUserCancelledError {
                        saveStatus = "Save failed: \(err.localizedDescription)"
                    }
                }
            }
            .sheet(isPresented: $showShare,
                   onDismiss: { autoDismiss() }) {
                ShareSheet(items: [videoURL])
            }
        }
        .presentationDetents([.medium, .large])
    }

    // MARK: helpers

    private var contentType: UTType {
        switch videoURL.pathExtension.lowercased() {
        case "mp4", "m4v": return .mpeg4Movie
        case "mov":         return .quickTimeMovie
        case "gif":         return .gif
        case "png":         return .png
        case "jpg", "jpeg": return .jpeg
        default:            return .data
        }
    }

    private var fileSize: String {
        let bytes = (try? videoURL.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        return ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }

    @ViewBuilder
    private func actionButton(_ title: String, icon: String, tint: Color,
                              action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.system(size: 17))
                    .foregroundStyle(.white)
                    .frame(width: 36, height: 36)
                    .background(RoundedRectangle(cornerRadius: 8).fill(tint))
                Text(title)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(Color.primary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.tertiary)
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 10)
                .fill(Color(.secondarySystemBackground)))
        }
        .buttonStyle(.plain)
    }

    private func saveToPhotos() {
        let ext = videoURL.pathExtension.lowercased()
        let isVideo = ["mp4", "mov", "m4v"].contains(ext)
        let isImage = ["png", "jpg", "jpeg", "gif"].contains(ext)
        // Photos write needs PHPhotoLibrary auth; we request it at the
        // moment of save rather than at app launch so the prompt is
        // contextual (the user just tapped "Save to Photos").
        import_PhotoLibrary { granted in
            guard granted else {
                saveStatus = "Photos access denied — enable in Settings"
                return
            }
            if isVideo {
                UISaveVideoAtPathToSavedPhotosAlbum(videoURL.path, nil, nil, nil)
                saveStatus = "✓ Saved to Photos"
                autoDismiss()
            } else if isImage, let ui = UIImage(contentsOfFile: videoURL.path) {
                UIImageWriteToSavedPhotosAlbum(ui, nil, nil, nil)
                saveStatus = "✓ Saved to Photos"
                autoDismiss()
            } else {
                saveStatus = "Format not supported by Photos"
            }
        }
    }

    /// Close the export sheet ~0.9 s after a successful save so the
    /// user briefly sees the green confirmation, then we get out of
    /// their way. Without this the sheet sat open with a one-line
    /// status and the user had to hit Done — strange UX.
    private func autoDismiss() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.9) {
            dismiss()
            onDismiss()
        }
    }

    /// Photos auth wrapper isolated so its single import is contained.
    private func import_PhotoLibrary(_ completion: @escaping (Bool) -> Void) {
        // PHPhotoLibrary needs the Photos framework; keeping the
        // import here avoids touching it at app launch.
        import_photos_request(completion)
    }

    private func import_photos_request(_ completion: @escaping (Bool) -> Void) {
        // Defer to PhotoSaver helper to avoid leaking Photos imports
        // into the file's preamble.
        PhotoSaver.requestAuth(completion)
    }
}

/// Minimal FileDocument wrapping the rendered video for fileExporter.
/// We don't read the bytes through Data — the file might be hundreds
/// of MB; SwiftUI reads from the FileWrapper(URL:) directly which
/// streams off disk.
private struct VideoFileDoc: FileDocument {
    static var readableContentTypes: [UTType] {
        [.mpeg4Movie, .quickTimeMovie, .gif, .png, .jpeg, .data]
    }
    let url: URL
    init(url: URL) { self.url = url }
    init(configuration: ReadConfiguration) throws {
        url = URL(fileURLWithPath: "/dev/null")
    }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        try FileWrapper(url: url, options: [.immediate])
    }
}

/// Tiny PhotoLibrary auth helper.
private enum PhotoSaver {
    static func requestAuth(_ completion: @escaping (Bool) -> Void) {
        let cur = PHPhotoLibrary.authorizationStatus(for: .addOnly)
        switch cur {
        case .authorized, .limited:
            completion(true)
        case .notDetermined:
            PHPhotoLibrary.requestAuthorization(for: .addOnly) { s in
                DispatchQueue.main.async {
                    completion(s == .authorized || s == .limited)
                }
            }
        default:
            completion(false)
        }
    }
}
