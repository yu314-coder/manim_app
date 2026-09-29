//
//  KeyBar.swift
//  ManimStudio
//
//  The row of extra keys above the on-screen keyboard. That keyboard has
//  no Esc, Ctrl or arrow keys (an iPhone's has no Tab either) and keeps
//  most of the symbols code needs behind Shift or its other pages, so on
//  an iPhone, or an iPad without a hardware keyboard, typing Python or
//  shell commands meant constant page switching.
//
//  The terminal uses the bar as its inputAccessoryView, replacing
//  SwiftTerm's generic one (whose F1–F10 keys nothing here uses). The code
//  editor floats it above the keyboard instead (FloatingKeyBarPresenter):
//  a WKWebView's first responder is WebKit's own content view, so the
//  editor can't hand UIKit an accessory; its bar shows only while the
//  on-screen keyboard is up.
//

import UIKit
import SwiftTerm

struct KeyBarKey {
    enum Kind {
        /// Types a symbol; drawn in the monospaced face.
        case symbol
        /// A named key or action: esc, tab, ^C, undo, …
        case function
        /// Fires on touch-down, then repeats while held (arrows).
        case repeating
        /// A sticky modifier (ctrl), lit while armed.
        case modifier
    }

    let title: String
    let icon: String?
    let accessibilityLabel: String
    let kind: Kind
    let action: () -> Void

    static func symbol(_ text: String, _ action: @escaping () -> Void) -> KeyBarKey {
        KeyBarKey(title: text, icon: nil, accessibilityLabel: text, kind: .symbol, action: action)
    }

    static func function(_ title: String, icon: String? = nil, name: String,
                         _ action: @escaping () -> Void) -> KeyBarKey {
        KeyBarKey(title: title, icon: icon, accessibilityLabel: name, kind: .function, action: action)
    }

    static func repeating(icon: String, name: String, _ action: @escaping () -> Void) -> KeyBarKey {
        KeyBarKey(title: "", icon: icon, accessibilityLabel: name, kind: .repeating, action: action)
    }
}

final class KeyBar: UIInputView, UIInputViewAudioFeedback {
    private static let isPad = UIDevice.current.userInterfaceIdiom == .pad
    static let barHeight: CGFloat = isPad ? 50 : 44
    private static let keyHeight: CGFloat = isPad ? 38 : 34
    private static let minKeyWidth: CGFloat = isPad ? 44 : 32
    /// Narrower than this (an iPhone, an iPad in Split View), only the
    /// trailing keys stay pinned and the leading ones scroll with the rest.
    private static let compactWidth: CGFloat = 560

    private static let symbolFill = UIColor(white: 1, alpha: 0.17)
    private static let functionFill = UIColor(white: 1, alpha: 0.08)
    private static let armedFill = UIColor(red: 0.388, green: 0.400, blue: 0.945, alpha: 1)

    private let leadingKeys: [KeyBarKey]
    private let scrollingKeys: [KeyBarKey]
    private let trailingKeys: [KeyBarKey]
    private var content: [UIView] = []
    private var builtCompact: Bool?
    private var modifierButton: UIButton?
    private var repeatTimer: Timer?

    var enableInputClicksWhenVisible: Bool { true }

    /// Lights the modifier key while armed.
    var modifierArmed = false {
        didSet { styleModifier() }
    }

