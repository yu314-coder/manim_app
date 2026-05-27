// ResonancePrimitives.swift — Resonance design-system primitives.
//
// Small, decorative SwiftUI views that signal "scientific instrument"
// at zero animation cost:
//   - Reticle           concentric crosshair (corner marker / readout)
//   - CornerBrackets    four L-shaped marks framing any viewport
//   - ResTag            mono uppercase pill chip with optional dot
//   - PhaseLine         live oscilloscope trace (Canvas + TimelineView)
//   - ResonanceMark     brand glyph (phase wave inside circle)
//
// All purely procedural — no bundled assets, no network. They render
// crisply at every dynamic-type setting and on both iPhone and iPad.
//
// The PhaseLine in particular is the app's signature motif: a thin,
// breathing wave that runs across the top of every primary surface.
// It pulses faster when a render is active.

import SwiftUI

// MARK: - Reticle

/// Concentric crosshair, useful as a corner marker or readout glyph.
struct Reticle: View {
    var size: CGFloat = 18
    var color: Color = Theme.trace
    var opacity: Double = 0.55

    var body: some View {
        Canvas { ctx, _ in
            let s = size
            let c = CGPoint(x: s/2, y: s/2)
            let stroke = GraphicsContext.Shading.color(color.opacity(opacity))
            let lw: CGFloat = 0.7
            // Outer circle
            ctx.stroke(Path(ellipseIn: CGRect(x: 1, y: 1, width: s-2, height: s-2)),
                       with: stroke, lineWidth: lw)
            // Inner circle
            ctx.stroke(Path(ellipseIn: CGRect(x: s/2 - s/6, y: s/2 - s/6,
                                              width: s/3, height: s/3)),
                       with: stroke, lineWidth: lw)
            // Cross ticks
            for (a, b) in [
                (CGPoint(x: c.x, y: 0),       CGPoint(x: c.x, y: s/4)),
                (CGPoint(x: c.x, y: s*0.75),  CGPoint(x: c.x, y: s)),
                (CGPoint(x: 0,    y: c.y),    CGPoint(x: s/4, y: c.y)),
                (CGPoint(x: s*0.75, y: c.y), CGPoint(x: s,    y: c.y)),
            ] {
                var p = Path(); p.move(to: a); p.addLine(to: b)
                ctx.stroke(p, with: stroke, lineWidth: lw)
            }
            // Center dot
            ctx.fill(Path(ellipseIn: CGRect(x: c.x-1, y: c.y-1, width: 2, height: 2)),
                     with: stroke)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

// MARK: - Corner brackets

/// Four L-shaped corner marks. Drop into a ZStack to frame any
/// viewport like an instrument cutout.
struct CornerBrackets: View {
    var inset: CGFloat = 8
    var length: CGFloat = 14
    var color: Color = Theme.ion
    var opacity: Double = 0.4
    var lineWidth: CGFloat = 1

    var body: some View {
        GeometryReader { geo in
            ZStack {
                bracket(at: .topLeading,    in: geo.size)
                bracket(at: .topTrailing,   in: geo.size)
                bracket(at: .bottomLeading, in: geo.size)
                bracket(at: .bottomTrailing,in: geo.size)
            }
            .allowsHitTesting(false)
        }
        .accessibilityHidden(true)
    }

    private func bracket(at corner: UnitPoint, in size: CGSize) -> some View {
        let x: CGFloat = (corner == .topLeading || corner == .bottomLeading)
            ? inset : size.width - inset - length
        let y: CGFloat = (corner == .topLeading || corner == .topTrailing)
            ? inset : size.height - inset - length
        // Two strokes per corner — horizontal arm + vertical arm
        let horizontal = Path { p in
            p.move(to: CGPoint(x: 0, y: 0))
            p.addLine(to: CGPoint(x: length, y: 0))
        }
        let vertical = Path { p in
            p.move(to: CGPoint(x: 0, y: 0))
            p.addLine(to: CGPoint(x: 0, y: length))
        }
        // Position so the L points into the corner
        let hOffsetY: CGFloat = (corner == .topLeading || corner == .topTrailing) ? 0 : length
        let vOffsetX: CGFloat = (corner == .topLeading || corner == .bottomLeading) ? 0 : length
        return ZStack(alignment: .topLeading) {
            horizontal.stroke(color.opacity(opacity), lineWidth: lineWidth)
                .offset(y: hOffsetY)
            vertical.stroke(color.opacity(opacity), lineWidth: lineWidth)
                .offset(x: vOffsetX)
        }
        .frame(width: length, height: length)
        .offset(x: x, y: y)
    }
}

// MARK: - Tag chip

/// Uppercase mono pill: status / metadata. Optional glowing dot.
struct ResTag: View {
    let text: String
    var color: Color = Theme.trace
    var showDot: Bool = true

    var body: some View {
        HStack(spacing: 6) {
            if showDot {
                Circle()
                    .fill(color)
                    .frame(width: 5, height: 5)
                    .shadow(color: color.opacity(0.9), radius: 3)
            }
            Text(text)
                .font(.resMono(10, weight: .medium))
                .tracking(1.4)
                .foregroundStyle(Theme.ion)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(
            Capsule()
                .fill(Theme.trace.opacity(0.06))
                .overlay(Capsule().stroke(Theme.hairline, lineWidth: 1))
        )
    }
}

// MARK: - Phase line
//
// A breathing oscilloscope trace. The signature motif. Driven by
// TimelineView(.animation) so SwiftUI handles the redraw cadence;
// CPU/GPU cost is tiny (a single Path stroke per frame).

struct PhaseLine: View {
    var amplitude: CGFloat = 10
    var frequency: CGFloat = 0.018
    var speed: Double = 0.6
    var seed: Double = 0
    var color: Color = Theme.trace
    var showTicks: Bool = true
    var glow: Bool = true

    var body: some View {
        TimelineView(.animation) { timeline in
            let t = timeline.date.timeIntervalSinceReferenceDate * speed + seed
            Canvas { ctx, size in
                draw(ctx: ctx, size: size, t: t)
            }
        }
        .accessibilityHidden(true)
    }

    private func draw(ctx: GraphicsContext, size: CGSize, t: Double) {
        let w = size.width, h = size.height, mid = h / 2
        // Calibration ticks along the bottom
        if showTicks {
            let tickColor = GraphicsContext.Shading.color(Theme.ion.opacity(0.10))
            var x: CGFloat = 0
            while x <= w {
                let major = x.truncatingRemainder(dividingBy: 64) == 0
                var p = Path()
                p.move(to: CGPoint(x: x + 0.5, y: h - 4))
                p.addLine(to: CGPoint(x: x + 0.5, y: h - (major ? 12 : 8)))
                ctx.stroke(p, with: tickColor, lineWidth: 1)
                x += 16
            }
        }
        // The trace: sum of two sines for organic feel
        var path = Path()
        let f = Double(frequency)
        var first = true
        var x: CGFloat = 0
        while x <= w {
            let phase = Double(x) * f + t
            let y = Double(mid)
                + Double(amplitude) * (sin(phase) + 0.35 * sin(phase * 2.3 + seed))
            let pt = CGPoint(x: x, y: CGFloat(y))
            if first { path.move(to: pt); first = false } else { path.addLine(to: pt) }
            x += 1
        }
        if glow {
            // Soft underlay
            ctx.stroke(path,
                       with: .color(color.opacity(0.35)),
                       style: StrokeStyle(lineWidth: 4, lineCap: .round))
        }
        ctx.stroke(path, with: .color(color),
                   style: StrokeStyle(lineWidth: 1.4, lineCap: .round))
        // Moving cursor — a small bead at ~78% of the width
        let cx = w * 0.78 + sin(t * 0.3) * w * 0.1
        let phaseAtCx = Double(cx) * f + t
        let cy = Double(mid) + Double(amplitude)
            * (sin(phaseAtCx) + 0.35 * sin(phaseAtCx * 2.3 + seed))
        ctx.fill(Path(ellipseIn: CGRect(x: cx - 2.5, y: cy - 2.5, width: 5, height: 5)),
                 with: .color(color))
        var vline = Path()
        vline.move(to: CGPoint(x: cx, y: 4))
        vline.addLine(to: CGPoint(x: cx, y: h - 4))
        ctx.stroke(vline, with: .color(Theme.trace.opacity(0.25)), lineWidth: 1)
    }
}

// MARK: - Resonance brand mark

/// Phase wave inscribed in a circle, rendered in the signature
/// indigo→violet→pink gradient. Used as the side-rail logo and on
/// the render-takeover screen.
struct ResonanceMark: View {
    var size: CGFloat = 40

    var body: some View {
        Canvas { ctx, _ in
            let s = size
            let c = CGPoint(x: s/2, y: s/2)
            let gradient = Gradient(colors: [Theme.indigo, Theme.violet, Theme.pink])
            let shading = GraphicsContext.Shading.linearGradient(
                gradient,
                startPoint: .zero, endPoint: CGPoint(x: s, y: s)
            )
            // Outer circle
            ctx.stroke(Path(ellipseIn: CGRect(x: 1, y: 1, width: s-2, height: s-2)),
                       with: shading, lineWidth: 1.4)
            // The wave
            var wave = Path()
            wave.move(to: CGPoint(x: s * 0.12, y: c.y))
            wave.addCurve(to: CGPoint(x: s * 0.40, y: c.y),
                          control1: CGPoint(x: s * 0.22, y: c.y - s * 0.20),
                          control2: CGPoint(x: s * 0.30, y: c.y + s * 0.20))
            wave.addCurve(to: CGPoint(x: s * 0.65, y: c.y),
                          control1: CGPoint(x: s * 0.50, y: c.y - s * 0.20),
                          control2: CGPoint(x: s * 0.55, y: c.y + s * 0.20))
            wave.addCurve(to: CGPoint(x: s * 0.88, y: c.y),
                          control1: CGPoint(x: s * 0.75, y: c.y - s * 0.20),
                          control2: CGPoint(x: s * 0.78, y: c.y + s * 0.20))
            ctx.stroke(wave, with: shading,
                       style: StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
            // Center pip
            ctx.fill(Path(ellipseIn: CGRect(x: c.x - 1.4, y: c.y - 1.4, width: 2.8, height: 2.8)),
                     with: .color(Theme.pink))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
