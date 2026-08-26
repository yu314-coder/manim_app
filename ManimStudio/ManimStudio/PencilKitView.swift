// PencilKitView.swift — iPad-only Apple Pencil sketch → Manim code.
//
// Flow: SketchSheetView hosts a PKCanvasView. On "Convert & Insert" each
// stroke is sampled, mapped into Manim's centred Y-up frame, and RECOGNISED
// into a clean primitive — Circle / Line / Square / Rectangle /
// RegularPolygon / Triangle — instead of a raw traced point dump. Shapes
// that aren't recognised fall back to a simplified Polygon (closed) or a
// smooth VMobject (open). The snippet is posted to the editor via the
// .editorInsertCode notification (observed in EditorPane → monaco.insertCode).
//
// FULLY OFFLINE: recognition is pure Swift geometry (least-squares circle
// fit, Ramer–Douglas–Peucker corner simplification, angle/side analysis) —
// no network, no Vision/ML model, no cloud. PencilKit is on-device.
//
// NEEDS DEVICE TESTING: PencilKit + the recognition thresholds want a real
// iPad + Pencil to tune; the Simulator has neither.
import SwiftUI
import PencilKit

// ─────────────────────────────────────────────────────────────
// Geometry primitives
// ─────────────────────────────────────────────────────────────

/// A 2-D point/vector in Manim coordinate space.
struct V2 {
    var x: Double, y: Double
    static func - (a: V2, b: V2) -> V2 { V2(x: a.x - b.x, y: a.y - b.y) }
    static func + (a: V2, b: V2) -> V2 { V2(x: a.x + b.x, y: a.y + b.y) }
    static func * (a: V2, s: Double) -> V2 { V2(x: a.x * s, y: a.y * s) }
    var length: Double { (x * x + y * y).squareRoot() }
    func dot(_ o: V2) -> Double { x * o.x + y * o.y }
    func dist(_ o: V2) -> Double { (self - o).length }
}

/// Manim's logical frame. frame_height is fixed at 8.0; frame_width is
/// derived from the render aspect ratio (1920×1080 default → ≈14.222).
enum ManimFrame {
    static let frameHeight: Double = 8.0
    static let aspectRatio: Double = 1920.0 / 1080.0
    static var frameWidth: Double { frameHeight * aspectRatio }
}

/// Canvas point (top-left origin, y-down) → Manim coord (centre origin,
/// y-up). A single uniform fit-to-frame scale keeps shapes undistorted.
struct SketchCoordinateMapper {
    let canvasSize: CGSize
    private var unitsPerPoint: Double {
        let w = Double(canvasSize.width), h = Double(canvasSize.height)
        guard w > 0, h > 0 else { return 1 }
        return min(ManimFrame.frameWidth / w, ManimFrame.frameHeight / h)
    }
    func toManim(_ p: CGPoint) -> V2 {
        let s = unitsPerPoint
        let cx = Double(canvasSize.width) / 2.0
        let cy = Double(canvasSize.height) / 2.0
        return V2(x: (Double(p.x) - cx) * s, y: -(Double(p.y) - cy) * s)
    }
}

// ─────────────────────────────────────────────────────────────
// Shape recognition (all offline)
// ─────────────────────────────────────────────────────────────

enum RecognizedShape {
    case line(V2, V2)
    case circle(center: V2, radius: Double)
    case square(center: V2, side: Double)
    case rectangle(center: V2, w: Double, h: Double)
    case regularPolygon(center: V2, n: Int, radius: Double)
    case polygon([V2])          // clean corners (closed)
    case smooth([V2])           // freeform (open)
}

enum ShapeRecognizer {

    static func centroid(_ p: [V2]) -> V2 {
        guard !p.isEmpty else { return V2(x: 0, y: 0) }
        let s = p.reduce(V2(x: 0, y: 0), +)
        return s * (1.0 / Double(p.count))
    }

    /// (minX, minY, width, height)
    static func bbox(_ p: [V2]) -> (origin: V2, size: V2) {
        let xs = p.map { $0.x }, ys = p.map { $0.y }
        let minx = xs.min() ?? 0, maxx = xs.max() ?? 0
        let miny = ys.min() ?? 0, maxy = ys.max() ?? 0
        return (V2(x: minx, y: miny), V2(x: maxx - minx, y: maxy - miny))
    }

