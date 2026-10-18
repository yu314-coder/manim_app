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
//  On a narrow width (an iPhone, an iPad in Split View) the bar has two
//  rows: the symbols scroll along the top, and every other key sits in a
//  fixed row below, so nothing needed all the time is ever scrolled away.
//  On a wide one it's a single row.
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

    /// Paste for a keyboard that has no ⌘V: the on-screen keyboard has no
    /// paste key, and neither the editor (Monaco in a web view) nor the
    /// terminal gets a working paste from iOS's own paste buttons. Reads the
    /// clipboard itself, so iOS may ask "Allow Paste?"; the user can allow
    /// it for good in Settings. (UIPasteControl, which avoids the prompt,
    /// stays disabled in this floating row.)
    static func paste(_ handler: @escaping (String) -> Void) -> KeyBarKey {
        .function("", icon: "doc.on.clipboard", name: "Paste") {
            guard UIPasteboard.general.hasStrings,
                  let text = UIPasteboard.general.string, !text.isEmpty else { return }
            handler(text)
        }
    }
}

final class KeyBar: UIInputView, UIInputViewAudioFeedback {
    private static let isPad = UIDevice.current.userInterfaceIdiom == .pad
    private static let rowHeight: CGFloat = isPad ? 50 : 44
    private static let keyHeight: CGFloat = isPad ? 38 : 34
    private static let minKeyWidth: CGFloat = isPad ? 44 : 32
    /// Narrower than this (an iPhone, an iPad in Split View), the bar
    /// takes two rows: one row would leave room for only a key or two
    /// between the pinned ones.
    private static let compactWidth: CGFloat = 560

    private static let symbolFill = UIColor(white: 1, alpha: 0.17)
    private static let functionFill = UIColor(white: 1, alpha: 0.08)
    private static let armedFill = UIColor(red: 0.388, green: 0.400, blue: 0.945, alpha: 1)

    private let leadingKeys: [KeyBarKey]
    private let scrollingKeys: [KeyBarKey]
    private let trailingKeys: [KeyBarKey]
    private var content: [UIView] = []
    private var builtCompact: Bool?
    /// One row or two. A self-sizing input accessory takes its height from
    /// its constraints, not from intrinsicContentSize.
    private lazy var heightConstraint: NSLayoutConstraint = {
        let constraint = heightAnchor.constraint(equalToConstant: Self.height(compact: !Self.isPad))
        constraint.priority = UILayoutPriority(999)
        return constraint
    }()

    private static func height(compact: Bool) -> CGFloat {
        (compact ? 2 : 1) * rowHeight
    }
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
        // Until the first layout knows the width, guess from the device.
        super.init(frame: CGRect(x: 0, y: 0, width: 320, height: Self.height(compact: !Self.isPad)),
                   inputViewStyle: floating ? .default : .keyboard)
        allowsSelfSizing = true
        heightConstraint.isActive = true
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
        CGSize(width: UIView.noIntrinsicMetric, height: heightConstraint.constant)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        guard bounds.width > 0 else { return }
        let compact = bounds.width < Self.compactWidth
        if compact != builtCompact {
            builtCompact = compact
            build(compact: compact)
            heightConstraint.constant = Self.height(compact: compact)
            invalidateIntrinsicContentSize()
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

        let scroller = KeyScrollView()
        scroller.showsHorizontalScrollIndicator = false
        scroller.alwaysBounceHorizontal = true
        // Keys fire as soon as they're touched; a sideways drag that starts
        // on one still scrolls (KeyScrollView takes the touch back).
        scroller.delaysContentTouches = false
        let middleRow = row(scrollingKeys, compact: compact)
        middleRow.translatesAutoresizingMaskIntoConstraints = false
        scroller.addSubview(middleRow)
        let inset: CGFloat = 6
        let gap: CGFloat = 8
        var constraints = [
            middleRow.leadingAnchor.constraint(equalTo: scroller.contentLayoutGuide.leadingAnchor),
            middleRow.trailingAnchor.constraint(equalTo: scroller.contentLayoutGuide.trailingAnchor),
            middleRow.topAnchor.constraint(equalTo: scroller.contentLayoutGuide.topAnchor),
            middleRow.bottomAnchor.constraint(equalTo: scroller.contentLayoutGuide.bottomAnchor),
            middleRow.heightAnchor.constraint(equalTo: scroller.frameLayoutGuide.heightAnchor),
        ]

        if compact {
            // Symbols scroll along the top; the rest share the bottom row
            // in equal widths, so it fits a phone without scrolling.
            let fixedRow = row(leadingKeys + trailingKeys, compact: compact)
            fixedRow.distribution = .fillEqually
            content = [scroller, fixedRow]
            for view in content {
                view.translatesAutoresizingMaskIntoConstraints = false
                addSubview(view)
            }
            constraints += [
                scroller.leadingAnchor.constraint(equalTo: safeAreaLayoutGuide.leadingAnchor, constant: inset),
                scroller.trailingAnchor.constraint(equalTo: safeAreaLayoutGuide.trailingAnchor, constant: -inset),
                scroller.topAnchor.constraint(equalTo: topAnchor),
                scroller.heightAnchor.constraint(equalToConstant: Self.rowHeight),

                fixedRow.leadingAnchor.constraint(equalTo: safeAreaLayoutGuide.leadingAnchor, constant: inset),
                fixedRow.trailingAnchor.constraint(equalTo: safeAreaLayoutGuide.trailingAnchor, constant: -inset),
                fixedRow.centerYAnchor.constraint(equalTo: topAnchor, constant: Self.rowHeight * 1.5),
            ]
        } else {
            let leadingRow = row(leadingKeys, compact: compact)
            let trailingRow = row(trailingKeys, compact: compact)
            content = [leadingRow, scroller, trailingRow]
            for view in content {
                view.translatesAutoresizingMaskIntoConstraints = false
                addSubview(view)
            }
            constraints += [
                leadingRow.leadingAnchor.constraint(equalTo: safeAreaLayoutGuide.leadingAnchor, constant: inset),
                leadingRow.centerYAnchor.constraint(equalTo: centerYAnchor),

                scroller.leadingAnchor.constraint(equalTo: leadingRow.trailingAnchor, constant: gap),
                scroller.trailingAnchor.constraint(equalTo: trailingRow.leadingAnchor, constant: -gap),
                scroller.topAnchor.constraint(equalTo: topAnchor),
                scroller.bottomAnchor.constraint(equalTo: bottomAnchor),

                trailingRow.trailingAnchor.constraint(equalTo: safeAreaLayoutGuide.trailingAnchor, constant: -inset),
                trailingRow.centerYAnchor.constraint(equalTo: centerYAnchor),
            ]
        }
        NSLayoutConstraint.activate(constraints)
        styleModifier()
    }

