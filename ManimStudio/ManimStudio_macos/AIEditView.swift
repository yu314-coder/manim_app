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
import UniformTypeIdentifiers

/// Floating "what the agent did" badge row. Shown briefly at the
/// top of the AI panel after an agent run so the user sees the
/// chain: applied → picked scene → rendering. Three pills with
/// staged checkmarks and a trailing chevron between each.
private struct AgentCursorTraceView: View {
    let trace: AIEditView.AgentTrace

    var body: some View {
        HStack(spacing: 6) {
            pill(text: "Applied", icon: "checkmark.circle.fill",
                 active: stepReached(.applied),
                 tint: Theme.success)
            chevron
            pill(text: trace.sceneName, icon: "rectangle.stack.fill",
                 active: stepReached(.picked),
                 tint: Theme.indigo)
            chevron
            pill(text: stepReached(.done) ? "Rendered"
                  : (stepReached(.rendering) ? "Rendering…" : "Preview"),
                 icon: stepReached(.rendering) ? "play.fill" : "play",
                 active: stepReached(.rendering),
                 tint: Theme.violet)
        }
        .padding(.horizontal, 8).padding(.vertical, 5)
        .background(.ultraThinMaterial,
                    in: Capsule(style: .continuous))
        .overlay(Capsule()
            .stroke(LinearGradient(
                colors: [Theme.indigo, Theme.violet, Theme.pink],
                startPoint: .leading, endPoint: .trailing),
                    lineWidth: 1))
        .shadow(color: Theme.glowPrimary.opacity(0.5), radius: 14)
    }

    private func stepReached(_ s: AIEditView.AgentTrace.Step) -> Bool {
        switch (trace.step, s) {
        case (.applied,   .applied):                                   return true
        case (.picked,    .applied), (.picked,    .picked):            return true
        case (.rendering, .applied), (.rendering, .picked),
             (.rendering, .rendering):                                  return true
        case (.done,      _):                                           return true
        default:                                                        return false
        }
    }

    @ViewBuilder
    private func pill(text: String, icon: String,
                      active: Bool, tint: Color) -> some View {
        HStack(spacing: 3) {
            Image(systemName: icon)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(active ? tint : Theme.textDim)
            Text(text)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(active ? Theme.textPrimary : Theme.textDim)
                .lineLimit(1)
        }
        .padding(.horizontal, 7).padding(.vertical, 3)
        .background(active
                    ? AnyShapeStyle(tint.opacity(0.20))
                    : AnyShapeStyle(Color.clear))
        .clipShape(Capsule())
    }

