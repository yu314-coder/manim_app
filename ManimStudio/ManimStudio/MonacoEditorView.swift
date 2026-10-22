import UIKit
import WebKit

/// A WKWebView-hosted Monaco editor with Python IntelliSense.
/// Bridges to Swift via WKScriptMessageHandler for text-change notifications
/// and `resolveRequest` queries that hit the Python daemon for docstrings/signatures.
///
/// The bundled Monaco distribution is the Vite-built one (vs/loader.js +
/// vs/editor/editor.main.js + hashed workers under vs/assets/). The
/// editor.main.js module installs its own `MonacoEnvironment.getWorker`
/// pointing at those hashed files, so the editor.html bootstrap no
/// longer needs to declare its own (legacy `getWorkerUrl` pointed at
/// `vs/base/worker/workerMain.js`, which doesn't exist in this
/// distribution and was causing the editor to wedge at load). With
/// that fix in place, monacoEnabled is back to true; the UITextView
/// fallback is kept for older bundles or when JS is disabled.
final class MonacoEditorView: UIView {

    // MARK: - Public API

    /// True when the WKWebView Monaco editor should be used. Flip to
    /// false to force the UITextView fallback (e.g. while debugging a
    /// bundle change without rebuilding).
    static let monacoEnabled = true

    /// Fired whenever the editor's text changes (debounced ~150ms in Monaco
    /// path, immediate in fallback).
    var onTextChanged: ((String) -> Void)?
    /// Fired when the editor finishes loading and is ready to accept code.
    var onEditorReady: (() -> Void)?
    /// The most recent text the editor reported (mirror, to avoid async gets on the hot path).
    private(set) var currentText: String = ""

    // MARK: - Internals

    let webView: WKWebView
    /// Plain UITextView used when `monacoEnabled` is false. Mirrors the
    /// behaviour the app had before the Monaco port — line numbers and
    /// rich IntelliSense are gone, but typing/scrolling/selection work.
    private let fallbackTextView = UITextView()
    private var isReady = false
    private var pendingSetCode: (code: String, language: String)?
    /// Typing on the on-screen keyboard rather than a hardware one; see
    /// `setTouchTyping` in editor.html.
    private var typingOnScreen = false

    /// Coding keys over the on-screen keyboard (KeyBar), shown while
    /// Monaco has focus.
    private lazy var keyBar = KeyBar.editor(
        send: { [weak self] key, text in self?.sendKey(key, text: text) },
        hideKeyboard: { [weak self] in self?.hideKeyboard() })
    private lazy var keyBarPresenter = FloatingKeyBarPresenter(bar: keyBar, host: self)