    private func row(_ keys: [KeyBarKey], compact: Bool) -> UIStackView {
        let stack = UIStackView(arrangedSubviews: keys.map { button(for: $0, compact: compact) })
        stack.axis = .horizontal
        stack.spacing = Self.isPad ? 6 : 4
        stack.alignment = .center
        return stack
    }

    private func button(for key: KeyBarKey, compact: Bool) -> UIButton {
        var config = UIButton.Configuration.filled()
        config.cornerStyle = .medium
        config.baseForegroundColor = .white
        config.baseBackgroundColor = key.kind == .symbol ? Self.symbolFill : Self.functionFill
        // The fixed row of a narrow bar shares out its width; slim insets
        // keep "ctrl" from truncating on the narrowest phones.
        let side: CGFloat = compact ? 2 : 8
        config.contentInsets = NSDirectionalEdgeInsets(top: 0, leading: side, bottom: 0, trailing: side)
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
            // Same as SwiftTerm's own paste: wrapped in bracketed-paste
            // markers when the program running asked for them.
            .paste { text in
                guard let tv else { return }
                let bracketed = tv.getTerminal().bracketedPasteMode
                if bracketed { tv.send(data: EscapeSequences.bracketedPasteStart[0...]) }
                tv.send(txt: text)
                if bracketed { tv.send(data: EscapeSequences.bracketedPasteEnd[0...]) }
            },
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

    /// Keys for Python: a sticky ctrl for ⌃A / ⌃C / ⌃V…, indent / outdent,
    /// undo, paste, the symbols on the
    /// keyboard's other pages, redo, completion, comment toggling,
    /// copy / cut / select all, and cursor keys. `send` gets a key name for `window.__editor.key` in
    /// editor.html, plus the text for "text".
    static func editor(send: @escaping (_ key: String, _ text: String) -> Void,
                       hideKeyboard: @escaping () -> Void) -> KeyBar {
        func key(_ name: String) -> () -> Void { { send(name, "") } }
        weak var bar: KeyBar?
        // Sticky, like the terminal's: tap it, then a letter on the
        // keyboard — A select all, C copy, X cut, V paste, Z undo, Y redo.
        // The editor un-lights it (`ctrlReleased`) once a letter is used.
        let ctrl = KeyBarKey(title: "ctrl", icon: nil, accessibilityLabel: "Control", kind: .modifier) {
            guard let bar else { return }
            bar.modifierArmed.toggle()
            send("ctrl", bar.modifierArmed ? "on" : "off")
        }
        let leading: [KeyBarKey] = [
            ctrl,
            // Also accepts the highlighted suggestion while the list is up
            // (Return just starts a new line when typing on the screen).
            .function("", icon: "arrow.right.to.line", name: "Indent, or accept suggestion", key("tab")),
            .function("", icon: "arrow.left.to.line", name: "Outdent", key("outdent")),
            .function("", icon: "arrow.uturn.backward", name: "Undo", key("undo")),
            .paste { text in send("paste", text) },
        ]
        // Symbols first: on a phone only the first ten or so are in view.
        var scrolling: [KeyBarKey] = ["(", ")", ":", "=", "[", "]", "{", "}", "'", "\"", "_", ".", ",",
                                      "+", "-", "*", "/", "<", ">", "!", "%", "&", "|", "@", "\\",
                                      "~", "^", "`", ";", "#"]
            .map { symbol in .symbol(symbol) { send("text", symbol) } }
        scrolling += [
            .function("", icon: "arrow.uturn.forward", name: "Redo", key("redo")),
            .function("", icon: "text.badge.plus", name: "Suggest completions", key("suggest")),
            .function("", icon: "number", name: "Toggle comment", key("comment")),
            .function("", icon: "doc.on.doc", name: "Copy", key("copy")),
            .function("", icon: "scissors", name: "Cut", key("cut")),
            .function("", icon: "selection.pin.in.out", name: "Select all", key("selectAll")),
        ]
        let trailing: [KeyBarKey] = [
            .repeating(icon: "arrow.left", name: "Left", key("left")),
            .repeating(icon: "arrow.up", name: "Up", key("up")),
            .repeating(icon: "arrow.down", name: "Down", key("down")),
            .repeating(icon: "arrow.right", name: "Right", key("right")),
            .function("", icon: "keyboard.chevron.compact.down", name: "Hide keyboard", hideKeyboard),
        ]
        let made = KeyBar(leading: leading, scrolling: scrolling, trailing: trailing, floating: true)
        bar = made
        return made
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
extension Notification.Name {
    /// Posted by FloatingKeyBarPresenter with userInfo["height"] (CGFloat):
    /// how tall the floating bar is on screen, 0 when it's hidden.
    static let editorKeyBarHeight = Notification.Name("editor.keyBar.height")
}

final class FloatingKeyBarPresenter: NSObject {
    private let bar: KeyBar
    private var announcedHeight: CGFloat = 0
    private weak var host: UIView?
    private var bottom: NSLayoutConstraint?
    /// How far the software keyboard reaches into the window; 0 while none
    /// is up.
    private var keyboardOverlap: CGFloat = 0
    /// Whether the keyboard last seen was the on-screen one (true) or a
    /// hardware keyboard's shortcuts bar (false).
    private var typingOnScreen: Bool?
    /// Told when typing switches between the on-screen keyboard and a
    /// hardware one; the editor relaxes its completion for touch typing.
    var onTypingOnScreenChange: ((Bool) -> Void)?

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
        let overlap = max(0, window.bounds.maxY - frame.minY)
        keyboardOverlap = frame.height > 150 ? overlap : 0
        // Only a keyboard that's coming up says which kind is in use; one
        // going away says nothing.
        if overlap > 0, typingOnScreen != (frame.height > 150) {
            typingOnScreen = frame.height > 150
            onTypingOnScreenChange?(frame.height > 150)
        }
        let duration = note.userInfo?[UIResponder.keyboardAnimationDurationUserInfoKey] as? Double ?? 0
        let curve = note.userInfo?[UIResponder.keyboardAnimationCurveUserInfoKey] as? UInt ?? 0
        update(duration: duration, options: UIView.AnimationOptions(rawValue: curve << 16))
    }

    @objc private func keyboardWillHide(_ note: Notification) {
        keyboardOverlap = 0
        update()
    }

    /// Tells the layout how much of the screen the bar covers.
    private func announce(_ height: CGFloat) {
        guard height != announcedHeight else { return }
        announcedHeight = height
        NotificationCenter.default.post(name: .editorKeyBarHeight, object: nil,
                                        userInfo: ["height": height])
    }

    private func update(duration: TimeInterval = 0, options: UIView.AnimationOptions = []) {
        guard isActive, keyboardOverlap > 0, let window = host?.window else {
            bar.isHidden = true
            announce(0)
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
        announce(bar.intrinsicContentSize.height)
    }

    private func attach(to window: UIWindow) {
        bar.removeFromSuperview()
        bar.translatesAutoresizingMaskIntoConstraints = false
        window.addSubview(bar)
        // Height from the bar itself: one row or two, by width.
        let bottom = bar.bottomAnchor.constraint(equalTo: window.bottomAnchor)
        NSLayoutConstraint.activate([
            bar.leadingAnchor.constraint(equalTo: window.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: window.trailingAnchor),
            bottom,
        ])
        self.bottom = bottom
    }
}
