// TerminalPane.swift — SwiftUI host for the real SwiftTerm-backed
// TerminalPaneViewController + PTYBridge. Drops the fake TextField
// "chat box" terminal; this is now a true ANSI/xterm terminal that
// pipes Python's stdin/stdout/stderr through pipes (PTYBridge).
import SwiftUI
import UIKit
import SwiftTerm

struct TerminalPane: View {
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "terminal")
                    .font(.system(size: 11)).foregroundStyle(Theme.cyan)
                Text("Console & Terminal").font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Circle().fill(Theme.success).frame(width: 6, height: 6)
                Text("manimstudio_shell")
                    .font(.system(size: 10)).foregroundStyle(Theme.textSecondary)
                Spacer()
                // Copy — grab the terminal's current selection (or all
                // visible text if nothing is selected) onto the system
                // clipboard, so the user can paste output elsewhere.
                Button {
                    if let tv = PTYBridge.shared.terminalView,
                       let sel = tv.getSelection(), !sel.isEmpty {
                        UIPasteboard.general.string = sel
                    } else if let tv = PTYBridge.shared.terminalView {
                        // No selection — fall back to the visible viewport.
                        let term = tv.getTerminal()
                        var lines: [String] = []
                        for r in 0..<term.rows {
                            if let line = term.getLine(row: r) {
                                lines.append(line.translateToString(trimRight: true))
                            }
                        }
                        UIPasteboard.general.string = lines.joined(separator: "\n")
                    }
                } label: {
                    Image(systemName: "doc.on.doc")
                        .font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
                }.buttonStyle(.plain).help("Copy")
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
