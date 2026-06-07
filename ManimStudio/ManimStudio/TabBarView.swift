// TabBarView.swift — pill-style tab strip (.tab-header / .tab-pill).
import SwiftUI

struct TabBarView: View {
    @ObservedObject private var theme = ThemeManager.shared   // accent → live retint
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
                        guard selection != tab else { return }
                        Haptics.selection()
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

// ─────────────────────────────────────────────────────────────
// BottomTabBar — native-feeling bottom navigation for iPhone (compact).
// Six evenly-spaced items (SF Symbol + label); the selected one gets the
// signature-gradient pill + glow. ContentView pins it to the bottom via
// .safeAreaInset, and its material bleeds under the home indicator.
// ─────────────────────────────────────────────────────────────
struct BottomTabBar: View {
    @ObservedObject private var theme = ThemeManager.shared   // accent → live retint
    @Binding var selection: AppTab

    var body: some View {
        HStack(spacing: 0) {
            ForEach(AppTab.allCases) { tab in
                let active = selection == tab
                Button {
                    guard selection != tab else { return }
                    Haptics.selection()
                    withAnimation(.spring(response: 0.34, dampingFraction: 0.8)) {
                        selection = tab
                    }
                } label: {
                    VStack(spacing: 3) {
                        ZStack {
                            if active {
                                RoundedRectangle(cornerRadius: 9, style: .continuous)
                                    .fill(Theme.signatureGradient)
                                    .frame(width: 46, height: 30)
                                    .shadow(color: Theme.glowPrimary, radius: 7, y: 2)
                            }
                            Image(systemName: tab.icon)
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundStyle(active ? .white : Theme.textDim)
                                .symbolEffect(.bounce, value: active)
                        }
                        .frame(height: 30)
                        Text(tab.title)
                            .font(.system(size: 9, weight: active ? .semibold : .medium))
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                            .foregroundStyle(active ? Theme.textPrimary : Theme.textDim)
                    }
                    .frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 7)
        .padding(.horizontal, 4)
        .padding(.bottom, 3)
        .frame(maxWidth: .infinity)
        .background(
            Theme.bgSecondary
                .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                         alignment: .top)
                .ignoresSafeArea(edges: .bottom)
        )
    }
}
