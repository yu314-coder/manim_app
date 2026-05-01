import Foundation
import UIKit
import PDFKit

/// LaTeX rendering engine for iOS using SwiftMath (native CoreText rendering).
/// Produces pixel-perfect math typesetting entirely offline — no WKWebView needed.
@objc class LaTeXEngine: NSObject {

    static let shared = LaTeXEngine()

    private var isInitialized = false

    override init() {
        super.init()
    }

    // MARK: - Initialize

    func initialize() {
        guard !isInitialized else { return }

        // ios_system not vendored in ManimStudio — busytex bridge handles all LaTeX.
        // initializeEnvironment()  // disabled

        isInitialized = true

        // Ensure signal dir exists
        let signalDir = NSTemporaryDirectory().appending("latex_signals/")
        try? FileManager.default.createDirectory(atPath: signalDir, withIntermediateDirectories: true)

        print("[LaTeX] Engine initialized (SwiftMath native renderer)")

        // Start watching for Python compile requests
        startSignalWatcher()
    }

    // MARK: - SwiftMath Rendering

    /// Render a LaTeX math expression to SVG with real vector `<path>` elements.
    /// Uses SwiftMath to parse LaTeX, then extracts CoreText glyph outlines as SVG paths.
    /// This produces the same kind of SVG that dvisvgm produces — manim parses it natively.
    func renderToSVG(expression: String, svgPath: String) -> Bool {
        // Render at 12pt — the same size TeX uses in manim's default
        // tex_template (\documentclass[12pt]{article}). This makes the
        // parsed SVG's dimensions match what desktop dvisvgm produces,
        // so manim's SCALE_FACTOR_PER_FONT_POINT (= 1/960) math gives
        // the same final on-screen size as desktop renders. SwiftMath's
        // defaultFont is 20pt which renders math ~1.7× too big.
        let mathFontSize: CGFloat = 12

        // Parse LaTeX into display list
        var error: NSError?
        guard let mathList = MTMathListBuilder.build(fromString: expression, error: &error),
              error == nil,
              let font = MTFontManager.fontManager.latinModernFont(withSize: mathFontSize),
              let displayList = MTTypesetter.createLineForMathList(mathList,
                  font: font,
                  style: .display) else {
            print("[LaTeX] SwiftMath parse error: \(error?.localizedDescription ?? "unknown")")
            return false
        }

        displayList.textColor = .white

        // Compute dimensions
        let contentW = displayList.width
        let contentH = displayList.ascent + displayList.descent
        let pad: CGFloat = 1.0
        let svgW = contentW + pad * 2
        let svgH = contentH + pad * 2

        // Position the display in CoreText coords:
        // In CoreText: y=0 is the bottom of the SVG, y goes up.
        // Baseline at y = pad + descent puts content bottom at y=pad (bottom padding)
        // and content top at y = pad + descent + ascent = pad + contentH (top padding)
        displayList.position = CGPoint(x: pad, y: pad + displayList.descent)

        // Extract SVG paths — pass svgH for Y-flip
        var svgPaths = ""
        extractSVGPaths(from: displayList, into: &svgPaths, offsetX: 0, offsetY: 0, svgHeight: svgH)

        if svgPaths.isEmpty {
            print("[LaTeX] No glyph paths extracted, falling back to rect")
            // Fallback: at least create a visible rect
            svgPaths = "<rect x=\"0\" y=\"0\" width=\"\(svgW)\" height=\"\(svgH)\" fill=\"white\"/>"
        }

        let svg = """
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="\(svgW)" height="\(svgH)" viewBox="0 0 \(svgW) \(svgH)">
        <g id="unique000">
        \(svgPaths)
        </g>
        </svg>
        """

        do {
            try svg.write(toFile: svgPath, atomically: true, encoding: .utf8)
            print("[LaTeX] Vector SVG created: \(svgPath) (\(Int(svgW))×\(Int(svgH))pt, \(svgPaths.count) chars)")
            return true
        } catch {
            print("[LaTeX] Failed to write SVG: \(error)")
            return false
        }
    }