    private var chevron: some View {
        Image(systemName: "chevron.right")
            .font(.system(size: 8, weight: .bold))
            .foregroundStyle(Theme.textDim)
    }
}

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
            // Agent-mode plan banner — only shown in agent mode so
            // edit mode stays minimal. Gives a visual signal that
            // multi-step tool calls are in scope.
            if svc.mode == .agent { agentBanner }
            Divider().background(Theme.borderSubtle)
            transcript
            Divider().background(Theme.borderSubtle)
            composer
            if svc.editedCode != nil {
                Divider().background(Theme.borderSubtle)
                acceptRejectBar
            }
        }
        .background(panelBackground)
        .overlay(panelBorder)
        .onAppear {
            svc.probeCLI()
            registry.refresh()
        }
        // Agent mode hands-off pipeline: when the service stages a
        // PendingApply, push the edit into the buffer, set the scene
        // picker, and trigger a preview render — no user clicks.
        // See AIEditService.finalize for where this gets set.
        .onChange(of: svc.pendingAutoApply) { _, apply in
            guard let apply = apply else { return }
            applyAndRunAgent(apply)
        }
        // Visual-QA: when the auto-render preview lands, send the
        // frames back through claude with the Review prompt. Caps
        // the window at 60s after arming so a stale render from
        // earlier in the session doesn't accidentally trigger.
        .onChange(of: app.lastRenderURL) { _, newURL in
            guard let newURL = newURL,
                  let pending = pendingReview,
                  Date().timeIntervalSince(pending.armedAt) < 60 else {
                return
            }
            pendingReview = nil
            Task { await runReviewPass(videoURL: newURL,
                                       goal: pending.goal) }
        }
        .overlay(agentCursorOverlay)
    }

    /// Drives the visible "fake cursor" sequence so the user sees
    /// the agent picking a scene + clicking Render. Uses a small
    /// overlay strip rather than a literal mouse pointer (less
    /// confusing — most users don't expect their cursor to move on
    /// its own).
    @State private var agentTrace: AgentTrace? = nil
    /// Set when an agent run kicks off auto-render and we want to
    /// queue a visual-QA review pass once the .mp4 lands. Cleared
    /// when the review fires or after a 60s safety window.
    @State private var pendingReview: PendingReview? = nil
    struct PendingReview: Equatable {
        let goal: String
        let armedAt: Date
    }

    struct AgentTrace: Equatable {
        var sceneName: String
        var step: Step
        enum Step { case applied, picked, rendering, done }
    }

    @ViewBuilder
    private var agentCursorOverlay: some View {
        if let t = agentTrace {
            VStack {
                AgentCursorTraceView(trace: t)
                    .padding(.top, 56)
                Spacer()
            }
            .frame(maxWidth: .infinity)
            .allowsHitTesting(false)
            .transition(.opacity.combined(with: .move(edge: .top)))
        }
    }

    /// Visual-QA pass: extract frames from the rendered .mp4 at 1
    /// fps and send them back through claude with the Review prompt.
    /// Reuses the existing chat session via the service's session-id,
    /// so this lands as a follow-up turn rather than starting fresh.
    @MainActor
    private func runReviewPass(videoURL: URL, goal: String) async {
        let frames: [URL]
        do {
            frames = try await AIReviewer.extractFrames(from: videoURL)
        } catch {
            return
        }
        guard !frames.isEmpty else { return }
        let dir = AIReviewer.framesDir(for: videoURL)
        let prompt = AIReviewer.buildReviewPrompt(originalGoal: goal,
                                                  framesDir: dir,
                                                  framePaths: frames)
        // Send on a tiny delay so the trace overlay finishes its fade
        // before the new turn appears in the transcript.
        try? await Task.sleep(nanoseconds: 600_000_000)
        svc.send(prompt: prompt,
                 originalCode: app.sourceCode,
                 modelAlias: "")
    }

    /// Apply, switch the scene picker, and post the render. Each
    /// step ticks the agent trace so the user sees what's happening.
    /// Also arms a visual-QA review pass keyed on the very next
    /// `lastRenderURL` change.
    private func applyAndRunAgent(_ apply: AIEditService.PendingApply) {
        // 1. Push the new code into the buffer.
        app.sourceCode = apply.code
        let scene = apply.suggestedScene
            ?? app.detectedScenes.first
            ?? ""
        withAnimation(.easeOut(duration: 0.25)) {
            agentTrace = AgentTrace(sceneName: scene.isEmpty ? "Scene" : scene,
                                    step: .applied)
        }
        // Arm the review-on-render-finished. Use the most recent
        // user prompt as the goal text.
        let goal = svc.turns.last?.prompt ?? ""
        pendingReview = PendingReview(goal: goal, armedAt: Date())
        svc.consumePendingAutoApply()

        // 2. Set the scene picker to the agent's choice (after a
        // short beat so the trace shows the "applied" step first).
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) {
            if !scene.isEmpty {
                app.selectedScene = scene
            }
            withAnimation(.easeInOut(duration: 0.3)) {
                agentTrace?.step = .picked
            }
        }

        // 3. Fire the preview render — picks up app.previewQuality /
        // FPS from the sidebar settings the user already configured.
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
            withAnimation(.easeInOut(duration: 0.3)) {
                agentTrace?.step = .rendering
            }
            NotificationCenter.default.post(name: .renderPreview, object: nil)
        }

        // 4. Fade the trace out after a couple seconds.
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.5) {
            withAnimation(.easeOut(duration: 0.4)) {
                agentTrace = nil
            }
        }
    }

    /// Layered background — deep navy fill + a faint top-down
    /// indigo→violet glow that pulses subtly while a turn is
    /// streaming. Keeps the panel feeling alive without being noisy.
    private var panelBackground: some View {
        ZStack {
            Theme.bgPrimary
            LinearGradient(
                colors: [Theme.indigo.opacity(svc.phase == .running ? 0.10 : 0.04),
                         .clear],
                startPoint: .top, endPoint: .center
            )
            .allowsHitTesting(false)
        }
        .animation(.easeInOut(duration: 0.6), value: svc.phase)
    }

    /// Vertical gradient border on the leading edge, plus a soft
    /// outer glow when running. Reads as "this is a special panel"
    /// without crowding the layout.
    private var panelBorder: some View {
        Rectangle()
            .fill(LinearGradient(
                colors: [Theme.indigo, Theme.violet, Theme.pink,
                         Theme.violet, Theme.indigo],
                startPoint: .top, endPoint: .bottom))
            .frame(width: 2)
            .opacity(svc.phase == .running ? 1 : 0.55)
            .shadow(color: Theme.glowPrimary
                    .opacity(svc.phase == .running ? 0.85 : 0),
                    radius: 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .allowsHitTesting(false)
            .animation(.easeInOut(duration: 0.6), value: svc.phase)
    }

    /// Plan-mode strip — visible only in agent mode. Shows what
    /// the agent is currently doing (latest tool call) with a
    /// pulsing indicator so the user knows the multi-step run is
    /// live. When idle, it's a static one-line hint.
    private var agentBanner: some View {
        HStack(spacing: 8) {
            ZStack {
                Circle()
                    .fill(LinearGradient(
                        colors: [Theme.indigo, Theme.violet],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing))
                    .frame(width: 18, height: 18)
                    .shadow(color: Theme.glowPrimary, radius: 6)
                Image(systemName: "wand.and.stars")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.white)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text("Agent")
                    .font(.system(size: 9, weight: .heavy)).tracking(1.2)
                    .foregroundStyle(Theme.violet)
                Text(agentBannerSubtitle)
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1).truncationMode(.tail)
            }
            Spacer()
            if svc.phase == .running, let last = activeToolCall {
                HStack(spacing: 5) {
                    pulsingDot
                    Text(last.name)
                        .font(.system(size: 9, weight: .semibold,
                                      design: .monospaced))
                        .foregroundStyle(Theme.textPrimary)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(Theme.bgTertiary))
                }
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
        .background(
            LinearGradient(
                colors: [Theme.indigo.opacity(0.18), Theme.violet.opacity(0.10)],
                startPoint: .leading, endPoint: .trailing))
        .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                 alignment: .bottom)
    }

    private var agentBannerSubtitle: String {
        switch svc.phase {
        case .running:
            if let last = activeToolCall {
                return "\(last.name): \(last.detail)"
            }
            return "Planning…"
        case .done:
            return "Plan complete"
        case .failed:
            return "Plan halted"
        case .idle:
            return "Multi-step: read → plan → execute → verify"
        }
    }

    /// Most recent tool call from the running turn — drives the
    /// agent banner's right-side status chip.
    private var activeToolCall: AIEditService.ToolCall? {
        svc.turns.last?.toolCalls.last
    }

    /// Animated dot used in agent-mode + thinking indicators.
    private var pulsingDot: some View {
        Circle()
            .fill(Theme.indigo)
            .frame(width: 5, height: 5)
            .opacity(svc.phase == .running ? 1 : 0.5)
            .shadow(color: Theme.glowPrimary, radius: 4)
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
                effortMenu
            }
        }
        .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 10)
        .background(Theme.bgSecondary)
    }

    /// Reasoning-effort picker. The list is model-aware so we never
    /// show levels the active model doesn't support: codex pulls
    /// supported_reasoning_levels per model from its catalog (e.g.
    /// gpt-5.5 has xhigh, gpt-5.4 doesn't); claude defaults to its
    /// CLI's universal {low, medium, high, max}, with haiku trimmed
    /// to {low, medium} since it's the budget model.
    private var effortMenu: some View {
        let levels = supportedEffortLevels()
        return Menu {
            // Auto first — empty string => no flag passed.
            Button {
                svc.effort = ""
            } label: {
                if svc.effort.isEmpty {
                    Label("Auto", systemImage: "checkmark")
                } else {
                    Text("Auto")
                }
            }
            if !levels.isEmpty { Divider() }
            ForEach(levels, id: \.self) { e in
                Button { svc.effort = e } label: {
                    if svc.effort == e {
                        Label(e.capitalized, systemImage: "checkmark")
                    } else {
                        Text(e.capitalized)
                    }
                }
            }
        } label: {
            HStack(spacing: 3) {
                Image(systemName: "gauge.high")
                    .font(.system(size: 9))
                Text(svc.effort.isEmpty
                     ? "Auto"
                     : svc.effort.capitalized)
                    .font(.system(size: 10, weight: .medium))
                Image(systemName: "chevron.down").font(.system(size: 8))
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(RoundedRectangle(cornerRadius: 6)
                .fill(Theme.bgTertiary))
        }
        .menuStyle(.borderlessButton)
        .frame(width: 86)
        .help("Reasoning effort (model-aware)")
        // If the user picks a model whose supported levels don't
        // include their previous choice, drop back to Auto so we
        // don't pass a level the CLI will reject.
        .onChange(of: selectedAlias) { _, _ in resetEffortIfUnsupported() }
        .onChange(of: svc.provider)  { _, _ in resetEffortIfUnsupported() }
    }

    /// Computes the effort levels available given the selected
    /// (provider, model). For codex: looks up the discovered model
    /// by id and reads its supportedEfforts. For claude: same lookup;
    /// if the chosen alias hasn't been resolved yet, falls back to
    /// the universal default {low, medium, high, max}.
    private func supportedEffortLevels() -> [String] {
        // Match either by alias or by exact model id (the picker
        // surfaces both; selectedAlias holds whichever was clicked).
        if let m = discovered.first(where: { $0.id == selectedAlias }),
           !m.supportedEfforts.isEmpty {
            return m.supportedEfforts
        }
        switch svc.provider {
        case .claude: return ["low", "medium", "high", "max"]
        case .codex:
            // No specific model picked → take the union of every
            // discovered codex model's levels so the picker is
            // useful from a fresh state.
            var seen: [String] = []
            for m in registry.codexModels {
                for e in m.supportedEfforts where !seen.contains(e) {
                    seen.append(e)
                }
            }
            return seen.isEmpty ? ["low", "medium", "high"] : seen
        }
    }

    private func resetEffortIfUnsupported() {
        guard !svc.effort.isEmpty else { return }
        if !supportedEffortLevels().contains(svc.effort) {
            svc.effort = ""
        }
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
                            // For codex the CLI cache often ships
                            // display_name == slug; only render once
                            // in that case. The description (if any)
                            // goes on the second line for context.
                            if let detail = m.detail, !detail.isEmpty {
                                VStack(alignment: .leading) {
                                    Text(m.display)
                                    Text(detail).font(.system(size: 9))
                                }
                            } else if m.display == m.id {
                                Text(m.id)
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

            // Thinking block (extended-thinking content, codex
            // reasoning items). Collapsible — defaults open while
            // running so the user sees the model's mind in motion,
            // collapses once the turn finishes to keep the chat tidy.
            if !turn.thinking.isEmpty {
                ThinkingBlock(text: turn.thinking,
                              live: turn.finishedAt == nil)
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

            // Code blocks captured live from Edit/Write/patch_apply
            // tool calls. Auto-scroll to the bottom while streaming
            // so the user watches the file get written line by line.
            if !turn.codeBlocks.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(turn.codeBlocks) { block in
                        CodeBlockView(block: block,
                                      live: turn.finishedAt == nil)
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
            // Attachment chips (images, PDFs, .tex, .txt, .xlsx, …).
            // Drop files onto the prompt or click the + paperclip.
            if !svc.attachments.isEmpty {
                attachmentStrip
            }

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
                .onDrop(of: [.fileURL], isTargeted: nil) { providers in
                    handleDroppedProviders(providers)
                    return true
                }

                HStack(spacing: 6) {
                    attachButton
                    actionButton
                }
                .padding(8)
            }

            HStack(spacing: 8) {
                Image(systemName: "command")
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.textDim)
                Text("⌘⏎ send  ·  drag files to attach  ·  ⇧⌘E close")
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.textDim)
                Spacer()
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Theme.bgSecondary)
    }

    /// Horizontal chip strip showing currently-attached files. Each
    /// chip has an icon by extension, the filename, and a "×"
    /// remove button.
    private var attachmentStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 5) {
                ForEach(svc.attachments, id: \.self) { url in
                    HStack(spacing: 4) {
                        Image(systemName: iconFor(url))
                            .font(.system(size: 9))
                            .foregroundStyle(tintFor(url))
                        Text(url.lastPathComponent)
                            .font(.system(size: 10))
                            .foregroundStyle(Theme.textPrimary)
                            .lineLimit(1).truncationMode(.middle)
                        Button {
                            svc.removeAttachment(url)
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 8, weight: .bold))
                                .foregroundStyle(Theme.textDim)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 7).padding(.vertical, 3)
                    .background(Capsule().fill(Theme.bgTertiary))
                    .overlay(Capsule()
                        .stroke(tintFor(url).opacity(0.45), lineWidth: 1))
                }
            }
        }
        .frame(maxHeight: 28)
    }

    private var attachButton: some View {
        Button {
            pickAttachments()
        } label: {
            Image(systemName: "paperclip")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 28, height: 28)
                .background(Circle().fill(Theme.bgTertiary))
        }
        .buttonStyle(.plain)
        .help("Attach images / PDF / .tex / .txt / .xlsx / .csv")
    }

    private func pickAttachments() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        if panel.runModal() == .OK {
            svc.addAttachments(panel.urls)
        }
    }

    private func handleDroppedProviders(_ providers: [NSItemProvider]) {
        for provider in providers {
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                guard let url = url else { return }
                Task { @MainActor in svc.addAttachments([url]) }
            }
        }
    }

    private func iconFor(_ url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "png", "jpg", "jpeg", "gif", "webp", "heic", "bmp":
            return "photo"
        case "pdf":                  return "doc.richtext"
        case "xlsx", "xls", "csv":   return "tablecells"
        case "tex":                  return "function"
        case "txt", "md":            return "doc.plaintext"
        case "json":                 return "curlybraces"
        case "py":                   return "chevron.left.forwardslash.chevron.right"
        default:                     return "doc"
        }
    }

    private func tintFor(_ url: URL) -> Color {
        switch url.pathExtension.lowercased() {
        case "png", "jpg", "jpeg", "gif", "webp", "heic", "bmp":
            return Theme.indigo
        case "pdf":                  return Theme.error
        case "xlsx", "xls", "csv":   return Theme.success
        case "tex":                  return Theme.violet
        default:                     return Theme.textSecondary
        }
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


// MARK: - thinking block + code block subviews

/// Collapsible "💭 Thinking" panel rendered above the assistant
/// reply. Live = streaming → keep open + show a pulsing brain icon.
/// Once the turn finishes, the user can toggle it on/off.
private struct ThinkingBlock: View {
    let text: String
    let live: Bool
    @State private var expanded: Bool = false

    var body: some View {
        let isOpen = live || expanded
        VStack(alignment: .leading, spacing: 6) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: live ? "brain.head.profile" : "brain")
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.violet)
                        .opacity(live ? 0.6 + 0.4 * sin(Date().timeIntervalSince1970 * 2) : 1)
                    Text("Thinking")
                        .font(.system(size: 10, weight: .semibold))
                        .tracking(0.5)
                        .foregroundStyle(Theme.violet)
                    if live {
                        Text("·").foregroundStyle(Theme.textDim)
                        Text("\(text.count) chars")
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(Theme.textDim)
                    }
                    Spacer()
                    Image(systemName: isOpen ? "chevron.up" : "chevron.down")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(Theme.textDim)
                }
            }
            .buttonStyle(.plain)
            .disabled(live)  // always-open while running

            if isOpen {
                Text(text)
                    .font(.system(size: 10, design: .monospaced))
                    .italic()
                    .foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .background(RoundedRectangle(cornerRadius: 7)
                        .fill(Theme.violet.opacity(0.08)))
                    .overlay(RoundedRectangle(cornerRadius: 7)
                        .stroke(Theme.violet.opacity(0.25), lineWidth: 1))
                    .textSelection(.enabled)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }
}