    /// `leading` and `trailing` stay put; `scrolling` scrolls sideways
    /// between them. `floating` is for a bar that isn't an input accessory
    /// and has to draw its own keyboard-like background.
    init(leading: [KeyBarKey], scrolling: [KeyBarKey], trailing: [KeyBarKey], floating: Bool = false) {
        leadingKeys = leading
        scrollingKeys = scrolling
        trailingKeys = trailing
        super.init(frame: CGRect(x: 0, y: 0, width: 320, height: Self.barHeight),
                   inputViewStyle: floating ? .default : .keyboard)
        allowsSelfSizing = true
        if floating {
            let blur = UIVisualEffectView(effect: UIBlurEffect(style: .systemChromeMaterialDark))
            blur.frame = bounds
            blur.autoresizingMask = [.flexibleWidth, .flexibleHeight]
            addSubview(blur)
            let hairline = UIView(frame: CGRect(x: 0, y: 0, width: bounds.width, height: 0.5))
            hairline.autoresizingMask = [.flexibleWidth, .flexibleBottomMargin]
            hairline.backgroundColor = UIColor(white: 1, alpha: 0.12)
            addSubview(hairline)
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) not supported") }

    override var intrinsicContentSize: CGSize {
        CGSize(width: UIView.noIntrinsicMetric, height: Self.barHeight)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        guard bounds.width > 0 else { return }
        let compact = bounds.width < Self.compactWidth
        if compact != builtCompact {
            builtCompact = compact
            build(compact: compact)
        }
    }

    override func willMove(toWindow newWindow: UIWindow?) {
        super.willMove(toWindow: newWindow)
        if newWindow == nil { stopRepeating() }
    }

    // MARK: - Layout

    private func build(compact: Bool) {
        content.forEach { $0.removeFromSuperview() }
        modifierButton = nil

        let leading = compact ? [] : leadingKeys
        let scrolling = compact ? leadingKeys + scrollingKeys : scrollingKeys
        let leadingRow = row(leading)
        let trailingRow = row(trailingKeys)
        let middleRow = row(scrolling)

        let scroller = KeyScrollView()
        scroller.showsHorizontalScrollIndicator = false
        scroller.alwaysBounceHorizontal = true
        // Keys fire as soon as they're touched; a sideways drag that starts
        // on one still scrolls (KeyScrollView takes the touch back).
        scroller.delaysContentTouches = false
        middleRow.translatesAutoresizingMaskIntoConstraints = false
        scroller.addSubview(middleRow)

        content = [leadingRow, scroller, trailingRow]
        for view in content {
            view.translatesAutoresizingMaskIntoConstraints = false
            addSubview(view)
        }
        let inset: CGFloat = 6
        let gap: CGFloat = 8
        NSLayoutConstraint.activate([
            leadingRow.leadingAnchor.constraint(equalTo: safeAreaLayoutGuide.leadingAnchor, constant: inset),
            leadingRow.centerYAnchor.constraint(equalTo: centerYAnchor),

            scroller.leadingAnchor.constraint(equalTo: leadingRow.trailingAnchor, constant: leading.isEmpty ? 0 : gap),
            scroller.trailingAnchor.constraint(equalTo: trailingRow.leadingAnchor, constant: -gap),
            scroller.topAnchor.constraint(equalTo: topAnchor),
            scroller.bottomAnchor.constraint(equalTo: bottomAnchor),

            middleRow.leadingAnchor.constraint(equalTo: scroller.contentLayoutGuide.leadingAnchor),
            middleRow.trailingAnchor.constraint(equalTo: scroller.contentLayoutGuide.trailingAnchor),
            middleRow.topAnchor.constraint(equalTo: scroller.contentLayoutGuide.topAnchor),
            middleRow.bottomAnchor.constraint(equalTo: scroller.contentLayoutGuide.bottomAnchor),
            middleRow.heightAnchor.constraint(equalTo: scroller.frameLayoutGuide.heightAnchor),

            trailingRow.trailingAnchor.constraint(equalTo: safeAreaLayoutGuide.trailingAnchor, constant: -inset),
            trailingRow.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])
        styleModifier()
    }

    private func row(_ keys: [KeyBarKey]) -> UIStackView {
        let stack = UIStackView(arrangedSubviews: keys.map(button))
        stack.axis = .horizontal
        stack.spacing = Self.isPad ? 6 : 4
        stack.alignment = .center
        return stack
    }

    private func button(for key: KeyBarKey) -> UIButton {
        var config = UIButton.Configuration.filled()
        config.cornerStyle = .medium
        config.baseForegroundColor = .white
        config.baseBackgroundColor = key.kind == .symbol ? Self.symbolFill : Self.functionFill
        config.contentInsets = NSDirectionalEdgeInsets(top: 0, leading: 8, bottom: 0, trailing: 8)
        if let icon = key.icon {
            config.image = UIImage(systemName: icon, withConfiguration:
                UIImage.SymbolConfiguration(pointSize: Self.isPad ? 16 : 14, weight: .semibold))
        }
        if !key.title.isEmpty {
            var title = AttributedString(key.title)
            title.font = key.kind == .symbol
                ? UIFont.monospacedSystemFont(ofSize: Self.isPad ? 19 : 17, weight: .regular)
                : UIFont.systemFont(ofSize: Self.isPad ? 15 : 13, weight: .semibold)
            config.attributedTitle = title
        }
        let button = UIButton(configuration: config)
        button.accessibilityLabel = key.accessibilityLabel
        button.heightAnchor.constraint(equalToConstant: Self.keyHeight).isActive = true
        button.widthAnchor.constraint(greaterThanOrEqualToConstant: Self.minKeyWidth).isActive = true

        switch key.kind {
        case .symbol, .function, .modifier:
            if key.kind == .modifier { modifierButton = button }
            button.addAction(UIAction { _ in
                UIDevice.current.playInputClick()
                key.action()
            }, for: .touchUpInside)
        case .repeating:
            button.addAction(UIAction { [weak self] _ in
                UIDevice.current.playInputClick()
                self?.startRepeating(key.action)
            }, for: .touchDown)
            button.addAction(UIAction { [weak self] _ in
                self?.stopRepeating()
            }, for: [.touchUpInside, .touchUpOutside, .touchCancel, .touchDragExit])
        }
        return button
    }

    private func styleModifier() {
        guard let button = modifierButton, var config = button.configuration else { return }
        config.baseBackgroundColor = modifierArmed ? Self.armedFill : Self.functionFill
        button.configuration = config
        button.accessibilityTraits = modifierArmed ? [.button, .selected] : .button
    }

    // MARK: - Auto-repeat

    private func startRepeating(_ action: @escaping () -> Void) {
        stopRepeating()
        action()
        // A held hardware key's rhythm: a pause, then steady repeats.
        repeatTimer = Timer.scheduledTimer(withTimeInterval: 0.45, repeats: false) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.repeatTimer = Timer.scheduledTimer(withTimeInterval: 0.07, repeats: true) { _ in
                    MainActor.assumeIsolated { action() }
                }
            }
        }
    }

    private func stopRepeating() {
        repeatTimer?.invalidate()
        repeatTimer = nil
    }
}

