import UIKit
import SwiftTerm

/// A reusable "terminal pane" that hosts a real xterm emulator
/// (SwiftTerm) attached to the shared PTY. Drop it anywhere a
/// terminal is needed and every byte Python writes to stdout/stderr
/// renders with correct ANSI color, `\r` line-overwrite, and
/// cursor positioning. pip, rich, tqdm, click, pytest all "just work"
/// because `os.isatty(1)` returns True inside Python.
final class TerminalPaneViewController: UIViewController {

    // MARK: - UI

    private let titleBar = UIView()
    private let trafficClose = UIButton(type: .system)
    private let trafficMin   = UIButton(type: .system)
    private let trafficMax   = UIButton(type: .system)
    private let titleLabel = UILabel()
    private let interruptButton = UIButton(type: .system)
    private let fontMinusButton = UIButton(type: .system)
    private let fontPlusButton  = UIButton(type: .system)
    private let menuButton      = UIButton(type: .system)
    private let clearButton     = UIButton(type: .system)

    /// The actual xterm emulator view.
    let terminal = TerminalView()

    /// Optional prompt banner that the hosting VC can set.
    var onMinimize: (() -> Void)?
    var onMaximize: (() -> Void)?
    var onClose:    (() -> Void)?
    var onInterrupt: (() -> Void)?

    private var fontSize: CGFloat = 13

