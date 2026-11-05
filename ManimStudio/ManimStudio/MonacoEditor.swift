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
    /// Generic passthrough — used by menu-bar commands that pick from
    /// Monaco's published action IDs (commentLine, indentLines, etc).
    func runAction(_ id: String) {
        view?.runEditorAction(id)
    }
    /// Render-error markers parsed from a Python traceback. Pass an
    /// empty array to clear them after a fresh render.
    func setMarkers(_ markers: [MonacoEditorView.EditorMarker]) {
        view?.setMarkers(markers)
    }
    /// Insert a string at the current cursor position.
    func insertCode(_ text: String) {
        view?.insertCode(text)
    }
    /// The code's size, from the editor pane's size menu.
    func setFontSize(_ size: CGFloat) { view?.setFontSize(size) }
    /// Re-focus the editor (returns keyboard).
    func refocus() { view?.refocus() }
    /// Shows `text` unless the editor already has it (it's what was just
    /// typed). For code that changes from outside — a Gallery load, a
    /// file opened, New.
    func showText(_ text: String) {
        guard let view, view.currentText != text else { return }
        view.setCode(text, language: "python")
    }
}

struct MonacoEditor: UIViewRepresentable {
    @Binding var text: String
    var fontSize: CGFloat = 13
    var controller: MonacoController? = nil

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    /// A holder for the app's one editor (MonacoEditorView.shared), so
    /// SwiftUI taking down an old pane takes down the holder, not the
    /// editor, which by then may be in the new one.
    final class Slot: UIView {}

    func makeUIView(context: Context) -> Slot {
        let slot = Slot()
        let v = MonacoEditorView.shared()
        v.removeFromSuperview()
        v.translatesAutoresizingMaskIntoConstraints = false
        slot.addSubview(v)
        NSLayoutConstraint.activate([
            v.topAnchor.constraint(equalTo: slot.topAnchor),
            v.leadingAnchor.constraint(equalTo: slot.leadingAnchor),
            v.trailingAnchor.constraint(equalTo: slot.trailingAnchor),
            v.bottomAnchor.constraint(equalTo: slot.bottomAnchor),
        ])
        Task { @MainActor in self.controller?.view = v }
        context.coordinator.lastReportedText = v.currentText
        v.setFontSize(fontSize)
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

                // If the introspection JSON is already on disk from a
                // previous run of this build, push it immediately —
                // reading the file is a cheap I/O hit, not a full
                // import-everything Python pass. On a cache MISS we do
                // NOT kick off the build here: that pass takes 10–30 s
                // and races with REPL bootstrap for the GIL, which is
                // the freeze the user reports at app open. The packages
                // tab triggers it on demand instead (see PackagesView)
                // and the user sees a spinner so it's not surprising.
                LibrarySymbolBuilder.shared.loadIfCached { json in
                    if let json = json {
                        v.setSymbolIndexJSON(json)
                    }
                }
            }
        }
        // Already loaded (a pane before this one showed it): only the code
        // may have changed meanwhile — a Gallery load from another tab.
        if v.isEditorReady, v.currentText != text {
            v.setCode(text, language: "python")
            context.coordinator.lastReportedText = text
        }
        return slot
    }

    func updateUIView(_ slot: Slot, context: Context) {
        // An older pane's holder, its editor gone to a newer one.
        guard let uiView = slot.subviews.first as? MonacoEditorView else { return }
        uiView.setFontSize(fontSize)
        // Only push down when SwiftUI's binding is ahead of the editor —
        // avoids a feedback loop where every keystroke triggers a setCode.
        if uiView.currentText != text && context.coordinator.lastReportedText != text {
            uiView.setCode(text, language: "python")
            context.coordinator.lastReportedText = text
        }
    }

    final class Coordinator {
        var parent: MonacoEditor
        var lastReportedText: String = ""
        init(_ parent: MonacoEditor) { self.parent = parent }
    }
}
