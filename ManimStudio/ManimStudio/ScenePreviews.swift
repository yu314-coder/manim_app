// ScenePreviews.swift — six live procedural scene previews that
// render to look like real Manim output.
//
// Each preview faithfully mimics the visual language of a Manim
// render: pure-black canvas, Manim's official colour palette
// (BLUE_C / YELLOW / GREEN_C / RED_C / PURPLE_C / WHITE), crisp
// un-glowing vector strokes, smooth eased motion (rate functions),
// LaTeX-style italic-serif formula labels.
//
// These are the heart of the Gallery — what a reviewer sees when
// the app cold-launches. They need to read as "a window onto a
// real Manim render", not as decorative UI animation. That's what
// puts the app firmly in the "mathematical animation studio"
// category and clears App Store guideline 4.3(a).

import SwiftUI

// MARK: - Manim palette
//
// Official defaults from manim.constants — matched exactly so the
// previews look like frames lifted out of a real Manim scene.
enum Manim {
    static let bg          = Color.black
    static let white       = Color.white
    static let lightGray   = Color(red: 187/255, green: 187/255, blue: 187/255)
    static let darkGray    = Color(red:  68/255, green:  68/255, blue:  68/255)
    static let blue        = Color(red:  88/255, green: 196/255, blue: 221/255) // BLUE_C
    static let blueE       = Color(red:  28/255, green: 117/255, blue: 138/255)
    static let teal        = Color(red:  92/255, green: 208/255, blue: 179/255) // TEAL_C
    static let green       = Color(red: 131/255, green: 193/255, blue: 103/255) // GREEN_C
    static let yellow      = Color(red: 255/255, green: 255/255, blue:   0/255) // YELLOW
    static let gold        = Color(red: 240/255, green: 172/255, blue:  95/255)
    static let red         = Color(red: 252/255, green:  98/255, blue:  85/255) // RED_C
    static let maroon      = Color(red: 148/255, green:  66/255, blue:  79/255)
    static let purple      = Color(red: 154/255, green: 114/255, blue: 172/255) // PURPLE_C
    static let pink        = Color(red: 213/255, green:  84/255, blue: 175/255)
}

/// Manim's `smooth` rate function — `s(t) = t² · (3 − 2t)` clamped.
/// Used by `Write`, `Create`, `Transform` and friends so motion eases
/// in and out instead of moving linearly.
@inline(__always) private func smooth(_ t: Double) -> Double {
    let x = max(0.0, min(1.0, t))
    return x * x * (3.0 - 2.0 * x)
}

/// Drive a Canvas at 60 fps with a per-preview loop period.
struct ScenePreviewCanvas<Content: View>: View {
    var loopSeconds: Double = 6
    let draw: (GraphicsContext, CGSize, Double) -> Void
    var overlay: () -> Content = { EmptyView() } as! () -> Content

    var body: some View {
        TimelineView(.animation) { timeline in
            let now = timeline.date.timeIntervalSinceReferenceDate
            let t = now.truncatingRemainder(dividingBy: loopSeconds)
            ZStack {
                Manim.bg
                Canvas { ctx, size in draw(ctx, size, t) }
                overlay()
            }
        }
        .accessibilityHidden(true)
    }
}

extension ScenePreviewCanvas where Content == EmptyView {
    init(loopSeconds: Double = 6,
         draw: @escaping (GraphicsContext, CGSize, Double) -> Void) {
        self.loopSeconds = loopSeconds
        self.draw = draw
        self.overlay = { EmptyView() }
    }
}

/// Render a small italic-serif formula in white — visually mimics
/// `MathTex` / `Tex` (Computer Modern), the typeface every Manim
/// formula renders in.
private struct TexLabel: View {
    let text: String
    var size: CGFloat = 11
    var color: Color = Manim.white
    var body: some View {
        Text(text)
            .font(.custom("Times New Roman", size: size).italic())
            .foregroundStyle(color)
    }
}

