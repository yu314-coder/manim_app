// ControlsSidebar.swift — Quick Preview / Final Render controls.
// Mirrors .workspace-controls-sidebar in manim_app.
import SwiftUI

struct ControlsSidebar: View {
    @ObservedObject private var theme = ThemeManager.shared   // accent → live retint
    @Binding var isOpen: Bool

    // Persisted via @AppStorage so the choices survive relaunches AND so
    // PythonRuntime can read them straight from UserDefaults inline before
    // every render (manim_preview_quality / _fps for Preview, manim_final_
    // quality / _fps for Render). The gear Settings sheet writes the same
    // final-render keys, so either surface is authoritative.
    @AppStorage("manim_preview_quality") private var previewQuality = "480p"
    @AppStorage("manim_preview_fps")     private var previewFPS = 15
    @AppStorage("manim_final_quality")   private var finalQuality = "1080p"
    @AppStorage("manim_final_fps")       private var finalFPS = 30
    @AppStorage("manim_format")          private var format = "mp4"

    // Quality labels map to manim's 0-5 preset index in
    // PythonRuntime.qualityIndex (the single source of truth):
    //   480p→0  720p→1  1080p→2  1440p→3  4K→4  8K→5.
    // 4K/8K render at true resolution but are very memory-heavy on iPad —
    // watch the RAM HUD; they can hit the jetsam ceiling.
    private let previewQualities = ["480p", "720p", "1080p"]
    private let finalQualities   = ["8K", "4K", "1440p", "1080p", "720p", "480p"]
    // mp4  — H.264 video (default)
    // gif  — animated GIF assembled from frames
    // html — single self-contained .html file with the video embedded
    //        as a base64 data URI (no external file dependency)
    private let formats = ["mp4","gif","html"]

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("Controls").font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                Button { withAnimation { isOpen = false } } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(width: 22, height: 22)
                        .background(Circle().fill(Theme.bgTertiary))
                }.buttonStyle(.plain)
            }

            section(title: "Quick Preview", icon: "bolt.fill", tint: Theme.warning) {
                pickerRow("Quality", selection: $previewQuality, options: previewQualities)
                stepperRow("FPS", value: $previewFPS, range: 1...120, presets: [15,24,30,60])
            }

            section(title: "Final Render", icon: "film.fill", tint: Theme.accentPrimary) {
                pickerRow("Quality", selection: $finalQuality, options: finalQualities)
                stepperRow("FPS", value: $finalFPS, range: 1...120, presets: [24,30,60,120])
                pickerRow("Format", selection: $format, options: formats)
            }

            Spacer()
        }
        .padding(12)
        .background(Theme.bgSecondary)
        .overlay(Rectangle().fill(Theme.borderSubtle).frame(width: 1), alignment: .leading)
        // All five controls persist straight to UserDefaults via @AppStorage
        // (manim_preview_quality / _fps, manim_final_quality / _fps,
        // manim_format). PythonRuntime reads those keys inline before every
        // render and converts the quality label to manim's preset index, so
        // there's nothing to mirror here — and the gear Settings sheet, which
        // writes the same keys, stays authoritative even when this drawer is
        // closed.
    }

    @ViewBuilder
    private func section<Content: View>(title: String, icon: String, tint: Color,
                                        @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 10)).foregroundStyle(tint)
                Text(title).font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .textCase(.uppercase)
                    .tracking(0.5)
            }
            content()
        }
        .glassCard()
    }

    @ViewBuilder
    private func pickerRow(_ label: String, selection: Binding<String>, options: [String]) -> some View {
        HStack {
            Text(label).font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
            Spacer()
            Menu {
                ForEach(options, id: \.self) { opt in
                    Button(opt) { selection.wrappedValue = opt }
                }
            } label: {
                HStack(spacing: 4) {
                    Text(selection.wrappedValue).font(.system(size: 11, weight: .medium))
                    Image(systemName: "chevron.down").font(.system(size: 8))
                }
                .foregroundStyle(Theme.textPrimary)
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.borderSubtle, lineWidth: 1))
            }
        }
    }

    @ViewBuilder
    private func stepperRow(_ label: String, value: Binding<Int>,
                            range: ClosedRange<Int>, presets: [Int]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label).font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
                Spacer()
                Text("\(value.wrappedValue)")
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
            }
            HStack(spacing: 4) {
                ForEach(presets, id: \.self) { p in
                    Button { value.wrappedValue = p } label: {
                        Text("\(p)")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(value.wrappedValue == p ? .white : Theme.textSecondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 4)
                            .background(
                                RoundedRectangle(cornerRadius: 5)
                                    .fill(value.wrappedValue == p
                                          ? AnyShapeStyle(Theme.signatureGradient)
                                          : AnyShapeStyle(Theme.bgTertiary))
                            )
                    }.buttonStyle(.plain)
                }
            }
        }
    }
}
