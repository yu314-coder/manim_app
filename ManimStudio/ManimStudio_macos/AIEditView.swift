// AIEditView.swift — embedded AI edit panel for the editor pane.
// Used to be a sheet; now lives as a collapsible right-side panel
// inside EditorPane so users can iterate prompt → preview → edit
// without losing track of the code they're editing.
//
// Header: provider toggle (Claude / Codex), mode toggle (Edit /
// Agent), model picker, new-session button, close.
// Body: prompt textarea on top, streaming output below.
// Footer: Accept / Reject when an edit is staged.
//
// The model picker shows the real, last-resolved model name next
// to each alias (cached in UserDefaults via AIEditService) — so
// users see "Opus → claude-opus-4-6" once a turn has run, not
// just "Opus (latest)".
import SwiftUI
import AppKit

struct AIEditView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var svc = AIEditService()
    /// Toggles the panel from inside EditorPane. The host view
    /// also flips this when the user presses ⇧⌘E or clicks the
    /// header AI Edit button.
    @Binding var open: Bool

    @State private var prompt: String = ""
    @State private var selectedAlias: String = ""

    /// Aliases are CLI-side — the actual model name comes back via
    /// svc.resolvedModel and gets cached per alias. Keeps the app
    /// future-proof: when Anthropic / OpenAI ship newer models, the
    /// CLI alias still resolves correctly without an app update.
    private var aliases: [(id: String, label: String)] {
        switch svc.provider {
        case .claude:
            return [("",        "Default"),
                    ("opus",    "Opus"),
                    ("sonnet",  "Sonnet"),
                    ("haiku",   "Haiku")]
        case .codex:
            // Codex aliases per `codex exec --help`. The CLI resolves
            // these to the latest variant ChatGPT lets the user use.
            return [("",                  "Default"),
                    ("gpt-5-codex",       "GPT-5 Codex"),
                    ("gpt-5",             "GPT-5"),
                    ("gpt-5-mini",        "GPT-5 Mini"),
                    ("o3",                "o3")]
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            promptBlock
            Divider()
            outputBlock
            if svc.editedCode != nil {
                Divider()
                acceptRejectBar
            }
        }
        .background(Theme.bgPrimary)
        .onAppear { svc.probeCLI() }
    }

    // MARK: - header

    private var header: some View {
        VStack(spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: "wand.and.sparkles")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.signatureGradient)
                Text("AI Edit")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text("BETA")
                    .font(.system(size: 8, weight: .bold)).tracking(1)
                    .foregroundStyle(Theme.amber)
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Capsule().stroke(Theme.amber.opacity(0.6),
                                                  lineWidth: 1))
                Spacer()

                Button {
                    svc.newSession()
                } label: {
                    Image(systemName: "plus.bubble")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(width: 22, height: 22)
                        .background(RoundedRectangle(cornerRadius: 5)
                            .fill(Theme.bgTertiary))
                }
                .buttonStyle(.plain)
                .help("Fresh session")

                Button { open = false } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(width: 22, height: 22)
                        .background(RoundedRectangle(cornerRadius: 5)
                            .fill(Theme.bgTertiary))
                }
                .buttonStyle(.plain)
                .help("Close (⇧⌘E)")
                .keyboardShortcut("e", modifiers: [.command, .shift])
            }

            HStack(spacing: 6) {
                providerToggle
                modeToggle
                Spacer()
                modelMenu
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(Theme.bgSecondary)
    }

    private var providerToggle: some View {
        HStack(spacing: 0) {
            ForEach(AIEditService.Provider.allCases) { p in
                Button {
                    svc.provider = p
                } label: {
                    Text(p.label)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(svc.provider == p ? .white : Theme.textSecondary)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .background(svc.provider == p
                                    ? AnyShapeStyle(Theme.signatureGradient)
                                    : AnyShapeStyle(Color.clear))
                }
                .buttonStyle(.plain)
            }
        }
        .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private var modeToggle: some View {
        HStack(spacing: 0) {
            ForEach(AIEditService.Mode.allCases) { m in
                Button {
                    svc.mode = m
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
        .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .help(svc.mode == .agent
              ? "Agent: multi-step plan + execute (auto-approves edits)"
              : "Edit: one-shot scene.py mutation")
    }

    private var modelMenu: some View {
        Menu {
            ForEach(aliases, id: \.id) { entry in
                Button {
                    selectedAlias = entry.id
                } label: {
                    VStack(alignment: .leading) {
                        Text(entry.label)
                        if let resolved = svc.resolvedName(
                            for: entry.id.isEmpty ? "default" : entry.id) {
                            Text("→ \(resolved)")
                                .font(.system(size: 9))
                        }
                    }
                }
            }
            Divider()
            if !svc.claudeCLIVersion.isEmpty,
               svc.provider == .claude {
                Text(svc.claudeCLIVersion)
            }
            if !svc.codexCLIVersion.isEmpty,
               svc.provider == .codex {
                Text(svc.codexCLIVersion)
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "cpu").font(.system(size: 10))
                Text(menuLabel)
                    .font(.system(size: 10, weight: .medium))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Image(systemName: "chevron.down").font(.system(size: 8))
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(RoundedRectangle(cornerRadius: 6)
                .fill(Theme.bgTertiary))
        }
        .menuStyle(.borderlessButton)
        .frame(width: 200)
    }

    /// Label combines alias + cached resolved name when known so the
    /// dropdown reads "Opus → claude-opus-4-6" instead of "Opus".
    private var menuLabel: String {
        let entry = aliases.first(where: { $0.id == selectedAlias })
            ?? aliases[0]
        if let resolved = svc.resolvedName(
            for: entry.id.isEmpty ? "default" : entry.id) {
            return "\(entry.label) · \(resolved)"
        }
        return entry.label
    }

    // MARK: - prompt + output

    private var promptBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text("Prompt")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                statusBadge
            }

            ZStack(alignment: .topLeading) {
                if prompt.isEmpty {
                    Text(placeholder)
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.textDim)
                        .padding(8)
                        .allowsHitTesting(false)
                }
                TextEditor(text: $prompt)
                    .font(.system(size: 11, design: .monospaced))
                    .scrollContentBackground(.hidden)
                    .padding(4)
            }
            .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgDeepest))
            .overlay(RoundedRectangle(cornerRadius: 6)
                .stroke(Theme.borderSubtle, lineWidth: 1))
            .frame(minHeight: 90, maxHeight: 160)

            HStack(spacing: 6) {
                sendButton
                if case .running = svc.phase {
                    Button("Stop") { svc.stop() }
                        .buttonStyle(.borderedProminent)
                        .tint(Theme.error)
                        .controlSize(.small)
                }
                Spacer()
                if svc.lastInputTokens + svc.lastOutputTokens > 0 {
                    Text("\(svc.lastInputTokens)→\(svc.lastOutputTokens) tok")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                }
                if svc.lastCostUSD > 0 {
                    Text(String(format: "$%.4f", svc.lastCostUSD))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                }
            }
        }
        .padding(10)
    }

    private var placeholder: String {
        switch (svc.provider, svc.mode) {
        case (_, .agent):
            return "Describe the animation you want generated…"
        case (.claude, .edit):
            return "What should claude change in scene.py?"
        case (.codex, .edit):
            return "What should codex change in scene.py?"
        }
    }

    private var sendButton: some View {
        Button {
            send()
        } label: {
            HStack(spacing: 4) {
                Image(systemName: svc.mode == .agent
                      ? "wand.and.stars" : "paperplane.fill")
                    .font(.system(size: 10))
                Text("Send").font(.system(size: 11, weight: .semibold))
                Text("⌘⏎").font(.system(size: 8))
                    .padding(.horizontal, 3).padding(.vertical, 1)
                    .background(Capsule().fill(.white.opacity(0.18)))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 6)
                .fill(Theme.signatureGradient))
            .shadow(color: Theme.glowPrimary, radius: 5, y: 1)
        }
        .buttonStyle(.plain)
        .disabled(promptIsEmpty || svc.phase == .running)
        .opacity((promptIsEmpty || svc.phase == .running) ? 0.5 : 1)
        .keyboardShortcut(.return, modifiers: .command)
    }

    private var promptIsEmpty: Bool {
        prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    @ViewBuilder
    private var statusBadge: some View {
        switch svc.phase {
        case .idle: EmptyView()
        case .running:
            HStack(spacing: 4) {
                ProgressView().controlSize(.small)
                Text("\(Int(svc.elapsed))s")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
        case .done(let applied):
            Image(systemName: applied
                  ? "checkmark.circle.fill" : "checkmark.circle")
                .font(.system(size: 11))
                .foregroundStyle(Theme.success)
        case .failed(let why):
            HStack(spacing: 3) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 9))
                Text(why).font(.system(size: 9))
            }
            .foregroundStyle(Theme.error)
            .lineLimit(1)
        }
    }

    private var outputBlock: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "terminal.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.indigo)
                Text("Output")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                if !svc.resolvedModel.isEmpty {
                    Text(svc.resolvedModel)
                        .font(.system(size: 8, weight: .semibold,
                                      design: .monospaced))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(Capsule().fill(Theme.indigo.opacity(0.6)))
                }
                Spacer()
                Text(svc.sessionId.prefix(8))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textDim)
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(Theme.bgSecondary)
            .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                     alignment: .bottom)

            ScrollViewReader { proxy in
                ScrollView {
                    Text(svc.output.isEmpty ? "(no output yet)" : svc.output)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(svc.output.isEmpty
                                          ? Theme.textDim : Theme.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .id("end")
                        .textSelection(.enabled)
                }
                .onChange(of: svc.output) { _, _ in
                    withAnimation { proxy.scrollTo("end", anchor: .bottom) }
                }
            }
            .background(Theme.bgDeepest)
        }
    }

    // MARK: - accept / reject

    private var acceptRejectBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "doc.text.below.ecg")
                .font(.system(size: 12))
                .foregroundStyle(Theme.indigo)
            VStack(alignment: .leading, spacing: 1) {
                Text("Edit ready")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(diffSummary)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            Button { svc.rejectEdit() } label: {
                Text("Reject")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(RoundedRectangle(cornerRadius: 6)
                        .fill(Theme.bgTertiary))
            }.buttonStyle(.plain)
            Button {
                if let edited = svc.acceptEdit() {
                    app.sourceCode = edited
                }
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "checkmark").font(.system(size: 10, weight: .bold))
                    Text("Accept").font(.system(size: 10, weight: .semibold))
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 12).padding(.vertical, 4)
                .background(RoundedRectangle(cornerRadius: 6)
                    .fill(Theme.signatureGradient))
                .shadow(color: Theme.glowPrimary, radius: 5)
            }.buttonStyle(.plain)
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(Theme.bgSecondary)
    }

    private var diffSummary: String {
        guard let edited = svc.editedCode else { return "" }
        let oldLines = app.sourceCode.split(separator: "\n").count
        let newLines = edited.split(separator: "\n").count
        let delta = newLines - oldLines
        let sign = delta >= 0 ? "+" : ""
        return "\(newLines) lines (\(sign)\(delta))"
    }

    // MARK: - send

    private func send() {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        svc.send(prompt: trimmed,
                 originalCode: app.sourceCode,
                 modelAlias: selectedAlias)
    }
}
