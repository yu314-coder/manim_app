//
//  DuoKeyboard.swift
//  ManimStudio
//
//  ManimStudio's own keyboard for the iPhone Duo held half-open like a
//  laptop: the lower half of the inner screen is the keyboard, the upper
//  half the code. It replaces the system keyboard there (the editor's
//  inputView) and puts what code needs on the keys themselves — digits,
//  brackets, : = _ and the rest on two rows above the letters, ctrl, tab,
//  undo, paste and arrows on the bottom row — so nothing hides behind a
//  "123" page and no key bar is needed. Anywhere else the system keyboard
//  and the floating key bar stay (MonacoEditorView decides).
//

import UIKit

final class DuoKeyboardView: UIInputView, UIInputViewAudioFeedback {
    /// `send` takes a key name for `window.__editor.key` (editor.html) and
    /// the text for "text"; `hide` puts the keyboard away.
    init(send: @escaping (_ key: String, _ text: String) -> Void, hide: @escaping () -> Void) {
        self.send = send
        self.hide = hide
        super.init(frame: CGRect(x: 0, y: 0, width: 400, height: 400), inputViewStyle: .keyboard)
        allowsSelfSizing = true
        backgroundColor = UIColor(white: 0.07, alpha: 1)
        buildKeys()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) not supported") }

    /// How tall the keyboard is: the lower half of the window.
    var height: CGFloat = 400 {
        didSet {
            guard height != oldValue else { return }
            invalidateIntrinsicContentSize()
        }
    }

    override var intrinsicContentSize: CGSize {
        CGSize(width: UIView.noIntrinsicMetric, height: height)
    }

    var enableInputClicksWhenVisible: Bool { true }

    // MARK: - Keys

    private enum Action {
        /// Types `normal`, or `shifted` while Shift is on.
        case text(String, shifted: String)
        case named(String)            // window.__editor.key name
        case shift, ctrl, backspace, space, enter, hide
    }

    private struct Key {
        let label: String
        let icon: String?
        let action: Action
        let weight: CGFloat
        let repeats: Bool
        let style: Style
        enum Style { case letter, symbol, function }
    }

    private let send: (String, String) -> Void
    private let hide: () -> Void
    private var rows: [[(Key, UIButton)]] = []
    private var shift = false { didSet { refreshLabels() } }
    private var capsLock = false
    private var lastShiftTap = Date.distantPast
    /// Sticky ctrl: the next letter runs its shortcut (A select all, C copy,
    /// X cut, V paste, Z undo, Y redo, F find, / comment).
    var ctrl = false { didSet { refreshLabels() } }
    private var repeatTimer: Timer?