/// Lets a sideways drag that starts on a key scroll the row; a scroll view
/// otherwise leaves touches that begin on controls alone.
private final class KeyScrollView: UIScrollView {
    override func touchesShouldCancel(in view: UIView) -> Bool { true }
}

extension KeyBar {
    // MARK: - Terminal

    /// Keys for the shell: the control characters its line editor knows
    /// (`help` lists them), a sticky ctrl for the rest, arrows for history
    /// and the cursor, and the symbols shell lines are made of.
    static func terminal(for terminalView: TerminalView) -> KeyBar {
        weak let tv = terminalView
        weak var bar: KeyBar?
        func send(_ bytes: [UInt8]) -> () -> Void { { tv?.send(bytes) } }
        func arrow(_ app: [UInt8], _ normal: [UInt8]) -> () -> Void {
            { guard let tv else { return }; tv.send(tv.getTerminal().applicationCursor ? app : normal) }
        }

        let ctrl = KeyBarKey(title: "ctrl", icon: nil, accessibilityLabel: "Control", kind: .modifier) {
            guard let tv else { return }
            tv.controlModifier.toggle()
            bar?.modifierArmed = tv.controlModifier
        }
        let leading: [KeyBarKey] = [
            .function("esc", name: "Escape", send([0x1b])),
            ctrl,
            .function("", icon: "arrow.right.to.line", name: "Tab, complete", send([0x09])),
        ]
        var scrolling: [KeyBarKey] = [
            .function("^C", name: "Control C, interrupt", send([0x03])),
            .function("^D", name: "Control D, end of input", send([0x04])),
            .function("^L", name: "Control L, clear screen", send([0x0c])),
            .function("^U", name: "Control U, clear line", send([0x15])),
        ]
        scrolling += ["|", "/", "-", "_", "~", ".", "*", "$", ">", "<", "&", "=", ":", ";",
                      "'", "\"", "`", "\\", "#", "!", "?", "(", ")", "[", "]", "{", "}"]
            .map { symbol in .symbol(symbol) { tv?.send(txt: symbol) } }
        let trailing: [KeyBarKey] = [
            .repeating(icon: "arrow.left", name: "Left",
                       arrow(EscapeSequences.moveLeftApp, EscapeSequences.moveLeftNormal)),
            .repeating(icon: "arrow.up", name: "Up, previous command",
                       arrow(EscapeSequences.moveUpApp, EscapeSequences.moveUpNormal)),
            .repeating(icon: "arrow.down", name: "Down, next command",
                       arrow(EscapeSequences.moveDownApp, EscapeSequences.moveDownNormal)),
            .repeating(icon: "arrow.right", name: "Right",
                       arrow(EscapeSequences.moveRightApp, EscapeSequences.moveRightNormal)),
            .function("", icon: "keyboard.chevron.compact.down", name: "Hide keyboard") {
                _ = tv?.resignFirstResponder()
            },
        ]
        let made = KeyBar(leading: leading, scrolling: scrolling, trailing: trailing)
        bar = made
        // SwiftTerm applies an armed ctrl to the next key typed on the
        // keyboard, then clears it; follow so the key doesn't stay lit.
        NotificationCenter.default.addObserver(forName: .terminalViewControlModifierReset,
                                               object: terminalView, queue: .main) { _ in
            MainActor.assumeIsolated { bar?.modifierArmed = false }
        }
        return made
    }

