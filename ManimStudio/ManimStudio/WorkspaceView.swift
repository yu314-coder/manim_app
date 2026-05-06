// WorkspaceView.swift — workspace tab: editor (left), preview (right),
// terminal (bottom), controls sidebar (right floating).
import SwiftUI

struct WorkspaceView: View {
    @Binding var sourceCode: String
    @Binding var isRendering: Bool
    @Binding var renderedVideoURL: URL?
    @State private var sidebarOpen = true
    @State private var hSplit: CGFloat = 0.5   // editor↔preview
    @State private var vSplit: CGFloat = 0.7   // top↔terminal
    @State private var compactPane: CompactPane = .editor
    @State private var compactSheet: CompactSheet? = nil

    /// On iPhone the three-pane horizontal layout is cramped to the
    /// point of unusable. Switch to a tab-style picker so each pane
    /// gets the full width. Sidebar / controls move into a sheet.
    @Environment(\.horizontalSizeClass) private var hSizeClass

    enum CompactPane: String, CaseIterable, Identifiable {
        case editor, preview, terminal
        var id: String { rawValue }
        var label: String {
            switch self {
            case .editor:   return "Editor"
            case .preview:  return "Preview"
            case .terminal: return "Terminal"
            }
        }
        var icon: String {
            switch self {
            case .editor:   return "chevron.left.forwardslash.chevron.right"
            case .preview:  return "play.rectangle"
            case .terminal: return "terminal"
            }
        }
    }
    enum CompactSheet: String, Identifiable {
        case controls
        var id: String { rawValue }
    }

    var body: some View {
        if hSizeClass == .compact {
            compactBody
        } else {
            regularBody
        }
    }

    // MARK: regular (iPad)

    private var regularBody: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                VStack(spacing: 0) {
                    HStack(spacing: 0) {
                        EditorPane(source: $sourceCode)
                            .frame(width: max(220, geo.size.width * hSplit - (sidebarOpen ? 280 : 0) * 0.5))
                        Divider().background(Theme.borderSubtle)
                        PreviewPane(videoURL: $renderedVideoURL)
                    }
                    .frame(height: max(180, geo.size.height * vSplit))

                    Rectangle()
                        .fill(Theme.borderSubtle)
                        .frame(height: 4)
                        .overlay(Rectangle().fill(Theme.accentPrimary.opacity(0.3)).frame(width: 32, height: 2))
                        .gesture(
                            DragGesture()
                                .onChanged { v in
                                    let new = vSplit + v.translation.height / geo.size.height
                                    vSplit = min(max(new, 0.25), 0.85)
                                }
                        )

                    TerminalPane()
                }
                .frame(maxWidth: .infinity)

                if sidebarOpen {
                    ControlsSidebar(isOpen: $sidebarOpen)
                        .frame(width: 280)
                        .transition(.move(edge: .trailing))
                }
            }
            .overlay(alignment: .trailing) {
                if !sidebarOpen {
                    Button {
                        withAnimation { sidebarOpen = true }
                    } label: {
                        Image(systemName: "slider.horizontal.3")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 36, height: 36)
                            .background(Circle().fill(Theme.signatureGradient))
                            .shadow(color: Theme.glowPrimary, radius: 8)
                    }
                    .buttonStyle(.plain)
                    .padding(.trailing, 12)
                }
            }
        }
        .background(Theme.bgPrimary)
        .onReceive(NotificationCenter.default.publisher(for: .menuViewToggleSidebar))
            { _ in withAnimation { sidebarOpen.toggle() } }
    }

    // MARK: compact (iPhone)

    private var compactBody: some View {
        VStack(spacing: 0) {
            // Pane selector — segmented picker. Three panes get the
            // full screen one at a time; the user swipes the picker
            // or taps to switch.
            HStack(spacing: 6) {
                ForEach(CompactPane.allCases) { pane in
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) { compactPane = pane }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: pane.icon).font(.system(size: 11))
                            Text(pane.label).font(.system(size: 12, weight: .medium))
                        }
                        .foregroundStyle(compactPane == pane ? .white : Theme.textSecondary)
                        .padding(.horizontal, 10).padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 7)
                                .fill(compactPane == pane
                                      ? AnyShapeStyle(Theme.signatureGradient)
                                      : AnyShapeStyle(Theme.bgTertiary))
                        )
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
                // Render-controls drawer button.
                Button {
                    compactSheet = .controls
                } label: {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 32, height: 32)
                        .background(Circle().fill(Theme.signatureGradient))
                }
                .buttonStyle(.plain)
                .help("Render controls")
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Theme.bgSecondary)
            .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1), alignment: .bottom)

            // Selected pane fills the rest of the screen.
            ZStack {
                switch compactPane {
                case .editor:   EditorPane(source: $sourceCode)
                case .preview:  PreviewPane(videoURL: $renderedVideoURL)
                case .terminal: TerminalPane()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Theme.bgPrimary)
        .sheet(item: $compactSheet) { _ in
            // Sidebar repurposed as a sheet on compact. The sidebar's
            // `isOpen` controls the visibility on iPad — on iPhone we
            // bind a dummy that closes the sheet instead.
            ControlsSidebar(isOpen: Binding(
                get: { compactSheet != nil },
                set: { if !$0 { compactSheet = nil } }
            ))
            .presentationDetents([.medium, .large])
        }
        .onReceive(NotificationCenter.default.publisher(for: .menuViewToggleSidebar))
            { _ in compactSheet = (compactSheet == nil) ? .controls : nil }
    }
}
