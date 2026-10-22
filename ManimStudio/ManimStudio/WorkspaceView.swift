// WorkspaceView.swift — workspace tab: editor (left), preview (right),
// terminal (bottom), controls sidebar (right floating).
import SwiftUI

struct WorkspaceView: View {
    @ObservedObject private var theme = ThemeManager.shared   // accent → live retint
    @Binding var sourceCode: String
    @Binding var isRendering: Bool
    @Binding var renderedVideoURL: URL?
    // Persisted via @AppStorage so the iPad layout you set (terminal split,
    // sidebar open/closed) sticks across launches. (@AppStorage has no
    // CGFloat overload, so the splits are stored as Double and bridged.)
    @AppStorage("manim_ws_sidebar_open") private var sidebarOpen = true
    @AppStorage("manim_ws_hsplit") private var hSplit: Double = 0.5   // editor↔preview
    @AppStorage("manim_ws_vsplit") private var vSplit: Double = 0.7   // top↔terminal
    @State private var compactPane: CompactPane = .editor   // open on the code editor
    @State private var compactSheet: CompactSheet? = nil
    /// Top edge (global y) of the code editor's key bar while it floats
    /// over the on-screen keyboard, 0 when hidden; and where the workspace
    /// itself ends. Their overlap is how far the panes stop short, so
    /// nothing hides under the bar on any device.
    @State private var keyBarTop: CGFloat = 0
    @State private var workspaceBottom: CGFloat = 0
    private var keyBarHeight: CGFloat {
        keyBarTop > 0 ? max(0, workspaceBottom - keyBarTop) : 0
    }

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
            case .terminal: return "Render Log"
            }
        }
        var icon: String {
            switch self {
            case .editor:   return "chevron.left.forwardslash.chevron.right"
            case .preview:  return "play.rectangle"
            case .terminal: return "doc.text.magnifyingglass"
            }
        }
    }
    enum CompactSheet: String, Identifiable {
        case controls
        var id: String { rawValue }
    }

    var body: some View {
        Group {
            if hSizeClass == .compact {
                compactBody
            } else {
                regularBody
            }
        }
        // While the key bar is up the workspace reaches past the top of the
        // keyboard's frame, down to the bar itself: the frame can start well
        // above the keys (the iPhone Duo leaves a band there), and the bar
        // sits on the keys.
        .ignoresSafeArea(keyBarTop > 0 ? .keyboard : [], edges: .bottom)
        .onGeometryChange(for: CGFloat.self) { $0.frame(in: .global).maxY } action: {
            workspaceBottom = $0
        }
        .onReceive(NotificationCenter.default.publisher(for: .editorKeyBarHeight)) { note in
            keyBarTop = note.userInfo?["top"] as? CGFloat ?? 0
        }
    }

    // MARK: regular (iPad)

    private var regularBody: some View {
        GeometryReader { geo in
            // Typing in the editor: the key bar covers the bottom of what
            // the keyboard leaves, so everything stops above it, and the
            // editor takes most of that short space (the terminal keeps a
            // few lines; SwiftTerm can't be resized to nothing).
            let avail = geo.size.height - keyBarHeight
            let topHeight = keyBarHeight > 0
                ? max(120, avail - 4 - 96)
                : max(180, geo.size.height * CGFloat(vSplit))
            HStack(alignment: .top, spacing: 0) {
                VStack(spacing: 0) {
                    HStack(spacing: 0) {
                        EditorPane(source: $sourceCode)
                            .frame(width: max(220, geo.size.width * CGFloat(hSplit) - (sidebarOpen ? 280 : 0) * 0.5))
                        Divider().background(Theme.borderSubtle)
                        PreviewPane(videoURL: $renderedVideoURL)
                    }
                    .frame(height: topHeight)

                    Rectangle()
                        .fill(Theme.borderSubtle)
                        .frame(height: 4)
                        .overlay(Rectangle().fill(Theme.accentPrimary.opacity(0.3)).frame(width: 32, height: 2))
                        .gesture(
                            DragGesture()
                                .onChanged { v in
                                    let new = vSplit + Double(v.translation.height / geo.size.height)
                                    vSplit = min(max(new, 0.25), 0.85)
                                }
                        )

                    TerminalPane()
                }
                .frame(maxWidth: .infinity)
                .padding(.bottom, keyBarHeight)

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
                        guard compactPane != pane else { return }
                        Haptics.selection()
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
            .padding(.bottom, keyBarHeight)
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
