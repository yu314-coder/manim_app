// TerminalPane.swift — SwiftUI host for the real SwiftTerm-backed
// TerminalPaneViewController + PTYBridge. Drops the fake TextField
// "chat box" terminal; this is now a true ANSI/xterm terminal that
// pipes Python's stdin/stdout/stderr through pipes (PTYBridge).
import SwiftUI
import UIKit
import SwiftTerm

struct TerminalPane: View {
    // Toggles to "Copied" briefly after a successful copy so the user
    // gets visual confirmation. Reset on a timer.
    @State private var justCopied: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "doc.text.magnifyingglass")
                    .font(.system(size: 11)).foregroundStyle(Theme.cyan)
                Text("Render Log").font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Circle().fill(Theme.success).frame(width: 6, height: 6)
                Text("manim output")
                    .font(.system(size: 10)).foregroundStyle(Theme.textSecondary)
                Spacer()
                // Copy — grab the terminal's current selection (or all
                // visible text if nothing is selected) onto the system
                // clipboard, so the user can paste output elsewhere.
                //
                // The big visible viewport scrape can take ~30 ms on a
                // 200-row terminal — not huge, but enough to feel laggy
                // if the user mashes the button. Do the read + join on
                // a background queue, then hop back to main to update
                // the pasteboard and the "Copied" indicator. The button
                // also briefly swaps icon + label so the user sees
                // confirmation, then resets after ~1.4 s.
                Button {
                    copyTerminal()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: justCopied
                              ? "checkmark.circle.fill"
                              : "doc.on.doc")
                            .font(.system(size: 11))
                            .foregroundStyle(justCopied
                                             ? Theme.success
                                             : Theme.textSecondary)
                        if justCopied {
                            Text("Copied")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(Theme.success)
                                .transition(.opacity.combined(with: .scale))
                        }
                    }
                }
                .buttonStyle(.plain)
                .help(justCopied ? "Copied to clipboard" : "Copy")
                .animation(.easeInOut(duration: 0.18), value: justCopied)
                // Del — clear the terminal screen + scrollback (ESC[2J + ESC[H + ESC[3J).
                Button {
                    PTYBridge.shared.terminalView?.feed(text: "\u{1b}[2J\u{1b}[3J\u{1b}[H")
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
                }.buttonStyle(.plain).help("Del")
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Theme.bgSecondary)
            .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1), alignment: .bottom)

            SwiftTermContainer()
                .background(Color.black)
        }
    }

    /// Grab terminal text on a background queue, write to the
    /// pasteboard on main, flash the "Copied" pill.
    private func copyTerminal() {
        // Snapshot whatever the user needs RIGHT NOW on the main thread.
        // SwiftTerm's TerminalView isn't documented as thread-safe; we
        // pull the strings here, then move the join/clipboard write off.
        guard let tv = PTYBridge.shared.terminalView else { return }
        let selection = tv.getSelection()
        let term = tv.getTerminal()
        let rows = term.rows
        var rawLines: [String] = []
        if let s = selection, !s.isEmpty {
            rawLines = [s]
        } else {
            rawLines.reserveCapacity(rows)
            for r in 0..<rows {
                if let line = term.getLine(row: r) {
                    rawLines.append(line.translateToString(trimRight: true))
                }
            }
        }
        DispatchQueue.global(qos: .userInitiated).async {
            let joined = rawLines.joined(separator: "\n")
            DispatchQueue.main.async {
                UIPasteboard.general.string = joined
                withAnimation(.easeOut(duration: 0.15)) {
                    justCopied = true
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) {
                    withAnimation(.easeIn(duration: 0.2)) {
                        justCopied = false
                    }
                }
            }
        }
    }
}

private struct SwiftTermContainer: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> TerminalPaneViewController {
        let vc = TerminalPaneViewController()
        // PTY pipes must exist before Py_Initialize because PythonRuntime
        // redirects sys.stdout/stderr through stdoutPipeWriteFD as part of
        // its own setup chain.
        PTYBridge.shared.setupIfNeeded()
        // ensureRuntimeReady() schedules Py_Initialize on PythonRuntime's
        // serial queue and — once init completes there — calls
        // startInteractiveShellIfNeeded() itself. So we just kick this
        // off and let the queue serialize boot → REPL-thread spawn.
        // Calling startInteractiveShellIfNeeded() ourselves would race
        // Py_Initialize and trip "Fatal Python error: take_gil".
        PythonRuntime.shared.ensureRuntimeReady()
        return vc
    }
    func updateUIViewController(_ vc: TerminalPaneViewController, context: Context) {}
}
