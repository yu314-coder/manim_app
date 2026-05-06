// Theme.swift — color palette + reusable styling helpers for the
// native macOS UI. Mirrors the dark aesthetic of the desktop app
// without sharing any code with the iOS target's Theme.swift.
import SwiftUI

enum Theme {
    // Backgrounds — three depth tiers.
    static let bgPrimary   = Color(red: 0.055, green: 0.055, blue: 0.075)
    static let bgSecondary = Color(red: 0.085, green: 0.085, blue: 0.110)
    static let bgTertiary  = Color(red: 0.130, green: 0.130, blue: 0.160)
    static let bgSurface   = Color(red: 0.180, green: 0.180, blue: 0.220)

    // Text.
    static let textPrimary   = Color(red: 0.93, green: 0.93, blue: 0.95)
    static let textSecondary = Color(red: 0.68, green: 0.68, blue: 0.74)
    static let textDim       = Color(red: 0.45, green: 0.45, blue: 0.50)

    // Borders.
    static let borderSubtle = Color.white.opacity(0.08)
    static let borderActive = Color.white.opacity(0.18)

    // Accents.
    static let accentPrimary = Color(red: 0.39, green: 0.40, blue: 0.95)
    static let accentSecond  = Color(red: 0.66, green: 0.34, blue: 0.97)

    // Status.
    static let success = Color(red: 0.19, green: 0.78, blue: 0.34)
    static let warning = Color(red: 0.96, green: 0.62, blue: 0.04)
    static let error   = Color(red: 0.96, green: 0.27, blue: 0.27)
    static let info    = Color(red: 0.34, green: 0.66, blue: 0.97)

    // Gradient used for primary actions (Render button etc.).
    static let signatureGradient = LinearGradient(
        colors: [accentPrimary, accentSecond],
        startPoint: .topLeading,
        endPoint: .bottomTrailing)

    // Soft glow under elevated/active controls.
    static let glowPrimary = Color(red: 0.39, green: 0.40, blue: 0.95)
        .opacity(0.45)
}
