// ControlsSidebar.swift — Quick Preview / Final Render controls.
// Mirrors .workspace-controls-sidebar in manim_app.
import SwiftUI

struct ControlsSidebar: View {
    @Binding var isOpen: Bool

    // Persisted so PythonRuntime (which reads UserDefaults["manim_quality"]
    // and ["manim_fps"] inline in the wrapper script) actually picks up
    // the user's choice, and so values survive relaunches.
    @AppStorage("manim_preview_quality") private var previewQuality = "480p"
    @AppStorage("manim_preview_fps")     private var previewFPS = 15
    @AppStorage("manim_final_quality")   private var finalQuality = "1080p"
    @AppStorage("manim_final_fps")       private var finalFPS = 30
    @AppStorage("manim_format")          private var format = "mp4"

    /// Map quality label → PythonRuntime's 0/1/2 enum. Rough mapping
    /// chosen so anything ≥ 1080p is "high", 480p–720p is "medium", and
    /// the lower tiers are "low" — keeps render time predictable.
    private static func qualityIndex(_ q: String) -> Int {
        switch q {
        case "120p","240p","360p":          return 0
        case "480p","720p":                 return 1
        default:                            return 2  // 1080p / 1440p / 4K / 8K
        }
    }

    private let previewQualities = ["120p", "240p", "360p", "480p", "720p", "1080p"]
    private let finalQualities   = ["8K", "4K", "1440p", "1080p", "720p", "480p"]
    private let formats = ["mp4","mov","gif","png"]

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
        // Mirror to the canonical keys PythonRuntime reads inline before
        // every render. Final values take effect for Render; Preview is
        // hardcoded low_quality on the Python side via an env var so its
        // numbers here are presentational only.
        .onAppear  { writeThrough() }
        .onChange(of: finalQuality) { _, _ in writeThrough() }
        .onChange(of: finalFPS)     { _, _ in writeThrough() }
    }

    private func writeThrough() {
        UserDefaults.standard.set(Self.qualityIndex(finalQuality), forKey: "manim_quality")
        UserDefaults.standard.set(finalFPS, forKey: "manim_fps")
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
