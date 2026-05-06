// TerminalView.swift — read-only NSTextView showing manim's
// stdout/stderr stream from RenderManager. Auto-scrolls to the
// bottom on new content. ANSI escape codes are stripped so the
// raw bytes don't show up as garbage characters.
import SwiftUI
import AppKit

struct TerminalView: NSViewRepresentable {
    @Binding var text: String
    var fontSize: CGFloat = 12

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSTextView.scrollableTextView()
        guard let tv = scroll.documentView as? NSTextView else { return scroll }

        tv.isEditable = false
        tv.isSelectable = true
        tv.allowsUndo = false
        tv.isAutomaticTextReplacementEnabled = false
        tv.usesFindBar = true
        tv.backgroundColor = NSColor.black
        tv.drawsBackground = true
        tv.textColor = NSColor(white: 0.93, alpha: 1)
        tv.font = NSFont.monospacedSystemFont(ofSize: fontSize, weight: .regular)
        tv.textContainerInset = NSSize(width: 6, height: 6)

        context.coordinator.textView = tv
        context.coordinator.apply(text)
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.apply(text)
    }

    func makeCoordinator() -> Coord { Coord() }

    final class Coord {
        weak var textView: NSTextView?
        private var lastApplied = ""

        func apply(_ text: String) {
            guard let tv = textView else { return }
            if text == lastApplied { return }
            // Append-only fast path — only the suffix changed.
            if text.hasPrefix(lastApplied) {
                let suffix = String(text.dropFirst(lastApplied.count))
                let cleaned = stripAnsi(suffix)
                if !cleaned.isEmpty {
                    let attr = NSAttributedString(string: cleaned, attributes: [
                        .font: tv.font ?? NSFont.monospacedSystemFont(
                            ofSize: 12, weight: .regular),
                        .foregroundColor: NSColor(white: 0.93, alpha: 1),
                    ])
                    tv.textStorage?.append(attr)
                    tv.scrollToEndOfDocument(nil)
                }
            } else {
                // Hard reset (clear-terminal etc.).
                tv.string = stripAnsi(text)
                tv.scrollToEndOfDocument(nil)
            }
            lastApplied = text
        }

        /// Strip ANSI CSI sequences (`ESC [ ... letter`) and the
        /// occasional bare `\r` so the raw stream renders cleanly
        /// in a text view that doesn't speak terminal escapes.
        private func stripAnsi(_ s: String) -> String {
            var out = ""
            out.reserveCapacity(s.count)
            var i = s.startIndex
            while i < s.endIndex {
                let c = s[i]
                if c == "\u{1B}" {
                    // ESC — try to parse a CSI and skip it.
                    let next = s.index(after: i)
                    if next < s.endIndex && s[next] == "[" {
                        var j = s.index(after: next)
                        while j < s.endIndex {
                            let cc = s[j]
                            if cc.isLetter || cc == "~" {
                                j = s.index(after: j)
                                break
                            }
                            j = s.index(after: j)
                        }
                        i = j
                        continue
                    }
                    // ESC followed by something else — skip just ESC.
                    i = next
                    continue
                }
                if c == "\r" {
                    // Convert bare \r to nothing (tqdm progress bars
                    // would otherwise rewrite the same line via \r;
                    // in a non-TTY view that just looks like clutter).
                    i = s.index(after: i)
                    continue
                }
                out.append(c)
                i = s.index(after: i)
            }
            return out
        }
    }
}
