// HeaderView.swift — top header bar with functional Settings / Theme / Help / Colors.
import SwiftUI

struct HeaderView: View {
    @Binding var isRendering: Bool
    @Binding var selectedScene: String   // "" = all scenes, "*" = explicit-all, otherwise class name
    var detectedScenes: [String]          // class names found in current source
    var onRender:  () -> Void
    var onPreview: () -> Void
    var onStop:    () -> Void
    var onNew:     () -> Void
    var onOpen:    () -> Void
    var onSave:    () -> Void

    // Persisted across launches and read by PythonRuntime before each
    // render. The GPU toggle now drives BOTH:
    //   • encode  — h264_videotoolbox (hardware) vs mpeg4 (software)
    //   • render  — CairoMetal GPU rasterization vs software cairo
    //               (when the CairoMetal shim is bundled; no-ops to
    //                software cairo otherwise)
    // Default ON. Hardware encode is ~5× faster; GPU rasterization is
    // correctness/parity (per profiling it doesn't change render speed —
    // lower FPS is the real speed lever).
    @AppStorage("manim_gpu_on") private var gpuOn = true
    @State private var autosaveText = "Autosaved"

    // Persistent UI state — used by the Settings sheet.
    @AppStorage("manim_accent_hex") private var accentHex: String = "6366F1"
                                                        // indigo default
    @AppStorage("manim_terminal_font") private var terminalFontSize: Double = 13

    // Observe the accent so the header's gradient buttons retint live the
    // moment the colour changes in Settings or the colour popover.
    @ObservedObject private var theme = ThemeManager.shared

    @State private var showSettings = false
    @State private var showHelp     = false
    @State private var showColors   = false

    /// iPhone gets a stripped-down single-line header — three-block
    /// layout with title + scene picker + render/preview/stop only.
    /// All secondary controls (GPU toggle, colors, theme, settings,
    /// help, file ops) move into a single overflow menu so the row
    /// fits in 390-pt portrait without truncating.
    @Environment(\.horizontalSizeClass) private var hSizeClass
    private var compact: Bool { hSizeClass == .compact }