    // MARK: - Lifecycle

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.020, green: 0.024, blue: 0.032, alpha: 1.0)
        buildUI()

        // Point the shared PTY at this terminal
        terminal.terminalDelegate = PTYBridge.shared
        PTYBridge.shared.terminalView = terminal

        // Apply the default font
        applyFontSize()

        // After a tick (once the terminal has laid out and knows its
        // column count) send the size over to the PTY so rich / textual
        // auto-fit.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            self?.syncSizeToPTY()
        }
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        syncSizeToPTY()
    }

    // MARK: - UI construction

    private func buildUI() {
        // Inner title bar (traffic lights + Terminal · xterm-256color
        // strip + interrupt/font/menu/clear buttons) was removed — the
        // outer SwiftUI TerminalPane already exposes Copy + Del, and
        // the duplicate row was eating vertical space + showing extra
        // controls the user explicitly asked to drop.

        terminal.translatesAutoresizingMaskIntoConstraints = false
        terminal.backgroundColor = UIColor(red: 0.020, green: 0.024, blue: 0.032, alpha: 1.0)
        // Let SwiftTerm manage its own input — it renders a software
        // cursor and hands keystrokes to the delegate (PTYBridge).
        view.addSubview(terminal)

        NSLayoutConstraint.activate([
            terminal.topAnchor.constraint(equalTo: view.topAnchor),
            terminal.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            terminal.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            terminal.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
    }

    private func buildTitleBar() {
        titleBar.translatesAutoresizingMaskIntoConstraints = false
        titleBar.backgroundColor = UIColor(red: 0.071, green: 0.071, blue: 0.102, alpha: 1.0)

        // Bottom divider line
        let divider = UIView()
        divider.translatesAutoresizingMaskIntoConstraints = false
        divider.backgroundColor = UIColor(white: 0.16, alpha: 1)
        titleBar.addSubview(divider)

        // Traffic lights — close/minimize/maximize
        func makeLight(_ button: UIButton, color: UIColor, glyph: String, action: Selector) {
            button.translatesAutoresizingMaskIntoConstraints = false
            button.backgroundColor = color
            button.layer.cornerRadius = 6
            // Priority 999 so the 0-width temporary layout pass breaks this
            // gracefully instead of logging a constraint conflict on launch.
            let bw = button.widthAnchor.constraint(equalToConstant: 12)
            let bh = button.heightAnchor.constraint(equalToConstant: 12)
            bw.priority = .init(999); bh.priority = .init(999)
            bw.isActive = true; bh.isActive = true
            let cfg = UIImage.SymbolConfiguration(pointSize: 8, weight: .heavy)
            if let img = UIImage(systemName: glyph, withConfiguration: cfg)?
                .withTintColor(UIColor(white: 0.12, alpha: 1), renderingMode: .alwaysOriginal) {
                button.setImage(img, for: .normal)
            }
            button.addTarget(self, action: action, for: .touchUpInside)
        }
        makeLight(trafficClose, color: UIColor(red: 1.00, green: 0.38, blue: 0.38, alpha: 1),
                  glyph: "xmark", action: #selector(didTapClose))
        makeLight(trafficMin,   color: UIColor(red: 1.00, green: 0.75, blue: 0.20, alpha: 1),
                  glyph: "minus", action: #selector(didTapMinimize))
        makeLight(trafficMax,   color: UIColor(red: 0.35, green: 0.85, blue: 0.45, alpha: 1),
                  glyph: "arrow.up.left.and.arrow.down.right", action: #selector(didTapMaximize))

        let lights = UIStackView(arrangedSubviews: [trafficClose, trafficMin, trafficMax])
        lights.translatesAutoresizingMaskIntoConstraints = false
        lights.axis = .horizontal
        lights.spacing = 8

        // Center title
        titleLabel.translatesAutoresizingMaskIntoConstraints = false
        titleLabel.text = "Terminal · xterm-256color"
        titleLabel.font = UIFont.monospacedSystemFont(ofSize: 12, weight: .semibold)
        titleLabel.textColor = UIColor(white: 0.88, alpha: 1)
        titleLabel.textAlignment = .center

        // Right-side icon buttons
        func iconButton(_ button: UIButton, systemName: String, tint: UIColor, action: Selector) {
            button.translatesAutoresizingMaskIntoConstraints = false
            var cfg = UIButton.Configuration.plain()
            cfg.image = UIImage(systemName: systemName,
                                withConfiguration: UIImage.SymbolConfiguration(pointSize: 12, weight: .semibold))
            cfg.contentInsets = NSDirectionalEdgeInsets(top: 4, leading: 6, bottom: 4, trailing: 6)
            cfg.baseForegroundColor = tint
            button.configuration = cfg
            button.addTarget(self, action: action, for: .touchUpInside)
        }
        iconButton(interruptButton, systemName: "stop.fill",
                   tint: UIColor(red: 1, green: 0.5, blue: 0.5, alpha: 1),
                   action: #selector(didTapInterrupt))
        iconButton(fontMinusButton, systemName: "textformat.size.smaller",
                   tint: UIColor(white: 0.7, alpha: 1),
                   action: #selector(didTapFontSmaller))
        iconButton(fontPlusButton, systemName: "textformat.size.larger",
                   tint: UIColor(white: 0.7, alpha: 1),
                   action: #selector(didTapFontLarger))
        iconButton(menuButton, systemName: "ellipsis.circle",
                   tint: UIColor(white: 0.7, alpha: 1),
                   action: #selector(didTapMenu))
        iconButton(clearButton, systemName: "trash",
                   tint: UIColor(white: 0.7, alpha: 1),
                   action: #selector(didTapClear))

        let rightControls = UIStackView(arrangedSubviews: [
            interruptButton, fontMinusButton, fontPlusButton,
            menuButton, clearButton,
        ])
        rightControls.translatesAutoresizingMaskIntoConstraints = false
        rightControls.axis = .horizontal
        rightControls.spacing = 0

        titleBar.addSubview(lights)
        titleBar.addSubview(titleLabel)
        titleBar.addSubview(rightControls)

        NSLayoutConstraint.activate([
            divider.leadingAnchor.constraint(equalTo: titleBar.leadingAnchor),
            divider.trailingAnchor.constraint(equalTo: titleBar.trailingAnchor),
            divider.bottomAnchor.constraint(equalTo: titleBar.bottomAnchor),
            divider.heightAnchor.constraint(equalToConstant: 0.5),

            lights.leadingAnchor.constraint(equalTo: titleBar.leadingAnchor, constant: 10),
            lights.centerYAnchor.constraint(equalTo: titleBar.centerYAnchor),

            titleLabel.centerXAnchor.constraint(equalTo: titleBar.centerXAnchor),
            titleLabel.centerYAnchor.constraint(equalTo: titleBar.centerYAnchor),
            titleLabel.leadingAnchor.constraint(greaterThanOrEqualTo: lights.trailingAnchor, constant: 12),
            titleLabel.trailingAnchor.constraint(lessThanOrEqualTo: rightControls.leadingAnchor, constant: -12),

            rightControls.trailingAnchor.constraint(equalTo: titleBar.trailingAnchor, constant: -4),
            rightControls.centerYAnchor.constraint(equalTo: titleBar.centerYAnchor),
            rightControls.heightAnchor.constraint(equalToConstant: 28),
        ])
    }

    // MARK: - Actions

    @objc private func didTapClose()     { onClose?() }
    @objc private func didTapMinimize()  { onMinimize?() }
    @objc private func didTapMaximize()  { onMaximize?() }
    @objc private func didTapInterrupt() {
        // Send Ctrl+C (0x03) to the PTY — Python sees it as SIGINT.
        PTYBridge.shared.send(data: [0x03])
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        onInterrupt?()
    }

    @objc private func didTapFontSmaller() {
        fontSize = max(9, fontSize - 1)
        applyFontSize()
    }

    @objc private func didTapFontLarger() {
        fontSize = min(22, fontSize + 1)
        applyFontSize()
    }

    @objc private func didTapClear() {
        // CSI 2J (erase display) + CSI H (home cursor)
        PTYBridge.shared.terminalView?.feed(text: "\u{1b}[2J\u{1b}[H")
    }

    @objc private func didTapMenu(_ sender: UIButton) {
        let alert = UIAlertController(title: "Terminal", message: nil, preferredStyle: .actionSheet)
        alert.addAction(UIAlertAction(title: "Reset PTY (reconnect Python)", style: .destructive) { [weak self] _ in
            self?.resetPTY()
        })
        alert.addAction(UIAlertAction(title: "Send Ctrl+D (EOF)", style: .default) { _ in
            PTYBridge.shared.send(data: [0x04])
        })
        alert.addAction(UIAlertAction(title: "Send Ctrl+Z (suspend)", style: .default) { _ in
            PTYBridge.shared.send(data: [0x1a])
        })
        alert.addAction(UIAlertAction(title: "Paste clipboard into terminal", style: .default) { _ in
            if let text = UIPasteboard.general.string {
                PTYBridge.shared.send(text: text)
            }
        })
        alert.addAction(UIAlertAction(title: "Select all in terminal", style: .default) { [weak self] _ in
            self?.terminal.selectAll(nil)
        })
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        if let popover = alert.popoverPresentationController {
            popover.sourceView = sender
            popover.sourceRect = sender.bounds
        }
        present(alert, animated: true)
    }

    private func resetPTY() {
        // Issue a clear and send a newline so the Python shell prompts again.
        PTYBridge.shared.terminalView?.feed(text: "\u{1b}[2J\u{1b}[H")
        PTYBridge.shared.send(data: [0x0a])
    }

    private func applyFontSize() {
        let font = UIFont.monospacedSystemFont(ofSize: fontSize, weight: .regular)
        terminal.font = font
        syncSizeToPTY()
    }

    private func syncSizeToPTY() {
        // After font or view size change, tell the PTY the new cols/rows.
        let cols = max(10, UInt16(terminal.getTerminal().cols))
        let rows = max(3,  UInt16(terminal.getTerminal().rows))
        PTYBridge.shared.updateWindowSize(cols: cols, rows: rows)
    }

    // MARK: - Public helpers

    /// Write a literal line into the terminal (without routing through PTY).
    /// Useful for the boot banner.
    func writeBanner(_ text: String) {
        terminal.feed(text: text)
    }
}
