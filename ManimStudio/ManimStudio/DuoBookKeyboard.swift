import SwiftUI
import UIKit

// MARK: - iPhone Duo held like a book
//
// Half-open with the hinge running top to bottom, the left screen is the
// app and the right screen is only a keyboard. iOS won't put its own
// keyboard on one screen — it splits it into thumb halves along the bottom
// of both — so the right screen is ManimStudio's: drawn like Apple's, with
// the focused editor's or terminal's key bar on top. The editor and the
// terminal keep the focus (and the caret) with an empty input view, so
// iOS shows no keyboard of its own, and take the keys from here.

/// Where the book keyboard's keys go: the editor or terminal that last
/// took the focus while held like a book.
@MainActor
final class DuoKeyTarget {
    static let shared = DuoKeyTarget()

    enum Press {
        case text(String)
        case backspace
        case enter
    }

    struct Sink {
        let owner: ObjectIdentifier
        /// That owner's key bar, shown on top of the keys.
        let bar: KeyBar
        let press: (Press) -> Void
    }

    private(set) var sink: Sink?
    /// Called when the sink changes (the keyboard swaps its key bar).
    var onChange: (() -> Void)?

    func activate(_ sink: Sink) {
        guard self.sink?.owner != sink.owner else { return }
        self.sink = sink
        onChange?()
    }

    func deactivate(_ owner: AnyObject) {
        guard sink?.owner == ObjectIdentifier(owner) else { return }
        sink = nil
        onChange?()
    }
}

/// The right screen.
struct DuoBookKeyboard: UIViewRepresentable {
    func makeUIView(context: Context) -> DuoBookKeyboardView { DuoBookKeyboardView() }
    func updateUIView(_ uiView: DuoBookKeyboardView, context: Context) {}
}

final class DuoBookKeyboardView: UIView {
    private enum Page { case letters, symbols }
    private enum Action {
        case text(String, shifted: String)
        case shift, backspace, enter, space, page(Page)
    }

    static let background = UIColor(red: 0.13, green: 0.13, blue: 0.14, alpha: 1)
    private static let letterFill = UIColor(white: 0.36, alpha: 1)
    private static let functionFill = UIColor(white: 0.24, alpha: 1)
    private static let pressedFill = UIColor(white: 0.55, alpha: 1)

    private var page = Page.letters { didSet { rebuildKeys() } }
    private var shift = false { didSet { updateKeyTitles() } }
    private var capsLock = false { didSet { updateKeyTitles() } }
    private var lastShiftTap = Date.distantPast

    private let barSlot = UIView()
    private let keysView = UIView()
    private var keyButtons: [(UIButton, Action)] = []
    private var rows: [[(Action, CGFloat)]] = []
    private var repeatTimer: Timer?

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = Self.background
        addSubview(barSlot)
        addSubview(keysView)
        rebuildKeys()
        DuoKeyTarget.shared.onChange = { [weak self] in self?.showBar() }
        showBar()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    // MARK: Layout

    override func layoutSubviews() {
        super.layoutSubviews()
        let inset: CGFloat = 8
        let width = bounds.width - 2 * inset
        let bottom = bounds.maxY - max(safeAreaInsets.bottom, inset)
        // Keys as tall as Apple's on a big screen, at most; what's left
        // over stays empty above the key bar.
        let gap: CGFloat = 8
        let rowCount = CGFloat(rows.count)
        let barHeight = barSlot.subviews.first?.intrinsicContentSize.height ?? 0
        let room = bottom - max(safeAreaInsets.top, inset) - barHeight - gap
        let keyHeight = min(72, (room - gap * (rowCount - 1)) / rowCount)
        let keysHeight = keyHeight * rowCount + gap * (rowCount - 1)
        keysView.frame = CGRect(x: inset, y: bottom - keysHeight, width: width, height: keysHeight)
        barSlot.frame = CGRect(x: 0, y: keysView.frame.minY - gap - barHeight,
                               width: bounds.width, height: barHeight)
        barSlot.subviews.first?.frame = barSlot.bounds

        // A row's keys share its width by weight; rows of nine keys sit
        // in the middle like Apple's.
        let unit = rows.map { row in
            (width - gap * CGFloat(row.count - 1)) / max(1, row.reduce(0) { $0 + $1.1 })
        }.min() ?? 0
        var index = 0
        for (r, row) in rows.enumerated() {
            let rowWidth = row.reduce(0) { $0 + $1.1 * unit } + gap * CGFloat(row.count - 1)
            var x = (width - rowWidth) / 2
            let y = CGFloat(r) * (keyHeight + gap)
            for (_, weight) in row {
                let w = weight * unit
                keyButtons[index].0.frame = CGRect(x: x, y: y, width: w, height: keyHeight)
                x += w + gap
                index += 1
            }
        }
    }

    // MARK: Key bar

    private func showBar() {
        barSlot.subviews.forEach { $0.removeFromSuperview() }
        if let bar = DuoKeyTarget.shared.sink?.bar {
            bar.removeFromSuperview()
            bar.translatesAutoresizingMaskIntoConstraints = true
            barSlot.addSubview(bar)
        }
        setNeedsLayout()
    }

    // MARK: Keys

