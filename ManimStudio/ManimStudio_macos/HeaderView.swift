// HeaderView.swift — top header bar matching the iOS HeaderView
// design (logo + autosave + file ops + scene picker + Render /
// Preview / Stop + GPU toggle + LaTeX status + Settings / Theme /
// Help). Same visual language as the iOS one but written from
// scratch for AppKit/macOS — no shared code.
import SwiftUI
import AppKit

struct HeaderView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var venv: VenvManager
    @StateObject private var latex = LaTeXProbe.shared
    var onRender:  () -> Void
    var onPreview: () -> Void
    var onStop:    () -> Void
    var onNew:     () -> Void
    var onOpen:    () -> Void
    var onSave:    () -> Void

    @State private var gpuOn = true
    @State private var showSettings = false
    @State private var showHelp = false
    @State private var showLatexPopover = false

    var body: some View {
        HStack(spacing: 14) {
            // ── LEFT: logo + title + autosave
            HStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Theme.signatureGradient)
                        .frame(width: 30, height: 30)
                        .shadow(color: Theme.glowPrimary, radius: 8)
                    Text("🎬").font(.system(size: 16))
                }
                VStack(alignment: .leading, spacing: 0) {
                    Text("Manim Animation Studio")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                    Text("Native · macOS · v1.0")
                        .font(.system(size: 9, weight: .medium))
                        .tracking(0.7)
                        .foregroundStyle(Theme.textDim)
                }
                autosaveBadge
            }

            Spacer(minLength: 8)

            // ── CENTER: file ops + scene picker + render row
            HStack(spacing: 6) {
                iconBtn("doc.badge.plus", "New (⌘N)", action: onNew)
                iconBtn("folder",         "Open (⌘O)", action: onOpen)
                iconBtn("square.and.arrow.down", "Save (⌘S)", action: onSave)
                Divider().frame(height: 16)

                scenePicker

                renderButton
                previewButton
                if app.isRendering { stopButton }

                Divider().frame(height: 16)
                gpuToggle
            }

            Spacer(minLength: 8)

            // ── RIGHT: LaTeX status + settings/theme/help
            HStack(spacing: 8) {
                latexStatus
                iconBtn("gearshape", "Settings") { showSettings.toggle() }
                iconBtn("questionmark.circle", "Help") { showHelp.toggle() }
            }
        }
        .padding(.horizontal, 14)
        .frame(height: 50)
        .background(headerBackground)
        .sheet(isPresented: $showSettings) {
            SettingsView()
                .environmentObject(app)
                .environmentObject(venv)
                .frame(minWidth: 540, minHeight: 480)
        }
        .sheet(isPresented: $showHelp) {
            HelpSheet()
                .frame(minWidth: 540, minHeight: 540)
        }
        .onAppear { latex.probe() }
    }

    // MARK: bg

    private var headerBackground: some View {
        ZStack {
            VisualEffectBackground(material: .titlebar)
            Theme.bgSecondary.opacity(0.85)
        }
        .overlay(
            Rectangle().fill(Theme.borderSubtle).frame(height: 1),
            alignment: .bottom)
    }

    // MARK: pieces

    private var autosaveBadge: some View {
        HStack(spacing: 5) {
            Circle().fill(Theme.success).frame(width: 6, height: 6)
                .shadow(color: Theme.glowSuccess, radius: 3)
            Text("Autosaved").font(.system(size: 10, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(Capsule().fill(Theme.bgTertiary))
    }

    private var scenePicker: some View {
        let scenes = app.detectedScenes
        return Menu {
            Button {
                app.selectedScene = ""
            } label: {
                if app.selectedScene.isEmpty {
                    Label("First detected", systemImage: "checkmark")
                } else {
                    Text("First detected")
                }
            }
            if !scenes.isEmpty { Divider() }
            ForEach(scenes, id: \.self) { name in
                Button {
                    app.selectedScene = name
                } label: {
                    if app.selectedScene == name {
                        Label(name, systemImage: "checkmark")
                    } else {
                        Text(name)
                    }
                }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: "rectangle.stack")
                    .font(.system(size: 11))
                Text(scenePickerLabel(scenes))
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(1).fixedSize()
                Image(systemName: "chevron.down").font(.system(size: 8))
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 7).fill(Theme.bgTertiary))
            .overlay(RoundedRectangle(cornerRadius: 7)
                .stroke(Theme.borderSubtle, lineWidth: 1))
        }
        .menuStyle(.borderlessButton)
        .frame(minWidth: 110)
    }

    private func scenePickerLabel(_ scenes: [String]) -> String {
        if !app.selectedScene.isEmpty { return app.selectedScene }
        return scenes.isEmpty ? "No Scene"
            : (scenes.first ?? "First")
    }

    private var renderButton: some View {
        Button(action: onRender) {
            HStack(spacing: 6) {
                Image(systemName: "play.fill")
                    .font(.system(size: 11, weight: .bold))
                Text("Render").font(.system(size: 12, weight: .semibold))
                Text("⌘R").font(.system(size: 9, weight: .medium))
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Capsule().fill(.white.opacity(0.18)))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.signatureGradient))
            .shadow(color: Theme.glowPrimary, radius: 8, y: 2)
        }
        .buttonStyle(.plain)
        .disabled(app.isRendering || !canRender)
        .opacity(canRender && !app.isRendering ? 1 : 0.5)
        .help("Render at Final quality (⌘R)")
        .keyboardShortcut("r", modifiers: [.command])
    }

    private var previewButton: some View {
        Button(action: onPreview) {
            HStack(spacing: 5) {
                Image(systemName: "eye").font(.system(size: 11))
                Text("Preview").font(.system(size: 12, weight: .medium))
                Text("⇧⌘R").font(.system(size: 9))
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Capsule().fill(Theme.bgSurface))
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            .overlay(RoundedRectangle(cornerRadius: 8)
                .stroke(Theme.borderActive, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(app.isRendering || !canRender)
        .opacity(canRender && !app.isRendering ? 1 : 0.5)
        .help("Quick preview at 480p / 15 fps (⇧⌘R)")
        .keyboardShortcut("r", modifiers: [.command, .shift])
    }

    private var stopButton: some View {
        Button(action: onStop) {
            HStack(spacing: 5) {
                Image(systemName: "stop.fill").font(.system(size: 11))
                Text("Stop").font(.system(size: 12, weight: .semibold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.error))
            .shadow(color: Theme.error.opacity(0.5), radius: 8, y: 2)
        }
        .buttonStyle(.plain)
        .keyboardShortcut(".", modifiers: [.command])
        .help("Stop (⌘.)")
    }

    private var gpuToggle: some View {
        Button {
            gpuOn.toggle()
        } label: {
            Image(systemName: "bolt.fill")
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(gpuOn ? .white : Theme.textSecondary)
                .frame(width: 28, height: 28)
                .background(
                    RoundedRectangle(cornerRadius: 7)
                        .fill(gpuOn
                              ? AnyShapeStyle(Theme.signatureGradient)
                              : AnyShapeStyle(Theme.bgTertiary)))
                .overlay(RoundedRectangle(cornerRadius: 7)
                    .stroke(gpuOn ? Color.clear : Theme.borderSubtle, lineWidth: 1))
                .shadow(color: gpuOn ? Theme.glowPrimary : .clear, radius: 6)
        }
        .buttonStyle(.plain)
        .help("GPU acceleration (VideoToolbox)")
    }

    private var latexStatus: some View {
        // Composite status: both pieces of the manim TeX pipeline
        // need to be present for `Tex(...)` / `Text(...)` to render.
        let tint: Color
        let label: String
        let icon: String
        switch (latex.status, latex.dvisvgm) {
        case (.found(let name, _), .found):
            tint = Theme.success; label = name; icon = "checkmark.seal"
        case (.found, _):
            tint = Theme.amber; label = "dvisvgm missing"
            icon = "exclamationmark.triangle"
        case (.missing, _), (.unknown, _) where latex.status == .missing:
            tint = Theme.amber; label = "LaTeX missing"
            icon = "exclamationmark.triangle"
        default:
            tint = Theme.textDim; label = "LaTeX"; icon = "function"
        }
        return Button {
            // Re-probe in case the user just installed something, then
            // pop the install instructions popover.
            latex.probe()
            showLatexPopover.toggle()
        } label: {
            HStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 10))
                Text(label).font(.system(size: 10, weight: .medium))
            }
            .foregroundStyle(tint)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(Capsule().fill(tint.opacity(0.12)))
            .overlay(Capsule().stroke(tint.opacity(0.4), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .help(latexHelpText)
        .popover(isPresented: $showLatexPopover, arrowEdge: .bottom) {
            LatexInstallPopover(latex: latex.status,
                                dvisvgm: latex.dvisvgm,
                                onRefresh: { latex.probe() })
                .frame(width: 380)
        }
    }

    private var latexHelpText: String {
        switch (latex.status, latex.dvisvgm) {
        case (.found(_, let l), .found(_, let d)):
            return "latex: \(l.path)\ndvisvgm: \(d.path)"
        case (.found, .missing):
            return "Found latex but dvisvgm is missing — click to fix"
        case (.missing, _):
            return "Click to install BasicTeX"
        default:
            return "Probing PATH for LaTeX…"
        }
    }

    @ViewBuilder
    private func iconBtn(_ icon: String, _ tip: String,
                         action: @escaping () -> Void = {}) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 28, height: 28)
                .background(RoundedRectangle(cornerRadius: 7)
                    .fill(Theme.bgTertiary))
                .overlay(RoundedRectangle(cornerRadius: 7)
                    .stroke(Theme.borderSubtle, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .help(tip)
    }

    private var canRender: Bool { venv.phase == .ready }
}

// MARK: - LaTeX install popover

private struct LatexInstallPopover: View {
    let latex: LaTeXProbe.Status
    let dvisvgm: LaTeXProbe.Status
    let onRefresh: () -> Void

    @StateObject private var fixer = LaTeXFixer.shared

    private static let installLatex   = "brew install --cask basictex"
    private static let installDvisvgm = "brew install dvisvgm"
    private static let installTexPkgs =
        "sudo tlmgr update --self && sudo tlmgr install standalone preview doublestroke ms relsize setspace rsfs"

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack(spacing: 8) {
                Image(systemName: statusIcon)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(statusTint)
                Text(headline).font(.system(size: 13, weight: .semibold))
                Spacer()
                Button { onRefresh(); fixer.runEndToEndTest() } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Theme.textSecondary)
                }
                .buttonStyle(.plain)
                .help("Re-check PATH and re-run pipeline test")
            }

            // ── Found path summary
            statusRow("LaTeX", latex)
            statusRow("dvisvgm", dvisvgm)
            pipelineRow

            // ── Auto-fix bar
            autoFixBar

            // ── Manual install commands (always available)
            if let why = nextStepDescription {
                Divider().padding(.vertical, 2)
                Text(why)
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !latex.isReady {
                stepLabel("Install BasicTeX (~80 MB)")
                copyableCommand(Self.installLatex)
                stepLabel("…then install the manim TeX packages")
                copyableCommand(Self.installTexPkgs)
            }
            if !dvisvgm.isReady {
                stepLabel("Install dvisvgm")
                copyableCommand(Self.installDvisvgm)
            }
            if !latex.isReady || !dvisvgm.isReady {
                Text("After installing, click the refresh icon above. Or skip TeX entirely by using non-text mobjects (Circle, Square, Dot, …).")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textDim)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .onAppear {
            fixer.detectBrew()
            if fixer.test == .unknown { fixer.runEndToEndTest() }
        }
    }

    // ── pipeline test result row
    private var pipelineRow: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: testIcon)
                .font(.system(size: 12))
                .foregroundStyle(testTint)
            VStack(alignment: .leading, spacing: 2) {
                Text("End-to-end test")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(testDetail)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
            if case .running = fixer.test {
                ProgressView().controlSize(.small)
            }
        }
    }

    private var testIcon: String {
        switch fixer.test {
        case .passed:     return "checkmark.circle.fill"
        case .failed:     return "xmark.circle.fill"
        case .running:    return "arrow.triangle.2.circlepath"
        case .unknown:    return "questionmark.circle"
        }
    }
    private var testTint: Color {
        switch fixer.test {
        case .passed:     return Theme.success
        case .failed:     return Theme.amber
        case .running:    return Theme.indigo
        case .unknown:    return Theme.textDim
        }
    }
    private var testDetail: String {
        switch fixer.test {
        case .passed(let bytes):
            return "compiled MathTex → \(bytes)-byte SVG ✓"
        case .failed(let stage, let msg):
            return "\(stage.rawValue): \(msg)"
        case .running:
            return "compiling test MathTex through pdflatex + dvisvgm…"
        case .unknown:
            return "not run yet"
        }
    }

    // ── Auto-fix action bar
    @ViewBuilder
    private var autoFixBar: some View {
        let plan = fixer.plan(latex: latex, dvisvgm: dvisvgm)
        if plan != .allGood {
            HStack(spacing: 8) {
                Image(systemName: "wand.and.stars")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                Text(plan.label)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.white)
                Spacer()
                Button {
                    runAutoFix(plan)
                } label: {
                    Text("Run")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12).padding(.vertical, 5)
                        .background(RoundedRectangle(cornerRadius: 6)
                            .fill(.white.opacity(0.22)))
                }
                .buttonStyle(.plain)
                .disabled(autoFixDisabled(plan))
                .opacity(autoFixDisabled(plan) ? 0.4 : 1)
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 8)
                .fill(Theme.signatureGradient))
        }
    }

    private func autoFixDisabled(_ plan: LaTeXFixer.NextStep) -> Bool {
        if case .noFixerAvailable = plan { return true }
        return false
    }

    /// Dispatches the planned command into the integrated terminal
    /// so the user sees real-time progress + can intervene if asked
    /// for a password (cask install) or a y/N confirmation.
    private func runAutoFix(_ plan: LaTeXFixer.NextStep) {
        switch plan {
        case .installLatex:
            TerminalBridge.shared.runInShell(Self.installLatex)
        case .installDvisvgm:
            TerminalBridge.shared.runInShell(Self.installDvisvgm)
        case .installManimTeXPackages:
            TerminalBridge.shared.runInShell(Self.installTexPkgs)
        case .restartShellForEnvVars:
            // Manual — the user has to close + reopen the workspace.
            // Leave a hint in the terminal so they can fix the
            // running shell without restarting the app.
            TerminalBridge.shared.runInShell(
                "export TEXMFROOT=$(ls -1d /usr/local/texlive/*basic 2>/dev/null | sort -r | head -1) && export TEXMFCNF=\"$TEXMFROOT/texmf-dist/web2c\" && export TEXMFHOME=\"$HOME/Library/texmf\" && echo set TEXMFROOT=$TEXMFROOT TEXMFHOME=$TEXMFHOME")
        case .allGood, .noFixerAvailable:
            break
        }
        // Re-probe and re-test in 30s — gives brew time to finish
        // most installs. User can also click the refresh icon.
        DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
            onRefresh()
            fixer.runEndToEndTest()
        }
    }

    private var nextStepDescription: String? {
        let plan = fixer.plan(latex: latex, dvisvgm: dvisvgm)
        switch plan {
        case .allGood:
            return nil
        case .installLatex, .installDvisvgm, .installManimTeXPackages:
            return "Manim's `Text(...)`, `MathTex(...)` and `Tex(...)` mobjects need both `pdflatex` AND `dvisvgm` to compile to SVG."
        case .restartShellForEnvVars:
            return "Both pieces are installed but the running shell hasn't picked up the TEXMF env vars. Click \"Run\" above to export them in the current session, or restart the workspace tab."
        case .noFixerAvailable(let reason):
            return reason + ". Install Homebrew first (https://brew.sh) then come back here."
        }
    }

    @ViewBuilder
    private func statusRow(_ label: String, _ s: LaTeXProbe.Status) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: s.isReady ? "checkmark.circle.fill"
                                        : "xmark.circle.fill")
                .font(.system(size: 12))
                .foregroundStyle(s.isReady ? Theme.success : Theme.amber)
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(detail(of: s))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(2).truncationMode(.middle)
            }
            Spacer()
        }
    }

    private func detail(of s: LaTeXProbe.Status) -> String {
        switch s {
        case .found(let name, let url): return "\(name) — \(url.path)"
        case .missing:                  return "not found on PATH"
        case .unknown:                  return "probing…"
        }
    }

    @ViewBuilder
    private func stepLabel(_ s: String) -> some View {
        Text(s)
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(Theme.textPrimary)
            .padding(.top, 4)
    }

    @ViewBuilder
    private func copyableCommand(_ cmd: String) -> some View {
        HStack(spacing: 6) {
            Text(cmd)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(2)
                .truncationMode(.tail)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button {
                let pb = NSPasteboard.general
                pb.clearContents()
                pb.setString(cmd, forType: .string)
            } label: {
                Image(systemName: "doc.on.doc")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 22, height: 22)
                    .background(RoundedRectangle(cornerRadius: 5)
                        .fill(Theme.bgSecondary))
            }
            .buttonStyle(.plain)
            .help("Copy command")

            Button {
                TerminalBridge.shared.runInShell(cmd)
            } label: {
                Image(systemName: "play.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(.white)
                    .frame(width: 22, height: 22)
                    .background(RoundedRectangle(cornerRadius: 5)
                        .fill(Theme.indigo))
            }
            .buttonStyle(.plain)
            .help("Run in integrated terminal")
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
    }

    /// Worst-of-the-two — drives the popover header.
    private var statusIcon: String {
        if latex.isReady && dvisvgm.isReady { return "checkmark.seal.fill" }
        if latex == .unknown || dvisvgm == .unknown {
            return "questionmark.circle"
        }
        return "exclamationmark.triangle.fill"
    }
    private var statusTint: Color {
        if latex.isReady && dvisvgm.isReady { return Theme.success }
        if latex == .unknown || dvisvgm == .unknown { return Theme.textDim }
        return Theme.amber
    }
    private var headline: String {
        if latex.isReady && dvisvgm.isReady { return "TeX pipeline ready" }
        if latex == .unknown || dvisvgm == .unknown { return "Probing…" }
        if !latex.isReady && !dvisvgm.isReady { return "LaTeX + dvisvgm missing" }
        if !latex.isReady { return "LaTeX missing" }
        return "dvisvgm missing"
    }
}

// Tiny help sheet — keeps the header completely self-contained.
private struct HelpSheet: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("ManimStudio · Help")
                    .font(.system(size: 18, weight: .bold))
                Spacer()
                Button("Close") { dismiss() }.keyboardShortcut(.escape, modifiers: [])
            }
            Divider()
            Group {
                section("Render keys",
                        "⌘R = Final  ·  ⇧⌘R = Quick preview  ·  ⌘. = Stop")
                section("Editor keys",
                        "⌘F find  ·  ⌥⌘L format  ·  ⌘/ comment toggle")
                section("Where files go",
                        "Documents/ManimStudio/Renders/    — your videos\n" +
                        "Documents/ManimStudio/Assets/     — your imports\n" +
                        "~/Library/Application Support/ManimStudio/venv/  — the per-app Python")
                section("Need more?",
                        "Manim docs: https://docs.manim.community/\n" +
                        "Project: https://github.com/yu314-coder/manim_app")
            }
            Spacer()
        }
        .padding(20)
    }
    @ViewBuilder
    private func section(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 13, weight: .semibold))
            Text(body)
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
