// PythonFormatter.swift — minimal, safe-by-default formatter for the
// editor buffer. Triggered by ⌥⌘L from the Code menu.
//
// What it does:
//   • Replaces leading tabs with 4 spaces (PEP 8 default).
//   • Strips trailing whitespace on every line.
//   • Collapses runs of 3+ blank lines to exactly 2.
//   • Ensures the file ends with exactly one trailing newline.
//   • Adds a single space after `#` for inline comments that don't
//     have one (`#foo` → `# foo`), but only when the `#` isn't part
//     of a string literal (best-effort: skip tokens inside quotes).
//
// What it deliberately doesn't do:
//   • Reflow long lines, reorder imports, change quote style, or
//     touch indentation depth — anything that requires real parsing
//     can break working code on iOS where we don't ship `black`.
//   • Format inside triple-quoted strings — those are detected and
//     left alone.
//
// Round-trips on its own output.
import Foundation

enum PythonFormatter {
    static func format(_ source: String) -> String {
        let normalized = source.replacingOccurrences(of: "\r\n", with: "\n")
        var lines = normalized.split(separator: "\n", omittingEmptySubsequences: false)
            .map { String($0) }

        var inTripleQuote: Character? = nil  // " or '

        for i in lines.indices {
            var line = lines[i]

            // Detect triple-quote toggles before any rewrite — odd
            // count of triple quotes flips the state for the rest
            // of the buffer.
            let stateBefore = inTripleQuote
            inTripleQuote = updatedTripleQuoteState(line: line, current: inTripleQuote)

            if stateBefore != nil {
                // Inside a triple-quoted string for the entirety of
                // (or part of) this line — leave it untouched.
                lines[i] = line
                continue
            }

            // Leading-tab → 4-space conversion. Only on indentation;
            // tabs INSIDE a line are too risky to touch.
            line = expandLeadingTabs(line)

            // Trailing whitespace.
            while let last = line.last, last == " " || last == "\t" {
                line.removeLast()
            }

            // Inline comment spacing — `#foo` → `# foo`. Skip if the
            // `#` is inside a string. We do a tiny tokenizer pass
            // tracking single/double quotes only.
            line = normalizeCommentSpace(line)

            lines[i] = line
        }

        // Collapse 3+ blank lines down to 2.
        var collapsed: [String] = []
        var blankRun = 0
        for line in lines {
            if line.isEmpty {
                blankRun += 1
                if blankRun <= 2 { collapsed.append(line) }
            } else {
                blankRun = 0
                collapsed.append(line)
            }
        }
        // Strip leading blank lines (trim only at top — bottom is
        // handled separately so the file ends with one \n).
        while collapsed.first == "" { collapsed.removeFirst() }
        // Strip trailing blanks; we'll re-add exactly one.
        while collapsed.last == "" { collapsed.removeLast() }

        return collapsed.joined(separator: "\n") + "\n"
    }

    // MARK: helpers

    private static func expandLeadingTabs(_ line: String) -> String {
        var out = ""
        var iterator = line.makeIterator()
        var inLeading = true
        while let c = iterator.next() {
            if inLeading && c == "\t" { out.append("    "); continue }
            if c != " " && c != "\t" { inLeading = false }
            out.append(c)
        }
        return out
    }

    /// Toggle when a line contains an odd number of triple quotes.
    /// Returns the state at end-of-line. `current` is the state at
    /// start-of-line (nil = outside, "/' = inside that quote type).
    private static func updatedTripleQuoteState(line: String,
                                                current: Character?) -> Character? {
        var state = current
        let chars = Array(line)
        var i = 0
        while i < chars.count {
            // Skip line comments OUTSIDE triple-quotes.
            if state == nil, chars[i] == "#" { return state }
            // Possible single-line string start/end (not triple).
            if state == nil, chars[i] == "\"" || chars[i] == "'" {
                // Check for triple.
                if i + 2 < chars.count,
                   chars[i + 1] == chars[i],
                   chars[i + 2] == chars[i] {
                    state = chars[i]
                    i += 3
                    continue
                }
                // Single-line string — skip past matching quote on this line.
                let q = chars[i]
                i += 1
                while i < chars.count {
                    if chars[i] == "\\" { i += 2; continue }
                    if chars[i] == q { i += 1; break }
                    i += 1
                }
                continue
            }
            if let s = state, chars[i] == s,
               i + 2 < chars.count,
               chars[i + 1] == s, chars[i + 2] == s {
                state = nil
                i += 3
                continue
            }
            i += 1
        }
        return state
    }

    /// Insert a space after `#` for inline comments lacking one.
    /// Skips when `#` sits inside a string literal.
    private static func normalizeCommentSpace(_ line: String) -> String {
        let chars = Array(line)
        var inS: Character? = nil
        var i = 0
        while i < chars.count {
            let c = chars[i]
            if inS == nil {
                if c == "'" || c == "\"" { inS = c; i += 1; continue }
                if c == "#" {
                    // Convert `#x` (where x is a non-space, non-#
                    // character) to `# x`. Skip if next char is space,
                    // `#`, `!` (shebang), or end of line.
                    if i + 1 < chars.count {
                        let next = chars[i + 1]
                        if next != " " && next != "#" && next != "!" {
                            var out = String(chars[0...i])
                            out.append(" ")
                            out.append(contentsOf: chars[(i + 1)...])
                            return out
                        }
                    }
                    return line
                }
            } else {
                if c == "\\" { i += 2; continue }
                if c == inS { inS = nil }
            }
            i += 1
        }
        return line
    }
}