    // MARK: - Code editor

    /// Keys for Python: indent / outdent, undo / redo, completion, comment
    /// toggling, the symbols on the keyboard's other pages, and cursor
    /// keys. `send` gets a key name for `window.__editor.key` in
    /// editor.html, plus the text for "text".
    static func editor(send: @escaping (_ key: String, _ text: String) -> Void,
                       hideKeyboard: @escaping () -> Void) -> KeyBar {
        func key(_ name: String) -> () -> Void { { send(name, "") } }
        let leading: [KeyBarKey] = [
            .function("", icon: "arrow.right.to.line", name: "Indent", key("tab")),
            .function("", icon: "arrow.left.to.line", name: "Outdent", key("outdent")),
        ]
        // Symbols first: on a phone only the first few keys are in view.
        var scrolling: [KeyBarKey] = ["(", ")", ":", "=", "[", "]", "{", "}", "'", "\"", "_", ".", ",",
                                      "+", "-", "*", "/", "<", ">", "!", "%", "&", "|", "@", "\\",
                                      "~", "^", "`", ";", "#"]
            .map { symbol in .symbol(symbol) { send("text", symbol) } }
        scrolling += [
            .function("", icon: "arrow.uturn.backward", name: "Undo", key("undo")),
            .function("", icon: "arrow.uturn.forward", name: "Redo", key("redo")),
            .function("", icon: "text.badge.plus", name: "Suggest completions", key("suggest")),
            .function("", icon: "number", name: "Toggle comment", key("comment")),
        ]
        let trailing: [KeyBarKey] = [
            .repeating(icon: "arrow.left", name: "Left", key("left")),
            .repeating(icon: "arrow.up", name: "Up", key("up")),
            .repeating(icon: "arrow.down", name: "Down", key("down")),
            .repeating(icon: "arrow.right", name: "Right", key("right")),
            .function("", icon: "keyboard.chevron.compact.down", name: "Hide keyboard", hideKeyboard),
        ]
        return KeyBar(leading: leading, scrolling: scrolling, trailing: trailing, floating: true)
    }
}

