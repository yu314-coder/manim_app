// TabBarView.swift — pill-style tab strip (.tab-header / .tab-pill).
import SwiftUI

struct TabBarView: View {
    @Binding var selection: AppTab

    var body: some View {
        HStack(spacing: 6) {
            ForEach(AppTab.allCases) { tab in
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) { selection = tab }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: tab.icon).font(.system(size: 11, weight: .semibold))
                        Text(tab.title).font(.system(size: 12, weight: .medium))
                    }
                    .padding(.horizontal, 14).padding(.vertical, 7)
                    .foregroundStyle(selection == tab ? .white : Theme.textSecondary)
                    .background(
                        Capsule().fill(
                            selection == tab
                            ? AnyShapeStyle(Theme.signatureGradient)
                            : AnyShapeStyle(Theme.bgTertiary)
                        )
                    )
                    .overlay(
                        Capsule().stroke(
                            selection == tab ? Color.clear : Theme.borderSubtle,
                            lineWidth: 1)
                    )
                    .shadow(color: selection == tab ? Theme.glowPrimary : .clear, radius: 6, y: 1)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(Theme.bgPrimary)
    }
}
