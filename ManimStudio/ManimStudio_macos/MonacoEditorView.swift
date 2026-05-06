// MonacoEditorView.swift — Monaco editor hosted in a WKWebView.
// Replaces the NSTextView-based EditorView with VS Code's editor:
// real Python intellisense, find widget, format-on-paste, indent
// guides, bracket pair colorization, minimap.
//
// Monaco is loaded from the jsdelivr CDN at first launch (saves
// ~14 MB of bundled assets and Monaco re-uses the cache for
// subsequent launches). When offline on first launch the editor
// shows a "Loading Monaco editor…" placeholder.
//
// Swift↔JS contract:
//   • controller.setText(s)        → window.__editor.setCode(s, "python")
//   • controller.setMarkers([…])   → window.__editor.setMarkers(…)
//   • controller.runAction(id)     → window.__editor.runAction(id)
//   • JS textChanged event         → @Binding text update
import SwiftUI
import WebKit
import AppKit

/// Reach-into handle the toolbar / menu bar uses to call Monaco
/// actions (find, format, comment, etc.) without exposing the
/// WKWebView itself to the rest of the app.
@MainActor
final class MonacoController {
    fileprivate weak var view: MonacoEditorWebView?
    func setMarkers(_ markers: [MarkerSpec]) { view?.setMarkers(markers) }
    func setSymbolIndex(_ json: String) { view?.setSymbolIndex(json) }
    func runAction(_ id: String) { view?.runAction(id) }
    func showFind() { view?.runAction("actions.find") }
    func showFindAndReplace() { view?.runAction("editor.action.startFindReplaceAction") }
    func format() { view?.runAction("editor.action.formatDocument") }
    func toggleComment() { view?.runAction("editor.action.commentLine") }
    func focus() { view?.refocus() }
}

struct MarkerSpec: Hashable {
    let line: Int
    let column: Int
    let message: String
}

struct MonacoEditorView: NSViewRepresentable {
    @Binding var text: String
    var fontSize: CGFloat = 13
    var controller: MonacoController? = nil

    func makeNSView(context: Context) -> MonacoEditorWebView {
        let v = MonacoEditorWebView(frame: .zero)
        Task { @MainActor in self.controller?.view = v }
        v.onTextChanged = { newText in
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
                v.setFontSize(fontSize)
                context.coordinator.lastReportedText = self.text
            }
        }
        return v
    }

    func updateNSView(_ webView: MonacoEditorWebView, context: Context) {
        if webView.currentText != text && context.coordinator.lastReportedText != text {
            webView.setCode(text, language: "python")
            context.coordinator.lastReportedText = text
        }
        if webView.currentFontSize != fontSize {
            webView.setFontSize(fontSize)
        }
    }

    func makeCoordinator() -> Coord { Coord(self) }

    final class Coord {
        var parent: MonacoEditorView
        var lastReportedText: String = ""
        init(_ p: MonacoEditorView) { parent = p }
    }
}

// MARK: - underlying NSView

final class MonacoEditorWebView: NSView, WKScriptMessageHandler {
    private let webView: WKWebView
    fileprivate var onTextChanged: ((String) -> Void)?
    fileprivate var onEditorReady: (() -> Void)?
    fileprivate var currentText: String = ""
    fileprivate var currentFontSize: CGFloat = 13
    private var isReady = false
    private var pendingScripts: [String] = []

    override init(frame: NSRect) {
        let userContent = WKUserContentController()
        let cfg = WKWebViewConfiguration()
        cfg.userContentController = userContent
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
        cfg.preferences.javaScriptCanOpenWindowsAutomatically = false
        webView = WKWebView(frame: frame, configuration: cfg)
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.setValue(false, forKey: "drawsBackground")  // dark theme bleeds through
        super.init(frame: frame)
        userContent.add(self, name: "editorBridge")

        addSubview(webView)
        NSLayoutConstraint.activate([
            webView.leadingAnchor.constraint(equalTo: leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: trailingAnchor),
            webView.topAnchor.constraint(equalTo: topAnchor),
            webView.bottomAnchor.constraint(equalTo: bottomAnchor),
        ])

        // Load editor.html from the app bundle (single file, no
        // nested resources). Allow CDN fetch by giving the page
        // network access (default WKWebView config does this).
        if let url = Bundle.main.url(forResource: "editor",
                                     withExtension: "html") {
            webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        } else {
            webView.loadHTMLString(
                "<html><body style='background:#111;color:#eee;padding:30px;font-family:-apple-system'>"
                + "<h2>editor.html missing from app bundle</h2></body></html>",
                baseURL: nil)
        }
    }
    required init?(coder: NSCoder) { fatalError() }

    deinit {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "editorBridge")
    }

    // MARK: WKScriptMessageHandler

    func userContentController(_ ucc: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let kind = body["kind"] as? String
        else { return }
        switch kind {
        case "ready":
            isReady = true
            for js in pendingScripts {
                webView.evaluateJavaScript(js)
            }
            pendingScripts.removeAll()
            onEditorReady?()
        case "textChanged":
            let text = (body["text"] as? String) ?? ""
            currentText = text
            onTextChanged?(text)
        default:
            break
        }
    }

    // MARK: Swift→JS

    func setCode(_ s: String, language: String) {
        currentText = s
        let escaped = encodeJSString(s)
        let lang = encodeJSString(language)
        run("window.__editor && window.__editor.setCode(\(escaped), \(lang));")
    }
    func setFontSize(_ size: CGFloat) {
        currentFontSize = size
        run("window.__editor && window.__editor.setFontSize(\(Int(size)));")
    }
    func runAction(_ id: String) {
        let escaped = encodeJSString(id)
        run("window.__editor && window.__editor.runAction(\(escaped));")
    }
    func setMarkers(_ markers: [MarkerSpec]) {
        let payload: [[String: Any]] = markers.map {
            ["line": $0.line, "column": $0.column, "message": $0.message]
        }
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let json = String(data: data, encoding: .utf8) else { return }
        run("window.__editor && window.__editor.setMarkers(\(json));")
    }
    /// `json` is the raw JSON blob from MonacoSymbolIndexer (same
    /// shape the JS-side `setSymbolIndex` expects).
    func setSymbolIndex(_ json: String) {
        // Sanity-check it parses, then embed as a JS object literal —
        // Monaco's setSymbolIndex takes the parsed object directly.
        guard (try? JSONSerialization.jsonObject(
            with: Data(json.utf8), options: [])) != nil else { return }
        run("window.__editor && window.__editor.setSymbolIndex(\(json));")
    }
    func refocus() {
        run("window.__editor && window.__editor.focusEditor();")
    }

    private func run(_ js: String) {
        if isReady {
            webView.evaluateJavaScript(js, completionHandler: nil)
        } else {
            pendingScripts.append(js)
        }
    }

    private func encodeJSString(_ s: String) -> String {
        // Use JSONSerialization to produce a properly escaped JS
        // string literal (handles quotes, newlines, unicode, etc.).
        if let data = try? JSONSerialization.data(
            withJSONObject: [s], options: [.fragmentsAllowed]),
            let json = String(data: data, encoding: .utf8) {
            // json is `["…"]` — strip the wrapping array.
            return String(json.dropFirst().dropLast())
        }
        return "\"\""
    }
}