    static func pathLength(_ p: [V2]) -> Double {
        guard p.count > 1 else { return 0 }
        var d = 0.0
        for i in 1..<p.count { d += p[i].dist(p[i - 1]) }
        return d
    }

    /// Ramer–Douglas–Peucker corner simplification.
    static func rdp(_ pts: [V2], epsilon: Double) -> [V2] {
        guard pts.count > 2 else { return pts }
        let a = pts.first!, b = pts.last!
        let ab = b - a
        let abLen = ab.length
        var maxDist = 0.0, idx = 0
        for i in 1..<(pts.count - 1) {
            let d: Double
            if abLen < 1e-9 {
                d = pts[i].dist(a)
            } else {
                // perpendicular distance to segment a-b
                let t = max(0, min(1, (pts[i] - a).dot(ab) / (abLen * abLen)))
                d = pts[i].dist(a + ab * t)
            }
            if d > maxDist { maxDist = d; idx = i }
        }
        if maxDist > epsilon {
            let left = rdp(Array(pts[0...idx]), epsilon: epsilon)
            let right = rdp(Array(pts[idx...]), epsilon: epsilon)
            return Array(left.dropLast()) + right
        }
        return [a, b]
    }

    /// Coefficient of variation (stddev / mean), 0 = perfectly uniform.
    private static func cv(_ vals: [Double]) -> Double {
        guard !vals.isEmpty else { return .infinity }
        let mean = vals.reduce(0, +) / Double(vals.count)
        guard mean > 1e-9 else { return .infinity }
        let varr = vals.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Double(vals.count)
        return varr.squareRoot() / mean
    }

    /// Endpoint gap below this fraction of the bounding-box diagonal counts
    /// as "closed". Shared by isClosed() and the RDP closing-vertex drop so
    /// the two can't drift apart (a mismatch was leaving squares as 5-gons
    /// and triangles as 4-gons → misclassified).
    static let closeGapFactor = 0.22

    static func recognize(_ pts: [V2], closed: Bool) -> RecognizedShape {
        guard pts.count >= 2 else { return .smooth(pts) }
        let diag = max(bbox(pts).size.length, 1e-6)

        if !closed {
            if let line = lineFit(pts, diag: diag) { return line }
            return .smooth(pts)
        }

        // Corner simplification first — the corner COUNT separates polygons
        // (few corners) from smooth blobs / circles (many corners), so a
        // square never gets misread as a circle and vice-versa.
        var corners = rdp(pts, epsilon: diag * 0.035)
        // Drop the duplicate closing vertex using the SAME tolerance as
        // isClosed(), so every closed stroke loses it (a smaller threshold
        // left near-but-not-touching squares/triangles with an extra corner).
        if corners.count >= 2, corners.first!.dist(corners.last!) < diag * closeGapFactor {
            corners.removeLast()
        }
        let n = corners.count

        // Many corners → a regular n-gon (≥7 sides) or a smooth circle. Try
        // the polygon fit first; a true circle's arbitrarily-spaced RDP
        // corners fail regularPolygonFit's equal-sides test and fall through.
        if n >= 7 {
            if let rp = regularPolygonFit(corners) { return rp }
            if let c = circleFit(pts) { return c }
            return .polygon(corners)
        }
        if n < 3 { return .smooth(pts) }
        if n == 3 { return .polygon(corners) }          // triangle
        if n == 4 { return rectangleFit(corners) ?? .polygon(corners) }
        return regularPolygonFit(corners) ?? .polygon(corners)   // n == 5 or 6
    }

    // MARK: shape fits

    private static func lineFit(_ pts: [V2], diag: Double) -> RecognizedShape? {
        let a = pts.first!, b = pts.last!
        let ab = b - a
        let len = ab.length
        guard len > 1e-6 else { return nil }
        var maxDev = 0.0
        for p in pts {
            let t = (p - a).dot(ab) / (len * len)
            maxDev = max(maxDev, p.dist(a + ab * t))
        }
        // Straight if deviation is small AND the endpoints span most of the
        // drawn path (rules out a folded-back scribble).
        if maxDev < len * 0.10 && len > pathLength(pts) * 0.80 {
            return .line(a, b)
        }
        return nil
    }