    /// Marketing version straight from the bundle
    /// (CFBundleShortVersionString = project MARKETING_VERSION), so the
    /// header label always matches the real build instead of a hardcoded
    /// string that silently drifts out of sync.
    private var appVersion: String {
        (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "1.3"
    }

    var body: some View {
        Group {
            if compact { compactBody } else { regularBody }
        }
        .preferredColorScheme(.dark)   // Resonance is a dark-only design
        .sheet(isPresented: $showSettings) {
            SettingsSheet(accentHex: $accentHex,
                          terminalFontSize: $terminalFontSize,
                          gpuOn: $gpuOn)
        }
        .sheet(isPresented: $showHelp) { HelpSheet() }
        .onReceive(NotificationCenter.default.publisher(for: .menuHelpOpenHelp))     { _ in showHelp = true }
        .onReceive(NotificationCenter.default.publisher(for: .menuHelpShortcuts))    { _ in showHelp = true }
        .onReceive(NotificationCenter.default.publisher(for: .menuHelpOpenSettings)) { _ in showSettings = true }
        .onReceive(NotificationCenter.default.publisher(for: .menuHelpOpenLog)) { _ in
            if let url = CrashLogger.shared.fileURL {
                let dir = url.deletingLastPathComponent().path
                if let u = URL(string: "shareddocuments://\(dir)") {
                    UIApplication.shared.open(u)
                }
            }
        }
    }

    // MARK: compact (iPhone)

    private var compactBody: some View {
        HStack(spacing: 8) {
            // App icon as a more menu — taps open settings/help/etc.
            Menu {
                Button { onNew() }  label: { Label("New File",  systemImage: "doc.badge.plus") }
                Button { onOpen() } label: { Label("Open…",     systemImage: "folder") }
                Button { onSave() } label: { Label("Save…",     systemImage: "square.and.arrow.down") }
                Divider()
                Toggle(isOn: $gpuOn) { Label("GPU acceleration", systemImage: "bolt.fill") }
                Button { showColors = true }  label: { Label("Accent color", systemImage: "paintpalette") }
                Divider()
                Button { showSettings = true } label: { Label("Settings", systemImage: "gearshape") }
                Button { showHelp = true }     label: { Label("Help",     systemImage: "questionmark.circle") }
            } label: {
                Text("🎬").font(.system(size: 20))
                    .frame(width: 34, height: 34)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            }
            .popover(isPresented: $showColors, arrowEdge: .bottom) {
                ColorPanelPopover(accentHex: $accentHex)
            }

            scenePicker

            Spacer(minLength: 4)

            // Render / Preview / Stop — iconified versions to fit.
            Button(action: onRender) {
                HStack(spacing: 4) {
                    Image(systemName: "play.fill").font(.system(size: 11, weight: .bold))
                    Text("Run").font(.system(size: 12, weight: .semibold))
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(RoundedRectangle(cornerRadius: 8).fill(Theme.signatureGradient))
            }
            .buttonStyle(.plain)
            .help("Render (⌘R)")
            Button(action: onPreview) {
                Image(systemName: "eye")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.textPrimary)
                    .frame(width: 34, height: 34)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            }
            .buttonStyle(.plain)
            .help("Preview (⇧⌘R)")
            if isRendering {
                Button(action: onStop) {
                    Image(systemName: "stop.fill")
                        .font(.system(size: 13))
                        .foregroundStyle(.white)
                        .frame(width: 34, height: 34)
                        .background(RoundedRectangle(cornerRadius: 8).fill(Theme.error))
                }
                .buttonStyle(.plain)
                .help("Stop")
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
        .frame(height: 48)
        .background(
            Theme.bgSecondary
                .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1), alignment: .bottom)
        )
    }

    // MARK: regular (iPad)

    private var regularBody: some View {
        HStack(spacing: 16) {
            // LEFT — logo + title + autosave
            HStack(spacing: 10) {
                Text("🎬").font(.system(size: 22))
                VStack(alignment: .leading, spacing: 0) {
                    Text("Manim Animation Studio")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                    Text("Professional Edition v\(appVersion)")
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.textDim)
                }
                HStack(spacing: 4) {
                    Circle().fill(Theme.success).frame(width: 6, height: 6)
                    Text(autosaveText).font(.system(size: 10)).foregroundStyle(Theme.textSecondary)
                }
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(Capsule().fill(Theme.bgTertiary))
            }

            Spacer(minLength: 12)

            // CENTER — file ops, render/preview/stop, GPU, colors
            HStack(spacing: 6) {
                headerBtn("doc.badge.plus", "New",  action: onNew)
                headerBtn("folder",         "Open", action: onOpen)
                headerBtn("square.and.arrow.down", "Save", action: onSave)
                Divider().frame(height: 18).background(Theme.borderSubtle)

                scenePicker
                primaryBtn(label: "Render", icon: "play.fill", shortcut: "F5",
                           action: onRender)
                secondaryBtn(label: "Preview", icon: "eye", shortcut: "F6",
                             action: onPreview)
                if isRendering {
                    dangerBtn(label: "Stop", icon: "stop.fill", action: onStop)
                }

                Divider().frame(height: 18).background(Theme.borderSubtle)
                Button {
                    gpuOn.toggle()
                } label: {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(gpuOn ? .white : Theme.textSecondary)
                        .frame(width: 30, height: 30)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(gpuOn
                                      ? AnyShapeStyle(Theme.signatureGradient)
                                      : AnyShapeStyle(Theme.bgTertiary))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(gpuOn ? Color.clear : Theme.borderSubtle,
                                        lineWidth: 1)
                        )
                        .shadow(color: gpuOn ? Theme.glowPrimary : .clear,
                                radius: 6)
                }
                .buttonStyle(.plain)
                .help(gpuOn ? "GPU acceleration ON (Metal render + hardware encode)"
                            : "GPU acceleration OFF (software render + encode)")

                // Colors → opens accent color picker.
                headerBtn("paintpalette", "Colors") { showColors.toggle() }
                    .popover(isPresented: $showColors) {
                        ColorPanelPopover(accentHex: $accentHex)
                    }
            }

            Spacer(minLength: 12)

            // RIGHT — LaTeX status, settings, theme toggle, help
            HStack(spacing: 8) {
                HStack(spacing: 4) {
                    Image(systemName: "function").font(.system(size: 10))
                    Text("LaTeX").font(.system(size: 10, weight: .medium))
                }
                .foregroundStyle(Theme.success)
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Capsule().fill(Theme.success.opacity(0.12)))
                .overlay(Capsule().stroke(Theme.success.opacity(0.4), lineWidth: 1))

                headerBtn("gearshape", "Settings") { showSettings.toggle() }
                headerBtn("questionmark.circle", "Help") { showHelp.toggle() }
            }
        }
        .padding(.horizontal, 14)
        .frame(height: 52)
        .background(
            Theme.bgSecondary
                .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1), alignment: .bottom)
        )
    }

    // MARK: scene picker

    @ViewBuilder
    private var scenePicker: some View {
        Menu {
            Button {
                selectedScene = ""
            } label: {
                if selectedScene.isEmpty {
                    Label("All scenes", systemImage: "checkmark")
                } else {
                    Text("All scenes")
                }
            }
            if !detectedScenes.isEmpty { Divider() }
            ForEach(detectedScenes, id: \.self) { name in
                Button {
                    selectedScene = name
                } label: {
                    if selectedScene == name {
                        Label(name, systemImage: "checkmark")
                    } else {
                        Text(name)
                    }
                }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: "rectangle.stack").font(.system(size: 11))
                Text(label)
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                Image(systemName: "chevron.down").font(.system(size: 9))
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderSubtle, lineWidth: 1))
        }
        .help("Choose which Scene class to render")
        .disabled(detectedScenes.isEmpty)
    }

    private var label: String {
        if selectedScene.isEmpty {
            return detectedScenes.isEmpty ? "No Scene" : "All (\(detectedScenes.count))"
        }
        return selectedScene
    }

    // MARK: button styles

    @ViewBuilder
    private func headerBtn(_ icon: String, _ tooltip: String, action: @escaping () -> Void = {}) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 30, height: 30)
                .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderSubtle, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .help(tooltip)
    }

    @ViewBuilder
    private func primaryBtn(label: String, icon: String, shortcut: String, action: @escaping () -> Void) -> some View {
        // Shortcut badge dropped — the menu bar surfaces ⌘R / F5 etc.
        // Inline badge + label was forcing truncation on iPad headers.
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 12, weight: .bold))
                Text(label)
                    .font(.system(size: 13, weight: .semibold))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 14).padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.signatureGradient))
            .shadow(color: Theme.glowPrimary, radius: 8, y: 2)
        }
        .buttonStyle(.plain)
        .help("\(label) (\(shortcut))")
    }

    @ViewBuilder
    private func secondaryBtn(label: String, icon: String, shortcut: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 12))
                Text(label)
                    .font(.system(size: 13, weight: .medium))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderActive, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .help("\(label) (\(shortcut))")
    }

    @ViewBuilder
    private func dangerBtn(label: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: 11))
                Text(label).font(.system(size: 12, weight: .semibold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.error))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Sheets