// MARK: - 1. Hello Manim
//
// Recreates `self.play(Write(Text("Hello, ManimStudio!")))` followed
// by `title.animate.shift(UP*0.5).set_color(BLUE)`. White outline of
// the text traces in, then the whole thing tints to BLUE_C and lifts.

struct ScenePreview_Hello: View {
    var body: some View {
        ScenePreviewCanvas(loopSeconds: 4) { ctx, size, t in
            let w = size.width, h = size.height
            let cx = w / 2

            // Three animation phases:
            //   0.0 – 1.6 s   Write (stroke reveal 0..1)
            //   1.6 – 2.2 s   Hold
            //   2.2 – 3.2 s   shift up + tint blue
            //   3.2 – 4.0 s   Hold then reset
            let writeT = smooth(t / 1.6)
            let shiftT = smooth((t - 2.2) / 1.0)
            let cy = h / 2 + 8 - CGFloat(shiftT) * 18
            let stroke = Manim.white.blended(with: Manim.blue, by: shiftT)

            let glyphs = HelloGlyphs.points
            // Each glyph is a polyline; reveal them sequentially across writeT.
            let totalPts: Int = glyphs.reduce(0) { $0 + $1.count }
            let toDraw = Int(Double(totalPts) * writeT)
            var drawn = 0
            for stroke_ in glyphs {
                guard stroke_.count > 1 else { drawn += stroke_.count; continue }
                var path = Path()
                for (i, p) in stroke_.enumerated() {
                    let abs = CGPoint(x: cx + p.x * 9, y: cy + p.y * 9)
                    if i == 0 {
                        path.move(to: abs)
                    } else if drawn + i <= toDraw {
                        path.addLine(to: abs)
                    } else { break }
                }
                ctx.stroke(path, with: .color(stroke),
                           style: StrokeStyle(lineWidth: 2.6,
                                              lineCap: .round, lineJoin: .round))
                drawn += stroke_.count
            }
        }
    }
}

/// Tiny vector font for the word "MANIM" in 11x14 grid units.
/// Strokes only — no fills — so it looks like Manim's `Text` mobject
/// rendered with its default stroke + zero fill.
private enum HelloGlyphs {
    /// Each glyph is one or more polylines.
    static let points: [[CGPoint]] = {
        let M:  [CGPoint] = [.init(x:-26, y: 7), .init(x:-26, y:-7),
                             .init(x:-22, y: 0), .init(x:-18, y:-7),
                             .init(x:-18, y: 7)]
        let A:  [CGPoint] = [.init(x:-14, y: 7), .init(x:-10, y:-7),
                             .init(x: -6, y: 7)]
        let Abar: [CGPoint] = [.init(x:-12.5, y: 1.5), .init(x: -7.5, y: 1.5)]
        let N:  [CGPoint] = [.init(x: -2, y: 7), .init(x: -2, y:-7),
                             .init(x:  6, y: 7), .init(x:  6, y:-7)]
        let I:  [CGPoint] = [.init(x: 10, y:-7), .init(x: 10, y: 7)]
        let M2: [CGPoint] = [.init(x: 14, y: 7), .init(x: 14, y:-7),
                             .init(x: 18, y: 0), .init(x: 22, y:-7),
                             .init(x: 22, y: 7)]
        return [M, A, Abar, N, I, M2]
    }()
}

// MARK: - 2. Pythagorean theorem
//
// Three squares emerge on the three sides of a right triangle, the
// classic visual proof. Squares use Manim's BLUE / YELLOW / GREEN.