    /// Algebraic (Kåsa) least-squares circle fit + radial-residual and
    /// angular-coverage checks. Density-independent (unlike a centroid
    /// estimate) and rejects open arcs so a 270° scribble isn't snapped to a
    /// full circle.
    private static func circleFit(_ pts: [V2]) -> RecognizedShape? {
        guard pts.count >= 5 else { return nil }
        // Fit x² + y² + D·x + E·y + F = 0 by least squares.
        var Sx = 0.0, Sy = 0.0, Sxx = 0.0, Syy = 0.0, Sxy = 0.0
        var Sxz = 0.0, Syz = 0.0, Sz = 0.0
        for p in pts {
            let z = p.x * p.x + p.y * p.y
            Sx += p.x; Sy += p.y; Sxx += p.x * p.x; Syy += p.y * p.y
            Sxy += p.x * p.y; Sxz += p.x * z; Syz += p.y * z; Sz += z
        }
        let nN = Double(pts.count)
        let m: [[Double]] = [[Sxx, Sxy, Sx], [Sxy, Syy, Sy], [Sx, Sy, nN]]
        let rhs = [-Sxz, -Syz, -Sz]
        func det3(_ a: [[Double]]) -> Double {
            a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
          - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
          + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
        }
        let det = det3(m)
        guard abs(det) > 1e-9 else { return nil }
        func col(_ a: [[Double]], _ c: Int, _ v: [Double]) -> [[Double]] {
            var b = a; for r in 0..<3 { b[r][c] = v[r] }; return b
        }
        let D = det3(col(m, 0, rhs)) / det
        let E = det3(col(m, 1, rhs)) / det
        let F = det3(col(m, 2, rhs)) / det
        let cx = -D / 2, cy = -E / 2
        let r2 = cx * cx + cy * cy - F
        guard r2 > 1e-9 else { return nil }
        let center = V2(x: cx, y: cy)
        let radii = pts.map { $0.dist(center) }
        guard cv(radii) < 0.16 else { return nil }     // points near radius r

        // Angular coverage: a gap > ~50° about the centre means it's an open
        // arc, not a closed circle.
        let angles = pts.map { atan2($0.y - cy, $0.x - cx) }.sorted()
        var maxGap = angles[0] + 2 * .pi - angles[angles.count - 1]   // wrap-around gap
        for i in 1..<angles.count { maxGap = max(maxGap, angles[i] - angles[i - 1]) }
        guard maxGap < 50.0 * .pi / 180.0 else { return nil }

        return .circle(center: center, radius: r2.squareRoot())
    }

    /// Axis-aligned rectangle/square from 4 corners (within ~16° of the
    /// horizontal/vertical). A tilted quad returns nil → emitted as a clean
    /// Polygon, which preserves its orientation exactly.
    private static func rectangleFit(_ corners: [V2]) -> RecognizedShape? {
        guard corners.count == 4 else { return nil }
        var edges: [V2] = []
        for i in 0..<4 {
            let e = corners[(i + 1) % 4] - corners[i]
            guard e.length > 1e-6 else { return nil }
            let deg = abs(atan2(e.y, e.x) * 180 / .pi)
            if min(deg, abs(deg - 90), abs(deg - 180)) > 12 { return nil }  // not axis-aligned
            edges.append(e)
        }
        // Dimensions from the ACTUAL edges (opposite-edge pairs averaged) —
        // the bbox inflates with even a small tilt, so don't use it.
        let pairA = (edges[0].length + edges[2].length) / 2   // edges 0,2
        let pairB = (edges[1].length + edges[3].length) / 2   // edges 1,3
        guard pairA > 1e-6, pairB > 1e-6 else { return nil }
        let center = centroid(corners)
        if max(pairA, pairB) / min(pairA, pairB) < 1.20 {
            return .square(center: center, side: (pairA + pairB) / 2)
        }
        // Width = the more-horizontal pair.
        let e0deg = abs(atan2(edges[0].y, edges[0].x) * 180 / .pi)
        let e0horizontal = min(e0deg, abs(e0deg - 180)) < 45
        return .rectangle(center: center,
                          w: e0horizontal ? pairA : pairB,
                          h: e0horizontal ? pairB : pairA)
    }

