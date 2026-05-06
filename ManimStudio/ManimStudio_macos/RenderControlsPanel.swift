// RenderControlsPanel.swift — collapsible right-side panel exposing
// Quick Preview + Final Render configuration. Mirrors the Windows
// desktop app's Controls sidebar, but native SwiftUI with the
// glassmorphic theme.
import SwiftUI

struct RenderControlsPanel: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var venv: VenvManager
    @Binding var open: Bool

    var body: some View {
        VStack(spacing: 12) {
            header
            ScrollView {
                VStack(spacing: 14) {
                    venvCard
                    finalRenderCard
                    quickPreviewCard
                    outputCard
                }
                .padding(12)
            }
        }
        .frame(width: 290)
        .background(Theme.bgPrimary)
        .overlay(
            Rectangle().fill(Theme.borderSubtle).frame(width: 1),
            alignment: .leading)
    }

    // MARK: header

    private var header: some View {
        HStack {
            SectionHeader(title: "Controls", icon: "slider.horizontal.3")
            Spacer()
            Button { withAnimation { open = false } } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(Theme.bgTertiary))
            }
            .buttonStyle(.plain)
            .help("Hide controls")
        }
        .padding(.horizontal, 14).padding(.top, 14)
    }

    // MARK: venv

    private var venvCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                SectionHeader(title: "Environment", icon: "shippingbox.fill")
                Spacer()
                StatusDot(state: venvDotState)
            }
            switch venv.status {
            case .ready:
                rowKV("manim", venv.manimVersion)
                if let py = venv.pythonInVenv {
                    rowKV("python", py.deletingLastPathComponent()
                            .deletingLastPathComponent()
                            .lastPathComponent)
                }
            case .missing, .unknown:
                Text("Not set up yet — open the welcome wizard from the menu bar.")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
            case .creating, .installing:
                Text("Setting up…")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.indigo)
            case .failed(let why):
                Text(why)
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.error)
            }
        }
        .padding(12)
        .glassCard()
    }

    private var venvDotState: StatusDot.DotState {
        switch venv.status {
        case .ready:           return .ok
        case .creating, .installing: return .active
        case .failed:          return .error
        default:               return .idle
        }
    }

    // MARK: render cards

    private var finalRenderCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "film.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.violet)
                SectionHeader(title: "Final Render")
            }

            picker(label: "Quality", selection: $app.renderQuality) {
                ForEach(RenderQuality.allCases) { q in Text(q.label).tag(q) }
            }
            stepper(label: "FPS", value: $app.renderFPS, range: 12...120, step: 6,
                    presets: [24, 30, 60, 120])
            picker(label: "Format", selection: $app.renderFormat) {
                ForEach(RenderFormat.allCases) { f in Text(f.label).tag(f) }
            }
        }
        .padding(12)
        .glassCard()
    }

    private var quickPreviewCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.amber)
                SectionHeader(title: "Quick Preview")
            }
            Text("⇧⌘R always renders 480p / 15 fps for fast iteration. Final settings apply only to ⌘R.")
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .glassCard()
    }

    private var outputCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "internaldrive")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.cyan)
                SectionHeader(title: "Output")
            }
            if let url = app.lastRenderURL {
                rowKV("last", url.lastPathComponent)
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([url])
                } label: {
                    Label("Reveal in Finder", systemImage: "magnifyingglass.circle")
                        .font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.indigo)
            } else {
                Text("No render yet. ⌘R renders the active Scene class.")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(12)
        .glassCard()
    }

    // MARK: helpers

    @ViewBuilder
    private func rowKV(_ k: String, _ v: String) -> some View {
        HStack(spacing: 10) {
            Text(k.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .tracking(1)
                .foregroundStyle(Theme.textDim)
                .frame(width: 56, alignment: .leading)
            Text(v)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1).truncationMode(.middle)
            Spacer()
        }
    }

    @ViewBuilder
    private func picker<T: Hashable, Content: View>(
        label: String,
        selection: Binding<T>,
        @ViewBuilder content: () -> Content
    ) -> some View {
        HStack {
            Text(label).font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
            Spacer()
            Picker("", selection: selection, content: content)
                .labelsHidden()
                .pickerStyle(.menu)
                .controlSize(.small)
                .tint(Theme.indigo)
        }
    }

    @ViewBuilder
    private func stepper(label: String,
                         value: Binding<Int>,
                         range: ClosedRange<Int>,
                         step: Int,
                         presets: [Int]) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(label).font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
                Spacer()
                Text("\(value.wrappedValue)")
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
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
                                          : AnyShapeStyle(Theme.bgTertiary)))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}
