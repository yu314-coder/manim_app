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
                Text("offlinai_shell")
                    .font(.system(size: 10)).foregroundStyle(Theme.textSecondary)
                Spacer()
                Button {
                    PTYBridge.shared.send(data: [0x03])      // Ctrl-C
                } label: {
                    Image(systemName: "xmark.octagon")
                        .font(.system(size: 11)).foregroundStyle(Theme.error)
                }.buttonStyle(.plain).help("Send Ctrl-C")
                Button {
                    PTYBridge.shared.terminalView?.feed(text: "\u{1b}[2J\u{1b}[H")
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11)).foregroundStyle(Theme.textSecondary)
                }.buttonStyle(.plain).help("Clear")
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