    private static func regularPolygonFit(_ corners: [V2]) -> RecognizedShape? {
        let n = corners.count
        guard n >= 5 else { return nil }
        let c = centroid(corners)
        let radii = corners.map { $0.dist(c) }
        var sides: [Double] = []
        for i in 0..<n { sides.append(corners[(i + 1) % n].dist(corners[i])) }
        // Equal radii AND equal side lengths → regular polygon.
        if cv(radii) < 0.12 && cv(sides) < 0.18 {
            let mean = radii.reduce(0, +) / Double(radii.count)
            return .regularPolygon(center: c, n: n, radius: mean)
        }
        return nil
    }
}

// ─────────────────────────────────────────────────────────────
// Manim code generation
// ─────────────────────────────────────────────────────────────

enum ManimCodeGenerator {

    /// Sample a PKStroke into points along its parametric path
    /// (PKStrokePath is parameterised over [0, count-1]).
    static func sample(_ stroke: PKStroke, step: CGFloat = 6) -> [CGPoint] {
        let path = stroke.path
        guard path.count > 0 else { return [] }
        var pts: [CGPoint] = []
        let last = CGFloat(path.count - 1)
        var t: CGFloat = 0
        while t <= last {
            pts.append(path.interpolatedLocation(at: t).applying(stroke.transform))
            t += step / 50.0
        }
        let realEnd = path.interpolatedLocation(at: last).applying(stroke.transform)
        if let endLoc = pts.last, hypot(endLoc.x - realEnd.x, endLoc.y - realEnd.y) > 0.5 {
            pts.append(realEnd)
        }
        return decimate(pts, minSpacing: step)
    }

    private static func decimate(_ pts: [CGPoint], minSpacing: CGFloat) -> [CGPoint] {
        guard let first = pts.first else { return [] }
        var out = [first]
        for p in pts.dropFirst() {
            if let last = out.last, hypot(p.x - last.x, p.y - last.y) >= minSpacing {
                out.append(p)
            }
        }
        return out
    }

    /// A stroke is "closed" if its endpoints are near each other relative to
    /// its overall size.
    private static func isClosed(_ pts: [V2]) -> Bool {
        guard pts.count >= 3, let a = pts.first, let b = pts.last else { return false }
        let diag = ShapeRecognizer.bbox(pts).size.length
        guard diag > 1e-6 else { return false }
        return a.dist(b) < diag * ShapeRecognizer.closeGapFactor
    }

    /// One recognised stroke.
    static func process(_ drawing: PKDrawing, canvasSize: CGSize) -> [RecognizedShape] {
        let mapper = SketchCoordinateMapper(canvasSize: canvasSize)
        return drawing.strokes.compactMap { stroke in
            let raw = sample(stroke).map { mapper.toManim($0) }
            guard raw.count >= 2 else { return nil }
            return ShapeRecognizer.recognize(raw, closed: isClosed(raw))
        }
    }

    private static func f(_ v: Double) -> String { String(format: "%.3f", v) }
    private static func p3(_ p: V2) -> String { "[\(f(p.x)), \(f(p.y)), 0]" }

    /// Emit one Manim statement (assigned to `name`) for a recognised shape.
    private static func emit(_ shape: RecognizedShape, name: String) -> [String] {
        switch shape {
        case let .line(a, b):
            return ["\(name) = Line(\(p3(a)), \(p3(b)))"]
        case let .circle(center, radius):
            return ["\(name) = Circle(radius=\(f(radius))).move_to(\(p3(center)))"]
        case let .square(center, side):
            return ["\(name) = Square(side_length=\(f(side))).move_to(\(p3(center)))"]
        case let .rectangle(center, w, h):
            return ["\(name) = Rectangle(width=\(f(w)), height=\(f(h))).move_to(\(p3(center)))"]
        case let .regularPolygon(center, n, radius):
            return ["\(name) = RegularPolygon(n=\(n)).scale(\(f(radius))).move_to(\(p3(center)))"]
        case let .polygon(pts):
            let body = pts.map { "    \(p3($0))," }.joined(separator: "\n")
            return ["\(name) = Polygon(", body, ")"]
        case let .smooth(pts):
            let arr = pts.map { p3($0) }.joined(separator: ", ")
            return ["\(name) = VMobject()", "\(name).set_points_smoothly([\(arr)])"]
        }
    }