    // MARK: iPhone Duo, held like a laptop
    //
    // Half-open with the hinge across the screen, iOS gives the keyboard
    // the whole lower half — keys at the bottom, a see-through band above
    // them — and the app the upper half. The key bar then moves into that
    // band (FloatingKeyBarPresenter.laptopHinge), so the code has the upper
    // half to itself. Anywhere else — other devices, the Duo flat, folded
    // or held like a book — the bar floats above the keyboard as before.
    private var hingePartlyOpen = false
    private var laptopPosture = false
    private var hingeInteraction: UIInteraction?

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard window != nil, hingeInteraction == nil else { return }
        if #available(iOS 27.1, *) {
            let interaction = UIHingeInteraction { [weak self] _, update in
                self?.hingePartlyOpen = update.hinge?.status == .partiallyOpen
                self?.updateKeyBarDocking()
            }
            addInteraction(interaction)
            hingeInteraction = interaction
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        updateKeyBarDocking()   // rotation turns book posture into laptop
    }

    private func updateKeyBarDocking() {
        guard let window else { return }
        // Laptop: half-open, and the hinge runs across the window (it's
        // taller than wide). Held like a book, iOS splits the keyboard
        // into thumb halves instead and the floating bar fits.
        let laptop = hingePartlyOpen && window.bounds.height > window.bounds.width
        guard laptop != laptopPosture else { return }
        laptopPosture = laptop
        keyBarPresenter.laptopHinge = laptop
    }

    override init(frame: CGRect) {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.allowsInlineMediaPlayback = true
        let ucc = WKUserContentController()
        config.userContentController = ucc
        // Allow WebGL/workers for Monaco
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        self.webView = WKWebView(frame: .zero, configuration: config)
        super.init(frame: frame)
        backgroundColor = UIColor(red: 0.098, green: 0.102, blue: 0.114, alpha: 1)

        if Self.monacoEnabled {
            ucc.add(self, name: "editor")
            setupView()
            loadEditor()
            keyBarPresenter.onTypingOnScreenChange = { [weak self] onScreen in
                self?.typingOnScreen = onScreen
                self?.applyTypingMode()
            }
        } else {
            setupFallbackView()
            // Ready immediately so any setCode queued by the controller
            // before viewDidLoad finishes flows through on the next tick.
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.isReady = true
                self.onEditorReady?()
                if let pending = self.pendingSetCode {
                    self.pendingSetCode = nil
                    self.setCode(pending.code, language: pending.language)
                }
            }
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) not supported") }

    private func setupView() {
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.backgroundColor = .clear
        webView.scrollView.bounces = false
        webView.scrollView.alwaysBounceVertical = false
        webView.scrollView.alwaysBounceHorizontal = false
        // KEEP the outer scrollView enabled — touch/pointer events flow
        // through it to Monaco's internal DOM scrollHandler. Disabling
        // it was silently swallowing two-finger-pan / wheel-scroll /
        // cursor-drag events on Mac Catalyst and iPad, so Monaco could
        // never see them. The body has `overflow: hidden` so the
        // scrollView itself never actually scrolls — Monaco's internal
        // div does. Directional locks stay off so horizontal pan
        // (wide lines) works too.
        webView.scrollView.isScrollEnabled = true
        webView.scrollView.delaysContentTouches = false  // selection gestures fire instantly
        webView.scrollView.canCancelContentTouches = false
        // Allow long-press / drag text selection — WKWebView treats
        // selection gestures through its scrollView by default; we
        // don't need to do anything special here, but make damn sure
        // nothing we set later accidentally gates it.
        webView.allowsLinkPreview = false       // don't steal long-press
        webView.isUserInteractionEnabled = true

        // Inspectable in debug builds so you can Safari-inspect Monaco
        // (right-click → Inspect Element) — invaluable for diagnosing
        // selection/scroll misbehaviour. No-op on release.
        #if DEBUG
        if #available(iOS 16.4, macCatalyst 16.4, *) {
            webView.isInspectable = true
        }
        #endif

        webView.hideFormAccessoryBar()
        // The keyboard takes its look from the focused view. SwiftUI's
        // dark scheme didn't reach the web view, so with the system in
        // light mode a light keyboard came up under the dark editor.
        webView.overrideUserInterfaceStyle = .dark

        addSubview(webView)
        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: topAnchor),
            webView.leadingAnchor.constraint(equalTo: leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: bottomAnchor),
        ])

        // Re-attach Monaco's text input on every tap. After a manim
        // render the WKWebView's UITextInput conformance goes stale
        // (keyboard logs `View <(null)> does not conform to UITextInput
        // protocol`) and the editor stops accepting keystrokes. Forcing
        // becomeFirstResponder + JS editor.focus() rebinds it.
        let tap = UITapGestureRecognizer(target: self, action: #selector(handleTapToFocus))
        tap.cancelsTouchesInView = false   // let Monaco still receive the click
        tap.delegate = self
        webView.addGestureRecognizer(tap)
    }

    override func willMove(toWindow newWindow: UIWindow?) {
        super.willMove(toWindow: newWindow)
        if newWindow == nil { keyBarPresenter.detach() }
    }

    /// Tells Monaco whether typing is on the screen, so Return there
    /// always starts a new line instead of taking a suggestion.
    private func applyTypingMode() {
        guard isReady else { return }
        webView.evaluateJavaScript(
            "window.__editor && window.__editor.setTouchTyping && window.__editor.setTouchTyping(\(typingOnScreen))")
    }

    /// A key from the key bar, handed to `window.__editor.key`.
    private func sendKey(_ key: String, text: String) {
        guard let data = try? JSONSerialization.data(withJSONObject: [key, text]),
              let args = String(data: data, encoding: .utf8) else { return }
        webView.evaluateJavaScript("window.__editor && window.__editor.key(...\(args))")
    }

    /// Blurs Monaco's text area rather than only ending editing natively:
    /// that dropped WebKit's input session but left the text area focused
    /// in the page, so the next tap raised no new focus and a hardware
    /// keyboard's keys went nowhere until the on-screen one was brought
    /// back.
    private func hideKeyboard() {
        webView.evaluateJavaScript("document.activeElement && document.activeElement.blur()") { [weak self] _, _ in
            self?.webView.endEditing(true)
        }
    }

    /// WebKit's view that takes keyboard input.
    private var webContentView: UIView? {
        webView.scrollView.subviews.first { String(describing: type(of: $0)).hasPrefix("WKContent") }
    }

    @objc private func handleTapToFocus() {
        // Typing reaches the page only while WebKit's content view is first
        // responder. If it isn't (the keyboard was put away some other way
        // while the text area kept the page's focus), blur and refocus the
        // text area so WebKit starts a new input session.
        let typing = webContentView?.isFirstResponder ?? false
        webView.becomeFirstResponder()
        webView.evaluateJavaScript(typing
            ? "window.__editor && window.__editor.focusEditor && window.__editor.focusEditor()"
            : "window.__editor && window.__editor.refocusEditor && window.__editor.refocusEditor()")
    }

    private func loadEditor() {
        guard let url = Bundle.main.url(forResource: "editor", withExtension: "html") else {
            print("[MonacoEditor] editor.html not found in bundle")
            return
        }
        webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
    }

    private func setupFallbackView() {
        fallbackTextView.translatesAutoresizingMaskIntoConstraints = false
        fallbackTextView.backgroundColor = UIColor(red: 0.039, green: 0.039, blue: 0.059, alpha: 1)
        fallbackTextView.textColor = UIColor(red: 0.94, green: 0.94, blue: 0.96, alpha: 1)
        fallbackTextView.tintColor = UIColor(red: 0.66, green: 0.33, blue: 0.97, alpha: 1)
        fallbackTextView.font = UIFont.monospacedSystemFont(ofSize: 13, weight: .regular)
        fallbackTextView.autocapitalizationType = .none
        fallbackTextView.autocorrectionType = .no
        fallbackTextView.smartDashesType = .no
        fallbackTextView.smartQuotesType = .no
        fallbackTextView.smartInsertDeleteType = .no
        fallbackTextView.spellCheckingType = .no
        fallbackTextView.keyboardAppearance = .dark
        fallbackTextView.alwaysBounceVertical = true
        fallbackTextView.textContainerInset = UIEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        fallbackTextView.delegate = self
        addSubview(fallbackTextView)
        NSLayoutConstraint.activate([
            fallbackTextView.topAnchor.constraint(equalTo: topAnchor),
            fallbackTextView.leadingAnchor.constraint(equalTo: leadingAnchor),
            fallbackTextView.trailingAnchor.constraint(equalTo: trailingAnchor),
            fallbackTextView.bottomAnchor.constraint(equalTo: bottomAnchor),
        ])
    }

    // MARK: - JS → Swift commands

    /// Replace the editor's code and set the language mode.
    ///
    /// Uses an explicit completion handler on `evaluateJavaScript` so
    /// that if the JS side errors out (escape bug, `window.__editor`
    /// not yet defined, WKWebView in a bad state, size limit, etc.)
    /// we see it in the console instead of silently leaving the buffer
    /// stale — that was the "file switched but content didn't update"
    /// symptom: the filename label updated synchronously from Swift,
    /// but `model.setValue(code)` never ran because the JS snippet
    /// threw, and the error vanished into `evaluateJavaScript`'s nil
    /// completion handler.
    func setCode(_ code: String, language: String = "python") {
        guard isReady else {
            pendingSetCode = (code, language)
            return
        }
        currentText = code
        if !Self.monacoEnabled {
            fallbackTextView.text = code
            return
        }
        let escaped = escapeForTemplate(code)
        let js = "window.__editor.setCode(`\(escaped)`, '\(language)'); true;"
        webView.evaluateJavaScript(js) { [weak self] _, err in
            guard let err = err else { return }
            // Log the failure AND retry once on the next runloop tick.
            // Common cause: a stray unescaped char in `code` that makes
            // the template-literal close early. The retry path uses
            // `postMessage` + a JSON-string payload, which doesn't need
            // to live inside a template literal and so doesn't share
            // the escaping hazard.
            print("[MonacoEditor] setCode JS failed: \(err.localizedDescription) — retrying via JSON payload")
            self?.setCodeViaJSON(code, language: language)
        }
    }

    /// Retry path that avoids template-literal escaping entirely by
    /// passing the code through `JSONSerialization` (which produces a
    /// valid JS string literal for any input) and `JSON.parse` on the
    /// JS side. Slower than the template-literal path, but immune to
    /// character-escaping bugs in `escapeForTemplate`.
    private func setCodeViaJSON(_ code: String, language: String) {
        guard let payload = try? JSONSerialization.data(
                withJSONObject: ["code": code, "language": language]),
              let json = String(data: payload, encoding: .utf8) else {
            print("[MonacoEditor] setCodeViaJSON: JSON encode failed")
            return
        }
        // Wrap in parens + JSON.parse so quotes/backslashes in `json`
        // don't need further escaping in the outer template literal.
        let js = """
        (function() {
          var o = \(json);
          window.__editor.setCode(o.code, o.language);
          return true;
        })();
        """
        webView.evaluateJavaScript(js) { _, err in
            if let err = err {
                print("[MonacoEditor] setCodeViaJSON JS failed: \(err.localizedDescription)")
            }
        }
    }

    /// Insert (replace current selection with) a code block. Used for "Apply to Editor".
    func insertCode(_ code: String) {
        guard isReady else { return }
        if !Self.monacoEnabled {
            let range = fallbackTextView.selectedRange
            if let textRange = fallbackTextView.selectedTextRange {
                fallbackTextView.replace(textRange, withText: code)
            } else {
                fallbackTextView.text.append(code)
            }
            currentText = fallbackTextView.text ?? ""
            onTextChanged?(currentText)
            // Position cursor at end of inserted block.
            let newPos = range.location + (code as NSString).length
            fallbackTextView.selectedRange = NSRange(location: newPos, length: 0)
            return
        }
        let escaped = escapeForTemplate(code)
        webView.evaluateJavaScript("window.__editor.insertCode(`\(escaped)`)")
    }

    /// Re-tag the editor's syntax-highlighting language without
    /// touching the buffer contents. Used when the user toggles
    /// the Python / C / C++ / Fortran selector — only the highlighter
    /// changes; their typed code stays put.
    func setLanguage(_ language: String) {
        guard isReady else { return }
        if !Self.monacoEnabled {
            // Fallback UITextView has no syntax highlighting; nothing to do.
            return
        }
        let escaped = language.replacingOccurrences(of: "'", with: "\\'")
        webView.evaluateJavaScript(
            "window.__editor.setLanguage('\(escaped)'); true;",
            completionHandler: nil)
    }

    /// Get the current text asynchronously.
    func getText(completion: @escaping (String) -> Void) {
        if !Self.monacoEnabled {
            completion(fallbackTextView.text ?? currentText)
            return
        }
        webView.evaluateJavaScript("window.__editor.getText()") { [weak self] result, _ in
            let text = result as? String ?? self?.currentText ?? ""
            completion(text)
        }
    }

    /// Push a pre-built `{"modules": {mod: {name: kind, ...}, ...}}` JSON
    /// payload (built by `LibrarySymbolBuilder` after Python boots) into
    /// Monaco. The completion provider merges this with its hardcoded
    /// LIB_SYMBOLS so introspection-discovered names show up in suggest.
    /// Push a list of error markers (one per offending line) into
    /// Monaco. Each marker shows a red gutter dot + a tooltip and
    /// shows up in Monaco's problems counter. Pass an empty array
    /// to clear all markers.
    struct EditorMarker {
        let line: Int
        let column: Int
        let message: String
    }
    func setMarkers(_ markers: [EditorMarker]) {
        guard isReady, Self.monacoEnabled else { return }
        let payload: [[String: Any]] = markers.map {
            [
                "line": $0.line,
                "column": $0.column,
                "message": $0.message,
            ]
        }
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let json = String(data: data, encoding: .utf8) else { return }
        webView.evaluateJavaScript("window.__editor && window.__editor.setMarkers(\(json));")
    }

    func setSymbolIndexJSON(_ json: String) {
        guard isReady, Self.monacoEnabled else { return }
        webView.evaluateJavaScript("window.__editor.setSymbolIndex(\(json))")
    }

    /// Trigger one of Monaco's built-in editor actions by ID.
    /// IDs are documented at https://microsoft.github.io/monaco-editor/api/
    /// e.g. "actions.find", "editor.action.startFindReplaceAction",
    /// "editor.action.formatDocument", "editor.action.commentLine".
    func runEditorAction(_ id: String) {
        guard isReady, Self.monacoEnabled else { return }
        webView.becomeFirstResponder()
        // window.__editor is the Swift-facing API wrapper. The inner
        // `editor` reference is captured in a closure inside editor.html
        // and isn't exposed as a property — earlier code that probed
        // `window.__editor.editor || .monacoEditor` always whiffed,
        // making Find/Replace silently no-op. Call the explicit
        // runAction method that editor.html exposes.
        let escaped = id.replacingOccurrences(of: "'", with: "\\'")
        webView.evaluateJavaScript("""
            window.__editor && window.__editor.runAction && window.__editor.runAction('\(escaped)');
            """)
    }

    /// Re-focus the editor input. Useful after a render: the WKWebView's
    /// text-input attachment goes stale (the keyboard logs `View <null>
    /// does not conform to UITextInput protocol`) and tapping the editor
    /// alone doesn't always reattach. Calling editor.focus() forces
    /// Monaco to put its caret back into a real input field.
    func refocus() {
        guard isReady, Self.monacoEnabled else { return }
        webView.becomeFirstResponder()
        webView.evaluateJavaScript("window.__editor && window.__editor.focusEditor && window.__editor.focusEditor()")
    }

    /// Convenience — empty index, mainly for first boot before Python is ready.
    func pushSymbolIndex() {
        setSymbolIndexJSON("{\"modules\":{}}")
    }

    // MARK: - Helpers

    /// Escape for JS template literal: backslash, backtick, `${`, and carriage returns.
    private func escapeForTemplate(_ s: String) -> String {
        return s
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "`", with: "\\`")
            .replacingOccurrences(of: "$", with: "\\$")
    }
}