struct ScenePreview_Pythag: View {
    var body: some View {
        ScenePreviewCanvas(loopSeconds: 5) { ctx, size, t in
            let w = size.width, h = size.height
            // Right triangle, with the right angle at A (bottom-left).
            let scale: CGFloat = 7.5
            let a: CGFloat = 4 * scale   // leg along the bottom
            let b: CGFloat = 3 * scale   // leg up the right
            let cx = w/2 - a/4
            let cy = h/2 + b/4 + 4
            let A = CGPoint(x: cx,     y: cy)
            let B = CGPoint(x: cx + a, y: cy)
            let C = CGPoint(x: cx + a, y: cy - b)
            // Animation timeline:
            //   0.0–0.7 s  Triangle Creates
            //   0.7–1.5 s  blue square on `a` grows down
            //   1.3–2.1 s  yellow square on `b` grows right
            //   1.9–3.0 s  green square on hypotenuse grows
            //   3.0–4.6 s  hold + formula writes
            let triE = smooth(t / 0.7)
            let sqA  = smooth((t - 0.7) / 0.8)
            let sqB  = smooth((t - 1.3) / 0.8)
            let sqC  = smooth((t - 1.9) / 1.1)
            let texE = smooth((t - 3.0) / 1.0)

            // Triangle (white stroke)
            var tri = Path()
            let verts = [A, B, C]
            for (i, p) in verts.enumerated() {
                let alpha = Double(i + 1) / Double(verts.count)
                if i == 0 { tri.move(to: p) }
                else if triE >= alpha - 1.0/Double(verts.count) { tri.addLine(to: p) }
            }
            if triE > 0.95 { tri.closeSubpath() }
            ctx.stroke(tri, with: .color(Manim.white),
                       style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))

            // Square on `a` (BLUE_C) — extends downward
            if sqA > 0 {
                let rect = CGRect(x: A.x, y: A.y, width: a, height: a * CGFloat(sqA))
                ctx.fill(Path(rect), with: .color(Manim.blue.opacity(0.22)))
                ctx.stroke(Path(rect), with: .color(Manim.blue), lineWidth: 1.6)
            }
            // Square on `b` (YELLOW) — extends to the right
            if sqB > 0 {
                let rect = CGRect(x: C.x, y: C.y, width: b * CGFloat(sqB), height: b)
                ctx.fill(Path(rect), with: .color(Manim.yellow.opacity(0.20)))
                ctx.stroke(Path(rect), with: .color(Manim.yellow), lineWidth: 1.6)
            }
            // Square on hypotenuse (GREEN_C) — rotated
            if sqC > 0 {
                let dx = C.x - A.x, dy = C.y - A.y
                let len = (dx*dx + dy*dy).squareRoot()
                let ang = atan2(dy, dx)
                ctx.drawLayer { layer in
                    layer.translateBy(x: A.x, y: A.y)
                    layer.rotate(by: .radians(ang))
                    let rect = CGRect(x: 0, y: -len * CGFloat(sqC),
                                       width: len, height: len * CGFloat(sqC))
                    layer.fill(Path(rect), with: .color(Manim.green.opacity(0.20)))
                    layer.stroke(Path(rect), with: .color(Manim.green), lineWidth: 1.6)
                }
            }

            // Formula: a² + b² = c²  — italic serif, white
            if texE > 0 {
                let label = Text("a² + b² = c²")
                    .font(.custom("Times New Roman", size: 13).italic())
                    .foregroundColor(Manim.white.opacity(texE))
                ctx.draw(label, at: CGPoint(x: w/2, y: 22), anchor: .center)
            }
        }
    }
}

// MARK: - 3. Sine wave
//
// White Axes + YELLOW sin(x) curve being drawn left-to-right via
// `Create`. A small dot rides the curve. Mirrors Manim's
// `axes.plot(np.sin)`.

