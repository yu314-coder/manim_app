// EditorView.swift — native NSTextView-backed code editor with
// minimal Python syntax highlighting. Keeps the editor 100% Swift,
// no WKWebView, no Monaco bundle. Trades feature density (no
// IntelliSense, no linting) for boot speed, low memory, and a
// faithful AppKit feel.
//
// Highlighter pipeline:
//   text changes → NSTextStorage.didProcessEditing → debounced
//   re-tokenization (PythonTokens) → NSAttributedString colors.
// Re-tokenizes the entire visible buffer; for files <50 KB this
// is sub-millisecond on M-series.
import SwiftUI
import AppKit

struct EditorView: NSViewRepresentable {
    @Binding var text: String
    var fontSize: CGFloat = 13

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSTextView.scrollableTextView()
        guard let tv = scroll.documentView as? NSTextView else { return scroll }

        tv.delegate = context.coordinator
        tv.allowsUndo = true
        tv.isAutomaticQuoteSubstitutionEnabled = false
        tv.isAutomaticDashSubstitutionEnabled  = false
        tv.isAutomaticTextReplacementEnabled   = false
        tv.isAutomaticSpellingCorrectionEnabled = false
        tv.isAutomaticDataDetectionEnabled = false
        tv.isAutomaticLinkDetectionEnabled = false
        tv.isContinuousSpellCheckingEnabled = false
        tv.isGrammarCheckingEnabled = false
        tv.usesFindBar = true
        tv.isIncrementalSearchingEnabled = true

        tv.backgroundColor = NSColor(srgbRed: 0.055, green: 0.055, blue: 0.075, alpha: 1)
        tv.drawsBackground = true
        tv.textColor = NSColor(white: 0.93, alpha: 1)
        tv.insertionPointColor = NSColor(srgbRed: 0.39, green: 0.40, blue: 0.95, alpha: 1)
        tv.font = NSFont.monospacedSystemFont(ofSize: fontSize, weight: .regular)
        tv.textContainerInset = NSSize(width: 6, height: 8)

        // Tab = 4 spaces (Python convention).
        let tabStop = NSTextTab(textAlignment: .left, location: 4 * 7)
        let pStyle  = NSMutableParagraphStyle()
        pStyle.tabStops = [tabStop]
        pStyle.defaultTabInterval = 4 * 7
        tv.defaultParagraphStyle = pStyle

        tv.string = text
        context.coordinator.textView = tv
        context.coordinator.applyHighlighting()
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let tv = scroll.documentView as? NSTextView else { return }
        if tv.string != text {
            // External update (e.g. Open file). Keep the cursor at start.
            tv.string = text
            context.coordinator.applyHighlighting()
        }
        if tv.font?.pointSize != fontSize {
            tv.font = NSFont.monospacedSystemFont(ofSize: fontSize, weight: .regular)
            context.coordinator.applyHighlighting()
        }
    }

    func makeCoordinator() -> Coord { Coord(self) }

    final class Coord: NSObject, NSTextViewDelegate {
        var parent: EditorView
        weak var textView: NSTextView?
        private var debounce: DispatchWorkItem?

        init(_ p: EditorView) { parent = p }

        func textDidChange(_ note: Notification) {
            guard let tv = textView else { return }
            parent.text = tv.string
            // Re-highlight on a short debounce so fast typing doesn't
            // spend cycles re-coloring the whole buffer per keystroke.
            debounce?.cancel()
            let work = DispatchWorkItem { [weak self] in self?.applyHighlighting() }
            debounce = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.08, execute: work)
        }

        // ── Highlighting ──────────────────────────────────────

        func applyHighlighting() {
            guard let tv = textView, let storage = tv.textStorage else { return }
            let src = tv.string as NSString
            let full = NSRange(location: 0, length: src.length)

            storage.beginEditing()
            // Reset to default attributes.
            storage.removeAttribute(.foregroundColor, range: full)
            storage.addAttribute(.foregroundColor,
                                 value: NSColor(white: 0.93, alpha: 1),
                                 range: full)
            for token in PythonTokens.tokenize(src as String) {
                storage.addAttribute(.foregroundColor,
                                     value: token.kind.nsColor,
                                     range: NSRange(location: token.start,
                                                    length: token.length))
            }
            storage.endEditing()
        }
    }
}

// MARK: - tokenizer

private enum PythonTokens {

    enum Kind {
        case keyword, builtin, string, number, comment, decorator, defName
        var nsColor: NSColor {
            switch self {
            case .keyword:   return NSColor(srgbRed: 0.78, green: 0.42, blue: 0.97, alpha: 1)
            case .builtin:   return NSColor(srgbRed: 0.34, green: 0.66, blue: 0.97, alpha: 1)
            case .string:    return NSColor(srgbRed: 0.55, green: 0.84, blue: 0.40, alpha: 1)
            case .number:    return NSColor(srgbRed: 0.96, green: 0.62, blue: 0.04, alpha: 1)
            case .comment:   return NSColor(white: 0.50, alpha: 1)
            case .decorator: return NSColor(srgbRed: 1.00, green: 0.60, blue: 0.30, alpha: 1)
            case .defName:   return NSColor(srgbRed: 0.96, green: 0.78, blue: 0.34, alpha: 1)
            }
        }
    }

