// AIEditView.swift — sheet UI for the AI Edit feature. Modeled
// loosely on the Windows desktop app's `web/ai-edit-window.html`
// but written purely in SwiftUI / AppKit.
//
// Layout: header with provider toggle (just Claude for now — Codex
// support can come later) + model picker + close, two-column body
// with prompt on the left and streaming output on the right, and an
// Accept/Reject bar that appears when the run finishes with a diff.
import SwiftUI
import AppKit

struct AIEditView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var svc = AIEditService()
    @Environment(\.dismiss) private var dismiss

    @State private var prompt: String = ""
    @State private var selectedModel: AIModel = .default

    enum AIModel: String, CaseIterable, Identifiable {
        case `default` = ""
        case opus      = "claude-opus-4-7"
        case sonnet    = "claude-sonnet-4-7"
        case haiku     = "claude-haiku-4-5"
        var id: String { rawValue }
        var label: String {
            switch self {
            case .default: return "Default"
            case .opus:    return "Opus 4.7"
            case .sonnet:  return "Sonnet 4.7"
            case .haiku:   return "Haiku 4.5"
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            body_
            if svc.editedCode != nil {
                acceptRejectBar
            }
        }
        .frame(minWidth: 940, minHeight: 600)
        .background(Theme.bgPrimary)
        .preferredColorScheme(.dark)
    }

    // MARK: - header

    private var header: some View {
        HStack(spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: "wand.and.sparkles")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.signatureGradient)
                Text("AI Edit")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text("BETA")
                    .font(.system(size: 9, weight: .bold))
                    .tracking(1)
                    .foregroundStyle(Theme.amber)
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .background(Capsule().stroke(Theme.amber.opacity(0.6), lineWidth: 1))
            }
            // Provider pill — only Claude active for now.
            HStack(spacing: 4) {
                providerPill("Claude", icon: "sparkles", active: true)
                providerPill("Codex",  icon: "chevron.left.forwardslash.chevron.right",
                             active: false, disabled: true)
            }
            Spacer()
            Menu {
                ForEach(AIModel.allCases) { m in
                    Button(m.label) { selectedModel = m }
                }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "cpu").font(.system(size: 11))
                    Text(selectedModel.label)
                        .font(.system(size: 12, weight: .medium))
                    Image(systemName: "chevron.down").font(.system(size: 9))
                }
                .foregroundStyle(Theme.textPrimary)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .background(RoundedRectangle(cornerRadius: 7)
                    .fill(Theme.bgTertiary))
            }
            .menuStyle(.borderlessButton)
            .frame(width: 130)

            Button {
                svc.newSession()
            } label: {
                Image(systemName: "plus.bubble")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 26, height: 26)
                    .background(RoundedRectangle(cornerRadius: 6)
                        .fill(Theme.bgTertiary))
            }
            .buttonStyle(.plain)
            .help("Start a fresh chat session")

            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 26, height: 26)
                    .background(RoundedRectangle(cornerRadius: 6)
                        .fill(Theme.bgTertiary))
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.escape, modifiers: [])
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(Theme.bgSecondary)
    }

    @ViewBuilder
    private func providerPill(_ name: String, icon: String,
                              active: Bool, disabled: Bool = false) -> some View
    {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 10))
            Text(name).font(.system(size: 11, weight: .semibold))
        }
        .foregroundStyle(active ? .white : Theme.textDim)
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 5)
                .fill(active
                      ? AnyShapeStyle(Theme.signatureGradient)
                      : AnyShapeStyle(Theme.bgTertiary))
        )
        .opacity(disabled ? 0.4 : 1)
    }

    // MARK: - body

    private var body_: some View {
        HSplitView {
            // ── LEFT: prompt + send
            VStack(alignment: .leading, spacing: 12) {
                Text("Prompt")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                ZStack(alignment: .topLeading) {
                    if prompt.isEmpty {
                        Text("Describe what you want to change…\nE.g. \"replace the title with Text('Pythagoras') and animate it\"")
                            .font(.system(size: 12))
                            .foregroundStyle(Theme.textDim)
                            .padding(10)
                            .allowsHitTesting(false)
                    }
                    TextEditor(text: $prompt)
                        .font(.system(size: 12, design: .monospaced))
                        .scrollContentBackground(.hidden)
                        .padding(6)
                }
                .background(RoundedRectangle(cornerRadius: 8)
                    .fill(Theme.bgDeepest))
                .overlay(RoundedRectangle(cornerRadius: 8)
                    .stroke(Theme.borderSubtle, lineWidth: 1))
                .frame(minHeight: 160)

                HStack(spacing: 8) {
                    sendButton
                    if case .running = svc.phase {
                        Button("Stop") { svc.stop() }
                            .buttonStyle(.borderedProminent)
                            .tint(Theme.error)
                    }
                    Spacer()
                    statusBadge
                }

                if svc.lastInputTokens + svc.lastOutputTokens > 0 {
                    HStack(spacing: 12) {
                        smallStat("in",  "\(svc.lastInputTokens) tok")
                        smallStat("out", "\(svc.lastOutputTokens) tok")
                        smallStat("$",   String(format: "%.4f", svc.lastCostUSD))
                    }
                }
                Spacer()
                Text("Tip: ⌘⏎ to send. Edits go through `claude -p` with the Read/Edit toolset enabled, sandboxed to a workspace dir. Click Accept to apply the result to your scene buffer.")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textDim)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
            .frame(minWidth: 320, idealWidth: 380)
            .background(Theme.bgPrimary)

            // ── RIGHT: streaming output
            VStack(spacing: 0) {
                HStack {
                    Image(systemName: "terminal.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.indigo)
                    Text("Output")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                    Spacer()
                    Text("session: \(svc.sessionId.prefix(8))")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                }
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(Theme.bgSecondary)
                .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                         alignment: .bottom)

                ScrollViewReader { proxy in
                    ScrollView {
                        Text(svc.output.isEmpty ? "(no output yet)" : svc.output)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(svc.output.isEmpty
                                             ? Theme.textDim : Theme.textPrimary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .id("end")
                            .textSelection(.enabled)
                    }
                    .onChange(of: svc.output) { _, _ in
                        withAnimation { proxy.scrollTo("end", anchor: .bottom) }
                    }
                }
                .background(Theme.bgDeepest)
            }
            .frame(minWidth: 420)
        }
    }

    private var sendButton: some View {
        Button {
            send()
        } label: {
            HStack(spacing: 5) {
                Image(systemName: "paperplane.fill")
                    .font(.system(size: 11))
                Text("Send").font(.system(size: 12, weight: .semibold))
                Text("⌘⏎").font(.system(size: 9))
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Capsule().fill(.white.opacity(0.18)))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 8)
                .fill(Theme.signatureGradient))
            .shadow(color: Theme.glowPrimary, radius: 8, y: 2)
        }
        .buttonStyle(.plain)
        .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                  || svc.phase == .running)
        .opacity((prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                  || svc.phase == .running) ? 0.5 : 1)
        .keyboardShortcut(.return, modifiers: .command)
    }

    @ViewBuilder
    private var statusBadge: some View {
        switch svc.phase {
        case .idle:
            EmptyView()
        case .running:
            HStack(spacing: 5) {
                ProgressView().controlSize(.small)
                Text("Working… \(Int(svc.elapsed))s")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
        case .done(let applied):
            Label(applied ? "Applied" : "Ready",
                  systemImage: applied ? "checkmark.circle.fill" : "checkmark.circle")
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(Theme.success)
        case .failed(let why):
            Label(why, systemImage: "exclamationmark.triangle.fill")
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(Theme.error)
                .lineLimit(1)
        }
    }

    @ViewBuilder
    private func smallStat(_ k: String, _ v: String) -> some View {
        HStack(spacing: 3) {
            Text(k.uppercased())
                .font(.system(size: 8, weight: .bold)).tracking(1)
                .foregroundStyle(Theme.textDim)
            Text(v)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Theme.textSecondary)
        }
    }

    // MARK: - accept / reject bar

    private var acceptRejectBar: some View {
        HStack(spacing: 12) {
            Image(systemName: "doc.text.below.ecg")
                .font(.system(size: 14))
                .foregroundStyle(Theme.indigo)
            VStack(alignment: .leading, spacing: 2) {
                Text("Edit ready")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(diffSummary)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            Button {
                svc.rejectEdit()
            } label: {
                Text("Reject")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 7)
                        .fill(Theme.bgTertiary))
            }
            .buttonStyle(.plain)
            Button {
                if let edited = svc.acceptEdit() {
                    app.sourceCode = edited
                }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "checkmark").font(.system(size: 11, weight: .bold))
                    Text("Accept").font(.system(size: 11, weight: .semibold))
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 14).padding(.vertical, 6)
                .background(RoundedRectangle(cornerRadius: 7)
                    .fill(Theme.signatureGradient))
                .shadow(color: Theme.glowPrimary, radius: 6)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(Theme.bgSecondary)
        .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                 alignment: .top)
    }

    private var diffSummary: String {
        guard let edited = svc.editedCode else { return "" }
        let oldLines = app.sourceCode.split(separator: "\n").count
        let newLines = edited.split(separator: "\n").count
        let delta = newLines - oldLines
        let sign = delta >= 0 ? "+" : ""
        return "\(newLines) lines (\(sign)\(delta) vs current)"
    }

    private func send() {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        svc.send(prompt: trimmed,
                 originalCode: app.sourceCode,
                 model: selectedModel.rawValue)
    }
}
