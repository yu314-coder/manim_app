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
    var onRender:  () -> Void
    var onPreview: () -> Void
    var onStop:    () -> Void
    var onNew:     () -> Void
    var onOpen:    () -> Void
    var onSave:    () -> Void

    @State private var gpuOn = true
    @State private var showSettings = false
    @State private var showHelp = false

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
        HStack(spacing: 4) {
            Image(systemName: "function").font(.system(size: 10))
            Text("LaTeX").font(.system(size: 10, weight: .medium))
        }
        .foregroundStyle(Theme.success)
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(Capsule().fill(Theme.success.opacity(0.12)))
        .overlay(Capsule().stroke(Theme.success.opacity(0.4), lineWidth: 1))
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