    static func generate(from drawing: PKDrawing, canvasSize: CGSize) -> String {
        let shapes = process(drawing, canvasSize: canvasSize)
        guard !shapes.isEmpty else { return "# Sketch produced no usable strokes.\n" }
        var lines = ["# --- Sketch import (\(shapes.count) shape\(shapes.count == 1 ? "" : "s")) ---"]
        var names: [String] = []
        for (i, s) in shapes.enumerated() {
            let name = "sketch_\(i + 1)"
            names.append(name)
            lines += emit(s, name: name)
        }
        lines.append("self.add(\(names.joined(separator: ", ")))")
        return lines.joined(separator: "\n") + "\n"
    }
}

// ─────────────────────────────────────────────────────────────
// PKCanvasView UIViewRepresentable (with tool picker)
// ─────────────────────────────────────────────────────────────

struct SketchCanvasView: UIViewRepresentable {
    @Binding var canvas: PKCanvasView
    /// Driven from the canvas DELEGATE so SwiftUI actually re-renders when
    /// strokes change. A PKCanvasView is a reference type, so mutating its
    /// `.drawing` does NOT invalidate a view that reads
    /// `canvas.drawing.strokes` directly — which is exactly why the Convert
    /// button stayed permanently disabled.
    @Binding var hasStrokes: Bool

    func makeUIView(context: Context) -> PKCanvasView {
        canvas.drawingPolicy = .anyInput          // Pencil + finger
        canvas.backgroundColor = .clear
        canvas.isOpaque = false
        canvas.alwaysBounceVertical = false
        canvas.delegate = context.coordinator
        attachToolPicker(canvas, context: context)
        return canvas
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {
        if uiView.delegate == nil { uiView.delegate = context.coordinator }
        if context.coordinator.toolPicker == nil {
            attachToolPicker(uiView, context: context)
        }
    }

    private func attachToolPicker(_ view: PKCanvasView, context: Context) {
        DispatchQueue.main.async {
            guard view.window != nil else { return }
            let picker = context.coordinator.toolPicker ?? PKToolPicker()
            picker.setVisible(true, forFirstResponder: view)
            picker.addObserver(view)
            view.becomeFirstResponder()
            context.coordinator.toolPicker = picker
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(hasStrokes: $hasStrokes) }

    final class Coordinator: NSObject, PKCanvasViewDelegate {
        var toolPicker: PKToolPicker?
        private let hasStrokes: Binding<Bool>
        init(hasStrokes: Binding<Bool>) { self.hasStrokes = hasStrokes }

        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            let nonEmpty = !canvasView.drawing.strokes.isEmpty
            if hasStrokes.wrappedValue != nonEmpty { hasStrokes.wrappedValue = nonEmpty }
        }
    }
}

// ─────────────────────────────────────────────────────────────
// The sheet
// ─────────────────────────────────────────────────────────────

struct SketchSheetView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var canvas = PKCanvasView()
    @State private var canvasSize: CGSize = .zero
    @State private var hasStrokes = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                GeometryReader { geo in
                    SketchCanvasView(canvas: $canvas, hasStrokes: $hasStrokes)
                        .background(Theme.bgPrimary)
                        .onAppear { canvasSize = geo.size }
                        .onChange(of: geo.size) { _, newSize in canvasSize = newSize }
                }
                Text("Draw a shape — circles, lines, rectangles, triangles and polygons are recognised. Everything runs on-device.")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textDim)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 16).padding(.vertical, 8)
                    .frame(maxWidth: .infinity)
                    .background(Theme.bgSecondary)
            }
            .ignoresSafeArea(.container, edges: .bottom)
            .navigationTitle("Sketch → Manim")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button("Clear") { canvas.drawing = PKDrawing(); hasStrokes = false }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Convert & Insert") {
                        let size = canvasSize == .zero ? canvas.bounds.size : canvasSize
                        let code = ManimCodeGenerator.generate(from: canvas.drawing, canvasSize: size)
                        NotificationCenter.default.post(
                            name: .editorInsertCode, object: nil, userInfo: ["code": code])
                        dismiss()
                    }
                    .disabled(!hasStrokes)
                }
            }
        }
        .preferredColorScheme(.dark)
    }
}
