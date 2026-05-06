// TabBarView.swift — pill-style tab strip below the header.
// Mirrors the iOS TabBarView design: rounded gradient pills for
// the active tab, hover/idle state for the rest, scrollable on
// narrow windows so the strip never clips.
import SwiftUI

struct TabBarView: View {
    @Binding var selection: SidebarSection

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(SidebarSection.allCases) { section in
                    pill(section)
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 8)
        }
        .background(
            ZStack {
                Theme.bgPrimary.opacity(0.88)
                VisualEffectBackground(material: .underWindowBackground)
                    .opacity(0.45)
            }
            .overlay(
                Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                alignment: .bottom)
        )
    }

    @ViewBuilder
    private func pill(_ section: SidebarSection) -> some View {
        let active = selection == section
        Button {
            withAnimation(.easeInOut(duration: 0.15)) { selection = section }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: section.icon)
                    .font(.system(size: 11, weight: .semibold))
                Text(section.label)
                    .font(.system(size: 12, weight: .medium))
            }
            .padding(.horizontal, 14).padding(.vertical, 6)
            .foregroundStyle(active ? .white : Theme.textSecondary)
            .background(
                Capsule().fill(active
                               ? AnyShapeStyle(Theme.signatureGradient)
                               : AnyShapeStyle(Theme.bgTertiary)))
            .overlay(Capsule().stroke(
                active ? Color.clear : Theme.borderSubtle, lineWidth: 1))
            .shadow(color: active ? Theme.glowPrimary : .clear,
                    radius: 6, y: 1)
        }
        .buttonStyle(.plain)
    }
}