// MARK: - WKScriptMessageHandler

extension MonacoEditorView: UIGestureRecognizerDelegate {
    // Coexist with Monaco's own DOM tap handlers — recognize ours but
    // don't preempt theirs (Monaco's caret-positioning click still fires).
    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,
                           shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool {
        return true
    }
}

extension MonacoEditorView: WKScriptMessageHandler {
    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "editor",
              let body = message.body as? [String: Any],
              let kind = body["kind"] as? String else { return }

        switch kind {
        case "ready":
            isReady = true
            onEditorReady?()
            // Apply any setCode queued before ready
            if let pending = pendingSetCode {
                pendingSetCode = nil
                setCode(pending.code, language: pending.language)
            }
            // Push symbol index now that JS is ready
            pushSymbolIndex()
            applyTypingMode()

        case "jserror":
            // editor.html installs a window.onerror that posts these.
            // Lets us see the precise reason Monaco failed to load
            // without attaching a Safari Web Inspector.
            let msg = body["msg"] as? String ?? "?"
            let src = body["src"] as? String ?? "?"
            let line = body["line"] as? Int ?? 0
            NSLog("[MonacoEditor] JS error: %@ (at %@:%d)", msg, src, line)

        case "textChanged":
            if let text = body["text"] as? String {
                currentText = text
                onTextChanged?(text)
            }

        case "focus":
            keyBarPresenter.isActive = body["focused"] as? Bool ?? false
            // Monaco takes focus in its own touch handling, and WebKit
            // doesn't always make its content view first responder for it:
            // the caret showed but a hardware keyboard's keys went nowhere
            // (and no on-screen keyboard came up). Hand WebKit the focus
            // and refocus the text area so it starts an input session.
            if body["focused"] as? Bool == true, webContentView?.isFirstResponder == false {
                webView.becomeFirstResponder()
                webView.evaluateJavaScript(
                    "window.__editor && window.__editor.refocusEditor && window.__editor.refocusEditor()")
            }

        case "ctrlReleased":
            keyBar.modifierArmed = false

        case "resolveRequest":
            handleResolveRequest(body)

        case "clipboardCopy":
            // Monaco sent selected text on Cmd+C/Cmd+X. Write to the
            // system pasteboard so it's available to other apps + the
            // iOS share sheet. Cut's buffer-side removal happens on
            // the JS side before this message arrives.
            if let text = body["text"] as? String, !text.isEmpty {
                UIPasteboard.general.string = text
            }

        case "clipboardPasteRequest":
            // Monaco wants to paste. Read the pasteboard and send the
            // text back via window.__editor.pasteFromClipboard(text).
            let text = UIPasteboard.general.string ?? ""
            let escaped = text
                .replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "`", with: "\\`")
                .replacingOccurrences(of: "$", with: "\\$")
            webView.evaluateJavaScript("window.__editor.pasteFromClipboard(`\(escaped)`)")