/// Streaming code block rendered inside a turn. Header shows the
/// tool + filename + line count. Body is monospaced source. While
/// the turn is live, an indigo pulse-ring on the icon signals
/// "still being written"; auto-scrolls to the bottom so the user
/// watches generation in real time.
private struct CodeBlockView: View {
    let block: AIEditService.CodeBlock
    let live: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                ZStack {
                    if live {
                        Circle()
                            .stroke(Theme.indigo.opacity(0.6), lineWidth: 1.5)
                            .frame(width: 16, height: 16)
                            .scaleEffect(1.4)
                            .opacity(0.4)
                    }
                    Image(systemName: iconName)
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 16, height: 16)
                        .background(Circle().fill(Theme.indigo))
                }
                Text(block.toolName)
                    .font(.system(size: 9, weight: .heavy)).tracking(1)
                    .foregroundStyle(Theme.indigo)
                Text((block.path as NSString).lastPathComponent)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1).truncationMode(.middle)
                Spacer()
                Text("\(lineCount) lines")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textDim)
            }
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(Theme.bgTertiary)

            ScrollViewReader { proxy in
                ScrollView {
                    Text(block.content)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                        .id("end")
                        .textSelection(.enabled)
                }
                .frame(maxHeight: 220)
                .onChange(of: block.content) { _, _ in
                    if live {
                        withAnimation { proxy.scrollTo("end", anchor: .bottom) }
                    }
                }
            }
            .background(Theme.bgDeepest)
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8)
            .stroke(Theme.indigo.opacity(live ? 0.45 : 0.20), lineWidth: 1))
    }

    private var iconName: String {
        switch block.toolName {
        case "Write":       return "doc.badge.plus"
        case "MultiEdit":   return "doc.on.doc"
        default:            return "pencil"
        }
    }

    private var lineCount: Int {
        block.content.split(whereSeparator: \.isNewline).count
    }
}

