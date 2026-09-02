// ControlsSidebar.swift — Quick Preview / Final Render controls.
// Mirrors .workspace-controls-sidebar in manim_app.
import SwiftUI
import Manim

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
    // Custom output resolution — used when Final quality == "Custom". Read
    // by PythonRuntime and applied to manim.config.pixel_width/height (the
    // wrapper rounds to even dims and derives an aspect-correct frame).
    @AppStorage("manim_custom_width")  private var customWidth = 1080
    @AppStorage("manim_custom_height") private var customHeight = 1920
    /// auto | h264 | hevc — read by PythonRuntime, which overrides
    /// python-ios-lib's encoder probe to match.
    @AppStorage("manim_video_codec")   private var videoCodec = "auto"
    /// Frames allowed to wait between the renderer and the encoder.
    /// "auto" keeps python-ios-lib's byte-bounded depth (~256 MB held at any
    /// resolution: 32 at 1080p, 8 at 4K, 2 at 8K).
    @AppStorage("manim_queue_depth")   private var queueDepth = "auto"
    /// Memory the frame queue may hold, in MB, when depth is "auto".
    /// The library turns this into a per-resolution depth, so it stays
    /// correct at every size — which a fixed frame count does not.
    @AppStorage("manim_queue_budget_mb") private var queueBudgetMB = 256

    // Quality labels map to manim's 0-5 preset index in
    // PythonRuntime.qualityIndex (the single source of truth):
    //   480p→0  720p→1  1080p→2  1440p→3  4K→4  8K→5.
    // 4K/8K render at true resolution but are very memory-heavy on iPad —
    // watch the RAM HUD; they can hit the jetsam ceiling.
    private let previewQualities = ["480p", "720p", "1080p"]
    private let finalQualities   = ["8K", "4K", "1440p", "1080p", "720p", "480p", "Custom"]
    // mp4  — H.264 video (default)
    // mov  — transparent background (alpha) — qtrle in a QuickTime
    //        container, for compositing over other footage/slides
    // gif  — animated GIF assembled from frames
    // html — single self-contained .html file with the video embedded
    //        as a base64 data URI (no external file dependency)
    private let formats = ["mp4","mov","gif","html"]

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
                if finalQuality == "Custom" { customResolution }
                stepperRow("FPS", value: $finalFPS, range: 1...120, presets: [24,30,60,120])
                pickerRow("Format", selection: $format, options: formats)
                if format == "mov" { transparentNote }
            }

            // Encoding applies to Quick Preview AND Final Render — both go
            // through the same writer, so these are deliberately outside the
            // two sections above rather than duplicated in each.
            section(title: "Encoding", icon: "cpu", tint: Theme.green) {
                Text("Applies to preview and render")
                    .font(.system(size: 9.5))
                    .foregroundStyle(Theme.textDim)
                pickerRow("Encoder", selection: $videoCodec,
                          options: ["auto", "h264", "hevc", "mpeg4"])
                encoderNote
                pickerRow("Queue depth", selection: $queueDepth,
                          options: ["auto", "2", "4", "8", "16", "32"])
                if queueDepth == "auto" {
                    stepperRow("Queue budget (MB)", value: $queueBudgetMB,
                               range: 32...2048, presets: [128, 256, 512, 1024])
                }
                queueNote
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

    /// Live answer from VideoToolbox for the resolution actually selected —
    /// the H.264 ceiling belongs to the media engine, so it differs per
    /// device (≈4K on an M4 / M3 iPad Air, 8K on an iPhone 17 Pro Max).
    private var encoderNote: some View {
        let size = RenderResolution.pixelSize(forQuality: finalQuality)
        let h264 = VideoEncoderProbe.h264Available(width: size.w, height: size.h)
        let hevc = VideoEncoderProbe.hevcAvailable(width: size.w, height: size.h)
        let picked = videoCodec
        let warn = (picked == "h264" && !h264) || (picked == "hevc" && !hevc)
        let text: String = {
            switch picked {
            case "h264":
                return h264 ? "H.264 encodes \(size.w)×\(size.h) in hardware here."
                            : "This device cannot encode \(size.w)×\(size.h) in H.264 — HEVC will be used instead."
            case "hevc":
                return hevc ? "HEVC encodes \(size.w)×\(size.h) in hardware here."
                            : "This device cannot encode \(size.w)×\(size.h) in HEVC — H.264 will be used instead."
            default:
                return "\(size.w)×\(size.h) → \(VideoEncoderProbe.autoChoice(width: size.w, height: size.h))"
            }
        }()
        return HStack(alignment: .top, spacing: 5) {
            Image(systemName: warn ? "exclamationmark.triangle" : "checkmark.seal")
                .font(.system(size: 10))
                .foregroundStyle(warn ? Theme.amber : Theme.accentPrimary)
            Text(text)
                .font(.system(size: 9.5))
                .foregroundStyle(Theme.textDim)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
    }

    /// What the chosen depth works out to at the selected resolution.
    /// The numbers come from the library's own `frameQueueDepth(forWidth:)`
    /// / `frameQueueBytes(forWidth:)` rather than being recomputed here, so
    /// the sidebar cannot drift from what the render actually does.
    private var queueNote: some View {
        let size = RenderResolution.pixelSize(forQuality: finalQuality)
        var cfg = ManimLib.RenderConfiguration()
        cfg.frameQueueDepth = queueDepth == "auto" ? nil : Int(queueDepth)
        cfg.frameQueueBudgetMB = queueBudgetMB
        let depth = cfg.frameQueueDepth(forWidth: size.w, height: size.h)
        let heldMB = Double(cfg.frameQueueBytes(forWidth: size.w, height: size.h)) / 1_048_576
        let frameMB = Double(size.w * size.h * 4) / 1_048_576
        let heavy = queueDepth != "auto" && heldMB > 600
        let text = String(
            format: "%@%d frames × %.0f MB ≈ %.0f MB held at %d×%d.%@",
            queueDepth == "auto" ? "Auto: " : "", depth, frameMB, heldMB, size.w, size.h,
            queueDepth == "auto" ? "" : " Fixed depth ignores the budget.")
        return HStack(alignment: .top, spacing: 5) {
            Image(systemName: heavy ? "exclamationmark.triangle" : "tray.2")
                .font(.system(size: 10))
                .foregroundStyle(heavy ? Theme.amber : Theme.accentPrimary)
            Text(text)
                .font(.system(size: 9.5))
                .foregroundStyle(Theme.textDim)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
    }

    /// Shown when the alpha format is picked — "mov" on its own doesn't
    /// tell you the background disappears.
    private var transparentNote: some View {
        HStack(alignment: .top, spacing: 5) {
            Image(systemName: "checkerboard.rectangle")
                .font(.system(size: 10))
                .foregroundStyle(Theme.accentPrimary)
            Text("Transparent background — no backdrop is drawn. Larger files (lossless). Preview always renders mp4.")
                .font(.system(size: 9.5))
                .foregroundStyle(Theme.textDim)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
    }

    // MARK: custom resolution

    /// Width × height fields + quick aspect presets (shown when Final
    /// quality == "Custom"). The wrapper rounds to even dims for H.264.
    private var customResolution: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                numberField($customWidth)
                Text("×").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.textDim)
                numberField($customHeight)
                Text("px").font(.system(size: 10, design: .monospaced)).foregroundStyle(Theme.textDim)
            }
            HStack(spacing: 6) {
                aspectChip("9:16", 1080, 1920)
                aspectChip("1:1", 1080, 1080)
                aspectChip("4:5", 1080, 1350)
                aspectChip("16:9", 1920, 1080)
            }
        }
        .padding(.vertical, 2)
    }

    private func numberField(_ value: Binding<Int>) -> some View {
        TextField("", value: value, format: .number)
            .keyboardType(.numberPad)
            .multilineTextAlignment(.center)
            .font(.system(size: 13, weight: .medium, design: .monospaced))
            .foregroundStyle(Theme.textPrimary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderSubtle, lineWidth: 1))
    }

    private func aspectChip(_ label: String, _ w: Int, _ h: Int) -> some View {
        let active = customWidth == w && customHeight == h
        return Button {
            customWidth = w; customHeight = h
        } label: {
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(active ? .white : Theme.textSecondary)
                .padding(.horizontal, 9).padding(.vertical, 5)
                .background(Capsule().fill(active
                    ? AnyShapeStyle(Theme.signatureGradient)
                    : AnyShapeStyle(Theme.bgTertiary)))
        }
        .buttonStyle(.plain)
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
