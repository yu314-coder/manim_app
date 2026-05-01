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

    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                VStack(spacing: 0) {
                    // TOP — editor + preview
                    HStack(spacing: 0) {
                        EditorPane(source: $sourceCode)
                            .frame(width: max(220, geo.size.width * hSplit - (sidebarOpen ? 280 : 0) * 0.5))
                        Divider().background(Theme.borderSubtle)
                        PreviewPane(videoURL: $renderedVideoURL)
                    }
                    .frame(height: max(180, geo.size.height * vSplit))

                    // Vertical splitter handle
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

                    // BOTTOM — real SwiftTerm terminal driven by PTYBridge.
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
    }
}