    private func buildKeys() {
        func letters(_ s: String) -> [Key] {
            s.map { Key(label: String($0), icon: nil, action: .text(String($0), shifted: $0.uppercased()),
                        weight: 1, repeats: false, style: .letter) }
        }
        func pairs(_ normal: [String], _ shifted: [String]) -> [Key] {
            zip(normal, shifted).map { Key(label: $0, icon: nil, action: .text($0, shifted: $1),
                                           weight: 1, repeats: false, style: .symbol) }
        }
        func fn(_ label: String, _ icon: String?, _ action: Action, _ weight: CGFloat = 1.3,
                repeats: Bool = false) -> Key {
            Key(label: label, icon: icon, action: action, weight: weight, repeats: repeats, style: .function)
        }
        let layout: [[Key]] = [
            pairs(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
                  ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"]),
            pairs(["(", ")", "[", "]", "{", "}", ":", "=", "_", ".", ","],
                  ["<", ">", "+", "-", "*", "/", ";", "|", "\\", "~", "?"]),
            letters("qwertyuiop"),
            letters("asdfghjkl") + pairs(["'"], ["\""]),
            [fn("", "shift", .shift, 1.5)] + letters("zxcvbnm")
                + [fn("", "delete.left", .backspace, 1.5, repeats: true)],
            [fn("ctrl", nil, .ctrl, 1.2),
             fn("", "arrow.right.to.line", .named("tab")),
             fn("", "arrow.left.to.line", .named("outdent")),
             fn("", "arrow.uturn.backward", .named("undo")),
             fn("", "doc.on.clipboard", .named("paste")),
             Key(label: "", icon: nil, action: .space, weight: 3, repeats: false, style: .letter),
             fn("", "arrow.left", .named("left"), 1, repeats: true),
             fn("", "arrow.up", .named("up"), 1, repeats: true),
             fn("", "arrow.down", .named("down"), 1, repeats: true),
             fn("", "arrow.right", .named("right"), 1, repeats: true),
             fn("", "return", .enter, 1.4),
             fn("", "keyboard.chevron.compact.down", .hide, 1.2)],
        ]
        rows = layout.map { row in row.map { key in (key, makeButton(key)) } }
        refreshLabels()
    }

    private func makeButton(_ key: Key) -> UIButton {
        var config = UIButton.Configuration.filled()
        config.cornerStyle = .medium
        config.baseForegroundColor = .white
        config.baseBackgroundColor = Self.fill(key.style)
        config.contentInsets = .zero
        if let icon = key.icon {
            config.image = UIImage(systemName: icon, withConfiguration:
                UIImage.SymbolConfiguration(pointSize: 17, weight: .medium))
        }
        let button = UIButton(configuration: config)
        button.accessibilityLabel = key.icon.map { _ in Self.spokenName(key.action) } ?? key.label
        if key.repeats {
            button.addAction(UIAction { [weak self] _ in self?.startRepeating(key.action) }, for: .touchDown)
            button.addAction(UIAction { [weak self] _ in self?.stopRepeating() },
                             for: [.touchUpInside, .touchUpOutside, .touchCancel, .touchDragExit])
        } else {
            button.addAction(UIAction { [weak self] _ in self?.press(key.action) }, for: .touchUpInside)
        }
        addSubview(button)
        return button
    }

    private static func fill(_ style: Key.Style) -> UIColor {
        switch style {
        case .letter: return UIColor(white: 0.30, alpha: 1)
        case .symbol: return UIColor(white: 0.22, alpha: 1)
        case .function: return UIColor(white: 0.16, alpha: 1)
        }
    }

    private static func spokenName(_ action: Action) -> String {
        switch action {
        case .shift: return "Shift"
        case .backspace: return "Delete"
        case .enter: return "Return"
        case .hide: return "Hide keyboard"
        case .named(let name): return name.capitalized
        default: return ""
        }
    }

    /// Letters and symbols show what Shift would type; shift and ctrl light up.
    private func refreshLabels() {
        let armed = UIColor(red: 0.388, green: 0.400, blue: 0.945, alpha: 1)
        for row in rows {
            for (key, button) in row {
                guard var config = button.configuration else { continue }
                switch key.action {
                case .text(let normal, let shifted):
                    var title = AttributedString(shift ? shifted : normal)
                    title.font = key.style == .letter
                        ? UIFont.systemFont(ofSize: 22, weight: .regular)
                        : UIFont.monospacedSystemFont(ofSize: 19, weight: .regular)
                    config.attributedTitle = title
                case .shift:
                    config.image = UIImage(systemName: capsLock ? "capslock.fill" : (shift ? "shift.fill" : "shift"),
                                           withConfiguration: UIImage.SymbolConfiguration(pointSize: 17, weight: .medium))
                    config.baseBackgroundColor = shift ? armed : Self.fill(key.style)
                case .ctrl:
                    var title = AttributedString("ctrl")
                    title.font = UIFont.systemFont(ofSize: 15, weight: .semibold)
                    config.attributedTitle = title
                    config.baseBackgroundColor = ctrl ? armed : Self.fill(key.style)
                default:
                    break
                }
                button.configuration = config
            }
        }
    }

    // MARK: - Typing

    private func press(_ action: Action) {
        UIDevice.current.playInputClick()
        switch action {
        case .text(let normal, let shifted):
            let text = shift ? shifted : normal
            if ctrl, text.count == 1 {
                ctrl = false
                send("ctrlKey", text.lowercased())
            } else {
                send("text", text)
            }
            if shift && !capsLock { shift = false }
        case .named(let name):
            send(name, "")
        case .shift:
            // Tap twice quickly for caps lock.
            let now = Date()
            if !shift {
                shift = true
            } else if capsLock {
                capsLock = false
                shift = false
            } else if now.timeIntervalSince(lastShiftTap) < 0.35 {
                capsLock = true
                refreshLabels()
            } else {
                shift = false
            }
            lastShiftTap = now
        case .ctrl:
            ctrl.toggle()
        case .backspace:
            send("backspace", "")
        case .space:
            send("text", " ")
        case .enter:
            send("enter", "")
        case .hide:
            hide()
        }
    }

    private func startRepeating(_ action: Action) {
        stopRepeating()
        press(action)
        repeatTimer = Timer.scheduledTimer(withTimeInterval: 0.45, repeats: false) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.repeatTimer = Timer.scheduledTimer(withTimeInterval: 0.07, repeats: true) { _ in
                    MainActor.assumeIsolated { self?.press(action) }
                }
            }
        }
    }

    private func stopRepeating() {
        repeatTimer?.invalidate()
        repeatTimer = nil
    }

    override func willMove(toWindow newWindow: UIWindow?) {
        super.willMove(toWindow: newWindow)
        if newWindow == nil { stopRepeating() }
    }

    // MARK: - Layout

    override func layoutSubviews() {
        super.layoutSubviews()
        let inset: CGFloat = 6, rowGap: CGFloat = 8, keyGap: CGFloat = 6
        let area = bounds.inset(by: UIEdgeInsets(top: 10, left: inset + safeAreaInsets.left,
                                                 bottom: max(10, safeAreaInsets.bottom),
                                                 right: inset + safeAreaInsets.right))
        guard area.width > 0, area.height > 0, !rows.isEmpty else { return }
        let rowHeight = (area.height - rowGap * CGFloat(rows.count - 1)) / CGFloat(rows.count)
        // One key width for every row — the largest that fits the fullest
        // row — so letters line up like a real keyboard; shorter rows center.
        let unit = rows.map { row in
            (area.width - keyGap * CGFloat(row.count - 1)) / row.reduce(0) { $0 + $1.0.weight }
        }.min() ?? 40
        for (index, row) in rows.enumerated() {
            let rowWeight = row.reduce(0) { $0 + $1.0.weight }
            let rowWidth = unit * rowWeight + keyGap * CGFloat(row.count - 1)
            var x = area.minX + max(0, (area.width - rowWidth) / 2)
            let y = area.minY + CGFloat(index) * (rowHeight + rowGap)
            for (key, button) in row {
                let width = unit * key.weight
                button.frame = CGRect(x: x, y: y, width: width, height: rowHeight)
                x += width + keyGap
            }
        }
    }
}
