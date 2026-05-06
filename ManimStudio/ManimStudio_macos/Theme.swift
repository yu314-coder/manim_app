// Theme.swift — high-tech color palette, gradient definitions,
// glassmorphic helpers, and reusable view modifiers for the
// native macOS UI.
//
// Visual language: deep navy + purple bg, indigo→violet→pink
// signature gradient, subtle glassmorphic surfaces, neon glow
// accents on active controls.
import SwiftUI
import AppKit

enum Theme {
    // ── Backgrounds — five depth tiers (deepest first).
    static let bgDeepest    = Color(red: 0.035, green: 0.040, blue: 0.060)
    static let bgPrimary    = Color(red: 0.055, green: 0.060, blue: 0.085)
    static let bgSecondary  = Color(red: 0.085, green: 0.090, blue: 0.120)
    static let bgTertiary   = Color(red: 0.130, green: 0.135, blue: 0.170)
    static let bgSurface    = Color(red: 0.180, green: 0.185, blue: 0.225)
    static let bgElevated   = Color(red: 0.220, green: 0.225, blue: 0.270)

    // ── Text.
    static let textPrimary   = Color(red: 0.95, green: 0.95, blue: 0.97)
    static let textSecondary = Color(red: 0.72, green: 0.72, blue: 0.78)
    static let textDim       = Color(red: 0.50, green: 0.50, blue: 0.55)
    static let textHint      = Color(red: 0.35, green: 0.35, blue: 0.40)

    // ── Borders.
    static let borderSubtle  = Color.white.opacity(0.06)
    static let borderActive  = Color.white.opacity(0.18)
    static let borderGlow    = Color(red: 0.55, green: 0.50, blue: 1.00).opacity(0.45)

    // ── Accents.
    static let indigo  = Color(red: 0.39, green: 0.42, blue: 0.97)
    static let violet  = Color(red: 0.66, green: 0.34, blue: 0.97)
    static let pink    = Color(red: 0.95, green: 0.34, blue: 0.71)
    static let cyan    = Color(red: 0.18, green: 0.78, blue: 0.94)
    static let teal    = Color(red: 0.10, green: 0.85, blue: 0.78)
    static let lime    = Color(red: 0.55, green: 0.92, blue: 0.32)
    static let amber   = Color(red: 0.99, green: 0.74, blue: 0.18)

    static let accentPrimary = indigo
    static let accentSecond  = violet

    // ── Status.
    static let success = Color(red: 0.20, green: 0.83, blue: 0.45)
    static let warning = Color(red: 0.97, green: 0.66, blue: 0.13)
    static let error   = Color(red: 0.97, green: 0.32, blue: 0.36)
    static let info    = Color(red: 0.30, green: 0.66, blue: 0.97)

    // ── Signature gradient — used for primary CTAs (Render),
    // header logo glow, focused-section underlines.
    static let signatureGradient = LinearGradient(
        colors: [indigo, violet, pink],
        startPoint: .topLeading,
        endPoint: .bottomTrailing)

    // Cool accent gradient used for status badges + section headers.
    static let coolGradient = LinearGradient(
        colors: [cyan, indigo],
        startPoint: .leading, endPoint: .trailing)

    // Soft glow under elevated controls.
    static let glowPrimary = indigo.opacity(0.45)
    static let glowAccent  = violet.opacity(0.35)
    static let glowSuccess = success.opacity(0.40)
}

// MARK: - high-tech surface modifiers

extension View {
    /// Glassmorphic card: translucent fill + thin border + soft inner
    /// highlight at the top.
    func glassCard(cornerRadius: CGFloat = 12) -> some View {
        self
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(Theme.bgSecondary.opacity(0.78))
                    .background(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .fill(.ultraThinMaterial)
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .strokeBorder(LinearGradient(
                        colors: [Color.white.opacity(0.10),
                                 Color.white.opacity(0.02)],
                        startPoint: .top, endPoint: .bottom),
                                  lineWidth: 1)
            )
    }

    /// Subtle inner-glow ring used for active/focused controls.
    func neonRing(_ color: Color = Theme.indigo,
                  radius: CGFloat = 10,
                  cornerRadius: CGFloat = 8) -> some View {
        self.overlay(
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(color, lineWidth: 1)
                .shadow(color: color.opacity(0.6), radius: radius)
        )
    }

    /// Apply the signature gradient as a fill on a foreground style.
    func signatureForeground() -> some View {
        self.foregroundStyle(Theme.signatureGradient)
    }
}

// MARK: - background materials

/// NSVisualEffectView wrapped for SwiftUI. Use as a translucent
/// underlayer (e.g. a window-background blur).
struct VisualEffectBackground: NSViewRepresentable {
    var material: NSVisualEffectView.Material = .underWindowBackground
    var blendingMode: NSVisualEffectView.BlendingMode = .behindWindow
    var emphasized: Bool = false

    func makeNSView(context: Context) -> NSVisualEffectView {
        let v = NSVisualEffectView()
        v.material = material
        v.blendingMode = blendingMode
        v.state = .active
        v.isEmphasized = emphasized
        return v
    }
    func updateNSView(_ v: NSVisualEffectView, context: Context) {
        v.material = material
        v.blendingMode = blendingMode
        v.isEmphasized = emphasized
    }
}

// MARK: - reusable bits

/// Animated glowing dot — used for "rendering / idle / error" status.
struct StatusDot: View {
    enum DotState { case idle, active, ok, error }
    let state: DotState

    @State private var pulse = false

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 8, height: 8)
            .shadow(color: color.opacity(0.7), radius: pulse ? 5 : 2)
            .scaleEffect(state == .active && pulse ? 1.18 : 1.0)
            .onAppear {
                if state == .active {
                    withAnimation(.easeInOut(duration: 0.85)
                                    .repeatForever(autoreverses: true)) {
                        pulse = true
                    }
                }
            }
    }

    private var color: Color {
        switch state {
        case .idle:   return Theme.textDim
        case .active: return Theme.indigo
        case .ok:     return Theme.success
        case .error:  return Theme.error
        }
    }
}

/// Section-header chip with a leading icon and uppercase tracking.
struct SectionHeader: View {
    let title: String
    var icon: String? = nil
    var body: some View {
        HStack(spacing: 6) {
            if let icon {
                Image(systemName: icon)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.indigo)
            }
            Text(title.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .tracking(1.2)
                .foregroundStyle(Theme.textSecondary)
        }
    }
}