    private func rebuildKeys() {
        keyButtons.forEach { $0.0.removeFromSuperview() }
        keyButtons = []
        func keys(_ s: String, shifted: String? = nil) -> [(Action, CGFloat)] {
            let plain = s.split(separator: " ").map(String.init)
            let upper = shifted?.split(separator: " ").map(String.init) ?? plain.map { $0.uppercased() }
            return zip(plain, upper).map { (.text($0, shifted: $1), 1) }
        }
        let digits = keys("1 2 3 4 5 6 7 8 9 0", shifted: "! @ # $ % ^ & * ( )")
        switch page {
        case .letters:
            rows = [
                digits,
                keys("q w e r t y u i o p"),
                keys("a s d f g h j k l '", shifted: "A S D F G H J K L \""),
                [(.shift, 1.5)] + keys("z x c v b n m") + [(.backspace, 1.5)],
                [(.page(.symbols), 2), (.space, 6), (.enter, 2)],
            ]
        case .symbols:
            let same = { (s: String) in keys(s, shifted: s) }
            rows = [
                digits,
                same("- / : ; ( ) $ & @ \""),
                same("[ ] { } # % ^ * + ="),
                same("_ \\ | ~ < > . , ? !") + [(.backspace, 1.5)],
                [(.page(.letters), 2), (.space, 6), (.enter, 2)],
            ]
        }
        for row in rows {
            for (action, _) in row {
                let button = makeButton(for: action)
                keysView.addSubview(button)
                keyButtons.append((button, action))
            }
        }
        updateKeyTitles()
        setNeedsLayout()
    }

    private func makeButton(for action: Action) -> UIButton {
        let button = UIButton(type: .custom)
        button.layer.cornerRadius = 8
        button.layer.cornerCurve = .continuous
        button.layer.shadowColor = UIColor.black.cgColor
        button.layer.shadowOpacity = 0.35
        button.layer.shadowRadius = 0
        button.layer.shadowOffset = CGSize(width: 0, height: 1)
        button.setTitleColor(.white, for: .normal)
        button.tintColor = .white
        switch action {
        case .text:
            button.backgroundColor = Self.letterFill
            button.titleLabel?.font = .systemFont(ofSize: 24)
        case .space:
            button.backgroundColor = Self.letterFill
            button.accessibilityLabel = "Space"
        case .shift:
            button.backgroundColor = Self.functionFill
        case .backspace:
            button.backgroundColor = Self.functionFill
            button.setImage(UIImage(systemName: "delete.left"), for: .normal)
            button.accessibilityLabel = "Delete"
            let hold = UILongPressGestureRecognizer(target: self, action: #selector(backspaceHeld(_:)))
            hold.minimumPressDuration = 0.4
            button.addGestureRecognizer(hold)
        case .enter:
            button.backgroundColor = Self.functionFill
            button.setImage(UIImage(systemName: "return"), for: .normal)
            button.accessibilityLabel = "Return"
        case .page(let to):
            button.backgroundColor = Self.functionFill
            button.setTitle(to == .symbols ? "123" : "ABC", for: .normal)
            button.titleLabel?.font = .systemFont(ofSize: 18)
            button.accessibilityLabel = to == .symbols ? "Numbers and symbols" : "Letters"
        }
        button.setPreferredSymbolConfiguration(.init(pointSize: 20, weight: .regular), forImageIn: .normal)
        button.addTarget(self, action: #selector(keyDown(_:)), for: .touchDown)
        button.addTarget(self, action: #selector(keyUp(_:)), for: [.touchUpOutside, .touchCancel])
        button.addTarget(self, action: #selector(keyTapped(_:)), for: .touchUpInside)
        return button
    }

    private var upper: Bool { shift || capsLock }

    private func updateKeyTitles() {
        for (button, action) in keyButtons {
            switch action {
            case .text(let plain, let shifted):
                let title = upper ? shifted : plain
                button.setTitle(title, for: .normal)
                button.accessibilityLabel = title
            case .shift:
                let name = capsLock ? "capslock.fill" : (shift ? "shift.fill" : "shift")
                button.setImage(UIImage(systemName: name), for: .normal)
                button.backgroundColor = upper ? Self.pressedFill : Self.functionFill
                button.accessibilityLabel = capsLock ? "Caps lock" : "Shift"
            default:
                break
            }
        }
    }

    private func action(of button: UIButton) -> Action? {
        keyButtons.first { $0.0 === button }?.1
    }

    @objc private func keyDown(_ button: UIButton) {
        button.alpha = 0.6
    }

    @objc private func keyUp(_ button: UIButton) {
        button.alpha = 1
    }

    @objc private func keyTapped(_ button: UIButton) {
        button.alpha = 1
        guard let action = action(of: button) else { return }
        let press = DuoKeyTarget.shared.sink?.press
        switch action {
        case .text(let plain, let shifted):
            press?(.text(upper ? shifted : plain))
            if shift && !capsLock { shift = false }
        case .space:
            press?(.text(" "))
        case .backspace:
            press?(.backspace)
        case .enter:
            press?(.enter)
        case .shift:
            // Double tap: caps lock, as on Apple's.
            let now = Date()
            if capsLock {
                capsLock = false
                shift = false
            } else if now.timeIntervalSince(lastShiftTap) < 0.35 {
                capsLock = true
            } else {
                shift.toggle()
            }
            lastShiftTap = now
        case .page(let to):
            page = to
            shift = false
            capsLock = false
        }
    }

    @objc private func backspaceHeld(_ gesture: UILongPressGestureRecognizer) {
        switch gesture.state {
        case .began:
            repeatTimer?.invalidate()
            repeatTimer = Timer.scheduledTimer(withTimeInterval: 0.08, repeats: true) { _ in
                MainActor.assumeIsolated { DuoKeyTarget.shared.sink?.press(.backspace) }
            }
        case .ended, .cancelled, .failed:
            repeatTimer?.invalidate()
            repeatTimer = nil
        default:
            break
        }
    }
}
