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

    @State private var gpuOn = false
    @State private var autosaveText = "Autosaved"

    // Persistent UI state — used by Settings/Theme sheets.
    @AppStorage("manim_theme_mode") private var themeMode: String = "dark"
                                                        // "dark" | "light" | "system"
    @AppStorage("manim_accent_hex") private var accentHex: String = "6366F1"
                                                        // indigo default
    @AppStorage("manim_terminal_font") private var terminalFontSize: Double = 13

    @State private var showSettings = false
    @State private var showHelp     = false
    @State private var showColors   = false

    var body: some View {
        HStack(spacing: 16) {
            // LEFT — logo + title + autosave
            HStack(spacing: 10) {
                Text("🎬").font(.system(size: 22))
                VStack(alignment: .leading, spacing: 0) {
                    Text("Manim Animation Studio")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                    Text("Professional Edition v1.1.2.0")
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
                Toggle("", isOn: $gpuOn)
                    .toggleStyle(.button)
                    .tint(Theme.accentPrimary)
                    .overlay(
                        Image(systemName: "bolt.fill")
                            .font(.system(size: 11))
                            .foregroundStyle(gpuOn ? .white : Theme.textSecondary)
                            .allowsHitTesting(false)
                    )
                    .help("GPU acceleration")

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
                headerBtn(themeIcon, "Theme: \(themeMode.capitalized)") { cycleTheme() }
                headerBtn("questionmark.circle", "Help") { showHelp.toggle() }
            }
        }
        .padding(.horizontal, 14)
        .frame(height: 52)
        .background(
            Theme.bgSecondary
                .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1), alignment: .bottom)
        )
        .preferredColorScheme(themeColorScheme)
        .sheet(isPresented: $showSettings) {
            SettingsSheet(themeMode: $themeMode,
                          accentHex: $accentHex,
                          terminalFontSize: $terminalFontSize,
                          gpuOn: $gpuOn)
        }
        .sheet(isPresented: $showHelp) {
            HelpSheet()
        }
    }

    // MARK: theme

    private var themeIcon: String {
        switch themeMode {
        case "light":  return "sun.max"
        case "system": return "circle.lefthalf.filled"
        default:       return "moon"
        }
    }
    private var themeColorScheme: ColorScheme? {
        switch themeMode {
        case "light":  return .light
        case "dark":   return .dark
        default:       return nil   // follow system
        }
    }
    private func cycleTheme() {
        switch themeMode {
        case "dark":   themeMode = "light"
        case "light":  themeMode = "system"
        default:       themeMode = "dark"
        }
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
                Image(systemName: "rectangle.stack").font(.system(size: 10))
                Text(label).font(.system(size: 11, weight: .medium)).lineLimit(1)
                Image(systemName: "chevron.down").font(.system(size: 8))
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderSubtle, lineWidth: 1))
        }
        .help("Choose which Scene class to render")
        .frame(maxWidth: 180)
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
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 11, weight: .bold))
                Text(label).font(.system(size: 12, weight: .semibold))
                Text(shortcut)
                    .font(.system(size: 9, weight: .medium))
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Capsule().fill(.white.opacity(0.18)))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.signatureGradient))
            .shadow(color: Theme.glowPrimary, radius: 8, y: 2)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func secondaryBtn(label: String, icon: String, shortcut: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 11))
                Text(label).font(.system(size: 12, weight: .medium))
                Text(shortcut).font(.system(size: 9))
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Capsule().fill(Theme.bgSurface))
            }
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderActive, lineWidth: 1))
        }
        .buttonStyle(.plain)
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
    @Binding var themeMode: String
    @Binding var accentHex: String
    @Binding var terminalFontSize: Double
    @Binding var gpuOn: Bool

    var body: some View {
        NavigationStack {
            Form {
                Section("Appearance") {
                    Picker("Theme", selection: $themeMode) {
                        Text("Dark").tag("dark")
                        Text("Light").tag("light")
                        Text("System").tag("system")
                    }
                    HStack {
                        Text("Accent")
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
                }
                Section("Terminal") {
                    HStack {
                        Text("Font size")
                        Slider(value: $terminalFontSize, in: 9...22, step: 1)
                        Text("\(Int(terminalFontSize))pt")
                            .font(.system(size: 12, design: .monospaced))
                            .frame(width: 44, alignment: .trailing)
                    }
                }
                Section("Render") {
                    Toggle("GPU acceleration (Metal)", isOn: $gpuOn)
                }
                Section("About") {
                    LabeledContent("Version", value: "1.1.2.0")
                    LabeledContent("Manim",   value: "0.20.1")
                    LabeledContent("Python",  value: "3.14")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

private struct HelpSheet: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    section("Getting started", """
                    Edit Python code in the Workspace tab. Define one or more \
                    `class MyScene(Scene): def construct(self): …` classes, then \
                    tap Render or Preview. Output appears in the preview pane and \
                    in the live terminal.
                    """)
                    section("Render vs Preview", """
                    Render uses high-quality settings (1080p, ~24-60 fps). \
                    Preview uses low-quality settings (480p, faster) for iteration.
                    """)
                    section("Scene picker", """
                    When more than one Scene class is detected, the picker (next \
                    to Render) lets you choose one. \"All\" renders every scene \
                    in source order.
                    """)
                    section("LaTeX", """
                    Manim's `Tex` and `MathTex` work via busytex. Math-mode \
                    (single-formula) is reliable; full-document LaTeX is gated.
                    """)
                    section("Saving outputs", """
                    Rendered MP4s land in Documents/ToolOutputs/. Documents is \
                    exposed in the iOS Files app so you can drag MP4s out.
                    """)
                    section("Packages tab", """
                    Lists every importable Python package bundled with the app, \
                    including version and a short description.
                    """)
                    section("Need more?", """
                    Manim docs:  https://docs.manim.community/
                    Project repo: https://github.com/yu314-coder/python-ios-lib/
                    """)
                }
                .padding(16)
            }
            .navigationTitle("Help")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
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