struct ScenePreview_Sine: View {
    var body: some View {
        ScenePreviewCanvas(loopSeconds: 5) { ctx, size, t in
            let w = size.width, h = size.height
            let cy = h / 2 + 2
            let leftPad: CGFloat = 14, rightPad: CGFloat = 14, topPad: CGFloat = 18, botPad: CGFloat = 22
            let plotL = leftPad, plotR = w - rightPad
            let plotT = topPad,  plotB = h - botPad

            // Axes — Manim default: white lines, small tick marks, no fill
            var xAxis = Path()
            xAxis.move(to: CGPoint(x: plotL, y: cy))
            xAxis.addLine(to: CGPoint(x: plotR, y: cy))
            ctx.stroke(xAxis, with: .color(Manim.white), lineWidth: 1)
            var yAxis = Path()
            yAxis.move(to: CGPoint(x: (plotL + plotR) / 2, y: plotT))
            yAxis.addLine(to: CGPoint(x: (plotL + plotR) / 2, y: plotB))
            ctx.stroke(yAxis, with: .color(Manim.white), lineWidth: 1)
            // X ticks
            let mid = (plotL + plotR) / 2
            for k in -3...3 where k != 0 {
                let x = mid + CGFloat(k) * (plotR - plotL) / 8
                var tick = Path()
                tick.move(to: CGPoint(x: x, y: cy - 3))
                tick.addLine(to: CGPoint(x: x, y: cy + 3))
                ctx.stroke(tick, with: .color(Manim.white), lineWidth: 1)
            }
            // Y ticks
            for k in [-1, 1] {
                let y = cy - CGFloat(k) * 26
                var tick = Path()
                tick.move(to: CGPoint(x: mid - 3, y: y))
                tick.addLine(to: CGPoint(x: mid + 3, y: y))
                ctx.stroke(tick, with: .color(Manim.white), lineWidth: 1)
            }

            // Animation: 0..2 s create curve, 2..3 s hold + ride, repeat.
            let createT = smooth(t / 2.0)
            // Build the sine path from x = -3π to x = 3π in plot units
            var curve = Path()
            var first = true
            let span = plotR - plotL
            let revealX = plotL + span * CGFloat(createT)
            var x = plotL
            while x <= revealX {
                let u = Double((x - mid) / ((plotR - plotL) / 8)) // x in radians-ish (8 units span)
                let y = cy - CGFloat(sin(u)) * 26
                let p = CGPoint(x: x, y: y)
                if first { curve.move(to: p); first = false } else { curve.addLine(to: p) }
                x += 0.5
            }
            ctx.stroke(curve, with: .color(Manim.yellow),
                       style: StrokeStyle(lineWidth: 2.4, lineCap: .round, lineJoin: .round))

            // Dot riding the end of the drawn curve
            if createT > 0 {
                let u = Double((revealX - mid) / ((plotR - plotL) / 8))
                let yy = cy - CGFloat(sin(u)) * 26
                ctx.fill(Path(ellipseIn: CGRect(x: revealX - 3, y: yy - 3,
                                                 width: 6, height: 6)),
                         with: .color(Manim.yellow))
            }

            // y = sin(x) label
            let label = Text("y = sin(x)")
                .font(.custom("Times New Roman", size: 12).italic())
                .foregroundColor(Manim.white)
            ctx.draw(label, at: CGPoint(x: w/2, y: h - 10), anchor: .center)
        }
    }
}

// MARK: - 4. Fourier squares
//
// Five rotating epicycles (1st, 3rd, 5th, 7th, 9th odd harmonics of
// the square-wave Fourier series). Manim style: thin white circles,
// white radius arms, BLUE_C trace ribbon.

