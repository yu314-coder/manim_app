// AIEditView.swift — chat-style AI Edit panel embedded in the
// editor pane. Designed to feel closer to Claude.ai / ChatGPT /
// Cursor's right-rail than the original two-column form-and-output
// layout it replaces.
//
// Visual structure:
//   ┌─ header ──────────────────────────────────────┐
//   │ AI Edit  [BETA]                    + ⊟        │
//   │ [Claude / Codex]  [Edit / Agent]   ▼ Opus     │
//   ├───────────────────────────────────────────────┤
//   │ scrollable conversation                        │
//   │  ╭ user prompt ─╮                              │
//   │  ╰──────────────╯                              │
//   │  assistant text + tool-call cards              │
//   │  …                                             │
//   ├───────────────────────────────────────────────┤
//   │ ⏎  prompt textarea …                  [Send]  │
//   ├───────────────────────────────────────────────┤
//   │ Edit ready · +12 lines     [Reject] [Accept]  │
//   └───────────────────────────────────────────────┘
import SwiftUI
import AppKit

struct AIEditView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var svc = AIEditService()
    @StateObject private var registry = AIModelRegistry.shared
    @Binding var open: Bool

    @State private var prompt: String = ""
    @State private var selectedAlias: String = ""

    /// CLI-side aliases ("opus", "sonnet", "haiku" for claude;
    /// "Auto" / no flag for codex). Always surfaced as a top section
    /// in the picker so the user can let the CLI pick the latest
    /// version automatically.
    private var aliases: [(id: String, label: String)] {
        switch svc.provider {
        case .claude:
            return [("",        "Auto"),
                    ("opus",    "Opus (latest)"),
                    ("sonnet",  "Sonnet (latest)"),
                    ("haiku",   "Haiku (latest)")]
        case .codex:
            return [("", "Auto")]
        }
    }

    /// Model IDs auto-discovered from each CLI's local cache. Shown
    /// below the aliases so the user can pin to a specific version.
    /// See AIModelRegistry for sources.
    private var discovered: [AIModelRegistry.DiscoveredModel] {
        switch svc.provider {
        case .claude: return registry.claudeModels
        case .codex:  return registry.codexModels
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().background(Theme.borderSubtle)
            transcript
            Divider().background(Theme.borderSubtle)
            composer
            if svc.editedCode != nil {
                Divider().background(Theme.borderSubtle)
                acceptRejectBar
            }
        }
        .background(Theme.bgPrimary)
        .onAppear {
            svc.probeCLI()
            registry.refresh()
        }
    }

    // MARK: - header

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                ZStack {
                    Circle()
                        .fill(Theme.signatureGradient)
                        .frame(width: 22, height: 22)
                        .shadow(color: Theme.glowPrimary, radius: 6)
                    Image(systemName: "sparkles")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.white)
                }
                Text("AI Edit")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text("BETA")
                    .font(.system(size: 8, weight: .heavy)).tracking(1)
                    .foregroundStyle(Theme.amber)
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .background(Capsule().stroke(Theme.amber.opacity(0.6),
                                                  lineWidth: 1))
                Spacer()
                iconButton("plus.bubble", "Fresh session") {
                    withAnimation(.spring) { svc.newSession() }
                }
                iconButton("sidebar.right", "Close (⇧⌘E)") { open = false }
                    .keyboardShortcut("e", modifiers: [.command, .shift])
            }

            // Toggles on their own row so neither gets clipped in
            // narrow panels — Codex was disappearing when the model
            // menu hogged horizontal space.
            HStack(spacing: 6) {
                providerToggle
                modeToggle
                Spacer()
            }
            // Model menu on a third row, full-width with a leading
            // "Model" tag, so the dropdown can grow without
            // squeezing the toggles above.
            HStack(spacing: 6) {
                Image(systemName: "cpu")
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.textDim)
                Text("Model").font(.system(size: 9, weight: .semibold))
                    .tracking(0.5).foregroundStyle(Theme.textDim)
                modelMenu
                Spacer()
            }
        }
        .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 10)
        .background(Theme.bgSecondary)
    }

    @ViewBuilder
    private func iconButton(_ icon: String, _ help: String,
                            action: @escaping () -> Void) -> some View
    {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 24, height: 24)
                .background(RoundedRectangle(cornerRadius: 6)
                    .fill(Theme.bgTertiary))
        }
        .buttonStyle(.plain)
        .help(help)
    }

    private var providerToggle: some View {
        HStack(spacing: 0) {
            ForEach(AIEditService.Provider.allCases) { p in
                Button {
                    withAnimation(.spring(response: 0.25)) {
                        svc.provider = p
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: p == .claude
                              ? "sparkles" : "chevron.left.forwardslash.chevron.right")
                            .font(.system(size: 9))
                        Text(p.label)
                            .font(.system(size: 10, weight: .semibold))
                    }
                    .foregroundStyle(svc.provider == p ? .white : Theme.textSecondary)
                    .padding(.horizontal, 9).padding(.vertical, 4)
                    .background(svc.provider == p
                                ? AnyShapeStyle(Theme.signatureGradient)
                                : AnyShapeStyle(Color.clear))
                }
                .buttonStyle(.plain)
            }
        }
        .background(RoundedRectangle(cornerRadius: 7)
            .fill(Theme.bgTertiary))
        .clipShape(RoundedRectangle(cornerRadius: 7))
        .help("Provider")
    }

    private var modeToggle: some View {
        HStack(spacing: 0) {
            ForEach(AIEditService.Mode.allCases) { m in
                Button {
                    withAnimation(.spring(response: 0.25)) { svc.mode = m }
                } label: {
                    HStack(spacing: 3) {
                        Image(systemName: m == .agent
                              ? "wand.and.stars" : "pencil.line")
                            .font(.system(size: 9))
                        Text(m.label).font(.system(size: 10, weight: .medium))
                    }
                    .foregroundStyle(svc.mode == m ? .white : Theme.textSecondary)
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(svc.mode == m
                                ? AnyShapeStyle(LinearGradient(
                                    colors: [Theme.indigo, Theme.violet],
                                    startPoint: .leading, endPoint: .trailing))
                                : AnyShapeStyle(Color.clear))
                }
                .buttonStyle(.plain)
            }
        }
        .background(RoundedRectangle(cornerRadius: 7).fill(Theme.bgTertiary))
        .clipShape(RoundedRectangle(cornerRadius: 7))
        .help(svc.mode == .agent
              ? "Agent: multi-step plan + execute"
              : "Edit: one-shot scene.py mutation")
    }

    private var modelMenu: some View {
        Menu {
            // ── Aliases (CLI auto-resolves to current version)
            Section("Aliases") {
                ForEach(aliases, id: \.id) { entry in
                    Button { selectedAlias = entry.id } label: {
                        if let resolved = svc.resolvedName(
                            for: entry.id.isEmpty ? "default" : entry.id) {
                            Text("\(entry.label) — \(resolved)")
                        } else {
                            Text(entry.label)
                        }
                    }
                }
            }
            // ── Discovered specific versions (auto-found on disk).
            if !discovered.isEmpty {
                Section("On this machine") {
                    ForEach(discovered, id: \.id) { m in
                        Button { selectedAlias = m.id } label: {
                            if let detail = m.detail, !detail.isEmpty {
                                VStack(alignment: .leading) {
                                    Text(m.display)
                                    Text(detail)
                                        .font(.system(size: 9))
                                }
                            } else {
                                Text("\(m.display) — \(m.id)")
                            }
                        }
                    }
                }
            }
            Divider()
            Button("Re-scan local model caches") {
                registry.refresh()
            }
            if svc.provider == .claude, !svc.claudeCLIVersion.isEmpty {
                Text(svc.claudeCLIVersion)
            }
            if svc.provider == .codex, !svc.codexCLIVersion.isEmpty {
                Text(svc.codexCLIVersion)
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: "cpu").font(.system(size: 10))
                Text(menuLabel)
                    .font(.system(size: 10, weight: .medium))
                    .lineLimit(1).truncationMode(.tail)
                Image(systemName: "chevron.down").font(.system(size: 8))
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(RoundedRectangle(cornerRadius: 7)
                .fill(Theme.bgTertiary))
        }
        .menuStyle(.borderlessButton)
        .frame(maxWidth: 220)
    }

    private var menuLabel: String {
        // Discovered specific model picked → show its display name.
        if let m = discovered.first(where: { $0.id == selectedAlias }) {
            return m.display
        }
        let entry = aliases.first(where: { $0.id == selectedAlias })
            ?? aliases[0]
        if let resolved = svc.resolvedName(
            for: entry.id.isEmpty ? "default" : entry.id) {
            return "\(entry.label) · \(resolved)"
        }
        return entry.label
    }

    // MARK: - transcript

    @ViewBuilder
    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if svc.turns.isEmpty {
                        emptyState
                    } else {
                        ForEach(svc.turns) { turn in
                            turnView(turn)
                                .id(turn.id)
                        }
                        if case .running = svc.phase {
                            thinkingDots
                        }
                    }
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(Theme.bgPrimary)
            .onChange(of: svc.turns.last?.text) { _, _ in
                if let last = svc.turns.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            .onChange(of: svc.turns.last?.toolCalls.count) { _, _ in
                if let last = svc.turns.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 6) {
                Image(systemName: "wand.and.sparkles")
                    .foregroundStyle(Theme.signatureGradient)
                Text("Edit your manim scene with AI")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
            }
            Text("Describe a change to scene.py and \(svc.provider.label) will edit it directly. Click **Accept** to apply the result, or **Reject** to discard.")
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            Text("TRY")
                .font(.system(size: 9, weight: .heavy)).tracking(1)
                .foregroundStyle(Theme.textDim)
                .padding(.top, 6)
            VStack(alignment: .leading, spacing: 6) {
                ForEach(samplePrompts, id: \.self) { s in
                    Button { prompt = s } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "arrow.up.left")
                                .font(.system(size: 9))
                                .foregroundStyle(Theme.textDim)
                            Text(s)
                                .font(.system(size: 11))
                                .foregroundStyle(Theme.textPrimary)
                                .lineLimit(2)
                                .multilineTextAlignment(.leading)
                            Spacer()
                        }
                        .padding(.horizontal, 10).padding(.vertical, 7)
                        .background(RoundedRectangle(cornerRadius: 8)
                            .fill(Theme.bgTertiary))
                        .overlay(RoundedRectangle(cornerRadius: 8)
                            .stroke(Theme.borderSubtle, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var samplePrompts: [String] {
        switch (svc.provider, svc.mode) {
        case (_, .agent):
            return [
                "Create an animation of the Pythagorean theorem with a 3-4-5 right triangle",
                "Generate a number-line scene that counts up from 1 to 10 with smooth easing",
            ]
        case (_, .edit):
            return [
                "Make all text twice as big and use the indigo→pink gradient",
                "Add a wait(1) before the final fade-out",
                "Replace the title Text(...) with MathTex(\\\"E = mc^2\\\")",
            ]
        }
    }

    // ── one chat turn

    @ViewBuilder
    private func turnView(_ turn: AIEditService.Turn) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // User prompt bubble — right-aligned, indigo gradient.
            HStack {
                Spacer(minLength: 28)
                Text(turn.prompt)
                    .font(.system(size: 11))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10).padding(.vertical, 7)
                    .background(RoundedRectangle(cornerRadius: 10)
                        .fill(Theme.signatureGradient))
                    .shadow(color: Theme.glowPrimary, radius: 4)
                    .frame(alignment: .trailing)
                    .textSelection(.enabled)
            }

            // Assistant text + tool calls, full width.
            if !turn.text.isEmpty {
                Text(.init(turn.text))   // accepts inline markdown
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }

            if !turn.toolCalls.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(turn.toolCalls) { call in
                        toolCallChip(call)
                    }
                }
            }

            if let err = turn.errorMessage {
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.error)
                    Text(err)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.error)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(8)
                .background(RoundedRectangle(cornerRadius: 7)
                    .fill(Theme.error.opacity(0.10)))
                .overlay(RoundedRectangle(cornerRadius: 7)
                    .stroke(Theme.error.opacity(0.35), lineWidth: 1))
            }

            // Footer caption — model + tokens + cost when present.
            HStack(spacing: 8) {
                if !turn.model.isEmpty {
                    Label(turn.model, systemImage: "cpu")
                        .font(.system(size: 9, design: .monospaced))
                        .labelStyle(.titleAndIcon)
                        .foregroundStyle(Theme.textDim)
                }
                if turn.inputTokens + turn.outputTokens > 0 {
                    Text("\(turn.inputTokens)→\(turn.outputTokens) tok")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                }
                if turn.costUSD > 0 {
                    Text(String(format: "$%.4f", turn.costUSD))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                }
                if let finished = turn.finishedAt {
                    Text(finished, style: .time)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                }
            }
            .padding(.top, 2)
        }
    }

    @ViewBuilder
    private func toolCallChip(_ call: AIEditService.ToolCall) -> some View {
        let style = ChipStyle.forTool(call.name)
        HStack(spacing: 6) {
            Image(systemName: style.icon)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(style.tint)
                .frame(width: 16)
            Text(call.name)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(style.tint)
            if !call.detail.isEmpty {
                Text(call.detail)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer()
        }
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(RoundedRectangle(cornerRadius: 6)
            .fill(style.tint.opacity(0.10)))
        .overlay(RoundedRectangle(cornerRadius: 6)
            .stroke(style.tint.opacity(0.30), lineWidth: 1))
    }

    private var thinkingDots: some View {
        HStack(spacing: 4) {
            ForEach(0..<3) { i in
                Circle()
                    .fill(Theme.indigo)
                    .frame(width: 5, height: 5)
                    .opacity(0.4)
                    .scaleEffect(1.0)
                    .animation(.easeInOut(duration: 0.7)
                                .repeatForever()
                                .delay(Double(i) * 0.18),
                               value: svc.elapsed)
            }
            Text("thinking… \(Int(svc.elapsed))s")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Theme.textDim)
                .padding(.leading, 4)
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
    }

    // MARK: - composer

    private var composer: some View {
        VStack(spacing: 6) {
            ZStack(alignment: .bottomTrailing) {
                ZStack(alignment: .topLeading) {
                    if prompt.isEmpty {
                        Text(placeholder)
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.textDim)
                            .padding(.horizontal, 12).padding(.vertical, 10)
                            .allowsHitTesting(false)
                    }
                    TextEditor(text: $prompt)
                        .font(.system(size: 11, design: .monospaced))
                        .scrollContentBackground(.hidden)
                        .padding(.horizontal, 8).padding(.vertical, 6)
                }
                .frame(minHeight: 64, maxHeight: 140)
                .background(RoundedRectangle(cornerRadius: 10)
                    .fill(Theme.bgDeepest))
                .overlay(RoundedRectangle(cornerRadius: 10)
                    .stroke(prompt.isEmpty
                            ? Theme.borderSubtle
                            : Theme.indigo.opacity(0.5),
                            lineWidth: 1))
                .animation(.easeInOut(duration: 0.15), value: prompt.isEmpty)

                // Send / Stop button inside the textarea (lower-right).
                actionButton
                    .padding(8)
            }

            HStack(spacing: 8) {
                Image(systemName: "command")
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.textDim)
                Text("⌘⏎ to send  ·  ⇧⌘E to close")
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.textDim)
                Spacer()
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Theme.bgSecondary)
    }

    private var placeholder: String {
        switch (svc.provider, svc.mode) {
        case (_, .agent):  return "Describe an animation to generate…"
        case (.claude, _): return "What should claude change in scene.py?"
        case (.codex,  _): return "What should codex change in scene.py?"
        }
    }

    @ViewBuilder
    private var actionButton: some View {
        if case .running = svc.phase {
            Button {
                svc.stop()
            } label: {
                Image(systemName: "stop.fill")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 28, height: 28)
                    .background(Circle().fill(Theme.error))
                    .shadow(color: Theme.error.opacity(0.4), radius: 5)
            }
            .buttonStyle(.plain)
            .help("Stop")
        } else {
            Button {
                send()
            } label: {
                Image(systemName: svc.mode == .agent
                      ? "wand.and.stars" : "arrow.up")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 28, height: 28)
                    .background(Circle().fill(Theme.signatureGradient))
                    .shadow(color: Theme.glowPrimary, radius: 5)
            }
            .buttonStyle(.plain)
            .disabled(promptIsEmpty)
            .opacity(promptIsEmpty ? 0.4 : 1)
            .keyboardShortcut(.return, modifiers: .command)
            .help("Send (⌘⏎)")
        }
    }

    private var promptIsEmpty: Bool {
        prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func send() {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        svc.send(prompt: trimmed,
                 originalCode: app.sourceCode,
                 modelAlias: selectedAlias)
        prompt = ""
    }

    // MARK: - accept / reject

    private var acceptRejectBar: some View {
        HStack(spacing: 10) {
            Image(systemName: "doc.text.below.ecg.fill")
                .font(.system(size: 14))
                .foregroundStyle(.white)
                .frame(width: 28, height: 28)
                .background(Circle().fill(Theme.indigo))

            VStack(alignment: .leading, spacing: 1) {
                Text("Edit ready")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(diffSummary)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            Button { svc.rejectEdit() } label: {
                Text("Reject")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                    .padding(.horizontal, 12).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 7)
                        .fill(Theme.bgTertiary))
            }
            .buttonStyle(.plain)
            Button {
                if let edited = svc.acceptEdit() {
                    app.sourceCode = edited
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 10, weight: .bold))
                    Text("Accept")
                        .font(.system(size: 10, weight: .semibold))
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 14).padding(.vertical, 5)
                .background(RoundedRectangle(cornerRadius: 7)
                    .fill(Theme.signatureGradient))
                .shadow(color: Theme.glowPrimary, radius: 5)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(LinearGradient(
            colors: [Theme.indigo.opacity(0.18), Theme.violet.opacity(0.10)],
            startPoint: .leading, endPoint: .trailing))
    }

    private var diffSummary: String {
        guard let edited = svc.editedCode else { return "" }
        let oldLines = app.sourceCode.split(separator: "\n").count
        let newLines = edited.split(separator: "\n").count
        let delta = newLines - oldLines
        let sign = delta >= 0 ? "+" : ""
        return "\(newLines) lines (\(sign)\(delta))"
    }
}

// MARK: - tool-call chip styling

private struct ChipStyle {
    let icon: String
    let tint: Color

    static func forTool(_ name: String) -> ChipStyle {
        switch name {
        case "Edit", "patch_apply":
            return ChipStyle(icon: "pencil.and.outline",  tint: Theme.indigo)
        case "Write":
            return ChipStyle(icon: "square.and.pencil",    tint: Theme.indigo)
        case "Read":
            return ChipStyle(icon: "doc.text.magnifyingglass",
                             tint: Theme.cyan)
        case "Bash", "shell_call":
            return ChipStyle(icon: "terminal.fill",         tint: Theme.success)
        case "Glob", "Grep":
            return ChipStyle(icon: "magnifyingglass",       tint: Theme.amber)
        case "WebSearch", "WebFetch":
            return ChipStyle(icon: "globe",                 tint: Theme.violet)
        default:
            return ChipStyle(icon: "wrench.and.screwdriver", tint: Theme.textSecondary)
        }
    }
}
