// TabBarView.swift — pill-style tab strip (.tab-header / .tab-pill).
import SwiftUI

struct TabBarView: View {
    @Binding var selection: AppTab
    @Environment(\.horizontalSizeClass) private var hSizeClass

    var body: some View {
        // On iPhone the five labeled pills overflow the screen width.
        // Wrap them in a horizontal ScrollView so they stay one line
        // and the user can scroll to reach the rightmost ones, and
        // tighten paddings + drop the trailing Spacer that was pushing
        // overflow.
        let compact = hSizeClass == .compact
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(AppTab.allCases) { tab in
                    Button {
                        withAnimation(.easeInOut(duration: 0.18)) { selection = tab }
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: tab.icon)
                                .font(.system(size: 11, weight: .semibold))
                            // On compact, hide the label for non-selected
                            // pills — selected tab keeps its title so
                            // the user always sees where they are.
                            if !compact || selection == tab {
                                Text(tab.title).font(.system(size: 12, weight: .medium))
                            }
                        }
                        .padding(.horizontal, compact ? 10 : 14)
                        .padding(.vertical, 7)
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
                        .shadow(color: selection == tab ? Theme.glowPrimary : .clear,
                                radius: 6, y: 1)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, compact ? 10 : 14)
            .padding(.vertical, compact ? 6 : 10)
        }
        .background(Theme.bgPrimary)
    }
}