/// Floats a KeyBar on top of the on-screen keyboard for a view that can't
/// give UIKit an input accessory: a WKWebView, whose first responder is
/// WebKit's internal content view. The bar lives in the host's window and
/// shows while `isActive` (the owner's editor has focus) and a software
/// keyboard is up. It's positioned from the keyboard notifications: a
/// window's own keyboardLayoutGuide reports an empty frame. A hardware
/// keyboard brings at most its shortcuts bar, far shorter than a software
/// keyboard, so the bar stays hidden then.
final class FloatingKeyBarPresenter: NSObject {
    private let bar: KeyBar
    private weak var host: UIView?
    private var bottom: NSLayoutConstraint?
    /// How far the software keyboard reaches into the window; 0 while none
    /// is up.
    private var keyboardOverlap: CGFloat = 0

    var isActive = false {
        didSet { update() }
    }

    init(bar: KeyBar, host: UIView) {
        self.bar = bar
        self.host = host
        super.init()
        bar.isHidden = true
        let nc = NotificationCenter.default
        nc.addObserver(self, selector: #selector(keyboardWillChangeFrame(_:)),
                       name: UIResponder.keyboardWillChangeFrameNotification, object: nil)
        nc.addObserver(self, selector: #selector(keyboardWillHide(_:)),
                       name: UIResponder.keyboardWillHideNotification, object: nil)
    }

    /// Takes the bar off screen, e.g. when the host leaves its window.
    func detach() {
        isActive = false
        bar.removeFromSuperview()
        bottom = nil
    }

    @objc private func keyboardWillChangeFrame(_ note: Notification) {
        guard let window = host?.window, let screen = window.windowScene?.screen,
              let end = (note.userInfo?[UIResponder.keyboardFrameEndUserInfoKey] as? NSValue)?.cgRectValue
        else { return }
        let frame = window.convert(end, from: screen.coordinateSpace)
        keyboardOverlap = frame.height > 150 ? max(0, window.bounds.maxY - frame.minY) : 0
        let duration = note.userInfo?[UIResponder.keyboardAnimationDurationUserInfoKey] as? Double ?? 0
        let curve = note.userInfo?[UIResponder.keyboardAnimationCurveUserInfoKey] as? UInt ?? 0
        update(duration: duration, options: UIView.AnimationOptions(rawValue: curve << 16))
    }

    @objc private func keyboardWillHide(_ note: Notification) {
        keyboardOverlap = 0
        update()
    }

    private func update(duration: TimeInterval = 0, options: UIView.AnimationOptions = []) {
        guard isActive, keyboardOverlap > 0, let window = host?.window else {
            bar.isHidden = true
            return
        }
        if bar.superview !== window { attach(to: window) }
        window.bringSubviewToFront(bar)
        if bar.isHidden {
            // Start at the bottom edge, under the keyboard, and rise with it.
            bottom?.constant = 0
            window.layoutIfNeeded()
            bar.isHidden = false
        }
        bottom?.constant = -keyboardOverlap
        UIView.animate(withDuration: duration, delay: 0, options: options) {
            window.layoutIfNeeded()
        }
    }

    private func attach(to window: UIWindow) {
        bar.removeFromSuperview()
        bar.translatesAutoresizingMaskIntoConstraints = false
        window.addSubview(bar)
        let bottom = bar.bottomAnchor.constraint(equalTo: window.bottomAnchor)
        NSLayoutConstraint.activate([
            bar.leadingAnchor.constraint(equalTo: window.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: window.trailingAnchor),
            bar.heightAnchor.constraint(equalToConstant: KeyBar.barHeight),
            bottom,
        ])
        self.bottom = bottom
    }
}