    /// Recursively extract SVG `<path>` elements from an MTDisplay tree.
    /// Each glyph's outline is converted from CoreText CGPath to SVG path data.
    /// svgHeight is used to flip Y: SVG_y = svgHeight - CoreText_y
    ///
    /// Position semantics:
    /// - MTMathListDisplay.subDisplays: positions RELATIVE to parent → accumulate x/y
    /// - MTFractionDisplay num/den: positions ABSOLUTE → pass parent's offset
    /// - MTRadicalDisplay radicand/degree: positions ABSOLUTE → pass parent's offset
    /// - MTLargeOpLimitsDisplay nucleus/upper/lower: positions ABSOLUTE → pass parent's offset
    /// - MTLineDisplay inner: position ABSOLUTE → pass parent's offset
    /// - MTAccentDisplay accentee: position ABSOLUTE → pass parent's offset
    /// - MTAccentDisplay accent: position RELATIVE to display's position
    private func extractSVGPaths(from display: MTDisplay, into svg: inout String, offsetX: CGFloat, offsetY: CGFloat, svgHeight: CGFloat) {
        let x = offsetX + display.position.x
        let y = offsetY + display.position.y

        if let ctrLine = display as? MTCTLineDisplay {
            // CTLine contains runs of glyphs — extract each glyph's path
            guard let line = ctrLine.line else { return }
            let runs = CTLineGetGlyphRuns(line) as! [CTRun]
            for run in runs {
                let font = (CTRunGetAttributes(run) as Dictionary)[kCTFontAttributeName] as! CTFont
                let glyphCount = CTRunGetGlyphCount(run)
                var glyphs = [CGGlyph](repeating: 0, count: glyphCount)
                var positions = [CGPoint](repeating: .zero, count: glyphCount)
                CTRunGetGlyphs(run, CFRangeMake(0, glyphCount), &glyphs)
                CTRunGetPositions(run, CFRangeMake(0, glyphCount), &positions)

                for i in 0..<glyphCount {
                    let gx = x + positions[i].x
                    let gy = y + positions[i].y

                    if let cgPath = CTFontCreatePathForGlyph(font, glyphs[i], nil) {
                        // Normal glyph with outline path
                        let svgD = cgPathToSVGData(cgPath, translateX: gx, translateY: gy, svgHeight: svgHeight)
                        if !svgD.isEmpty {
                            svg += "<path d=\"\(svgD)\" fill=\"white\"/>\n"
                        }
                    } else {
                        // CTFontCreatePathForGlyph returns nil for some glyphs (minus sign, dots, rules)
                        // Fall back to bounding box rectangle — this is critical for minus signs, hyphens, etc.
                        var glyph = glyphs[i]
                        var boundingRect = CGRect.zero
                        CTFontGetBoundingRectsForGlyphs(font, .default, &glyph, &boundingRect, 1)
                        // Only create a rect if the bounding box has meaningful size
                        if boundingRect.width > 0.01 && boundingRect.height > 0.01 {
                            let rx = gx + boundingRect.origin.x
                            let ry = gy + boundingRect.origin.y
                            let rw = boundingRect.width
                            let rh = boundingRect.height
                            // Y-flip: SVG_y = svgHeight - (CoreText_y + height)
                            let svgY = svgHeight - (ry + rh)
                            svg += "<rect x=\"\(fmt(rx))\" y=\"\(fmt(svgY))\" width=\"\(fmt(rw))\" height=\"\(fmt(rh))\" fill=\"white\"/>\n"
                        }
                    }
                }
            }
        } else if let mathList = display as? MTMathListDisplay {
            // subDisplays positions are RELATIVE to this display → accumulate offsets
            for sub in mathList.subDisplays {
                extractSVGPaths(from: sub, into: &svg, offsetX: x, offsetY: y, svgHeight: svgHeight)
            }
        } else if let fracDisplay = display as? MTFractionDisplay {
            // Fraction: numerator and denominator positions are ABSOLUTE
            // (set via updateNumeratorPosition: self.position.x + centering, self.position.y + numeratorUp)
            // So pass offsetX/Y from PARENT, not from fraction itself
            if let num = fracDisplay.numerator {
                extractSVGPaths(from: num, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
            if let den = fracDisplay.denominator {
                extractSVGPaths(from: den, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
            // Fraction line: drawn at (position.x, position.y + linePosition)
            if fracDisplay.lineThickness > 0 {
                let lineY = svgHeight - (y + fracDisplay.linePosition)
                let lt = max(fracDisplay.lineThickness, 0.5)
                let lx = fmt(x)
                let ly1 = fmt(lineY - lt/2)
                let ly2 = fmt(lineY + lt/2)
                let lx2 = fmt(x + fracDisplay.width)
                svg += "<path d=\"M\(lx) \(ly1)L\(lx2) \(ly1)L\(lx2) \(ly2)L\(lx) \(ly2)Z\" fill=\"white\"/>\n"
            }
        } else if let radDisplay = display as? MTRadicalDisplay {
            // radicand and degree positions are ABSOLUTE
            if let radicand = radDisplay.radicand {
                extractSVGPaths(from: radicand, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
            if let degree = radDisplay.degree {
                extractSVGPaths(from: degree, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
            // Radical glyph: drawn after translate(position.x + radicalShift, position.y)
            // So its effective origin is (x + radicalShift, y)
            if let radGlyph = radDisplay.radicalGlyph {
                let radX = x + radDisplay.radicalShift
                extractSVGPaths(from: radGlyph, into: &svg, offsetX: radX, offsetY: y, svgHeight: svgHeight)
            }
            // Radical overline: drawn at (_radicalGlyph.width, ascent - topKern - lineThickness/2) relative to (position.x + radicalShift, position.y)
            if radDisplay.lineThickness > 0, let radGlyph = radDisplay.radicalGlyph, let radicand = radDisplay.radicand {
                let lineBaseX = x + radDisplay.radicalShift + radGlyph.width
                let lineBaseY = y + radDisplay.ascent - radDisplay.topKern - radDisplay.lineThickness / 2
                let svgLineY = svgHeight - lineBaseY
                let lt = max(radDisplay.lineThickness, 0.4)
                svg += "<path d=\"M\(fmt(lineBaseX)) \(fmt(svgLineY - lt/2))L\(fmt(lineBaseX + radicand.width)) \(fmt(svgLineY - lt/2))L\(fmt(lineBaseX + radicand.width)) \(fmt(svgLineY + lt/2))L\(fmt(lineBaseX)) \(fmt(svgLineY + lt/2))Z\" fill=\"white\"/>\n"
            }
        } else if let largeOp = display as? MTLargeOpLimitsDisplay {
            // nucleus, upperLimit, lowerLimit positions are ABSOLUTE
            if let nucleus = largeOp.nucleus {
                extractSVGPaths(from: nucleus, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
            if let upperLimit = largeOp.upperLimit {
                extractSVGPaths(from: upperLimit, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
            if let lowerLimit = largeOp.lowerLimit {
                extractSVGPaths(from: lowerLimit, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
        } else if let accentDisplay = display as? MTAccentDisplay {
            // accentee position is ABSOLUTE (set to self.position in updateAccenteePosition)
            if let accentee = accentDisplay.accentee {
                extractSVGPaths(from: accentee, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
            // accent glyph is drawn after translate(position.x, position.y)
            // So accent.position is RELATIVE to the display's position
            if let accent = accentDisplay.accent {
                extractSVGPaths(from: accent, into: &svg, offsetX: x, offsetY: y, svgHeight: svgHeight)
            }
        } else if let lineDisplay = display as? MTLineDisplay {
            // inner position is ABSOLUTE (set to self.position in updateInnerPosition)
            if let inner = lineDisplay.inner {
                extractSVGPaths(from: inner, into: &svg, offsetX: offsetX, offsetY: offsetY, svgHeight: svgHeight)
            }
            // Overline/underline: drawn at (position.x, position.y + lineShiftUp)
            if lineDisplay.lineThickness > 0 {
                let lineY = svgHeight - (y + lineDisplay.lineShiftUp)
                let lt = max(lineDisplay.lineThickness, 0.4)
                let innerW = lineDisplay.inner?.width ?? lineDisplay.width
                svg += "<path d=\"M\(fmt(x)) \(fmt(lineY - lt/2))L\(fmt(x + innerW)) \(fmt(lineY - lt/2))L\(fmt(x + innerW)) \(fmt(lineY + lt/2))L\(fmt(x)) \(fmt(lineY + lt/2))Z\" fill=\"white\"/>\n"
            }
        } else if let glyphConst = display as? MTGlyphConstructionDisplay {
            // Extensible delimiters: multiple glyphs assembled vertically
            // Drawn after translate(position.x, position.y - shiftDown)
            guard let mtFont = glyphConst.font else { return }
            let ctFont = mtFont.ctFont!
            let effY = y - glyphConst.shiftDown
            for i in 0..<glyphConst.numGlyphs {
                let gx = x + glyphConst.positions[i].x
                let gy = effY + glyphConst.positions[i].y
                if let cgPath = CTFontCreatePathForGlyph(ctFont, glyphConst.glyphs[i], nil) {
                    let svgD = cgPathToSVGData(cgPath, translateX: gx, translateY: gy, svgHeight: svgHeight)
                    if !svgD.isEmpty {
                        svg += "<path d=\"\(svgD)\" fill=\"white\"/>\n"
                    }
                } else {
                    var g = glyphConst.glyphs[i]
                    var boundingRect = CGRect.zero
                    CTFontGetBoundingRectsForGlyphs(ctFont, .default, &g, &boundingRect, 1)
                    if boundingRect.width > 0.01 && boundingRect.height > 0.01 {
                        let rx = gx + boundingRect.origin.x
                        let ry = gy + boundingRect.origin.y
                        let rw = boundingRect.width
                        let rh = boundingRect.height
                        let svgY = svgHeight - (ry + rh)
                        svg += "<rect x=\"\(fmt(rx))\" y=\"\(fmt(svgY))\" width=\"\(fmt(rw))\" height=\"\(fmt(rh))\" fill=\"white\"/>\n"
                    }
                }
            }
        } else if let glyphDisplay = display as? MTGlyphDisplay {
            // Single large glyph (big operators, delimiters)
            // Drawn after translate(position.x, position.y - shiftDown)
            // Also supports horizontal scaling (scaleX) for stretchy arrows
            guard let mtFont = glyphDisplay.font, let glyph = glyphDisplay.glyph else { return }
            let ctFont = mtFont.ctFont!
            let effY = y - glyphDisplay.shiftDown
            if let cgPath = CTFontCreatePathForGlyph(ctFont, glyph, nil) {
                let svgD: String
                if glyphDisplay.scaleX != 1.0 {
                    svgD = cgPathToSVGData(cgPath, translateX: x, translateY: effY, svgHeight: svgHeight, scaleX: glyphDisplay.scaleX)
                } else {
                    svgD = cgPathToSVGData(cgPath, translateX: x, translateY: effY, svgHeight: svgHeight)
                }
                if !svgD.isEmpty {
                    svg += "<path d=\"\(svgD)\" fill=\"white\"/>\n"
                }
            } else {
                // Fallback: use bounding box rectangle for glyphs without outlines
                var g = glyph
                var boundingRect = CGRect.zero
                CTFontGetBoundingRectsForGlyphs(ctFont, .default, &g, &boundingRect, 1)
                if boundingRect.width > 0.01 && boundingRect.height > 0.01 {
                    let rx = x + boundingRect.origin.x * glyphDisplay.scaleX
                    let ry = effY + boundingRect.origin.y
                    let rw = boundingRect.width * glyphDisplay.scaleX
                    let rh = boundingRect.height
                    let svgY = svgHeight - (ry + rh)
                    svg += "<rect x=\"\(fmt(rx))\" y=\"\(fmt(svgY))\" width=\"\(fmt(rw))\" height=\"\(fmt(rh))\" fill=\"white\"/>\n"
                }
            }
        }
    }

    /// Convert a CGPath to SVG path data string.
    /// CoreText: Y goes UP from glyph origin. SVG: Y goes DOWN from top.
    /// Full transform: SVG_x = tx + glyph_x * sx, SVG_y = svgHeight - (ty + glyph_y)
    private func cgPathToSVGData(_ path: CGPath, translateX tx: CGFloat, translateY ty: CGFloat, svgHeight sh: CGFloat, scaleX sx: CGFloat = 1.0) -> String {
        var d = ""
        path.applyWithBlock { elementPtr in
            let element = elementPtr.pointee
            let pts = element.points
            switch element.type {
            case .moveToPoint:
                d += "M\(fmt(pts[0].x * sx + tx)) \(fmt(sh - (ty + pts[0].y)))"
            case .addLineToPoint:
                d += "L\(fmt(pts[0].x * sx + tx)) \(fmt(sh - (ty + pts[0].y)))"
            case .addQuadCurveToPoint:
                d += "Q\(fmt(pts[0].x * sx + tx)) \(fmt(sh - (ty + pts[0].y))) \(fmt(pts[1].x * sx + tx)) \(fmt(sh - (ty + pts[1].y)))"
            case .addCurveToPoint:
                d += "C\(fmt(pts[0].x * sx + tx)) \(fmt(sh - (ty + pts[0].y))) \(fmt(pts[1].x * sx + tx)) \(fmt(sh - (ty + pts[1].y))) \(fmt(pts[2].x * sx + tx)) \(fmt(sh - (ty + pts[2].y)))"
            case .closeSubpath:
                d += "Z"
            @unknown default:
                break
            }
        }
        return d
    }

    private func fmt(_ v: CGFloat) -> String {
        String(format: "%.3f", v)
    }

    // MARK: - CoreText Plain Text Rendering

    /// Render plain text to SVG using CoreText (perfect unicode support + font fallback).
    /// This handles ALL unicode characters — math symbols, CJK, emoji, etc.
    /// Used by manimpango as a replacement for Cairo text rendering on iOS.
    func renderTextToSVG(text: String, fontName: String, fontSize: CGFloat, svgPath: String,
                         colorHex: String = "#FFFFFF", bold: Bool = false, italic: Bool = false) -> Bool {
        guard !text.isEmpty else { return false }

        // Create font with traits
        var traits: CTFontSymbolicTraits = []
        if bold { traits.insert(.boldTrait) }
        if italic { traits.insert(.italicTrait) }

        var font: CTFont
        if fontName.isEmpty || fontName == "sans-serif" {
            // Use system font — best unicode coverage + automatic font cascade
            font = CTFontCreateUIFontForLanguage(.system, fontSize, nil)!
        } else {
            font = CTFontCreateWithName(fontName as CFString, fontSize, nil)
        }

        // Apply bold/italic traits
        if !traits.isEmpty, let modified = CTFontCreateCopyWithSymbolicTraits(font, fontSize, nil, traits, [.boldTrait, .italicTrait]) {
            font = modified
        }

        // Parse color
        let r: CGFloat, g: CGFloat, b: CGFloat
        if colorHex.count >= 7 && colorHex.hasPrefix("#") {
            let hex = colorHex.dropFirst()
            r = CGFloat(UInt8(hex.prefix(2), radix: 16) ?? 255) / 255.0
            g = CGFloat(UInt8(hex.dropFirst(2).prefix(2), radix: 16) ?? 255) / 255.0
            b = CGFloat(UInt8(hex.dropFirst(4).prefix(2), radix: 16) ?? 255) / 255.0
        } else {
            r = 1; g = 1; b = 1
        }
        let color = UIColor(red: r, green: g, blue: b, alpha: 1.0)

        // Create attributed string
        let attrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: color
        ]
        let attrStr = NSAttributedString(string: text, attributes: attrs)

        // Create CTLine for layout
        let line = CTLineCreateWithAttributedString(attrStr)

        // Measure
        var ascent: CGFloat = 0
        var descent: CGFloat = 0
        var leading: CGFloat = 0
        let lineWidth = CGFloat(CTLineGetTypographicBounds(line, &ascent, &descent, &leading))

        let pad: CGFloat = 1.0
        let svgW = lineWidth + pad * 2
        let svgH = ascent + descent + pad * 2

        // Extract glyph paths from each run
        var svgPaths = ""
        let runs = CTLineGetGlyphRuns(line) as! [CTRun]
        for run in runs {
            let runFont = (CTRunGetAttributes(run) as Dictionary)[kCTFontAttributeName] as! CTFont
            let glyphCount = CTRunGetGlyphCount(run)
            var glyphs = [CGGlyph](repeating: 0, count: glyphCount)
            var positions = [CGPoint](repeating: .zero, count: glyphCount)
            CTRunGetGlyphs(run, CFRangeMake(0, glyphCount), &glyphs)
            CTRunGetPositions(run, CFRangeMake(0, glyphCount), &positions)

            for i in 0..<glyphCount {
                // CoreText positions: x is horizontal, y is baseline-relative
                // We place baseline at y = pad + descent in CoreText coords
                let gx = pad + positions[i].x
                let gy = pad + descent + positions[i].y

                if let cgPath = CTFontCreatePathForGlyph(runFont, glyphs[i], nil) {
                    let svgD = cgPathToSVGData(cgPath, translateX: gx, translateY: gy, svgHeight: svgH)
                    if !svgD.isEmpty {
                        svgPaths += "<path d=\"\(svgD)\" fill=\"white\"/>\n"
                    }
                } else {
                    // Bounding box fallback for glyphs without outlines (minus, rules, etc.)
                    var glyph = glyphs[i]
                    var boundingRect = CGRect.zero
                    CTFontGetBoundingRectsForGlyphs(runFont, .default, &glyph, &boundingRect, 1)
                    if boundingRect.width > 0.01 && boundingRect.height > 0.01 {
                        let rx = gx + boundingRect.origin.x
                        let ry = gy + boundingRect.origin.y
                        let rw = boundingRect.width
                        let rh = boundingRect.height
                        let svgY = svgH - (ry + rh)
                        svgPaths += "<rect x=\"\(fmt(rx))\" y=\"\(fmt(svgY))\" width=\"\(fmt(rw))\" height=\"\(fmt(rh))\" fill=\"white\"/>\n"
                    }
                }
            }
        }

        if svgPaths.isEmpty { return false }

        let svg = """
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="\(svgW)" height="\(svgH)" viewBox="0 0 \(svgW) \(svgH)">
        \(svgPaths)
        </svg>
        """

        do {
            try svg.write(toFile: svgPath, atomically: true, encoding: .utf8)
            return true
        } catch {
            return false
        }
    }

    // MARK: - Signal File Watcher (Python→Swift IPC)

    private var signalTimer: Timer?

    private func startSignalWatcher() {
        DispatchQueue.main.async {
            self.signalTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
                self?.checkForCompileRequest()
                self?.checkForTextRequest()
                self?.checkForDocCompileRequest()
                self?.checkForMathCompileRequest()
                self?.checkForPreviewRequest()
                self?.checkForEditorApplyRequest()
                self?.checkForOpenInEditorRequest()
            }
            // Preload the WASM engine so the first pdflatex call doesn't
            // pay the cold-start tax. busytex is the default path —
            // larger footprint (~230 MB of data packages to stream
            // into MEMFS) but it's the only engine that actually
            // compiles real beamer/tikz docs. SwiftLaTeX stays
            // reachable via `export OFFLINAI_ENGINE=swiftlatex` as a
            // fallback for anyone who explicitly wants pdftex 1.40.21.
            let engine = ProcessInfo.processInfo.environment["OFFLINAI_ENGINE"]?.lowercased()
            if engine == "swiftlatex" || engine == "web" {
                WebLaTeXEngine.shared.preload()
            } else {
                BusytexEngine.shared.preload()
            }
        }
    }

    /// Fired by offlinai_shell when `pdflatex foo.tex` produces a PDF
    /// — surfaces the PDF in the editor's output preview panel. Signal
    /// file contains a single line with the absolute path to the PDF.
    var onPreviewRequest: ((_ pdfPath: String) -> Void)?

    /// Fired by `offlinai_ai` when it applies an AI-authored edit.
    /// Signal file is JSON: `{"path": "/abs/file.py", "content": "…"}`.
    /// CodeEditorViewController hooks this to refresh the Monaco editor
    /// so the on-screen view matches the file on disk — otherwise the
    /// editor's in-memory buffer is stale after an `ai` edit and the
    /// next debounced auto-save overwrites the AI's change.
    var onEditorApplyRequest: ((_ path: String, _ content: String) -> Void)?

    /// Fired by `offlinai_ai` when the user starts the REPL with no
    /// file open — it creates a scratch file and asks the editor to
    /// load it so there's always a target to edit. Signal file is a
    /// plain text with the absolute path to load.
    var onOpenInEditorRequest: ((_ path: String) -> Void)?

    private func checkForOpenInEditorRequest() {
        let signalDir = NSTemporaryDirectory().appending("latex_signals/")
        let signalFile = signalDir.appending("open_in_editor.txt")
        guard FileManager.default.fileExists(atPath: signalFile),
              let content = try? String(contentsOfFile: signalFile, encoding: .utf8) else {
            return
        }
        try? FileManager.default.removeItem(atPath: signalFile)
        let path = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !path.isEmpty,
              FileManager.default.fileExists(atPath: path) else { return }
        onOpenInEditorRequest?(path)
    }

    private func checkForEditorApplyRequest() {
        let signalDir = NSTemporaryDirectory().appending("latex_signals/")
        let signalFile = signalDir.appending("ai_editor_apply.json")
        guard FileManager.default.fileExists(atPath: signalFile),
              let data = try? Data(contentsOf: URL(fileURLWithPath: signalFile)) else {
            return
        }
        try? FileManager.default.removeItem(atPath: signalFile)
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let path = obj["path"] as? String,
              let content = obj["content"] as? String else {
            return
        }
        onEditorApplyRequest?(path, content)
    }

    private func checkForPreviewRequest() {
        let signalDir = NSTemporaryDirectory().appending("latex_signals/")
        let signalFile = signalDir.appending("preview_request.txt")
        guard FileManager.default.fileExists(atPath: signalFile),
              let content = try? String(contentsOfFile: signalFile,
                                        encoding: .utf8) else {
            return
        }
        try? FileManager.default.removeItem(atPath: signalFile)
        let payload = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !payload.isEmpty else { return }
        // pywebview shim sends http(s):// URLs raw — those need to be
        // loaded by the WKWebView with their real origin (cookies,
        // CSP, referer, first-party storage all key off scheme+host).
        // Wrapping them in a file:// meta-refresh redirect breaks all
        // of that. So pass the URL through as-is and let the preview
        // controller route http(s) → URLRequest, file path → file URL.
        if payload.hasPrefix("http://") || payload.hasPrefix("https://") {
            onPreviewRequest?(payload)
            return
        }
        guard FileManager.default.fileExists(atPath: payload) else { return }
        onPreviewRequest?(payload)
    }

    // MARK: WASM-based pdflatex bridge
    //
    // Python-side writes a request file at
    //   $TMPDIR/latex_signals/compile_doc_request.txt
    // with format:
    //   Line 1: input .tex file path (absolute, must exist on disk)
    //   Line 2: output .pdf file path (absolute, parent must be writable)
    //   Line 3: optional "jobname" (filename without extension, used by
    //           pdftex for aux/log output)
    //
    // We hand the source to WebLaTeXEngine (WKWebView + WASM pdftex)
    // which runs the real pdflatex entirely offline — no crash-prone
    // C library ever touched. When it completes, we write:
    //   - the PDF bytes to the requested output path
    //   - a sidecar "<output>.log" with pdftex's transcript
    //   - a tiny "<request_id>_done.txt" marker next to the request file
    //     so Python can detect completion.
    private var compileDocInFlight = false

    private func checkForDocCompileRequest() {
        guard !compileDocInFlight else { return }
        let signalDir = NSTemporaryDirectory().appending("latex_signals/")
        let signalFile = signalDir.appending("compile_doc_request.txt")
        guard FileManager.default.fileExists(atPath: signalFile),
              let content = try? String(contentsOfFile: signalFile,
                                        encoding: .utf8) else {
            return
        }
        try? FileManager.default.removeItem(atPath: signalFile)

        let lines = content.components(separatedBy: "\n")
        guard lines.count >= 2 else { return }
        let texPath = lines[0].trimmingCharacters(in: .whitespacesAndNewlines)
        let pdfPath = lines[1].trimmingCharacters(in: .whitespacesAndNewlines)
        let jobname = lines.count >= 3
            ? lines[2].trimmingCharacters(in: .whitespacesAndNewlines)
            : (texPath as NSString).deletingPathExtension
        // Line 4 (new): command the user invoked (pdflatex/xelatex/latex).
        // Used to pick the busytex driver. Absent for old Python callers,
        // defaults to pdflatex.
        let invokedCommand = (lines.count >= 4
            ? lines[3].trimmingCharacters(in: .whitespacesAndNewlines)
            : "pdflatex").lowercased()
        guard !texPath.isEmpty, !pdfPath.isEmpty,
              let source = try? String(contentsOfFile: texPath, encoding: .utf8) else {
            writeDoneMarker(signalDir: signalDir, status: -99,
                            message: "can't read input .tex")
            return
        }

        compileDocInFlight = true
        let mainName = (jobname.isEmpty ? "main" : jobname) + ".tex"
        // Pass the .tex file's directory so sibling assets (images,
        // \input-ed subfiles, .bib files) are findable by the engine.
        let workingDir = URL(fileURLWithPath: texPath).deletingLastPathComponent()

        // Register a progress pipe the Python shell can tail. Truncate
        // so only THIS compile's milestones show up; Python seeks to EOF
        // before polling so stale content from a prior compile is
        // invisible anyway.
        let progressPath = signalDir + "compile_progress.log"
        FileManager.default.createFile(atPath: progressPath, contents: nil)

        // Engine choice: busytex by default (pdftex 1.40.25 + xetex +
        // luatex, preloaded texmf via MEMFS — the only path that
        // actually compiles real beamer/tikz docs). SwiftLaTeX
        // (pdftex 1.40.21) stays reachable as a fallback via
        // `export OFFLINAI_ENGINE=swiftlatex` for the rare case
        // someone needs it (e.g. debugging the older engine).
        let engineChoice: String = {
            let env = ProcessInfo.processInfo.environment["OFFLINAI_ENGINE"]?.lowercased()
            if env == "swiftlatex" || env == "web" { return "swiftlatex" }
            return "busytex"
        }()
        // Only pdflatex is supported. xelatex was removed — the
        // CJK/fontspec/fontconfig plumbing it needs (bundled Noto
        // CJK fonts, /etc/fonts setup, ctex hooks) was adding
        // 30+ MB of app size for a feature most users don't touch.
        // Anything that's not explicitly pdflatex still routes to
        // the pdftex driver — it's lenient and handles plain TeX /
        // raw DVI requests acceptably.
        let busytexDriver = "pdftex_bibtex8"
        _ = invokedCommand  // silence unused-variable warning
        let completion: (Int, String, Data?) -> Void = { [weak self] status, logText, pdfData in
            defer {
                self?.compileDocInFlight = false
                // Unhook both progress pipes — editor-side compiles
                // shouldn't clutter the shell's progress file.
                WebLaTeXEngine.shared.shellProgressPath = nil
                BusytexEngine.shared.shellProgressPath = nil
            }
            // Always write the log so user can diagnose.
            let logPath = (pdfPath as NSString).deletingPathExtension + ".log"
            try? logText.write(toFile: logPath, atomically: true, encoding: .utf8)
            if let pdf = pdfData, status == 0 {
                do {
                    try pdf.write(to: URL(fileURLWithPath: pdfPath))
                    self?.writeDoneMarker(signalDir: signalDir, status: 0,
                                          message: "ok (\(pdf.count) bytes)")
                } catch {
                    self?.writeDoneMarker(signalDir: signalDir, status: -1,
                                          message: "write failed: \(error)")
                }
            } else {
                self?.writeDoneMarker(signalDir: signalDir, status: status,
                                      message: "compile failed (status=\(status))")
            }
        }
        if engineChoice == "swiftlatex" {
            WebLaTeXEngine.shared.shellProgressPath = progressPath
            WebLaTeXEngine.shared.compile(texSource: source,
                                           mainFileName: mainName,
                                           workingDir: workingDir,
                                           completion: completion)
        } else {
            BusytexEngine.shared.shellProgressPath = progressPath
            BusytexEngine.shared.compile(texSource: source,
                                          mainFileName: mainName,
                                          workingDir: workingDir,
                                          driver: busytexDriver,
                                          completion: completion)
        }
    }

    private func writeDoneMarker(signalDir: String, status: Int, message: String) {
        let markerPath = signalDir + "compile_doc_done.txt"
        let text = "\(status)\n\(message)\n"
        try? text.write(toFile: markerPath, atomically: true, encoding: .utf8)
    }

    // MARK: - Math compile request (manim MathTex → real LaTeX → PNG → SVG)
    //
    // Python (offlinai_latex.tex_to_svg) writes a request file at
    //   $TMPDIR/latex_signals/compile_math_request.txt
    // with format:
    //   Line 1: request id (sha256[:16] of expression — used in done marker)
    //   Line 2: output SVG path (Python's caller expects this written)
    //   Line 3: foreground color hex (#FFFFFF or 6-digit, optional — defaults FFFFFF)
    //   Line 4+: math expression (literal LaTeX, may span multiple lines
    //            but newlines are preserved into the wrapped document)
    //
    // We hand the expression to BusytexEngine.compileMath which produces
    // a real PDF via xelatex (full LaTeX, ctex/xeCJK for CJK in \text{...}),
    // then rasterise the PDF page to a high-DPI PNG, embed as base64
    // <image> in an SVG, and write to `svgPath`. Python polls for
    // `math_done_<requestId>.txt` to detect completion.
    private var compileMathInFlight = false
    /// When the current in-flight compile started. If it overruns the
    /// watchdog, we orphan it so a stuck WASM call doesn't permanently
    /// block every subsequent MathTex compile (manifests as the "last
    /// few scenes show SwiftMath placeholder" symptom).
    private var compileMathStartedAt: Date?
    /// Bookkeeping for the orphaned-request done marker.
    private var compileMathInFlightId: String?
    private var compileMathInFlightSignalDir: String?

    /// Hard cap on a single math compile. Cold-start BusyTeX needs ~30 s
    /// for WASM + texmf preload; warm compiles take 1–3 s. 90 s is a
    /// generous ceiling — anything longer means the WASM call hung.
    private let mathCompileWatchdogSeconds: TimeInterval = 90.0

    private func checkForMathCompileRequest() {
        // Watchdog: if the current compile has been in-flight too long,
        // write a failure done marker for the orphaned request and let
        // the next one through. The orphaned compile may still complete
        // and write its SVG — manim caches by filename hash so a late
        // overwrite is harmless.
        if compileMathInFlight,
           let startedAt = compileMathStartedAt,
           Date().timeIntervalSince(startedAt) > mathCompileWatchdogSeconds {
            if let dir = compileMathInFlightSignalDir,
               let id = compileMathInFlightId {
                writeMathDoneMarker(signalDir: dir, requestId: id,
                                    status: -98, message: "compile watchdog tripped")
            }
            compileMathInFlight = false
            compileMathStartedAt = nil
            compileMathInFlightId = nil
            compileMathInFlightSignalDir = nil
        }
        guard !compileMathInFlight else { return }
        let signalDir = NSTemporaryDirectory().appending("latex_signals/")
        let signalFile = signalDir.appending("compile_math_request.txt")
        guard FileManager.default.fileExists(atPath: signalFile),
              let content = try? String(contentsOfFile: signalFile, encoding: .utf8) else {
            return
        }
        try? FileManager.default.removeItem(atPath: signalFile)

        let lines = content.components(separatedBy: "\n")
        guard lines.count >= 4 else { return }
        let requestId = lines[0].trimmingCharacters(in: .whitespacesAndNewlines)
        let svgPath = lines[1].trimmingCharacters(in: .whitespacesAndNewlines)
        let colorHex = lines[2].trimmingCharacters(in: .whitespacesAndNewlines)
        let expression = lines[3...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)

        guard !requestId.isEmpty, !svgPath.isEmpty, !expression.isEmpty else {
            writeMathDoneMarker(signalDir: signalDir, requestId: requestId.isEmpty ? "unknown" : requestId,
                                status: -10, message: "missing request fields")
            return
        }

        compileMathInFlight = true
        compileMathStartedAt = Date()
        compileMathInFlightId = requestId
        compileMathInFlightSignalDir = signalDir
        let color = colorHex.isEmpty ? "FFFFFF" : colorHex

        BusytexEngine.shared.compileMath(
            expression: expression, colorHex: color
        ) { [weak self] status, logText, pdfData in
            defer {
                // Only clear in-flight bookkeeping if this callback owns
                // it. If the watchdog already tripped and a newer compile
                // is now running, leave its bookkeeping alone.
                if self?.compileMathInFlightId == requestId {
                    self?.compileMathInFlight = false
                    self?.compileMathStartedAt = nil
                    self?.compileMathInFlightId = nil
                    self?.compileMathInFlightSignalDir = nil
                }
            }
            guard let self else { return }
            // Always write a log next to the SVG for diagnostics.
            let logPath = (svgPath as NSString).deletingPathExtension + ".latex.log"
            try? logText.write(toFile: logPath, atomically: true, encoding: .utf8)

            guard status == 0, let pdf = pdfData else {
                self.writeMathDoneMarker(signalDir: signalDir, requestId: requestId,
                                         status: status,
                                         message: "xelatex failed")
                return
            }

            // Render PDF page 1 to PNG at 4x DPI off the main thread.
            DispatchQueue.global(qos: .userInitiated).async {
                guard let rendered = self.renderPDFToPNG(pdfData: pdf, scale: 4.0) else {
                    self.writeMathDoneMarker(signalDir: signalDir, requestId: requestId,
                                              status: -11,
                                              message: "PDF→PNG render failed")
                    return
                }
                let svg = self.buildImageSVG(pngData: rendered.pngData,
                                              widthPt: rendered.widthPt,
                                              heightPt: rendered.heightPt)
                do {
                    try svg.write(toFile: svgPath, atomically: true, encoding: .utf8)
                    self.writeMathDoneMarker(signalDir: signalDir, requestId: requestId,
                                              status: 0,
                                              message: "ok (\(rendered.pngData.count) bytes)")
                } catch {
                    self.writeMathDoneMarker(signalDir: signalDir, requestId: requestId,
                                              status: -12,
                                              message: "svg write failed: \(error)")
                }
            }
        }
    }

    private func writeMathDoneMarker(signalDir: String, requestId: String,
                                      status: Int, message: String) {
        let markerPath = signalDir + "math_done_\(requestId).txt"
        let text = "\(status)\n\(message)\n"
        try? text.write(toFile: markerPath, atomically: true, encoding: .utf8)
    }

    /// Render the first page of `pdfData` to PNG bytes. `scale` is the
    /// DPI multiplier — 4.0 means 288 DPI on a 72 DPI PDF, which keeps
    /// math glyphs sharp at any reasonable manim zoom level.
    /// Returns nil on parse / draw failure.
    private func renderPDFToPNG(pdfData: Data, scale: CGFloat) -> (pngData: Data, widthPt: CGFloat, heightPt: CGFloat)? {
        guard let document = PDFDocument(data: pdfData),
              let page = document.page(at: 0) else { return nil }
        let bounds = page.bounds(for: .mediaBox)
        guard bounds.width > 0, bounds.height > 0 else { return nil }
        let pixelSize = CGSize(width: bounds.width * scale,
                                height: bounds.height * scale)

        let format = UIGraphicsImageRendererFormat()
        format.scale = 1.0
        format.opaque = false
        let renderer = UIGraphicsImageRenderer(size: pixelSize, format: format)
        let image = renderer.image { ctx in
            let cg = ctx.cgContext
            // PDF coordinate system has y going up from bottom; UIKit
            // graphics context has y going down from top — flip + scale
            // so the page lands right-side-up at the requested DPI.
            cg.saveGState()
            cg.translateBy(x: 0, y: pixelSize.height)
            cg.scaleBy(x: scale, y: -scale)
            page.draw(with: .mediaBox, to: cg)
            cg.restoreGState()
        }
        guard let pngData = image.pngData() else { return nil }
        return (pngData, bounds.width, bounds.height)
    }

    /// Build a minimal SVG that wraps a single base64-PNG image. The
    /// SVG dimensions are in PDF points (1pt = 1/72 inch) so manim's
    /// SCALE_FACTOR_PER_FONT_POINT math gives the same on-screen size
    /// as desktop dvisvgm output. Manim's patched svg_mobject.py
    /// recognises `<image>` and produces an ImageMobject from the PNG.
    private func buildImageSVG(pngData: Data, widthPt: CGFloat, heightPt: CGFloat) -> String {
        let b64 = pngData.base64EncodedString()
        let w = String(format: "%.3f", Double(widthPt))
        let h = String(format: "%.3f", Double(heightPt))
        return """
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="\(w)pt" height="\(h)pt" viewBox="0 0 \(w) \(h)">
        <image x="0" y="0" width="\(w)" height="\(h)" preserveAspectRatio="none" xlink:href="data:image/png;base64,\(b64)"/>
        </svg>
        """
    }

    // MARK: LaTeX signal handler

    private func checkForCompileRequest() {
        let signalDir = NSTemporaryDirectory().appending("latex_signals/")
        let signalFile = signalDir.appending("compile_request.txt")

        guard FileManager.default.fileExists(atPath: signalFile),
              let content = try? String(contentsOfFile: signalFile, encoding: .utf8) else {
            return
        }

        // Delete signal file immediately to prevent re-processing
        try? FileManager.default.removeItem(atPath: signalFile)

        let lines = content.components(separatedBy: "\n")
        guard lines.count >= 2 else { return }

        let expression = lines[0].trimmingCharacters(in: .whitespacesAndNewlines)
        let svgPath = lines[1].trimmingCharacters(in: .whitespacesAndNewlines)

        guard !expression.isEmpty, !svgPath.isEmpty else { return }

        print("[LaTeX] Signal: '\(expression.prefix(50))' → \(svgPath)")

        // Render synchronously with SwiftMath (fast, no async needed)
        let success = renderToSVG(expression: expression, svgPath: svgPath)

        if !success {
            // No silent fallback. Write a bright error SVG with the
            // SwiftMath failure so it shows up in the rendered video.
            // Python's `tex_to_svg` then surfaces the failure too — but
            // even if it didn't, the user would see exactly which
            // expression broke instead of a vague placeholder.
            print("[LaTeX] SwiftMath failed for: \(expression.prefix(120))")
            let esc = expression
                .replacingOccurrences(of: "&", with: "&amp;")
                .replacingOccurrences(of: "<", with: "&lt;")
                .replacingOccurrences(of: ">", with: "&gt;")
            let errSvg = """
            <?xml version="1.0" encoding="UTF-8"?>
            <svg xmlns="http://www.w3.org/2000/svg" width="640" height="40" viewBox="0 0 640 40">
              <rect x="0" y="0" width="640" height="40" fill="#220000"/>
              <g id="unique000">
                <path d="M 0 0 L 640 0 L 640 40 L 0 40 Z" fill="#ff5555"/>
                <text x="4" y="14" font-family="monospace" font-size="11" fill="white">SwiftMath failed</text>
                <text x="4" y="30" font-family="monospace" font-size="11" fill="white">\(esc.prefix(80))</text>
              </g>
            </svg>
            """
            try? errSvg.write(toFile: svgPath, atomically: true, encoding: .utf8)
        }
    }

    // MARK: Plain text signal handler

    /// Signal file format for text rendering:
    /// Line 1: TEXT (literal marker)
    /// Line 2: SVG output path
    /// Line 3: font name (or empty for system font)
    /// Line 4: font size (number)
    /// Line 5: color hex (#FFFFFF)
    /// Line 6: style flags (bold,italic or empty)
    /// Line 7+: the actual text content (may span multiple lines)
    private func checkForTextRequest() {
        let signalDir = NSTemporaryDirectory().appending("latex_signals/")
        let signalFile = signalDir.appending("text_request.txt")

        guard FileManager.default.fileExists(atPath: signalFile),
              let content = try? String(contentsOfFile: signalFile, encoding: .utf8) else {
            return
        }

        try? FileManager.default.removeItem(atPath: signalFile)

        let lines = content.components(separatedBy: "\n")
        guard lines.count >= 7, lines[0].trimmingCharacters(in: .whitespacesAndNewlines) == "TEXT" else { return }

        let svgPath = lines[1].trimmingCharacters(in: .whitespacesAndNewlines)
        let fontName = lines[2].trimmingCharacters(in: .whitespacesAndNewlines)
        let fontSize = CGFloat(Double(lines[3].trimmingCharacters(in: .whitespacesAndNewlines)) ?? 12.0)
        let colorHex = lines[4].trimmingCharacters(in: .whitespacesAndNewlines)
        let styleFlags = lines[5].trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        // Text content is everything from line 6 onwards (may contain newlines)
        let textContent = lines[6...].joined(separator: "\n")

        guard !svgPath.isEmpty, !textContent.isEmpty else { return }

        let bold = styleFlags.contains("bold")
        let italic = styleFlags.contains("italic")

        let success = renderTextToSVG(text: textContent, fontName: fontName, fontSize: fontSize,
                                       svgPath: svgPath, colorHex: colorHex, bold: bold, italic: italic)

        if !success {
            // Write minimal fallback
            let esc = textContent
                .replacingOccurrences(of: "&", with: "&amp;")
                .replacingOccurrences(of: "<", with: "&lt;")
                .replacingOccurrences(of: ">", with: "&gt;")
            let w = max(Double(textContent.count) * Double(fontSize) * 0.6, 20)
            let h = Double(fontSize) * 1.5
            let fallback = """
            <?xml version="1.0" encoding="UTF-8"?>
            <svg xmlns="http://www.w3.org/2000/svg" width="\(w)" height="\(h)" viewBox="0 0 \(w) \(h)">
            <text x="0" y="\(fontSize)" font-size="\(fontSize)" fill="white">\(esc.prefix(80))</text>
            </svg>
            """
            try? fallback.write(toFile: svgPath, atomically: true, encoding: .utf8)
        }
    }
}