private struct SettingsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var accentHex: String
    @Binding var terminalFontSize: Double
    @Binding var gpuOn: Bool

    // Additional settings — read where the rest of the app reads them.
    @AppStorage("manim_final_quality") private var finalQuality = "1080p"
    @AppStorage("manim_final_fps")     private var finalFPS = 30
    @AppStorage("manim_format")        private var format = "mp4"
    @AppStorage("manim_terminal_font_family") private var terminalFontFamily = "Menlo"

    /// Quick accent presets (default indigo first). Uppercase hex so the
    /// selected-ring comparison against accentHex.uppercased() matches.
    private static let accentPresets = ["6366F1", "8B5CF6", "EC4899", "F43F5E",
                                        "F59E0B", "10B981", "06B6D4", "3B82F6"]

    @State private var confirmReset = false
    @State private var confirmClearOutputs = false
    @State private var confirmClearLogs = false
    @State private var showShareLog = false

    var body: some View {
        NavigationStack {
            Form {
                // — Accent ————————————————————————————————————
                Section {
                    HStack {
                        Text("Hex")
                        Spacer()
                        TextField("Hex", text: $accentHex)
                            .frame(width: 90)
                            .multilineTextAlignment(.trailing)
                            .font(.system(size: 13, design: .monospaced))
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                        Circle()
                            .fill(Color(hex: accentHex) ?? .indigo)
                            .frame(width: 18, height: 18)
                            .overlay(Circle().stroke(Color.secondary.opacity(0.3), lineWidth: 1))
                    }
                    HStack(spacing: 12) {
                        ForEach(Self.accentPresets, id: \.self) { hx in
                            Button { accentHex = hx } label: {
                                Circle()
                                    .fill(Color(hex: hx) ?? .gray)
                                    .frame(width: 26, height: 26)
                                    .overlay(Circle().stroke(.white,
                                        lineWidth: accentHex.uppercased() == hx ? 2 : 0))
                            }
                            .buttonStyle(.plain)
                        }
                        Spacer()
                    }
                    .padding(.vertical, 2)
                    // Live preview — retints the instant the accent changes.
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(Theme.accentGradient(forHex: accentHex))
                        .frame(height: 24)
                        .overlay(Text("Signature gradient")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.9)))
                } header: {
                    Text("Accent colour")
                } footer: {
                    Text("Tints buttons, highlights, selection and the signature gradient across the app. The app uses a fixed dark theme.")
                }

                // — Render Log ─────────────────────────────────────
                Section("Render Log") {
                    HStack {
                        Text("Font size")
                        Slider(value: $terminalFontSize, in: 9...22, step: 1)
                        Text("\(Int(terminalFontSize))pt")
                            .font(.system(size: 12, design: .monospaced))
                            .frame(width: 44, alignment: .trailing)
                    }
                    Picker("Font family", selection: $terminalFontFamily) {
                        Text("Menlo").tag("Menlo")
                        Text("SF Mono").tag("SF Mono")
                        Text("Courier").tag("Courier")
                    }
                }

                // — Render —————————————————————————————————————
                Section("Render") {
                    Toggle(isOn: $gpuOn) {
                        Label("GPU acceleration (Metal + VideoToolbox)",
                              systemImage: "bolt.fill")
                    }
                    Picker(selection: $finalQuality) {
                        ForEach(["480p", "720p", "1080p", "1440p", "4K", "8K"],
                                id: \.self) { Text($0).tag($0) }
                    } label: {
                        Label("Final quality", systemImage: "film")
                    }
                    Picker(selection: $finalFPS) {
                        ForEach([24, 30, 60, 120], id: \.self) { Text("\($0) fps").tag($0) }
                    } label: {
                        Label("Final FPS", systemImage: "speedometer")
                    }
                    Picker(selection: $format) {
                        ForEach(["mp4", "gif", "html"], id: \.self) { Text($0).tag($0) }
                    } label: {
                        Label("Output format", systemImage: "doc")
                    }
                }

                // — Storage ————————————————————————————————————
                Section("Storage") {
                    LabeledContent("Renders folder",
                                   value: "Documents/ToolOutputs")
                    LabeledContent("Assets folder",
                                   value: "Documents/Assets")
                    LabeledContent("Workspace cwd",
                                   value: "Documents/Workspace")
                    Button(role: .destructive) {
                        confirmClearOutputs = true
                    } label: {
                        Label("Delete all rendered outputs",
                              systemImage: "film.stack")
                    }
                }

                // — Diagnostics ———————————————————————————————
                Section("Diagnostics") {
                    if let url = CrashLogger.shared.fileURL {
                        LabeledContent("Log file",
                                       value: url.lastPathComponent)
                            .font(.system(size: 12, design: .monospaced))
                        NavigationLink {
                            LogViewerView(url: url)
                        } label: {
                            Label("View log", systemImage: "doc.text.magnifyingglass")
                        }
                        Button {
                            showShareLog = true
                        } label: {
                            Label("Share log file",
                                  systemImage: "square.and.arrow.up")
                        }
                    }
                    Button(role: .destructive) {
                        confirmClearLogs = true
                    } label: {
                        Label("Clear log file", systemImage: "trash")
                    }
                }

                // — About ———————————————————————————————————————
                Section("About") {
                    LabeledContent("Version",      value: bundleVersion())
                    LabeledContent("Build",        value: bundleBuild())
                    LabeledContent("Manim",        value: "0.20.1")
                    LabeledContent("Python",       value: "3.14")
                    LabeledContent("Device",       value: deviceModel())
                    Link(destination: URL(string: "https://docs.manim.community/")!) {
                        Label("Manim documentation",
                              systemImage: "book")
                    }
                    Link(destination: URL(string: "https://github.com/yu314-coder/python-ios-lib/")!) {
                        Label("python-ios-lib repo",
                              systemImage: "chevron.left.forwardslash.chevron.right")
                    }
                }

                // — Reset ———————————————————————————————————————
                Section {
                    Button(role: .destructive) {
                        confirmReset = true
                    } label: {
                        Label("Reset all settings", systemImage: "arrow.counterclockwise")
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .confirmationDialog("Reset every preference?",
                                isPresented: $confirmReset,
                                titleVisibility: .visible) {
                Button("Reset", role: .destructive) { resetAllSettings() }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Theme, accent, render presets, GPU toggle, fonts.\nDoes not delete files in Documents.")
            }
            .confirmationDialog("Delete all rendered outputs?",
                                isPresented: $confirmClearOutputs,
                                titleVisibility: .visible) {
                Button("Delete", role: .destructive) { clearOutputs() }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Removes everything in Documents/ToolOutputs/. Renders cannot be recovered.")
            }
            .confirmationDialog("Clear log file?",
                                isPresented: $confirmClearLogs,
                                titleVisibility: .visible) {
                Button("Clear", role: .destructive) { clearLogFile() }
                Button("Cancel", role: .cancel) {}
            }
            .sheet(isPresented: $showShareLog) {
                if let url = CrashLogger.shared.fileURL {
                    ShareSheet(items: [url])
                }
            }
        }
    }

    // MARK: actions

    private func resetAllSettings() {
        let keys = ["manim_theme_mode", "manim_accent_hex",
                    "manim_terminal_font", "manim_terminal_font_family",
                    "manim_gpu_on",
                    "manim_final_quality", "manim_final_fps",
                    "manim_preview_quality", "manim_preview_fps",
                    "manim_format", "manim_quality", "manim_fps"]
        for k in keys { UserDefaults.standard.removeObject(forKey: k) }
        accentHex = "6366F1"
        terminalFontSize = 13
        terminalFontFamily = "Menlo"
        gpuOn = true
        finalQuality = "1080p"
        finalFPS = 30
        format = "mp4"
    }

    private func clearOutputs() {
        guard let docs = FileManager.default.urls(for: .documentDirectory,
                                                  in: .userDomainMask).first else { return }
        let dir = docs.appendingPathComponent("ToolOutputs")
        if let entries = try? FileManager.default.contentsOfDirectory(at: dir,
                                                                       includingPropertiesForKeys: nil) {
            for u in entries { try? FileManager.default.removeItem(at: u) }
        }
    }

    private func clearLogFile() {
        guard let url = CrashLogger.shared.fileURL else { return }
        try? Data().write(to: url)
    }

    private func bundleVersion() -> String {
        (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "?"
    }
    private func bundleBuild() -> String {
        (Bundle.main.infoDictionary?["CFBundleVersion"] as? String) ?? "?"
    }
    private func deviceModel() -> String {
        var info = utsname()
        uname(&info)
        return withUnsafePointer(to: &info.machine) { ptr -> String in
            ptr.withMemoryRebound(to: CChar.self, capacity: Int(_SYS_NAMELEN)) {
                String(cString: $0)
            }
        }
    }
}

private struct HelpSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var copied: String? = nil

    enum Tab: String, CaseIterable, Identifiable {
        case guide      = "Guide"
        case shortcuts  = "Shortcuts"
        case snippets   = "Snippets"
        case faq        = "FAQ"
        case trouble    = "Troubleshooting"
        var id: String { rawValue }
        var icon: String {
            switch self {
            case .guide:     return "book"
            case .shortcuts: return "keyboard"
            case .snippets:  return "doc.on.doc"
            case .faq:       return "questionmark.bubble"
            case .trouble:   return "wrench.and.screwdriver"
            }
        }
    }
    @State private var tab: Tab = .guide

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("", selection: $tab) {
                    ForEach(Tab.allCases) { t in
                        Label(t.rawValue, systemImage: t.icon).tag(t)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 12).padding(.vertical, 8)

                switch tab {
                case .guide:     guideTab
                case .shortcuts: shortcutsTab
                case .snippets:  snippetsTab
                case .faq:       faqTab
                case .trouble:   troubleTab
                }
            }
            .navigationTitle("Help")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always),
                        prompt: "Search help…")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .overlay(alignment: .bottom) {
                if let c = copied {
                    Text("Copied: \(c)")
                        .font(.system(size: 12, weight: .medium))
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        .background(.thinMaterial, in: Capsule())
                        .padding(.bottom, 16)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(.easeOut(duration: 0.2), value: copied)
        }
    }

    // MARK: tabs

    private var guideTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                ForEach(filtered(guideSections), id: \.0) { (title, body) in
                    section(title, body)
                }
            }
            .padding(16)
        }
    }

    private var shortcutsTab: some View {
        List {
            ForEach(filtered2(shortcutGroups), id: \.0) { group in
                Section(group.0) {
                    ForEach(group.1, id: \.0) { (key, desc) in
                        HStack {
                            Text(key)
                                .font(.system(size: 13, design: .monospaced))
                                .frame(width: 110, alignment: .leading)
                                .foregroundStyle(Theme.accentPrimary)
                            Text(desc).foregroundStyle(Theme.textPrimary)
                        }
                    }
                }
            }
        }
    }

    private var snippetsTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(filtered2(snippets), id: \.0) { (title, items) in
                    Text(title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                    ForEach(items, id: \.0) { (name, code) in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(name)
                                    .font(.system(size: 12, weight: .semibold))
                                Spacer()
                                Button {
                                    UIPasteboard.general.string = code
                                    withAnimation(.easeOut(duration: 0.15)) {
                                        copied = name
                                    }
                                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
                                        if copied == name {
                                            withAnimation(.easeIn(duration: 0.2)) {
                                                copied = nil
                                            }
                                        }
                                    }
                                } label: {
                                    Label(copied == name ? "Copied" : "Copy",
                                          systemImage: copied == name
                                              ? "checkmark.circle.fill"
                                              : "doc.on.doc")
                                        .font(.system(size: 11, weight: copied == name ? .semibold : .regular))
                                        .foregroundStyle(copied == name ? Theme.success : Color.primary)
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                                .tint(copied == name ? Theme.success : Theme.accentPrimary)
                            }
                            Text(code)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(Theme.textPrimary)
                                .padding(8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(RoundedRectangle(cornerRadius: 6)
                                    .fill(Theme.bgSecondary))
                                .overlay(RoundedRectangle(cornerRadius: 6)
                                    .stroke(Theme.borderSubtle, lineWidth: 1))
                                .textSelection(.enabled)
                        }
                    }
                }
            }
            .padding(16)
        }
    }

    private var faqTab: some View {
        List {
            ForEach(filtered(faqs), id: \.0) { (q, a) in
                DisclosureGroup {
                    Text(a).font(.system(size: 13)).foregroundStyle(.secondary)
                        .padding(.top, 4)
                } label: {
                    Text(q).font(.system(size: 13, weight: .medium))
                }
            }
        }
    }

    private var troubleTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                ForEach(filtered(troubleshooting), id: \.0) { (title, body) in
                    section(title, body)
                }
                Divider().padding(.vertical, 4)
                Text("Quick actions")
                    .font(.system(size: 13, weight: .semibold))
                actionRow("Reveal log file in Files app",
                          icon: "doc.text.magnifyingglass") {
                    if let url = CrashLogger.shared.fileURL {
                        UIApplication.shared.open(folderURL(url))
                    }
                }
                actionRow("Open Manim docs in browser",
                          icon: "book") {
                    if let u = URL(string: "https://docs.manim.community/") {
                        UIApplication.shared.open(u)
                    }
                }
                actionRow("Open project repo",
                          icon: "chevron.left.forwardslash.chevron.right") {
                    if let u = URL(string: "https://github.com/yu314-coder/python-ios-lib/") {
                        UIApplication.shared.open(u)
                    }
                }
            }
            .padding(16)
        }
    }

    // MARK: data

    private let guideSections: [(String, String)] = [
        ("Getting started",
         "Edit Python code in the Workspace tab. Define one or more `class MyScene(Scene): def construct(self): …` classes, then tap Render or Preview. Output appears in the preview pane and in the live terminal."),
        ("Render vs Preview",
         "Render uses your Final Render quality (right sidebar or Settings — defaults to 1080p / 30 fps). Preview uses the separate Quick Preview quality (defaults to 480p / 15 fps) for tight iteration loops; raise it to 720p or 1080p in the sidebar when you need a closer look."),
        ("Scene picker",
         "When more than one Scene class is detected, the dropdown next to Render lets you pick one. \"All scenes\" renders every Scene subclass in source order."),
        ("LaTeX (Tex / MathTex)",
         "Manim's Tex and MathTex run through busytex. Single-formula math mode is reliable; full document LaTeX is gated pending a newer pdftex.xcframework."),
        ("Where outputs land",
         "Documents/ToolOutputs/<run_id>/videos/<resolution>/<scene>.mp4 — visible in the Files app under On My iPad / Manim Studio."),
        ("Workspace, Assets, History",
         "Workspace is the cwd the shell starts in. Assets is for files you import (images, audio, fonts). History scans ToolOutputs and shows every render with thumbnail / share / delete."),
        ("Packages tab",
         "Lists every Python package bundled in the app — name, version, category, short description. Fully offline; filter by category or search. The list is baked in, so the tab opens instantly."),
        ("GPU button (lightning)",
         "Turns on Metal-accelerated cairo rasterization plus VideoToolbox hardware H.264 encoding. It mainly speeds the encode stage — the per-frame math (manim's Python interpolation) dominates total render time, so the biggest speed levers are lowering the FPS or the resolution, not this toggle. OFF uses the CPU cairo backend and the software encoder."),
        ("Output formats",
         "The Final Render format (right sidebar or Settings) can be mp4 (H.264 video), gif (looping animation), or html (a self-contained player page). Preview always uses mp4 for speed."),
        ("Appearance",
         "The app uses a fixed dark theme. Pick an accent colour in Settings → Accent colour or the palette button in the header — it retints buttons, highlights, selection and the signature gradient across the whole app."),
    ]

    private let shortcutGroups: [(String, [(String, String)])] = [
        ("File", [
            ("⌘ N",       "New file"),
            ("⌘ O",       "Open file…"),
            ("⌘ S",       "Save…"),
        ]),
        ("Render", [
            ("⌘ R",       "Render (Final quality)"),
            ("⇧ ⌘ R",     "Preview (Quick Preview quality)"),
            ("⌘ .",       "Stop render"),
            ("⌥ ⌘ G",     "Toggle GPU acceleration"),
        ]),
        ("View", [
            ("⌘ 1",       "Gallery tab"),
            ("⌘ 2",       "Workspace tab"),
            ("⌘ 3",       "Assets tab"),
            ("⌘ 4",       "Packages tab"),
            ("⌘ 5",       "History tab"),
            ("⌘ 6",       "System tab"),
            ("⌘ \\",      "Toggle right sidebar"),
        ]),
        ("Editor — find / nav", [
            ("⌘ F",       "Find"),
            ("⌘ ⌥ F",     "Find & Replace"),
            ("⌘ G",       "Find next"),
            ("⇧ ⌘ G",     "Find previous"),
            ("⌘ L",       "Go to line"),
            ("⌘ T",       "Quick symbol lookup"),
        ]),
        ("Editor — text", [
            ("⌘ /",       "Toggle line comment"),
            ("⌘ ]",       "Indent"),
            ("⌘ [",       "Outdent"),
            ("⌥ ↑",       "Move line up"),
            ("⌥ ↓",       "Move line down"),
            ("⇧ ⌘ D",     "Duplicate selection"),
            ("⌥ ⌘ I",     "Format document"),
            ("⌃ Space",   "Trigger completion"),
        ]),
        ("Editor — selection", [
            ("⌘ A",       "Select all"),
            ("⇧ ⌥ ↑",     "Expand selection"),
            ("⇧ ⌥ ↓",     "Shrink selection"),
            ("⌘ D",       "Add next match to selection"),
        ]),
        ("Help / Settings", [
            ("⌘ ?",       "Open this help"),
            ("⇧ ⌘ K",     "Keyboard shortcuts"),
        ]),
        ("Shell", [
            ("help",    "List all builtins"),
            ("ls / cd", "Filesystem"),
            ("clear",   "Clear terminal"),
            ("top / htop", "Process + system snapshot"),
            ("python",  "Python version banner"),
            ("Ctrl+C",  "Interrupt running command"),
        ]),
    ]

    private let snippets: [(String, [(String, String)])] = [
        ("Manim", [
            ("Hello scene",
             """
             from manim import *

             class Hello(Scene):
                 def construct(self):
                     t = Text(\"Hello, ManimStudio!\")
                     self.play(Write(t))
                     self.wait(1)
             """),
            ("Fade between two formulas",
             """
             from manim import *

             class FadeMath(Scene):
                 def construct(self):
                     a = MathTex(r\"e^{i\\pi} + 1 = 0\")
                     b = MathTex(r\"\\int_0^1 x^2\\,dx = \\tfrac{1}{3}\")
                     self.play(Write(a))
                     self.wait(0.5)
                     self.play(ReplacementTransform(a, b))
                     self.wait(1)
             """),
            ("Move + recolor",
             """
             from manim import *

             class Move(Scene):
                 def construct(self):
                     dot = Dot(LEFT * 3, color=YELLOW)
                     self.add(dot)
                     self.play(dot.animate.shift(RIGHT * 6).set_color(BLUE), run_time=2)
             """),
        ]),
        ("Imports", [
            ("Numpy + matplotlib check",
             """
             import numpy as np, matplotlib.pyplot as plt
             x = np.linspace(0, 2*np.pi, 200)
             plt.plot(x, np.sin(x))
             plt.savefig(\"/tmp/sin.png\")
             """),
        ]),
    ]

    private let faqs: [(String, String)] = [
        ("Why does Preview look lower-res than Render?",
         "Preview has its own Quick Preview quality (defaults to 480p / 15 fps) in the right sidebar, separate from Final Render quality — so you can iterate fast and still render at full quality. Raise Quick Preview to 720p/1080p for a closer look, or press ⌘R for a Final render."),
        ("Where can I find my renders?",
         "Files app → On My iPad → Manim Studio → ToolOutputs/. Or use the History tab in the app."),
        ("The app freezes on launch.",
         "Close it once and reopen. The first launch after a new build warms up Python and imports manim/numpy/scipy/matplotlib (~10 s). Subsequent launches are much faster."),
        ("`pip install …` doesn't work.",
         "Correct — pip is intentionally disabled. iOS app sandboxes don't expose a writable site-packages, and most pip wheels need a working compiler / linker which iOS forbids. The Packages tab lists everything pre-bundled."),
        ("Can I use my own fonts?",
         "Drop .ttf / .otf into Assets, then reference by path in Text(font='/path/to/font.ttf', text='…')."),
        ("Why is `top` showing my process only?",
         "iOS sandboxing prevents reading other processes' info. `top` shows this process's RSS, CPU time, and the device-wide stats sysctl exposes (RAM, CPU count, uptime)."),
        ("What's in the log file?",
         "Settings → Diagnostics → Share log file. Captures Python tracebacks, render output, and signal-level crash backtraces. Send it along when reporting a render bug."),
    ]

    private let troubleshooting: [(String, String)] = [
        ("Render hangs at \"loading manim…\"",
         "First render of a session imports manim and friends — can take 10–30 s on a fresh launch. Subsequent renders are seconds. If it's still stuck after a minute, force-quit and reopen."),
        ("Render produces no video file",
         "Check the terminal pane for a Python traceback. Common causes: a Scene class that raises in construct(), a missing font file, or insufficient disk space (clear ToolOutputs in Settings)."),
        ("Editor completion is empty",
         "manim and Python builtins always autocomplete. Full library APIs (numpy / scipy / matplotlib …) come from a symbol index built in the background after your first render — when those libraries are already loaded — then cached. Run one render and they'll populate."),
        ("\"symbol not found in flat namespace\" on import",
         "Means a C extension references a symbol that isn't bundled. Send the log file (Settings → Diagnostics → Share log file) — these are usually one-line stub additions."),
        ("Files app doesn't show my renders",
         "Documents must be exposed via UIFileSharingEnabled + LSSupportsOpeningDocumentsInPlace (both set in Info.plist). Sometimes Files takes a few seconds to refresh after a render — pull-to-refresh in Files."),
    ]

    // MARK: filter helpers (live search)

    private func filtered<T>(_ pairs: [(String, T)]) -> [(String, T)] where T: StringProtocol {
        guard !query.isEmpty else { return pairs }
        let q = query.lowercased()
        return pairs.filter {
            $0.0.lowercased().contains(q) || String($0.1).lowercased().contains(q)
        }
    }
    private func filtered2<U>(_ groups: [(String, [(String, U)])]) -> [(String, [(String, U)])] {
        guard !query.isEmpty else { return groups }
        let q = query.lowercased()
        return groups.compactMap { g in
            let kept = g.1.filter { item in
                g.0.lowercased().contains(q)
                    || item.0.lowercased().contains(q)
                    || (item.1 as? String).map { $0.lowercased().contains(q) } ?? false
            }
            return kept.isEmpty ? nil : (g.0, kept)
        }
    }

    // MARK: small UI helpers

    @ViewBuilder
    private func actionRow(_ title: String, icon: String,
                           action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.accentPrimary)
                    .frame(width: 24)
                Text(title).font(.system(size: 13))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                Image(systemName: "chevron.right").font(.system(size: 10))
                    .foregroundStyle(Theme.textDim)
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgSecondary))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderSubtle, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private func folderURL(_ fileURL: URL) -> URL {
        // shareddocuments:// scheme opens Files app at the directory.
        let dir = fileURL.deletingLastPathComponent().path
        return URL(string: "shareddocuments://\(dir)") ?? fileURL
    }

    @ViewBuilder
    private func section(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 14, weight: .semibold))
            Text(body).font(.system(size: 13))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct ColorPanelPopover: View {
    @Binding var accentHex: String
    private let presets: [String] = [
        "6366F1", // indigo
        "A855F7", // violet
        "EC4899", // pink
        "F43F5E", // rose
        "F59E0B", // amber
        "10B981", // emerald
        "14B8A6", // teal
        "06B6D4", // cyan
        "3B82F6", // blue
        "8B5CF6", // purple
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Accent color").font(.system(size: 13, weight: .semibold))
            LazyVGrid(columns: Array(repeating: GridItem(.fixed(28), spacing: 8), count: 5),
                      spacing: 8) {
                ForEach(presets, id: \.self) { hex in
                    Button {
                        accentHex = hex
                    } label: {
                        Circle()
                            .fill(Color(hex: hex) ?? .indigo)
                            .frame(width: 28, height: 28)
                            .overlay(
                                Circle()
                                    .strokeBorder(.white,
                                                  lineWidth: accentHex == hex ? 2 : 0)
                            )
                            .overlay(
                                Circle()
                                    .strokeBorder(Color.black.opacity(0.18),
                                                  lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            HStack {
                Text("#")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(.secondary)
                TextField("Hex", text: $accentHex)
                    .font(.system(size: 12, design: .monospaced))
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .frame(width: 80)
                Circle()
                    .fill(Color(hex: accentHex) ?? .indigo)
                    .frame(width: 18, height: 18)
                    .overlay(Circle().stroke(Color.secondary.opacity(0.3), lineWidth: 1))
            }
        }
        .padding(14)
        .frame(minWidth: 240)
    }
}

// MARK: - Color hex helper

extension Color {
    /// Initialize from a 6- or 8-char hex string ("#RRGGBB" or "RRGGBBAA").
    init?(hex raw: String) {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("#") { s.removeFirst() }
        guard s.count == 6 || s.count == 8,
              let v = UInt64(s, radix: 16) else { return nil }
        let r, g, b, a: Double
        if s.count == 8 {
            r = Double((v >> 24) & 0xff) / 255
            g = Double((v >> 16) & 0xff) / 255
            b = Double((v >>  8) & 0xff) / 255
            a = Double(  v        & 0xff) / 255
        } else {
            r = Double((v >> 16) & 0xff) / 255
            g = Double((v >>  8) & 0xff) / 255
            b = Double(  v        & 0xff) / 255
            a = 1
        }
        self.init(.sRGB, red: r, green: g, blue: b, opacity: a)
    }
}