    struct Token { let start: Int; let length: Int; let kind: Kind }

    private static let keywords: Set<String> = [
        "False", "None", "True", "and", "as", "assert", "async", "await",
        "break", "class", "continue", "def", "del", "elif", "else", "except",
        "finally", "for", "from", "global", "if", "import", "in", "is",
        "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
        "while", "with", "yield", "match", "case",
    ]
    private static let builtins: Set<String> = [
        "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
        "callable", "chr", "classmethod", "complex", "delattr", "dict",
        "dir", "divmod", "enumerate", "eval", "exec", "filter", "float",
        "format", "frozenset", "getattr", "globals", "hasattr", "hash",
        "help", "hex", "id", "input", "int", "isinstance", "issubclass",
        "iter", "len", "list", "locals", "map", "max", "memoryview", "min",
        "next", "object", "oct", "open", "ord", "pow", "print", "property",
        "range", "repr", "reversed", "round", "set", "setattr", "slice",
        "sorted", "staticmethod", "str", "sum", "super", "tuple", "type",
        "vars", "zip", "self",
    ]

    static func tokenize(_ src: String) -> [Token] {
        let chars = Array(src.utf16)
        var tokens: [Token] = []
        var i = 0
        let n = chars.count

        func isIdStart(_ c: UTF16.CodeUnit) -> Bool {
            return (c == 0x5F) || (c >= 0x41 && c <= 0x5A) || (c >= 0x61 && c <= 0x7A)
        }
        func isIdCont(_ c: UTF16.CodeUnit) -> Bool {
            return isIdStart(c) || (c >= 0x30 && c <= 0x39)
        }
        func isDigit(_ c: UTF16.CodeUnit) -> Bool { c >= 0x30 && c <= 0x39 }

        while i < n {
            let c = chars[i]

            // Comment to end of line.
            if c == 0x23 {
                let start = i
                while i < n && chars[i] != 0x0A { i += 1 }
                tokens.append(Token(start: start, length: i - start, kind: .comment))
                continue
            }
            // String literals (no triple-quote tracking — treat each
            // run of single/double-quoted chars as one span).
            if c == 0x22 || c == 0x27 {
                let q = c
                let start = i
                i += 1
                // Triple-quote detection.
                let isTriple = (i + 1 < n && chars[i] == q && chars[i + 1] == q)
                if isTriple {
                    i += 2
                    while i + 2 < n {
                        if chars[i] == q && chars[i + 1] == q && chars[i + 2] == q {
                            i += 3; break
                        }
                        i += 1
                    }
                } else {
                    while i < n && chars[i] != q && chars[i] != 0x0A {
                        if chars[i] == 0x5C && i + 1 < n { i += 2; continue } // escape
                        i += 1
                    }
                    if i < n && chars[i] == q { i += 1 }
                }
                tokens.append(Token(start: start, length: i - start, kind: .string))
                continue
            }
            // Decorator.
            if c == 0x40 && (i == 0 || chars[i - 1] == 0x0A || chars[i - 1] == 0x20) {
                let start = i
                i += 1
                while i < n && isIdCont(chars[i]) { i += 1 }
                if i > start + 1 {
                    tokens.append(Token(start: start, length: i - start, kind: .decorator))
                    continue
                }
            }
            // Identifier / keyword.
            if isIdStart(c) {
                let start = i
                while i < n && isIdCont(chars[i]) { i += 1 }
                let len = i - start
                let str = String(decoding: chars[start..<i], as: UTF16.self)
                if keywords.contains(str) {
                    tokens.append(Token(start: start, length: len, kind: .keyword))
                    // After "def" / "class", color the name.
                    if str == "def" || str == "class" {
                        var j = i
                        while j < n && (chars[j] == 0x20 || chars[j] == 0x09) { j += 1 }
                        if j < n && isIdStart(chars[j]) {
                            let ns = j
                            while j < n && isIdCont(chars[j]) { j += 1 }
                            tokens.append(Token(start: ns, length: j - ns, kind: .defName))
                            i = j
                        }
                    }
                } else if builtins.contains(str) {
                    tokens.append(Token(start: start, length: len, kind: .builtin))
                }
                continue
            }
            // Number.
            if isDigit(c) {
                let start = i
                while i < n {
                    let cc = chars[i]
                    if isDigit(cc) || cc == 0x2E /* . */
                        || cc == 0x65 || cc == 0x45 /* e/E */
                        || cc == 0x78 || cc == 0x58 /* x/X */
                        || (cc >= 0x61 && cc <= 0x66)  /* a-f */
                        || (cc >= 0x41 && cc <= 0x46)  /* A-F */
                        || cc == 0x5F /* _ */
                    { i += 1 } else { break }
                }
                tokens.append(Token(start: start, length: i - start, kind: .number))
                continue
            }
            i += 1
        }
        return tokens
    }
}
