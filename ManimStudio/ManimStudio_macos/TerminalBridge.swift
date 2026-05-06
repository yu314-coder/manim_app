// TerminalBridge.swift — singleton that lets RenderManager push
// commands into the running PTY terminal. TerminalProcessView
// registers a `send(text:)` closure when the WKView mounts; the
// closure is just a forward to SwiftTerm.LocalProcessTerminalView's
// `send(txt:)` which writes to the shell's stdin.
//
// Why a singleton: ContentView constructs RenderManager and
// TerminalProcessView in different SwiftUI subtrees; passing a
// reference between them would require dragging an
// @ObservableObject through the view hierarchy. The singleton
// gives RenderManager direct access without restructuring.
import Foundation

@MainActor
final class TerminalBridge {
    static let shared = TerminalBridge()
    private init() {}

    /// Set by TerminalProcessView. nil before the terminal is mounted.
    var sendCommand: ((String) -> Void)?

    /// Convenience wrapper — appends `\n` so the shell executes the
    /// command immediately. Falls back to a NSLog warning if no
    /// terminal is attached (the user hasn't opened the Workspace
    /// tab yet).
    func runInShell(_ command: String) {
        guard let send = sendCommand else {
            NSLog("[bridge] terminal not mounted; can't send: %@", command)
            return
        }
        send(command + "\n")
    }

    /// Send Ctrl-C (0x03) to the shell — interrupts the running
    /// command (the manim render).
    func interrupt() {
        guard let send = sendCommand else { return }
        send("\u{0003}")
    }
}
