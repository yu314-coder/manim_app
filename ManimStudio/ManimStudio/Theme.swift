// Theme.swift — color tokens lifted from manim_app/web/styles.css :root vars
// Goal: 1:1 match with the desktop app's dark glassmorphism palette.

import SwiftUI

enum Theme {
    // Backgrounds
    static let bgPrimary    = Color(hex: 0x0A0A0F)
    static let bgSecondary  = Color(hex: 0x12121A)
    static let bgTertiary   = Color(hex: 0x1A1A28)
    static let bgSurface    = Color(hex: 0x222235)
    static let bgCard       = Color(hex: 0x1A1A28).opacity(0.8)

    // Text
    static let textPrimary   = Color(hex: 0xF0F0F5)
    static let textSecondary = Color(hex: 0xA8A8B8)
    static let textDim       = Color(hex: 0x6B6B80)

    // Accents
    static let accentPrimary   = Color(hex: 0x6366F1) // indigo
    static let accentSecondary = Color(hex: 0xA855F7) // violet
    static let accentTertiary  = Color(hex: 0xEC4899) // pink
    static let success         = Color(hex: 0x22C55E)
    static let warning         = Color(hex: 0xF59E0B)
    static let error           = Color(hex: 0xEF4444)
    static let info            = Color(hex: 0x0EA5E9)
    static let cyan            = Color(hex: 0x06B6D4)

    // Signature gradient (header buttons, primary accents)
    static let signatureGradient = LinearGradient(
        colors: [Color(hex: 0x6366F1), Color(hex: 0x8B5CF6), Color(hex: 0xA855F7)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )

    static let borderSubtle = Color(hex: 0x6366F1).opacity(0.15)
    static let borderActive = Color(hex: 0x6366F1).opacity(0.40)
    static let glowPrimary  = Color(hex: 0x6366F1).opacity(0.35)

    // Fonts
    static let uiFont   = Font.system(.body,  design: .default)
    static let monoFont = Font.system(.body,  design: .monospaced)
}

extension Color {
    init(hex: UInt32, alpha: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >>  8) & 0xFF) / 255.0
        let b = Double( hex        & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}

// Frosted glass card — `.glassCard()` modifier
struct GlassCard: ViewModifier {
    var padding: CGFloat = 12
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Theme.bgCard)
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Theme.borderSubtle, lineWidth: 1)
            )
    }
}

extension View {
    func glassCard(padding: CGFloat = 12) -> some View {
        modifier(GlassCard(padding: padding))
    }
}
