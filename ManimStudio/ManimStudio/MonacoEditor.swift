// MonacoEditor.swift — SwiftUI wrapper around the UIKit MonacoEditorView.
import SwiftUI
import UIKit

/// Lets the parent reach into the Monaco WKWebView to trigger built-in
/// actions (Find, focus, etc.) without subclassing the SwiftUI wrapper.
/// Plain class — not ObservableObject (we don't observe its state, the
/// parent just calls methods on it). Stored in the parent via @State.
@MainActor
final class MonacoController {
    fileprivate weak var view: MonacoEditorView?

    /// Trigger Monaco's built-in find widget (same as Ctrl+F in VS Code).
    func showFind() {
        view?.runEditorAction("actions.find")
    }
    /// Trigger find-and-replace.
    func showFindAndReplace() {
        view?.runEditorAction("editor.action.startFindReplaceAction")
    }
    /// Re-focus the editor (returns keyboard).
    func refocus() { view?.refocus() }
}

struct MonacoEditor: UIViewRepresentable {
    @Binding var text: String
    var fontSize: CGFloat = 14
    var controller: MonacoController? = nil

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> MonacoEditorView {
        let v = MonacoEditorView(frame: .zero)
        Task { @MainActor in self.controller?.view = v }
        v.onTextChanged = { newText in
            // Coalesce on main; SwiftUI mutates @Binding from main only.
            DispatchQueue.main.async {
                if context.coordinator.lastReportedText != newText {
                    context.coordinator.lastReportedText = newText
                    self.text = newText
                }
            }
        }
        v.onEditorReady = {
            DispatchQueue.main.async {
                v.setCode(self.text, language: "python")
                context.coordinator.lastReportedText = self.text
                // Defer LibrarySymbolBuilder by 4 s so app launch isn't
                // blocked, the terminal pane finishes booting Python +
                // offlinai_shell, and any crash inside `import moderngl*`
                // (OpenGL context init aborts the process on iOS) hits
                // after the UI is interactive — at which point the
                // introspection script's skip-list catches it cleanly.
                DispatchQueue.main.asyncAfter(deadline: .now() + 4) {
                    LibrarySymbolBuilder.shared.build { json in
                        v.setSymbolIndexJSON(json)
                    }
                }
            }
        }
        return v
    }

    func updateUIView(_ uiView: MonacoEditorView, context: Context) {
        // Only push down when SwiftUI's binding is ahead of the editor —
        // avoids a feedback loop where every keystroke triggers a setCode.
        if uiView.currentText != text && context.coordinator.lastReportedText != text {
            uiView.setCode(text, language: "python")
            context.coordinator.lastReportedText = text
        }
    }

    static func dismantleUIView(_ uiView: MonacoEditorView, coordinator: Coordinator) {
        // No-op; SwiftUI cleans up automatically.
    }

    final class Coordinator {
        var parent: MonacoEditor
        var lastReportedText: String = ""
        init(_ parent: MonacoEditor) { self.parent = parent }
    }
}
