// WebHost.swift — WKWebView wrapper that loads the bundled web/
// frontend (Monaco editor, AI edit panel, xterm.js, modals — same
// HTML/CSS/JS the Windows desktop app uses). Replaces PyWebView's
// container window with a native AppKit one.
//
// JS↔Swift IPC contract: the web layer continues to call
// `window.pywebview.api.<method>(args)` exactly as it does on
// Windows. Our `IPCHandler` intercepts every such call, forwards
// it to the embedded Python's `app.api.<method>` via PythonHost,
// and feeds the result back through `pywebview.api.<method>`'s
// promise — meaning every existing renderer_desktop.js call site
// works unchanged.
//
// Phase 1 (this file): WKWebView shell + page loader + a stub
// IPC handler that logs unhandled calls. Phase 2 wires PythonHost
// into the dispatch path.
import SwiftUI
import WebKit

// MARK: - SwiftUI bridge

struct WebHost: NSViewRepresentable {
    func makeNSView(context: Context) -> WKWebView {
        // ── User content controller — registers the JS message
        // handler that fronts every pywebview.api.* call.
        let userContent = WKUserContentController()
        userContent.add(context.coordinator, name: "pywebviewBridge")

        // Pre-inject a `window.pywebview` shim so the page's existing
        // `window.pywebview.api.*` callers find it on first load.
        // The shim posts messages to `pywebviewBridge` and tracks
        // promises for the eventual reply.
        let shim = pywebviewShimSource()
        userContent.addUserScript(WKUserScript(source: shim,
                                                injectionTime: .atDocumentStart,
                                                forMainFrameOnly: false))

        let cfg = WKWebViewConfiguration()
        cfg.userContentController = userContent
        cfg.preferences.javaScriptCanOpenWindowsAutomatically = false
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled") // Cmd-Opt-I inspector

        let webView = WKWebView(frame: .zero, configuration: cfg)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.setValue(false, forKey: "drawsBackground")  // dark theme behind transparent body
        context.coordinator.webView = webView

        loadFrontend(into: webView)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {}

    func makeCoordinator() -> IPCHandler { IPCHandler() }

    // MARK: load

    private func loadFrontend(into webView: WKWebView) {
        guard let url = Bundle.main.url(forResource: "web/index", withExtension: "html") else {
            // Helpful failure: load an inline page explaining the missing bundle.
            let html = """
            <html><body style="background:#111;color:#eee;font-family:-apple-system;
                padding:40px;font-size:14px">
            <h2>Frontend bundle not found</h2>
            <p>Expected <code>Resources/web/index.html</code> inside the .app bundle.</p>
            <p>Drag the <code>web/</code> folder into the macOS target's
            <i>Copy Bundle Resources</i> phase.</p>
            </body></html>
            """
            webView.loadHTMLString(html, baseURL: nil)
            return
        }
        // Load with a directory base URL so all relative asset paths
        // (web/monaco/..., web/xterm/..., web/fontawesome/...) resolve.
        let dir = url.deletingLastPathComponent()
        webView.loadFileURL(url, allowingReadAccessTo: dir)
    }

    // MARK: pywebview shim — installed at document-start

    private func pywebviewShimSource() -> String {
        // Mirrors the shape PyWebView exposes to the Windows app:
        //   window.pywebview.api          — callable methods proxy
        //   window.pywebview.token        — opaque (unused on macOS, kept for parity)
        //   window.pywebview._call(...)   — internal promise dispatcher
        //
        // Every renderer_desktop.js call like
        //   window.pywebview.api.render_scene(code, opts)
        // becomes a postMessage to `pywebviewBridge` with a unique
        // requestId; PythonHost responds via webView.evaluateJavaScript
        // calling `window.pywebview._resolve(requestId, payload)`.
        return """
        (function() {
            if (window.pywebview) return;
            const _pending = {};
            let _seq = 0;
            function _call(method, args) {
                const id = ++_seq;
                return new Promise(function(resolve, reject) {
                    _pending[id] = { resolve: resolve, reject: reject };
                    try {
                        webkit.messageHandlers.pywebviewBridge.postMessage({
                            id: id, method: method, args: args || []
                        });
                    } catch (e) {
                        delete _pending[id];
                        reject(e);
                    }
                });
            }
            // Trap every property read on `api` to manufacture a
            // method on demand. The Windows app calls a long tail of
            // method names and we'd rather not enumerate them.
            const api = new Proxy({}, {
                get: function(_, name) {
                    if (name === 'then') return undefined; // not a thenable
                    return function(...a) { return _call(name, a); };
                }
            });
            window.pywebview = {
                api: api,
                token: 'macos',
                _call: _call,
                _resolve: function(id, payload) {
                    const p = _pending[id]; if (!p) return;
                    delete _pending[id]; p.resolve(payload);
                },
                _reject: function(id, message) {
                    const p = _pending[id]; if (!p) return;
                    delete _pending[id]; p.reject(new Error(message));
                },
            };
            // Some renderer code checks for `pywebviewready` event
            // (PyWebView fires this when its JS bridge is up).
            try { window.dispatchEvent(new Event('pywebviewready')); } catch (e) {}
        })();
        """
    }
}

// MARK: - IPC handler

final class IPCHandler: NSObject, WKScriptMessageHandler,
                        WKNavigationDelegate, WKUIDelegate {
    weak var webView: WKWebView?

    func userContentController(_ ucc: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let id     = body["id"] as? Int,
              let method = body["method"] as? String
        else { return }
        let args = (body["args"] as? [Any]) ?? []

        // Phase 1: forward to PythonHost when wired; for now reply with
        // a "not-yet-implemented" payload so the page can render.
        Task.detached { [weak self] in
            let payload = await Self.dispatch(method: method, args: args)
            await MainActor.run { self?.reply(id: id, payload: payload) }
        }
    }

    /// Phase 2 — forward every JS pywebview.api.* call to the
    /// embedded Python's `bootstrap_macos.api.<method>(*args)`.
    /// PythonHost serializes onto its own GIL queue so concurrent
    /// IPC calls from the WebView don't stomp each other.
    static func dispatch(method: String, args: [Any]) async -> Any? {
        await MainActor.run {
            PythonHost.shared.dispatch(method: method, args: args)
        }
    }

    private func reply(id: Int, payload: Any?) {
        guard let webView = webView else { return }
        let json: String
        if payload is NSNull {
            json = "null"
        } else if let data = try? JSONSerialization.data(
            withJSONObject: payload as Any,
            options: [.fragmentsAllowed]),
                  let s = String(data: data, encoding: .utf8) {
            json = s
        } else {
            json = "null"
        }
        let js = "window.pywebview && window.pywebview._resolve(\(id), \(json));"
        webView.evaluateJavaScript(js, completionHandler: nil)
    }

    // MARK: nav

    func webView(_ webView: WKWebView,
                 didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: Error) {
        NSLog("[macos.web] provisional nav failed: %@", error.localizedDescription)
    }
}