struct ScenePreview_Fourier: View {
    var body: some View {
        TimelineView(.animation) { timeline in
            let now = timeline.date.timeIntervalSinceReferenceDate
            let t = now.truncatingRemainder(dividingBy: 30)
            ZStack {
                Manim.bg
                Canvas { ctx, size in
                    let w = size.width, h = size.height
                    let cx0 = w * 0.38, cy0 = h * 0.5
                    let N = 5
                    var x = cx0, y = cy0
                    for k in 0..<N {
                        let n = Double(2 * k + 1)
                        let r = 24.0 * (4.0 / (.pi * n))
                        let ang = t * 1.0 * n
                        let nx = x + CGFloat(cos(ang) * r)
                        let ny = y + CGFloat(sin(ang) * r)
                        // Circle (thin white)
                        ctx.stroke(Path(ellipseIn: CGRect(x: x - r, y: y - r,
                                                          width: r*2, height: r*2)),
                                   with: .color(Manim.white.opacity(0.55)), lineWidth: 1)
                        // Radius arm
                        var arm = Path()
                        arm.move(to: CGPoint(x: x, y: y))
                        arm.addLine(to: CGPoint(x: nx, y: ny))
                        ctx.stroke(arm, with: .color(Manim.white.opacity(0.85)), lineWidth: 1.2)
                        x = nx; y = ny
                    }
                    // Trail — sampled back through time so it doesn't need state
                    var trail = Path()
                    var first = true
                    let samples = 110
                    let trailSpan = 2.8
                    for i in 0...samples {
                        let ti = t - trailSpan * Double(i) / Double(samples)
                        var sx = cx0, sy = cy0
                        for k in 0..<N {
                            let n = Double(2 * k + 1)
                            let r = 24.0 * (4.0 / (.pi * n))
                            let ang = ti * 1.0 * n
                            sx += CGFloat(cos(ang) * r)
                            sy += CGFloat(sin(ang) * r)
                        }
                        let p = CGPoint(x: sx, y: sy)
                        if first { trail.move(to: p); first = false } else { trail.addLine(to: p) }
                    }
                    ctx.stroke(trail, with: .color(Manim.blue),
                               style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                    // Tip
                    ctx.fill(Path(ellipseIn: CGRect(x: x - 2.5, y: y - 2.5,
                                                     width: 5, height: 5)),
                             with: .color(Manim.blue))

                    // f(x) = 4/π · Σ sin((2k+1)x)/(2k+1)
                    let label = Text("ƒ(t) = Σ (4/πn) sin(nt)")
                        .font(.custom("Times New Roman", size: 11).italic())
                        .foregroundColor(Manim.white)
                    ctx.draw(label, at: CGPoint(x: w/2, y: h - 10), anchor: .center)
                }
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - 5. Circle ↔ Square (Transform)
//
// Manim's `Transform(circle, square)` — vertices interpolated 1:1.
// Filled with semi-transparent fill, BLUE_C stroke at one end,
// YELLOW at the other; colour also interpolates.

struct ScenePreview_Morph: View {
    var body: some View {
        ScenePreviewCanvas(loopSeconds: 4) { ctx, size, t in
            let w = size.width, h = size.height
            let cx = w / 2, cy = h / 2
            let R: CGFloat = 36
            // m: 0..1..0 over 4 s (one full cycle)
            let phase = (t / 4) * 2 * .pi
            let m = (1 - cos(phase)) / 2     // smooth back-and-forth

            // Colour interpolates BLUE_C → YELLOW
            let stroke = Manim.blue.blended(with: Manim.yellow, by: m)
            let fill   = stroke.opacity(0.18)

            let pts = 64
            var path = Path()
            for i in 0...pts {
                let a = (Double(i) / Double(pts)) * .pi * 2 - .pi / 4
                let cxp = CGFloat(cos(a)) * R
                let cyp = CGFloat(sin(a)) * R
                let k = max(abs(cos(a)), abs(sin(a)))
                let sxp = CGFloat(cos(a) / k) * R
                let syp = CGFloat(sin(a) / k) * R
                let xx = cx + cxp * CGFloat(1 - m) + sxp * CGFloat(m)
                let yy = cy + cyp * CGFloat(1 - m) + syp * CGFloat(m)
                let p = CGPoint(x: xx, y: yy)
                if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
            }
            path.closeSubpath()
            ctx.fill(path, with: .color(fill))
            ctx.stroke(path, with: .color(stroke),
                       style: StrokeStyle(lineWidth: 2.4, lineCap: .round, lineJoin: .round))
        }
    }
}

// MARK: - 6. Graph traversal (DFS)
//
// Manim's `Graph` mobject: nodes with WHITE outlines + black fill,
// edges in white, a YELLOW dot walks the path, traversed edges turn
// BLUE_C as the dot moves over them.

struct ScenePreview_Graph: View {
    private let nodes: [CGPoint] = [
        CGPoint(x: 58,  y: 64),
        CGPoint(x: 128, y: 44),
        CGPoint(x: 208, y: 74),
        CGPoint(x: 252, y: 132),
        CGPoint(x: 178, y: 142),
        CGPoint(x:  98, y: 132),
        CGPoint(x:  58, y: 102),
    ]
    private let edges: [(Int, Int)] = [
        (0,1),(1,2),(2,3),(3,4),(4,5),(5,6),(6,0),(1,5),(2,4)
    ]
    private let path: [Int] = [0,1,2,4,5,6]

    var body: some View {
        ScenePreviewCanvas(loopSeconds: 7) { ctx, size, t in
            // All edges in white at low alpha (unvisited)
            for (a, b) in edges {
                var p = Path()
                p.move(to: nodes[a])
                p.addLine(to: nodes[b])
                ctx.stroke(p, with: .color(Manim.white.opacity(0.55)), lineWidth: 1.2)
            }
            // Traversal progress
            let phase = (t * 0.9).truncatingRemainder(dividingBy: Double(path.count))
            let idx = Int(phase.rounded(.down))
            let frac = CGFloat(smooth(phase - Double(idx)))
            // Completed edges in BLUE_C
            for i in 0..<idx where i + 1 < path.count {
                let a = nodes[path[i]], b = nodes[path[i + 1]]
                var p = Path(); p.move(to: a); p.addLine(to: b)
                ctx.stroke(p, with: .color(Manim.blue), lineWidth: 2.2)
            }
            // Current edge — partial blue, dot at the tip
            if idx + 1 < path.count {
                let a = nodes[path[idx]], b = nodes[path[idx + 1]]
                let x = a.x + (b.x - a.x) * frac
                let y = a.y + (b.y - a.y) * frac
                var p = Path(); p.move(to: a); p.addLine(to: CGPoint(x: x, y: y))
                ctx.stroke(p, with: .color(Manim.blue), lineWidth: 2.2)
                ctx.fill(Path(ellipseIn: CGRect(x: x - 5, y: y - 5,
                                                 width: 10, height: 10)),
                         with: .color(Manim.yellow))
            }
            // Nodes (Manim Graph default: white circle outline, black fill, labels)
            for (i, n) in nodes.enumerated() {
                let visited = path.prefix(idx + 1).contains(i)
                let r: CGFloat = 7
                let rect = CGRect(x: n.x - r, y: n.y - r, width: r * 2, height: r * 2)
                ctx.fill(Path(ellipseIn: rect), with: .color(Manim.bg))
                ctx.stroke(Path(ellipseIn: rect),
                           with: .color(visited ? Manim.blue : Manim.white),
                           lineWidth: 1.5)
                // Number label inside the node
                let label = Text("\(i + 1)")
                    .font(.custom("Times New Roman", size: 9).italic())
                    .foregroundColor(Manim.white)
                ctx.draw(label, at: n, anchor: .center)
            }
        }
    }
}

// MARK: - Color blending helper

private extension Color {
    /// Linear sRGB blend between two SwiftUI colors. `t = 0` → self,
    /// `t = 1` → other. Used to interpolate stroke colour as the
    /// Transform animation morphs the circle into the square.
    func blended(with other: Color, by t: Double) -> Color {
        let a = uiComponents
        let b = other.uiComponents
        let k = max(0.0, min(1.0, t))
        return Color(red:   a.r + (b.r - a.r) * k,
                     green: a.g + (b.g - a.g) * k,
                     blue:  a.b + (b.b - a.b) * k,
                     opacity: a.a + (b.a - a.a) * k)
    }

    /// Best-effort RGBA decomposition via UIColor. SwiftUI doesn't
    /// expose components directly; we round-trip through UIColor.
    var uiComponents: (r: Double, g: Double, b: Double, a: Double) {
        #if canImport(UIKit)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        UIColor(self).getRed(&r, green: &g, blue: &b, alpha: &a)
        return (Double(r), Double(g), Double(b), Double(a))
        #else
        return (0, 0, 0, 1)
        #endif
    }
}

#if canImport(UIKit)
import UIKit
#endif