        default:
            break
        }
    }

    private func handleResolveRequest(_ body: [String: Any]) {
        // ManimStudio doesn't ship the IntelliSenseEngine daemon — return
        // an empty resolve so Monaco's hover popup just doesn't fill in.
        guard let id = body["id"] as? String else { return }
        let js = "window.__editor.resolveResponse('\(id)', ``, ``)"
        webView.evaluateJavaScript(js)
    }
}

// MARK: - UITextViewDelegate (fallback path)

extension MonacoEditorView: UITextViewDelegate {
    func textViewDidChange(_ textView: UITextView) {
        currentText = textView.text ?? ""
        onTextChanged?(currentText)
    }
}

// MARK: - WebKit's form bar

private extension WKWebView {
    /// Drops WebKit's form bar (previous / next / Done) from over the
    /// keyboard. It does nothing useful for a code editor, and on a phone
    /// it took a third of the space left above the keyboard; the key bar
    /// has its own hide-keyboard key. WebKit's content view, which takes
    /// the keyboard's focus, gets a subclass whose inputAccessoryView is
    /// nil, the same way web-view app frameworks hide it.
    func hideFormAccessoryBar() {
        guard let content = scrollView.subviews.first(where: {
            String(describing: type(of: $0)).hasPrefix("WKContent")
        }) else { return }
        let base: AnyClass = type(of: content)
        let name = "\(NSStringFromClass(base))_NoFormBar"
        if let existing = NSClassFromString(name) {
            object_setClass(content, existing)
            return
        }
        guard let subclass = objc_allocateClassPair(base, name, 0) else { return }
        let getter = #selector(getter: UIResponder.inputAccessoryView)
        if let method = class_getInstanceMethod(UIResponder.self, getter) {
            let nothing: @convention(block) (AnyObject) -> UIView? = { _ in nil }
            class_addMethod(subclass, getter, imp_implementationWithBlock(nothing),
                            method_getTypeEncoding(method))
        }
        objc_registerClassPair(subclass)
        object_setClass(content, subclass)
    }
}
