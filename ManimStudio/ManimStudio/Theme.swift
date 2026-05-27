// Theme.swift — the Resonance design system tokens
//
// Resonance is a scientific-instrument aesthetic for mathematical
// animation: deep "void" backgrounds, a brand thread of
// indigo→violet→pink, an oscilloscope cyan "trace" colour for live
// signal, and a typographic stack built around geometric display +
// neutral UI + tabular mono.
//
// Backwards compatibility: every legacy token (bgPrimary, accentPrimary,
// signatureGradient, …) still resolves to a Resonance value so the rest
// of the app compiles unchanged.

import SwiftUI

enum Theme {
    // ─────────────────────────────────────────────────────────
    // Resonance surfaces — deeper than the previous palette so
    // the brand colours and the "trace" cyan read as live signals
    // against true void rather than just "dark gray UI".
    // ─────────────────────────────────────────────────────────
    static let void     = Color(hex: 0x06060C)
    static let deep     = Color(hex: 0x0B0C18)
    static let surface  = Color(hex: 0x11132A)
    static let raised   = Color(hex: 0x181B3A)
    static let bezel    = Color(hex: 0x222652)          // instrument bezel
    static let hairline    = Color(red: 120/255, green: 130/255, blue: 220/255, opacity: 0.10)
    static let hairBright  = Color(red: 190/255, green: 200/255, blue: 255/255, opacity: 0.20)

    // Brand thread (unchanged)
    static let indigo   = Color(hex: 0x6366F1)
    static let violet   = Color(hex: 0xA855F7)
    static let pink     = Color(hex: 0xEC4899)

    // Live signal — oscilloscope trace + semantic
    static let trace    = Color(hex: 0x7DF9FF)
    static let traceDim = Color(hex: 0x3DD9E5)
    static let amber    = Color(hex: 0xFBBF24)
    static let green    = Color(hex: 0x34D399)
    static let red      = Color(hex: 0xF87171)

    // Text scale (cool-leaning so it reads as instrument readout, not
    // warm UI body)
    static let phosphor = Color(hex: 0xE6E8FF)  // primary
    static let ion      = Color(hex: 0xA5A9D6)  // secondary
    static let dim      = Color(hex: 0x6B6F94)  // tertiary
    static let faint    = Color(hex: 0x3A3D62)  // quaternary

    // ─────────────────────────────────────────────────────────
    // Legacy aliases — every existing call-site keeps working.
    // Repointed to the Resonance values so the new look propagates
    // through the app without per-file edits.
    // ─────────────────────────────────────────────────────────
    static let bgPrimary    = void
    static let bgSecondary  = deep
    static let bgTertiary   = surface
    static let bgSurface    = raised
    static let bgCard       = surface.opacity(0.85)

    static let textPrimary   = phosphor
    static let textSecondary = ion
    static let textDim       = dim

    static let accentPrimary   = indigo
    static let accentSecondary = violet
    static let accentTertiary  = pink
    static let success         = green
    static let warning         = amber
    static let error           = red
    static let info            = trace
    static let cyan            = trace

    // Signature gradient (indigo → violet → pink, 135°)
    static let signatureGradient = LinearGradient(
        colors: [indigo, violet, pink],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )
    static let signatureGradientSoft = LinearGradient(
        colors: [indigo.opacity(0.6), violet.opacity(0.55), pink.opacity(0.5)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )

    static let borderSubtle = hairline
    static let borderActive = hairBright
    static let glowPrimary  = violet.opacity(0.45)

    // Legacy font fields (kept so older call-sites still resolve).
    static let uiFont   = Font.system(.body,  design: .default)
    static let monoFont = Font.system(.body,  design: .monospaced)
}

// ─────────────────────────────────────────────────────────────
// Typography
//
// Resonance uses three families:
//   Display — Space Grotesk          (hero titles, scene names)
//   UI      — Geist Sans             (body, controls)
//   Mono    — Geist Mono             (readouts, formulas, code)
//
// To upgrade beyond the system fallback, drop the relevant .ttf /
// .otf files into the app's Resources folder and register them in
// Info.plist under the UIAppFonts array, e.g.:
//
//   <key>UIAppFonts</key>
//   <array>
//     <string>SpaceGrotesk-Regular.ttf</string>
//     <string>SpaceGrotesk-SemiBold.ttf</string>
//     <string>Geist-Regular.ttf</string>
//     <string>GeistMono-Regular.ttf</string>
//   </array>
//
// Until those files are present, the helpers below fall back to
// SF Pro Rounded (display), SF Pro (UI), SF Mono (mono) — which
// matches the Resonance look closely enough that the differentiator
// is the layout + motion language, not the typeface.
// ─────────────────────────────────────────────────────────────
extension Font {
    /// Geometric display face for headings, scene titles, hero copy.
    static func resDisplay(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        if Self.isFontRegistered("SpaceGrotesk-SemiBold")
            || Self.isFontRegistered("Space Grotesk") {
            return .custom("Space Grotesk", size: size).weight(weight)
        }
        return .system(size: size, weight: weight, design: .rounded)
    }

    /// Neutral UI face for body, controls, settings.
    static func resUI(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        if Self.isFontRegistered("Geist-Regular") || Self.isFontRegistered("Geist") {
            return .custom("Geist", size: size).weight(weight)
        }
        return .system(size: size, weight: weight, design: .default)
    }

    /// Tabular mono for readouts, frame counters, formulas, code.
    static func resMono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        if Self.isFontRegistered("GeistMono-Regular") || Self.isFontRegistered("Geist Mono") {
            return .custom("Geist Mono", size: size).weight(weight)
        }
        return .system(size: size, weight: weight, design: .monospaced)
    }

    /// CoreText registration probe. Cheap; CT caches its font list.
    fileprivate static func isFontRegistered(_ name: String) -> Bool {
        #if canImport(UIKit)
        return UIFont(name: name, size: 12) != nil
        #else
        return false
        #endif
    }
}

#if canImport(UIKit)
import UIKit
#endif

// ─────────────────────────────────────────────────────────────
// Color hex helper (unchanged)
// ─────────────────────────────────────────────────────────────
extension Color {
    init(hex: UInt32, alpha: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >>  8) & 0xFF) / 255.0
        let b = Double( hex        & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}

// ─────────────────────────────────────────────────────────────
// Frosted glass card — `.glassCard()` (legacy modifier, kept)
// ─────────────────────────────────────────────────────────────
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
