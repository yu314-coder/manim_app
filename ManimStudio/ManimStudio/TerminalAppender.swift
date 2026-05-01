// TerminalAppender.swift — feeds Python streaming output into the
// SwiftTerm view, mirroring CodeBench's appendToTerminalFiltered.
// Lines starting with internal wrapper-debug tags route to NSLog only;
// the user-visible terminal stays focused on their script's output.
import Foundation
import SwiftTerm

@MainActor
final class TerminalAppender {
    static let shared = TerminalAppender()

    /// Prefixes whose lines are wrapper diagnostics — sent to Xcode
    /// console only, dropped from the SwiftTerm feed.
    private static let noisePrefixes: [String] = [
        "[diag]", "[fallback]",
        "[py-exec]", "[manim-font]", "[manim rendered]",
        "[manim-debug]",
    ]

    /// Carries a partial line across `append()` calls so we don't
    /// classify a half-line as user output by mistake.
    private var lineBuffer: String = ""

    /// Append a chunk of streaming output. Splits on newline, classifies
    /// each line, routes accordingly. SwiftTerm needs `\\r\\n` on iOS to
    /// position the cursor in column 0 — we emit that for every kept
    /// line so prompts don't stair-step.
    func append(_ chunk: String) {
        guard !chunk.isEmpty else { return }
        lineBuffer += chunk
        // Walk completed lines (anything followed by \\n).
        var emit = ""
        while let nlIdx = lineBuffer.firstIndex(of: "\n") {
            let line = String(lineBuffer[lineBuffer.startIndex..<nlIdx])
            lineBuffer.removeSubrange(lineBuffer.startIndex...nlIdx)
            if Self.noisePrefixes.contains(where: { line.hasPrefix($0) }) {
                NSLog("[py] %@", line)
            } else {
                emit += line + "\r\n"
            }
        }
        // For tqdm-style \\r-only bursts, the buffer keeps accumulating
        // across calls but never has a \\n — flush it directly so the
        // user sees the live progress bar update in place.
        if !lineBuffer.isEmpty && lineBuffer.contains("\r") {
            // Filter out a tagged line if the prefix matches; otherwise
            // emit the partial buffer (preserves \\r so SwiftTerm
            // overwrites the same row).
            let isNoise = Self.noisePrefixes.contains(where: { lineBuffer.hasPrefix($0) })
            if !isNoise {
                emit += lineBuffer
            }
            lineBuffer = ""
        }
        if !emit.isEmpty {
            PTYBridge.shared.terminalView?.feed(text: emit)
        }
    }
}
