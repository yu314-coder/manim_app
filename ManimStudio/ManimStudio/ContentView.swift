// ContentView.swift — top-level app shell.
import SwiftUI
import UniformTypeIdentifiers

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
    @State private var selectedScene: String = ""
    @State private var confirmNew = false
    @State private var showOpener  = false
    @State private var showSaver   = false
    @State private var saveDoc: PythonSourceDoc? = nil

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
        .confirmationDialog("Start a new file?", isPresented: $confirmNew, titleVisibility: .visible) {
            Button("Discard current code", role: .destructive) {
                sourceCode = ""; selectedScene = ""
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Your current code will be cleared. Save first if you need it.")
        }
        .fileImporter(isPresented: $showOpener,
                      allowedContentTypes: [.pythonScript, .plainText],
                      allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                let scope = url.startAccessingSecurityScopedResource()
                defer { if scope { url.stopAccessingSecurityScopedResource() } }
                if let s = try? String(contentsOf: url, encoding: .utf8) {
                    sourceCode = s
                    selectedScene = ""
                }
            }
        }
        .fileExporter(isPresented: $showSaver,
                      document: saveDoc,
                      contentType: .pythonScript,
                      defaultFilename: "scene") { _ in }
    }

    private func triggerRender(quick: Bool) {
        guard !isRendering else { return }
        isRendering = true
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
        if let img = result.imagePath,
           FileManager.default.fileExists(atPath: img) {
            renderedVideoURL = URL(fileURLWithPath: img)
            let done = "\n\u{1b}[1;32m[\(label)]\u{1b}[0m output: \(img)\r\n"
            done.withCString { cs in
                _ = Darwin.write(PTYBridge.shared.stdoutPipeWriteFD, cs, strlen(cs))
            }
        }
        isRendering = false
    }

    private func stopRender() {
        guard isRendering else { return }
        // Equivalent to typing Ctrl-C in the terminal — manim catches the
        // KeyboardInterrupt between animations and aborts cleanly.
        PTYBridge.shared.send(data: [0x03])
        PythonRuntime.shared.interruptPythonMainThread()
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
