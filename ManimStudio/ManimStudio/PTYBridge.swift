import Foundation
import Darwin
import SwiftTerm
import GameController  // for GCKeyboard magic-keyboard detection

/// A pseudo-terminal (PTY) that bridges CPython's stdin/stdout/stderr
/// to a SwiftTerm TerminalView.
///
/// `openpty()` is available in the iOS libSystem without any entitlement
/// (only `fork`/`exec` are blocked in the app sandbox). We:
///   1. Create a PTY master/slave pair
///   2. dup2 the slave FD onto Python's stdin (0), stdout (1), stderr (2)
///   3. Spawn a background queue that `read()`s from the master FD and
///      feeds every byte into the SwiftTerm emulator, which renders it
///   4. Forward TerminalView input back into the master FD so stdin reads
///      in Python see the user's typed text
///   5. On TerminalView resize, fire TIOCSWINSZ so curses / textual /
///      rich's auto-width detection reflow
///
/// Once this is set up, `os.isatty(1)` returns True inside Python, which
/// is the signal pip/rich/tqdm/click/pytest all check to decide whether
/// to use interactive output vs buffered. They start "just working."
final class PTYBridge: NSObject, TerminalViewDelegate {

    static let shared = PTYBridge()

    /// PTY master FD — we read from here to get what Python wrote, and
    /// write to here to send user keystrokes back to Python's stdin.
    private(set) var masterFD: Int32 = -1

    /// PTY slave FD — dup2'd onto Python's 0/1/2. We keep a copy open
    /// so the PTY doesn't close when Python's file descriptors turn over.
    private var slaveFD: Int32 = -1

    /// Write end of the stdout pipe. With the pipe (not PTY) design on
    /// iOS, Python's sys.stdout gets redirected to this fd at the
    /// Python level (os.fdopen) instead of dup2'ing fd 1 process-wide —
    /// so Swift print() stays on Xcode console.
    private(set) var stdoutPipeWriteFD: Int32 = -1

    /// The terminal view we're rendering into. Weak — owned by the VC.
    weak var terminalView: TerminalView? {
        didSet {
            // Flush any bytes that arrived before the VC attached.
            flushPendingBytes()
        }
    }

    /// Optional callback fired for every chunk of bytes we feed into
    /// the terminal view. The VC uses this to keep its `terminalLogBuffer`
    /// in sync so the Copy / Export-log buttons still capture the full
    /// scrollback even though Python output now bypasses appendToTerminal.
    var onOutputBytes: (([UInt8]) -> Void)?

    /// Our background read source — pulls bytes off the master FD.
    private var readSource: DispatchSourceRead?
    /// Tail of an incoming PTY chunk that didn't end on a newline.
    /// Held over to the next read so the [manim-debug] line filter
    /// can match across chunk boundaries.
    private var debugFilterCarry: [UInt8] = []

    /// Bytes that arrived from Python's stdout BEFORE terminalView was
    /// set. Without this buffer, the REPL's boot banner ("CodeBench shell
    /// — type help …") would vanish into the void.
    private var pendingBytes = [UInt8]()
    private let pendingLock = NSLock()

    /// Coalesced feed buffer. The pipe-read source can fire dozens of
    /// times per second under tqdm; flushing one main.async-scheduled
    /// SwiftTerm.feed() per ~30 ms (instead of one per chunk) keeps the
    /// main run loop free for SwiftUI redraws and button hits.
    private var feedBuffer: [UInt8] = []
    private let feedBufferLock = NSLock()
    private var feedDrainScheduled = false

    private func flushPendingBytes() {
        pendingLock.lock()
        let bytes = pendingBytes
        pendingBytes.removeAll(keepingCapacity: false)
        pendingLock.unlock()
        guard !bytes.isEmpty else { return }
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.terminalView?.feed(byteArray: bytes[...])
            self.onOutputBytes?(bytes)
        }
    }

    /// Saved copies of the original stdin/stdout/stderr so tests can
    /// restore if they need to.
    private var savedStdin:  Int32 = -1
    private var savedStdout: Int32 = -1
    private var savedStderr: Int32 = -1

    /// Whether setup() has successfully run once. Guards against
    /// double-dup2 if called again.
    private(set) var isReady = false

    private override init() {
        super.init()
    }

    // MARK: - Setup

    /// Call this exactly once, typically from the app delegate, BEFORE
    /// any Python code that might write to stdout runs.
    ///
    /// iOS blocks `openpty()` (EPERM) for sandboxed apps. We use
    /// plain `pipe()` pairs instead:
    ///   • stdin pipe: user keystrokes → write-end → read-end = fd 0 in Python
    ///   • stdout pipe: Python writes → fd 1/2 = write-end → read-end → SwiftTerm
    /// We lose real TTY semantics (no kernel echo, no canonical mode,
    /// no termios) but keystrokes flow and `FORCE_COLOR=1` makes
    /// pip/rich/tqdm produce ANSI output anyway. Local echo is
    /// handled in `send(source:data:)` by feeding typed bytes back
    /// into the terminal view directly.
    func setupIfNeeded() {
        guard !isReady else { return }

        // stdin pipe: [0]=read end (dup2'd onto fd 0, Python reads),
        //             [1]=write end (we write keystrokes here).
        var stdinPipe: [Int32] = [-1, -1]
        // stdout pipe: [0]=read end (we read Python output),
        //              [1]=write end (dup2'd onto fd 1 & 2).
        var stdoutPipe: [Int32] = [-1, -1]

        guard Darwin.pipe(&stdinPipe) == 0 else {
            NSLog("[PTY] stdin pipe() failed: errno=\(errno)")
            return
        }
        guard Darwin.pipe(&stdoutPipe) == 0 else {
            NSLog("[PTY] stdout pipe() failed: errno=\(errno)")
            Darwin.close(stdinPipe[0]); Darwin.close(stdinPipe[1])
            return
        }

        // Save originals so we can restore them if ever needed.
        savedStdin  = dup(0)
        savedStdout = dup(1)
        savedStderr = dup(2)

        // Python stdin ← stdin-pipe read end (dup2'd onto fd 0 so
        // Python's sys.stdin naturally reads from our pipe).
        _ = dup2(stdinPipe[0], 0)
        Darwin.close(stdinPipe[0])

        // Python stdout / stderr: do NOT dup2 onto fd 1 / fd 2. Both
        // are shared with iOS and Swift:
        //   • fd 1 — Swift `print(...)` writes here. If hijacked,
        //     "[app] Returning to foreground" etc. bleed into the
        //     terminal.
        //   • fd 2 — iOS os_log / WebKit / notification subsystems
        //     flood this with OSLOG diagnostic messages.
        // Instead, keep the pipe write end alive here and let
        // PythonRuntime redirect sys.stdout / sys.stderr at the Python
        // level via os.fdopen(fd). Swift print() keeps its Xcode-
        // console destination; Python's output lands in the terminal.
        stdoutPipeWriteFD = stdoutPipe[1]

        // Set the stdout read end to non-blocking so our dispatch
        // source doesn't stall when Python is idle.
        _ = fcntl(stdoutPipe[0], F_SETFL,
                  fcntl(stdoutPipe[0], F_GETFL) | O_NONBLOCK)

        // fd 1 / fd 2 are NOT hijacked — Swift print / iOS os_log stay
        // on Xcode console. Python redirects sys.stdout/sys.stderr at
        // the Python level via stdoutPipeWriteFD (see PythonRuntime).

        // Public handles: masterFD keeps the name for historical
        // reasons — it's the stdin write end we push keystrokes into.
        masterFD = stdinPipe[1]
        // slaveFD now holds the stdout-pipe read end for the read loop.
        slaveFD = stdoutPipe[0]

        startReadLoop()

        isReady = true
        NSLog("[PTY] ready (pipes): stdin_w=\(stdinPipe[1]) stdout_r=\(stdoutPipe[0])")

        // Status line shown the moment the terminal pane appears, so
        // the user isn't staring at an empty black box. The real
        // shell banner + prompt land on fresh lines below as soon as
        // offlinai_shell.repl() finishes booting — no overlap because
        // this line ends in \r\n. Boot is kicked off from
        // ManimStudioApp.init so by the time the user lands in
        // Workspace, the prompt is usually already there.
        let banner = "\u{1b}[38;5;244m[terminal ready — booting Python REPL...]\u{1b}[0m\r\n"
        banner.withCString { cs in
            _ = Darwin.write(stdoutPipeWriteFD, cs, strlen(cs))
        }

        installMagicKeyboardObservers()
    }

    // MARK: - Magic keyboard detection

    private var magicKeyboardObserverInstalled = false
    private func installMagicKeyboardObservers() {
        guard !magicKeyboardObserverInstalled else { return }
        magicKeyboardObserverInstalled = true
        let nc = NotificationCenter.default
        nc.addObserver(forName: .GCKeyboardDidConnect, object: nil, queue: .main) { [weak self] _ in
            self?.logMagicKeyboard(state: "connected")
        }
        nc.addObserver(forName: .GCKeyboardDidDisconnect, object: nil, queue: .main) { [weak self] _ in
            self?.logMagicKeyboard(state: "disconnected")
        }
        // Already-connected check on setup
        if GCKeyboard.coalesced != nil {
            logMagicKeyboard(state: "connected (already present)")
        }
    }

    private func logMagicKeyboard(state: String) {
        NSLog("[PTY] magic keyboard \(state)")
        let banner = "\u{1b}[38;5;244m[magic keyboard \(state)]\u{1b}[0m\r\n"
        DispatchQueue.main.async { [weak self] in
            self?.terminalView?.feed(text: banner)
        }
    }

    // MARK: - Read loop

    private func startReadLoop() {
        // With the pipe-based setup, the stdout-pipe READ end is in
        // `slaveFD` (name kept for backwards compat). This is what
        // Python's stdout/stderr writes land in.
        let readFD = slaveFD
        let queue = DispatchQueue(label: "codebench.pty.reader", qos: .userInteractive)
        let source = DispatchSource.makeReadSource(fileDescriptor: readFD, queue: queue)

        source.setEventHandler { [weak self] in
            guard let self = self else { return }
            var buffer = [UInt8](repeating: 0, count: 4096)
            let n = buffer.withUnsafeMutableBufferPointer { bp in
                Darwin.read(readFD, bp.baseAddress, bp.count)
            }
            guard n > 0 else { return }
            let rawUnfiltered = Array(buffer[0..<n])

            // Tee every byte the PTY emits into the persistent log
            // file BEFORE filtering. Captures the [manim-debug] /
            // tqdm / Python tracebacks unfiltered so the log file
            // retains the raw stream for crash diagnosis.
            CrashLogger.shared.appendRaw(Data(rawUnfiltered))

            // Strip [manim-debug] lines before SwiftTerm sees them.
            // The wrapper script peppers these prints throughout the
            // render pipeline (codec init, encoded-batch counters,
            // stream-close events) — useful in the log for failure
            // diagnosis, but pure noise on the terminal pane during
            // normal use. The filter buffers across reads because a
            // chunk boundary can land mid-line.
            let raw = self.stripDebugLines(rawUnfiltered)
            guard !raw.isEmpty else { return }

            // First pass: detect + strip our private OSC mode-switch
            // sequences. TUI apps (ncdu, vim, …) write
            //   "\x1b]codebench;raw\x1b\\"    — enter raw input mode
            //   "\x1b]codebench;cooked\x1b\\" — return to cooked mode
            // to tell LineBuffer to stop line-editing and forward each
            // keystroke directly. We strip them here so they never
            // reach SwiftTerm (which would show them as garbage chars).
            let rawModeMarker: [UInt8] = Array("\u{1B}]codebench;raw\u{1B}\\".utf8)
            let cookedModeMarker: [UInt8] = Array("\u{1B}]codebench;cooked\u{1B}\\".utf8)
            // `ai` REPL toggles on entry/exit so the LineBuffer knows to
            // complete `/xxx` against the AI slash-command list on Tab
            // and to echo the list when a bare `/` is typed.
            let aiOnMarker: [UInt8] = Array("\u{1B}]codebench;ai-on\u{1B}\\".utf8)
            let aiOffMarker: [UInt8] = Array("\u{1B}]codebench;ai-off\u{1B}\\".utf8)
            var modeStripped: [UInt8] = []
            modeStripped.reserveCapacity(raw.count)
            var i = 0
            while i < raw.count {
                if _indexOf(rawModeMarker, in: raw, at: i) {
                    DispatchQueue.main.async {
                        LineBuffer.shared.setRawMode(true)
                    }
                    i += rawModeMarker.count
                    continue
                }
                if _indexOf(cookedModeMarker, in: raw, at: i) {
                    DispatchQueue.main.async {
                        LineBuffer.shared.setRawMode(false)
                    }
                    i += cookedModeMarker.count
                    continue
                }
                if _indexOf(aiOnMarker, in: raw, at: i) {
                    DispatchQueue.main.async {
                        LineBuffer.shared.setAIMode(true)
                    }
                    i += aiOnMarker.count
                    continue
                }
                if _indexOf(aiOffMarker, in: raw, at: i) {
                    DispatchQueue.main.async {
                        LineBuffer.shared.setAIMode(false)
                    }
                    i += aiOffMarker.count
                    continue
                }
                modeStripped.append(raw[i])
                i += 1
            }

            // ONLCR emulation: a real PTY's termios layer translates
            // bare LF to CRLF on output so a newline both advances the
            // cursor AND returns it to column 0. Our pipe has no termios,
            // so Python's `\n` arrives here as plain 0x0A and SwiftTerm
            // interprets it as "cursor down, same column" — producing
            // prompts stair-stepped to the right of the previous line's
            // content. Convert every lone LF to CRLF here. Existing CRs
            // (CRLF sequences) are preserved untouched.
            var cooked: [UInt8] = []
            cooked.reserveCapacity(modeStripped.count + 16)
            var j = 0
            while j < modeStripped.count {
                let b = modeStripped[j]
                if b == 0x0A {
                    let prev = j > 0 ? modeStripped[j - 1] : (cooked.last ?? 0)
                    if prev != 0x0D {
                        cooked.append(0x0D)
                    }
                    cooked.append(0x0A)
                } else {
                    cooked.append(b)
                }
                j += 1
            }
            let slice = cooked

            // Coalesce: instead of dispatching one main.async per pipe
            // event (which floods the main run loop during a manim
            // render and locks the UI), append into a shared buffer
            // and dispatch at most one drain per ~30 ms (~33 fps).
            // SwiftTerm renders the accumulated bytes in one feed()
            // call; main stays free for buttons + redraws.
            self.feedBufferLock.lock()
            self.feedBuffer.append(contentsOf: slice)
            let needsSchedule = !self.feedDrainScheduled
            if needsSchedule { self.feedDrainScheduled = true }
            self.feedBufferLock.unlock()

            if needsSchedule {
                DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(30)) { [weak self] in
                    guard let self = self else { return }
                    self.feedBufferLock.lock()
                    let bytes = self.feedBuffer
                    self.feedBuffer.removeAll(keepingCapacity: true)
                    self.feedDrainScheduled = false
                    self.feedBufferLock.unlock()
                    guard !bytes.isEmpty else { return }
                    if let tv = self.terminalView {
                        tv.feed(byteArray: bytes[...])
                    } else {
                        self.pendingLock.lock()
                        self.pendingBytes.append(contentsOf: bytes)
                        self.pendingLock.unlock()
                    }
                    self.onOutputBytes?(bytes)
                }
            }
        }

        source.resume()
        readSource = source
    }

    /// Drop any line that begins with the literal "[manim-debug]" from
    /// the byte stream before SwiftTerm sees it. Lines that don't match
    /// pass through untouched — including tqdm progress bars (which
    /// only use \r, no \n, so they're emitted as a single growing
    /// buffer the user sees animate normally).
    ///
    /// Buffering: input is split on \n. The final fragment (which may
    /// not end on \n yet) is held in `debugFilterCarry` and prepended
    /// to the next chunk so a `[manim-debug]` line spanning a chunk
    /// boundary is still caught. tqdm-style updates that use only \r
    /// stay in the carry until a real \n flushes them — fine for our
    /// purpose because tqdm rewrites the same line via \r within one
    /// "Animation N: …" prefix that always finishes with \n eventually.
    fileprivate func stripDebugLines(_ input: [UInt8]) -> [UInt8] {
        let prefix: [UInt8] = Array("[manim-debug]".utf8)
        var work = debugFilterCarry + input
        debugFilterCarry.removeAll(keepingCapacity: true)
        var out: [UInt8] = []
        out.reserveCapacity(work.count)
        var lineStart = 0
        var i = 0
        while i < work.count {
            if work[i] == 0x0A {  // '\n'
                let length = i - lineStart + 1
                if length >= prefix.count + 1 {
                    var matches = true
                    for k in 0..<prefix.count {
                        if work[lineStart + k] != prefix[k] { matches = false; break }
                    }
                    if matches { lineStart = i + 1; i += 1; continue }
                }
                // Keep this line.
                out.append(contentsOf: work[lineStart...i])
                lineStart = i + 1
            }
            i += 1
        }
        // Unterminated remainder. Critical: only carry it forward if
        // it COULD still be the start of a "[manim-debug]" line. If
        // the bytes already disqualify it from matching the prefix,
        // flush them out immediately. The shell prompt is a notable
        // case: "mobile@iPad ~/Workspace % " never ends in \n, and
        // unconditionally carrying held the prompt hostage forever.
        if lineStart < work.count {
            let tail = Array(work[lineStart..<work.count])
            if isPrefixOfDebugMarker(tail, marker: prefix), tail.count <= 4096 {
                debugFilterCarry = tail
            } else {
                out.append(contentsOf: tail)
            }
        }
        return out
    }

    /// True iff `tail` is a (proper or full) byte-prefix of `marker`.
    /// `tail = "[manim-d"` → true (could grow into "[manim-debug]").
    /// `tail = "mobile@i"` → false (definitely not — flush now).
    /// Empty tail → true (any future bytes could begin the marker).
    private func isPrefixOfDebugMarker(_ tail: [UInt8],
                                       marker: [UInt8]) -> Bool {
        if tail.count > marker.count { return false }
        for i in 0..<tail.count {
            if tail[i] != marker[i] { return false }
        }
        return true
    }

    /// Return true iff `haystack[at...]` starts with `needle`. Used by
    /// the read loop to detect OSC mode-switch markers (raw / cooked).
    private func _indexOf(_ needle: [UInt8], in haystack: [UInt8], at: Int) -> Bool {
        guard at + needle.count <= haystack.count else { return false }
        for k in 0..<needle.count {
            if haystack[at + k] != needle[k] { return false }
        }
        return true
    }

    // MARK: - Env vars for pretty output

    /// Called before Py_Initialize so pip, rich, tqdm, click see the
    /// right tty-flavored environment and produce interactive output.
    static func exportTTYEnv(cols: Int = 80, rows: Int = 24) {
        setenv("TERM",              "xterm-256color", 1)
        setenv("COLORTERM",         "truecolor",       1)
        setenv("FORCE_COLOR",       "1",               1)
        setenv("CLICOLOR",          "1",               1)
        setenv("CLICOLOR_FORCE",    "1",               1)
        setenv("PYTHONUNBUFFERED",  "1",               1)
        setenv("PYTHONIOENCODING",  "utf-8",           1)
        setenv("COLUMNS",           String(cols),      1)
        setenv("LINES",             String(rows),      1)
        // Hint to pip and friends to not buffer
        setenv("PIP_NO_COLOR",      "0",               1)   // let rich color
        setenv("PAGER",             "cat",             1)   // `pip help` shouldn't page
    }

    // MARK: - Resize forwarding

    /// Forward the current TerminalView's columns/rows to the PTY so
    /// curses-like libraries reflow. Call from the TerminalViewDelegate
    /// `sizeChanged` hook.
    func updateWindowSize(cols: UInt16, rows: UInt16) {
        guard masterFD >= 0 else { return }
        var ws = winsize()
        ws.ws_col = cols
        ws.ws_row = rows
        ws.ws_xpixel = 0
        ws.ws_ypixel = 0
        _ = ioctl(masterFD, UInt(TIOCSWINSZ), &ws)
        setenv("COLUMNS", String(cols), 1)
        setenv("LINES",   String(rows), 1)
    }

    // MARK: - Writing to Python's stdin

    /// Push a byte array into the PTY master — appears to Python as if
    /// typed on stdin. Used by the TerminalView delegate for keystrokes.
    func send(data: [UInt8]) {
        if data.isEmpty { return }
        // On-demand PTY setup: if somehow we got a keystroke before
        // setupIfNeeded ran (app launch timing, terminal view attached
        // super early, etc.), open the PTY right now and retry. This
        // means the very first key the user taps always lands — no
        // more "send dropped: masterFD=-1" after the fix + rebuild.
        if masterFD < 0 {
            NSLog("[PTY] send before setup — calling setupIfNeeded now")
            setupIfNeeded()
            if masterFD < 0 {
                NSLog("[PTY] setupIfNeeded failed; dropping \(data.count) bytes")
                return
            }
        }
        let preview = data.prefix(32).map { String(format: "%02x", $0) }.joined(separator: " ")
        NSLog("[PTY] → master(\(masterFD)): \(data.count) bytes: \(preview)")
        data.withUnsafeBufferPointer { bp in
            let n = Darwin.write(masterFD, bp.baseAddress, bp.count)
            if n < 0 {
                NSLog("[PTY] write failed: errno=\(errno)")
            } else if n != data.count {
                NSLog("[PTY] partial write: \(n) of \(data.count) bytes")
            }
        }
    }

    func send(text: String) {
        send(data: Array(text.utf8))
    }

    // MARK: - TerminalViewDelegate

    func send(source: TerminalView, data: ArraySlice<UInt8>) {
        // All line editing is done locally in Swift (see LineBuffer
        // below). This mirrors how a real PTY's kernel line discipline
        // works: the kernel handles char-by-char echoing, cursor
        // movement, backspace, history etc., and only delivers
        // COMPLETE LINES to the application when the user presses
        // Enter.
        //
        // Benefits over Python-side editing:
        //  • Works before Python has initialized (cold-launch typing).
        //  • No pipe round-trip per keystroke — instant echo.
        //  • Swift has direct access to the TerminalView so cursor
        //    math is simple and synchronous.
        //
        // When the user presses Enter, LineBuffer writes the full line
        // (plus \n) into our stdin pipe so Python reads it like a
        // normal line-mode stdin.
        LineBuffer.shared.handle(bytes: data, terminalView: source,
                                 pipeWrite: { [weak self] bytes in
            self?.send(data: bytes)
        })
    }

    func sizeChanged(source: TerminalView, newCols: Int, newRows: Int) {
        updateWindowSize(cols: UInt16(newCols), rows: UInt16(newRows))
        // SwiftTerm reflows content on resize; any palette rows below
        // the input line may now be in unpredictable positions. Wipe
        // and re-render cleanly so we don't leave stale duplicates
        // on screen. Also pass the new row count so the palette caps
        // itself to fit without causing the terminal to scroll.
        LineBuffer.shared.handleTerminalResize(terminalView: source, rows: newRows)
    }

    func setTerminalTitle(source: TerminalView, title: String) {
        // TerminalView sets this via the OSC 0 escape; the hosting VC can
        // observe if it wants to update the title bar, but we don't need
        // anything here by default.
    }

    func hostCurrentDirectoryUpdate(source: TerminalView, directory: String?) {
        // Optional hook for cwd-aware UI.
    }

    func scrolled(source: TerminalView, position: Double) {
        // no-op
    }

    func rangeChanged(source: TerminalView, startY: Int, endY: Int) {
        // no-op
    }

    func requestOpenLink(source: TerminalView, link: String, params: [String: String]) {
        // SwiftTerm auto-detects anything path-shaped as a link (including
        // TeX's "(./beamer.cls" style stdout). Only hand http(s) URLs to
        // UIApplication — everything else just causes LaunchServices
        // error -50 "invalid input parameters" noise in the console.
        guard let url = URL(string: link),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else { return }
        DispatchQueue.main.async {
            UIApplication.shared.open(url)
        }
    }

    func bell(source: TerminalView) {
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
    }

    func clipboardCopy(source: TerminalView, content: Data) {
        UIPasteboard.general.string = String(data: content, encoding: .utf8)
    }

    func iTermContent(source: TerminalView, content: ArraySlice<UInt8>) {
        // iTerm2 proprietary escapes — ignore
    }
}


// MARK: - LineBuffer (Swift-side "cooked" line discipline)
//
// Replaces a kernel PTY's ICANON / ECHO line-editing. Takes raw bytes
// from SwiftTerm (arrow keys, control chars, printable text), maintains
// an internal line buffer + cursor position + history, echoes edits
// back to the TerminalView immediately, and only pushes a complete
// line into Python's stdin pipe when the user presses Enter.
//
// All operations happen on the main actor: the TerminalViewDelegate
// callback is main-thread and LineBuffer methods are only called from
// there.

final class LineBuffer {

    static let shared = LineBuffer()

    /// The current typed-line bytes (UTF-8).
    private var buf: [UInt8] = []
    /// Cursor byte offset within `buf`.
    private var cursor: Int = 0
    /// Command history, newest last.
    private var history: [String] = []
    /// Index into history when navigating with ↑ / ↓. Equal to
    /// history.count when not navigating.
    private var histIdx: Int = 0
    /// Saved partial line when the user starts history navigation.
    private var savedPartial: [UInt8] = []
    /// Partial CSI / SS3 escape sequence being accumulated from input.
    private var escBuf: [UInt8] = []
    /// Escape-sequence state machine: .idle, .esc (just saw ESC),
    /// .csi (saw ESC [), .ss3 (saw ESC O).
    private enum EscState { case idle, esc, csi, ss3 }
    private var escState: EscState = .idle

    /// When raw mode is on, every byte from the TerminalView is
    /// forwarded straight to Python's stdin with NO line editing,
    /// NO echo, NO history navigation. This is what ncurses TUI
    /// apps (ncdu, vim, htop, …) need so they can handle keypresses
    /// byte-by-byte themselves.
    ///
    /// Python switches the mode by writing our private OSC sequence:
    ///   "\x1b]codebench;raw\x1b\\"     — enter raw mode
    ///   "\x1b]codebench;cooked\x1b\\"  — return to cooked (line-buffered)
    /// The PTYBridge read loop detects these in outgoing bytes, strips
    /// them before feeding SwiftTerm, and calls `setRawMode`.
    private var _isRawMode = false

    func setRawMode(_ raw: Bool) {
        _isRawMode = raw
        if raw {
            // Discard any in-progress cooked-mode line so we don't
            // accidentally commit it when the app exits.
            buf.removeAll(keepingCapacity: false)
            cursor = 0
            histIdx = history.count
            escState = .idle
            escBuf.removeAll(keepingCapacity: false)
        }
        NSLog("[LineBuffer] raw mode → \(raw)")
    }

    var isRawMode: Bool { _isRawMode }

    /// AI mode — set when the user enters the `ai` REPL. Changes Tab
    /// behaviour (slash commands instead of shell builtins) and
    /// shows a floating command palette when `/` is typed, matching
    /// the UX of Claude Code / Cursor / Warp: instant appearance on
    /// `/`, real-time filter as the user keeps typing, arrow-key
    /// navigation, Tab/Enter to select, Esc to dismiss.
    private var _isAIMode = false

    func setAIMode(_ on: Bool) {
        _isAIMode = on
        if !on { hidePalette() }
        NSLog("[LineBuffer] ai mode → \(on)")
    }

    /// The AI REPL's slash-command vocabulary + one-line descriptions.
    /// Kept in sync with `_SLASH` in offlinai_ai/__init__.py — if
    /// Python adds a new command, add it here too.
    private static let aiSlashCommands: [(cmd: String, desc: String)] = [
        ("/help",   "show command list"),
        ("/model",  "set active model (registry slug)"),
        ("/models", "list cached models"),
        ("/load",   "load cached model (auto-picks if only one)"),
        ("/pull",   "download a model (no arg → list registry)"),
        ("/run",    "pull + load + enter AI"),
        ("/mode",   "set mode: allow/plan/auto/bypass/nothing"),
        ("/file",   "set target file for edits"),
        ("/show",   "show current target file"),
        ("/ls",     "list workspace files"),
        ("/usage",  "show token usage"),
        ("/reset",  "reset conversation"),
        ("/clear",  "clear the terminal"),
        ("/quit",   "exit ai"),
        ("/exit",   "exit ai"),
    ]

    // MARK: - Floating slash-command palette

    /// Is the palette currently drawn below the input line?
    private var _paletteVisible = false
    /// Number of rows the palette occupies (for cleanup).
    private var _paletteRows = 0
    /// Currently-highlighted entry in the filtered list.
    private var _paletteSelected = 0
    /// Filtered view of `aiSlashCommands` matching the current buffer.
    private var _paletteFiltered: [(cmd: String, desc: String)] = []

    /// Terminal height in cells. Tracked via `handleTerminalResize` so
    /// the palette can cap its row count to what fits below the input
    /// line without causing the terminal to scroll. Scrolling breaks
    /// cursor save/restore (`\x1B[s` / `\x1B[u`) because the saved
    /// absolute row isn't updated when lines shift up — that was the
    /// "`/pull` appears twice as I type" symptom the user reported.
    private var _terminalRows: Int = 24

    /// Render the palette below the current input line. Uses save/
    /// restore cursor (`\x1B[s` / `\x1B[u`) + erase-below (`\x1B[J`)
    /// so we don't need to track how many rows we drew last time —
    /// the erase takes care of whatever's below, even if SwiftTerm
    /// reflowed content after a window resize. That was the bug the
    /// user reported: "expand the terminal size by dragging, the same
    /// thing will show twice like `/load`" — the old code tracked row
    /// counts as integers and went stale on resize, so `clearPaletteRows`
    /// didn't actually clear the old rows and the new rows drew on
    /// top of them, producing a double list.
    /// Fixed height of the palette area. Always drawn at this size so
    /// clearing is consistent between renders — previous attempts at a
    /// variable-height palette left stale fragments on screen when the
    /// filter shrank between keystrokes ("/rrn" and "/reuet" corruption).
    private static let aiPaletteHeight = 6

    private func renderPalette(terminalView tv: TerminalView) {
        guard let prefixStr = String(bytes: buf, encoding: .utf8) else { return }
        let needle = prefixStr.isEmpty ? "/" : prefixStr
        let filtered = Self.aiSlashCommands.filter {
            $0.cmd.hasPrefix(needle)
        }
        _paletteFiltered = filtered
        if _paletteFiltered.isEmpty {
            clearPaletteRows(terminalView: tv)
            hidePalette()
            return
        }
        if _paletteSelected >= _paletteFiltered.count {
            _paletteSelected = 0
        }

        // Fixed-height render: always draw exactly `aiPaletteHeight`
        // rows below the prompt, filling with either filtered commands
        // or blank lines. This way clearPaletteRows always knows how
        // many to clear regardless of how the filter changed — no
        // stale fragments. First N rows show commands (with the
        // highlighted one around _paletteSelected), remaining rows
        // are blank.
        let visible = min(_paletteFiltered.count, Self.aiPaletteHeight - 1)
        let overflow = _paletteFiltered.count - visible
        // Scroll window so the selected entry is always in view.
        var firstIdx = 0
        if _paletteSelected >= visible {
            firstIdx = _paletteSelected - visible + 1
        }

        clearPaletteRows(terminalView: tv)

        let maxCmd = _paletteFiltered.map { $0.cmd.count }.max() ?? 8
        for slot in 0..<Self.aiPaletteHeight {
            echo([0x0D, 0x0A], tv)                   // CR+LF next row
            echo(Array("\u{1B}[2K".utf8), tv)        // clear entire line
            if slot < visible {
                let i = firstIdx + slot
                let entry = _paletteFiltered[i]
                let padded = entry.cmd.padding(
                    toLength: maxCmd, withPad: " ", startingAt: 0)
                let row: String
                if i == _paletteSelected {
                    row = "\u{1B}[7m ▸ \(padded)  \(entry.desc)  \u{1B}[0m"
                } else {
                    row = "   \(padded)  \u{1B}[2m\(entry.desc)\u{1B}[0m"
                }
                echo(Array(row.utf8), tv)
            } else if slot == visible && overflow > 0 {
                // "+N more" hint row
                let hint = "\u{1B}[2m   … \(overflow) more (↑↓ to navigate)\u{1B}[0m"
                echo(Array(hint.utf8), tv)
            }
            // else: blank row, already cleared
        }

        _paletteRows = Self.aiPaletteHeight
        _paletteVisible = true

        // Return cursor to the input line.
        let col = 4 /* "ai> " */ + Self.bufVisibleWidth(buf)
        echo(Array("\u{1B}[\(_paletteRows)A".utf8), tv)
        echo([0x0D], tv)
        if col > 0 {
            echo(Array("\u{1B}[\(col)C".utf8), tv)
        }
    }

    /// Clear previously-drawn palette rows. Uses per-row explicit
    /// `\x1B[2K` (clear entire line) so each old row is definitively
    /// wiped. Consistently clears `aiPaletteHeight` rows if palette
    /// was visible.
    private func clearPaletteRows(terminalView tv: TerminalView) {
        guard _paletteRows > 0 else { return }
        let rows = _paletteRows
        for _ in 0..<rows {
            echo([0x0D, 0x0A], tv)
            echo(Array("\u{1B}[2K".utf8), tv)
        }
        echo(Array("\u{1B}[\(rows)A".utf8), tv)
        echo([0x0D], tv)
        let col = 4 + Self.bufVisibleWidth(buf)
        if col > 0 {
            echo(Array("\u{1B}[\(col)C".utf8), tv)
        }
        _paletteRows = 0
    }

    /// Visible cell count of a UTF-8 byte buffer. Counts lead bytes only,
    /// skips continuation bytes (10xxxxxx). Not wide-char-aware but fine
    /// for the ASCII slash commands that typing `/` triggers.
    private static func bufVisibleWidth(_ bytes: [UInt8]) -> Int {
        var n = 0
        for b in bytes {
            if (b & 0xC0) != 0x80 { n += 1 }
        }
        return n
    }

    /// Called by PTYBridge when the TerminalView's cell grid changes
    /// size (user drags the split, rotates the device, etc.). If a
    /// palette is visible, its old rows may have reflowed into stale
    /// positions — wipe the area below the input line and redraw.
    func handleTerminalResize(terminalView tv: TerminalView, rows: Int) {
        _terminalRows = max(4, rows)
        guard _paletteVisible else { return }
        // After resize, clear + redraw at the new width. Use the same
        // relative-move approach as renderPalette — no save/restore.
        clearPaletteRows(terminalView: tv)
        renderPalette(terminalView: tv)
    }

    private func hidePalette() {
        _paletteVisible = false
        _paletteFiltered.removeAll()
        _paletteSelected = 0
        // Note: this does NOT clear the rows on screen — that requires
        // a TerminalView. Call clearPaletteRows(terminalView:) first
        // from any key handler that has tv in scope.
    }

    /// Commands that do something useful with no argument. Selecting one
    /// from the palette submits the line immediately; commands NOT in
    /// this set (e.g. `/model`, `/mode`, `/file`, `/run`) fill `/cmd ` and
    /// wait for the user to provide the argument before Enter.
    ///
    /// `/load` is standalone: with no arg it lists cached models and
    /// auto-loads the only one (or prompts to pick).
    /// `/pull` is standalone: with no arg it prints the registry.
    private static let aiStandaloneCommands: Set<String> = [
        "/help", "/quit", "/exit", "/clear", "/usage",
        "/models", "/reset", "/ls", "/show",
        "/load", "/pull", "/run",
    ]

    /// Tab (or any fill action): replace the input buffer with the
    /// highlighted palette entry + trailing space, leaving the palette
    /// hidden. User types args or presses Enter.
    private func fillPaletteSelection(terminalView tv: TerminalView) {
        guard _paletteSelected < _paletteFiltered.count else { return }
        let chosen = _paletteFiltered[_paletteSelected].cmd
        replaceBufferWith(chosen + " ", terminalView: tv)
        clearPaletteRows(terminalView: tv)
        hidePalette()
    }

    /// Enter in palette: fill + submit (if command takes no args) or
    /// fill-and-wait (if it needs an arg).
    private func acceptPaletteSelection(terminalView tv: TerminalView,
                                        pipeWrite: @escaping ([UInt8]) -> Void) {
        guard _paletteSelected < _paletteFiltered.count else { return }
        let chosen = _paletteFiltered[_paletteSelected].cmd
        let standalone = Self.aiStandaloneCommands.contains(chosen)
        if standalone {
            replaceBufferWith(chosen, terminalView: tv)
            clearPaletteRows(terminalView: tv)
            hidePalette()
            commitLine(terminalView: tv, pipeWrite: pipeWrite)
        } else {
            replaceBufferWith(chosen + " ", terminalView: tv)
            clearPaletteRows(terminalView: tv)
            hidePalette()
        }
    }

    /// Replace the current input buffer with `text` in one atomic
    /// screen update: clear the existing line, reprint prompt, print
    /// new text. The prompt matches Python's `ai> ` (cyan + reset).
    private func replaceBufferWith(_ text: String, terminalView tv: TerminalView) {
        // Wipe the current input line, move to column 0, reprint prompt.
        echo(Array("\u{1B}[2K\r\u{1B}[36mai>\u{1B}[0m ".utf8), tv)
        buf = Array(text.utf8)
        cursor = buf.count
        echo(buf, tv)
    }

    private init() {}

    // MARK: - Public entry point

    /// Process a batch of bytes from SwiftTerm. Handles every key /
    /// escape sequence we care about, calls `pipeWrite(line+\n)` once
    /// per Enter press.
    func handle(bytes: ArraySlice<UInt8>,
                terminalView: TerminalView,
                pipeWrite: @escaping ([UInt8]) -> Void) {
        if _isRawMode {
            // TUI mode: forward every byte straight to Python with no
            // echo and no line editing. The TUI app (ncdu, vim, …)
            // handles each byte itself.
            pipeWrite(Array(bytes))
            return
        }
        // Scroll the terminal to the bottom so the user always sees
        // the prompt they're typing into. This fires for keyboard
        // events only — program output (e.g. a running `python` script
        // writing to stdout) goes through a different path and does
        // NOT auto-scroll, so a user who scrolled up to read earlier
        // output stays put until they interact.
        if !bytes.isEmpty {
            scrollToBottom(terminalView)
        }
        for b in bytes {
            processByte(b, terminalView: terminalView, pipeWrite: pipeWrite)
        }
    }

    // MARK: - Echo helpers

    private func echo(_ bytes: [UInt8], _ terminalView: TerminalView) {
        if bytes.isEmpty { return }
        terminalView.feed(byteArray: ArraySlice(bytes))
    }

    private func echo(_ s: String, _ terminalView: TerminalView) {
        echo(Array(s.utf8), terminalView)
    }

    /// Jump the TerminalView's scroll position to the bottom. Called
    /// on every user keystroke so that typing at the prompt always
    /// brings the prompt back into view — matches the convention of
    /// bash/zsh/iTerm2 ("scroll-on-input"). Program output (from a
    /// running `python` or `cc`) does NOT call this, so a user who
    /// scrolled up to read past output stays where they were until
    /// they type something.
    private func scrollToBottom(_ tv: TerminalView) {
        // SwiftTerm's TerminalView exposes `scroll(toPosition:)` on a
        // 0.0–1.0 scale; 1.0 == fully scrolled down.
        tv.scroll(toPosition: 1.0)
    }

    // MARK: - Byte dispatcher

    private func processByte(_ b: UInt8,
                             terminalView tv: TerminalView,
                             pipeWrite: @escaping ([UInt8]) -> Void) {
        // Escape-sequence state machine
        switch escState {
        case .esc:
            if b == 0x5B /* [ */ {
                escState = .csi
                escBuf.removeAll(keepingCapacity: true)
                return
            }
            if b == 0x4F /* O */ {
                escState = .ss3
                return
            }
            // Unknown ESC-prefixed byte; drop both.
            escState = .idle
            return

        case .csi:
            // CSI: ESC [ <params> <final-byte in 0x40..0x7E>
            if b >= 0x40 && b <= 0x7E {
                handleCSI(final: b, params: escBuf, terminalView: tv)
                escBuf.removeAll(keepingCapacity: true)
                escState = .idle
                return
            }
            escBuf.append(b)
            if escBuf.count > 16 { escState = .idle; escBuf.removeAll() }
            return

        case .ss3:
            handleSS3(b, terminalView: tv)
            escState = .idle
            return

        case .idle:
            break
        }

        // Regular byte handling
        switch b {
        case 0x1B: // ESC
            escState = .esc
        case 0x0D, 0x0A: // Enter (CR or LF)
            // Palette-open Enter: accept highlighted entry. If the
            // chosen command takes no arguments (/help, /quit, /clear,
            // /exit, /usage, /models, /reset, /ls, /show), submit it
            // immediately. Otherwise fill it in with a trailing space
            // and wait for the user to type an argument + Enter again.
            if _paletteVisible && _paletteSelected < _paletteFiltered.count {
                acceptPaletteSelection(terminalView: tv,
                                       pipeWrite: pipeWrite)
                return
            }
            commitLine(terminalView: tv, pipeWrite: pipeWrite)
        case 0x7F, 0x08: // Backspace / BS
            backspace(terminalView: tv)
        case 0x03: // Ctrl-C
            // Two paths for interrupt — which one matters depends on
            // whether Python is reading stdin or executing code:
            //   1) If the REPL is blocked in os.read(0, …), the REPL
            //      will see the 0x03 byte and raise KeyboardInterrupt
            //      inside its own frame.
            //   2) If the user script is running (e.g. `while True:`),
            //      the REPL is NOT reading stdin — bytes pile up in the
            //      pipe. We need PyErr_SetInterrupt() which asynchronously
            //      raises KeyboardInterrupt in the Python main thread at
            //      the next bytecode boundary.
            //   3) When the `ai` REPL is mid-generation (polling Swift's
            //      response file in a tight time.sleep loop, NOT reading
            //      stdin), neither of the above helps. Write the cancel
            //      signal file directly so AIEngine.pollCancel picks it
            //      up within 150ms, calls runner.cancelGeneration(), and
            //      writes ai_done.txt with status -130; Python's
            //      _stream_response then returns normally with that
            //      status and handles it as "user cancelled".
            echo([0x5e, 0x43, 0x0d, 0x0a], tv) // "^C\r\n"
            buf.removeAll(keepingCapacity: true)
            cursor = 0
            histIdx = history.count
            // Also dismiss the palette if it's showing.
            if _paletteVisible {
                clearPaletteRows(terminalView: tv)
                hidePalette()
            }
            if _isAIMode {
                let sig = NSTemporaryDirectory() + "latex_signals/"
                try? FileManager.default.createDirectory(
                    atPath: sig, withIntermediateDirectories: true)
                let cancelPath = sig + "ai_cancel.txt"
                try? "1".write(toFile: cancelPath,
                               atomically: true, encoding: .utf8)
            }
            pipeWrite([0x03])
            PythonRuntime.shared.interruptPythonMainThread()
        case 0x04: // Ctrl-D — EOF if buffer empty, else forward-delete
            if buf.isEmpty {
                pipeWrite([0x04])
            } else {
                deleteForward(terminalView: tv)
            }
        case 0x01: // Ctrl-A — home
            moveHome(terminalView: tv)
        case 0x05: // Ctrl-E — end
            moveEnd(terminalView: tv)
        case 0x15: // Ctrl-U — clear line
            clearLine(terminalView: tv)
        case 0x0B: // Ctrl-K — clear to end
            clearToEnd(terminalView: tv)
        case 0x17: // Ctrl-W — kill word
            killWord(terminalView: tv)
        case 0x0C: // Ctrl-L — clear screen
            echo([0x1B, 0x5B, 0x32, 0x4A, 0x1B, 0x5B, 0x48], tv) // ESC[2J ESC[H
        case 0x09: // Tab — complete command or filename
            if _paletteVisible && _paletteSelected < _paletteFiltered.count {
                // Tab in palette = fill in highlighted command, wait
                // for user to either type args or press Enter.
                fillPaletteSelection(terminalView: tv)
                return
            }
            handleTab(terminalView: tv)
        default:
            if b >= 0x20 || b >= 0x80 {
                // Printable ASCII or UTF-8 continuation / lead byte
                insert([b], terminalView: tv)
            }
            // other control bytes: ignore
        }
    }

    // MARK: - CSI / SS3 dispatch (arrow keys, home, end, delete)

    private func handleCSI(final: UInt8, params: [UInt8], terminalView tv: TerminalView) {
        let p = String(bytes: params, encoding: .ascii) ?? ""
        // When the palette is open, arrow up/down navigates the
        // command list instead of command history.
        if _paletteVisible && (final == 0x41 || final == 0x42) {
            let step = (final == 0x41) ? -1 : 1
            let n = _paletteFiltered.count
            if n > 0 {
                _paletteSelected = (_paletteSelected + step + n) % n
                renderPalette(terminalView: tv)
            }
            return
        }
        switch final {
        case 0x41: historyPrev(terminalView: tv)    // A — up
        case 0x42: historyNext(terminalView: tv)    // B — down
        case 0x43: moveRight(terminalView: tv)      // C — right
        case 0x44: moveLeft(terminalView: tv)       // D — left
        case 0x48: moveHome(terminalView: tv)       // H — home
        case 0x46: moveEnd(terminalView: tv)        // F — end
        case 0x7E: // ~ — parameterized
            switch p {
            case "1", "7": moveHome(terminalView: tv)
            case "4", "8": moveEnd(terminalView: tv)
            case "3":      deleteForward(terminalView: tv)
            default: break
            }
        default: break
        }
    }

    private func handleSS3(_ b: UInt8, terminalView tv: TerminalView) {
        switch b {
        case 0x41: historyPrev(terminalView: tv)
        case 0x42: historyNext(terminalView: tv)
        case 0x43: moveRight(terminalView: tv)
        case 0x44: moveLeft(terminalView: tv)
        case 0x48: moveHome(terminalView: tv)
        case 0x46: moveEnd(terminalView: tv)
        default: break
        }
    }

    // MARK: - Editing primitives

    private func insert(_ data: [UInt8], terminalView tv: TerminalView) {
        buf.insert(contentsOf: data, at: cursor)
        cursor += data.count
        // Redraw: print inserted bytes + the tail, then move cursor
        // back to its logical position.
        let tail = Array(buf[cursor...])
        echo(data + tail, tv)
        if !tail.isEmpty {
            echo("\u{1B}[\(tail.count)D", tv)
        }

        // AI-mode palette: show/update when the buffer starts with `/`,
        // hide otherwise. Real-time filtering as user types.
        if _isAIMode {
            if buf.first == 0x2F /* '/' */ {
                _paletteSelected = 0  // reset selection on edit
                renderPalette(terminalView: tv)
            } else if _paletteVisible {
                clearPaletteRows(terminalView: tv)
                hidePalette()
            }
        }
    }

    private func backspace(terminalView tv: TerminalView) {
        guard cursor > 0 else { return }
        // Step back one UTF-8 code point.
        var i = cursor - 1
        while i > 0 && (buf[i] & 0xC0) == 0x80 { i -= 1 }
        let removed = cursor - i
        buf.removeSubrange(i..<cursor)
        cursor = i
        // Move back `removed` columns, reprint tail, clear EOL, move back.
        echo(String(repeating: "\u{08}", count: removed), tv)
        redrawTail(terminalView: tv)
        // Keep the palette in sync with the edited buffer.
        if _isAIMode {
            if buf.first == 0x2F /* '/' */ {
                _paletteSelected = 0
                renderPalette(terminalView: tv)
            } else if _paletteVisible {
                clearPaletteRows(terminalView: tv)
                hidePalette()
            }
        }
    }

    private func deleteForward(terminalView tv: TerminalView) {
        guard cursor < buf.count else { return }
        var j = cursor + 1
        while j < buf.count && (buf[j] & 0xC0) == 0x80 { j += 1 }
        buf.removeSubrange(cursor..<j)
        redrawTail(terminalView: tv)
    }

    private func moveLeft(terminalView tv: TerminalView) {
        guard cursor > 0 else { return }
        var i = cursor - 1
        while i > 0 && (buf[i] & 0xC0) == 0x80 { i -= 1 }
        let moved = cursor - i
        cursor = i
        echo("\u{1B}[\(moved)D", tv)
    }

    private func moveRight(terminalView tv: TerminalView) {
        guard cursor < buf.count else { return }
        var j = cursor + 1
        while j < buf.count && (buf[j] & 0xC0) == 0x80 { j += 1 }
        let moved = j - cursor
        cursor = j
        echo("\u{1B}[\(moved)C", tv)
    }

    private func moveHome(terminalView tv: TerminalView) {
        if cursor > 0 {
            echo("\u{1B}[\(cursor)D", tv)
            cursor = 0
        }
    }

    private func moveEnd(terminalView tv: TerminalView) {
        if cursor < buf.count {
            let delta = buf.count - cursor
            echo("\u{1B}[\(delta)C", tv)
            cursor = buf.count
        }
    }

    private func clearLine(terminalView tv: TerminalView) {
        if cursor > 0 { echo("\u{1B}[\(cursor)D", tv) }
        echo("\u{1B}[K", tv)
        buf.removeAll(keepingCapacity: true)
        cursor = 0
        if _isAIMode && _paletteVisible {
            clearPaletteRows(terminalView: tv)
            hidePalette()
        }
    }

    private func clearToEnd(terminalView tv: TerminalView) {
        if cursor < buf.count {
            buf.removeSubrange(cursor..<buf.count)
            echo("\u{1B}[K", tv)
        }
    }

    private func killWord(terminalView tv: TerminalView) {
        guard cursor > 0 else { return }
        var i = cursor
        while i > 0 && buf[i - 1] == 0x20 { i -= 1 }
        while i > 0 && buf[i - 1] != 0x20 { i -= 1 }
        let removed = cursor - i
        buf.removeSubrange(i..<cursor)
        cursor = i
        echo("\u{1B}[\(removed)D", tv)
        redrawTail(terminalView: tv)
    }

    private func redrawTail(terminalView tv: TerminalView) {
        let tail = Array(buf[cursor...])
        echo(tail, tv)
        echo([0x1B, 0x5B, 0x4B], tv) // ESC [ K — clear to EOL
        if !tail.isEmpty {
            echo("\u{1B}[\(tail.count)D", tv)
        }
    }

    // MARK: - History

    private func historyPrev(terminalView tv: TerminalView) {
        guard !history.isEmpty, histIdx > 0 else { return }
        if histIdx == history.count {
            savedPartial = buf
        }
        histIdx -= 1
        replaceLine(with: Array(history[histIdx].utf8), terminalView: tv)
    }

    private func historyNext(terminalView tv: TerminalView) {
        guard histIdx < history.count else { return }
        histIdx += 1
        if histIdx == history.count {
            replaceLine(with: savedPartial, terminalView: tv)
        } else {
            replaceLine(with: Array(history[histIdx].utf8), terminalView: tv)
        }
    }

    private func replaceLine(with new: [UInt8], terminalView tv: TerminalView) {
        if cursor > 0 { echo("\u{1B}[\(cursor)D", tv) }
        echo("\u{1B}[K", tv)
        buf = new
        cursor = new.count
        echo(new, tv)
    }

    // MARK: - Tab completion

    /// Builtins defined by offlinai_shell.py — used for first-word
    /// completion. Keep this list in sync with BUILTINS in that file.
    private static let builtins: [String] = [
        // Shell essentials
        "cat", "cd", "clear", "cp", "date", "echo", "env", "exit",
        "export", "find", "grep", "head", "help", "history", "ll", "la",
        "ls", "man", "mkdir", "mv", "pwd", "quit", "rm", "rmdir",
        "tail", "touch", "tree", "uptime", "wc", "which",
        // Disk-usage family
        "du", "df", "ncdu", "stat",
        // System monitoring
        "top", "htop",
        // Source control (iOS-compat subset)
        "git",
        // Language runners
        "python", "python3",
        "cc", "gcc", "clang",
        "c++", "g++", "clang++",
        "gfortran", "f77", "f90", "f95",
        // LaTeX compilers
        "pdflatex", "latex", "tex", "pdftex", "xelatex",
        "latex-diagnose",
        // Package manager
        "pip", "pip3",
        "pip-install", "pip-uninstall", "pip-list",
        "pip-show", "pip-freeze", "pip-check",
    ]

    private func handleTab(terminalView tv: TerminalView) {
        // Find the word before cursor.
        let prefixBytes = Array(buf[0..<cursor])
        guard let prefixStr = String(bytes: prefixBytes, encoding: .utf8) else { return }

        // Word boundary: last whitespace before cursor.
        let wordStart = prefixStr.lastIndex(where: { $0 == " " || $0 == "\t" })
            .map { prefixStr.index(after: $0) } ?? prefixStr.startIndex
        let partial = String(prefixStr[wordStart...])

        // Is this the first word on the line? → command completion.
        // Otherwise → filesystem path completion.
        let isFirstWord = !prefixStr.contains(where: { $0 == " " || $0 == "\t" })
        // For file-extension-aware commands (pdflatex foo.tex, python
        // bar.py etc.) filter the path completions to the extensions
        // that command actually consumes — noise-reducing and matches
        // bash-completion behavior.
        let firstToken = prefixStr
            .split(whereSeparator: { $0 == " " || $0 == "\t" })
            .first.map(String.init) ?? ""
        let extFilter: Set<String>? = Self.extensionsForCommand(firstToken)
        // In AI mode, a `/`-prefixed first word completes against the
        // slash-command vocabulary. Non-slash input in AI mode is a
        // user prompt to the model — no completion (path completion
        // would insert random filenames into the prompt).
        let candidates: [String]
        if _isAIMode && isFirstWord {
            // AI-mode first-word Tab is owned by the palette system,
            // not the shell builtin completer — the palette is already
            // visible (or will be when the user types `/`). Fall
            // through to the palette-aware Tab handler at the call
            // site instead of emitting bash-style line-dumps here.
            return
        } else if _isAIMode && !isFirstWord {
            // Argument position in AI mode — the only command that
            // benefits from path completion is `/load <file>`.
            candidates = firstToken == "/load"
                ? completePath(partial: partial, extensions: ["gguf"])
                : []
        } else {
            candidates = isFirstWord
                ? completeCommand(partial: partial)
                : completePath(partial: partial, extensions: extFilter)
        }

        guard !candidates.isEmpty else { return }

        if candidates.count == 1 {
            // Unambiguous — complete the whole match, then add a
            // trailing space (for commands) or '/' (for dirs).
            let full = candidates[0]
            finishCompletion(partial: partial, full: full,
                             appendSpace: isFirstWord && !full.hasSuffix("/"),
                             terminalView: tv)
        } else {
            // Find longest common prefix — if it extends `partial`,
            // insert up to it. (Avoids noisy multi-match display; zsh
            // and bash both do this on single tab.)
            let common = longestCommonPrefix(candidates)
            if common.count > partial.count {
                finishCompletion(partial: partial, full: common,
                                 appendSpace: false, terminalView: tv)
            }
            // Otherwise already at branching point — do nothing;
            // user can press Ctrl-L to clear or keep typing.
        }
    }

    private func completeCommand(partial: String) -> [String] {
        LineBuffer.builtins.filter { $0.hasPrefix(partial) }.sorted()
    }

    /// Extensions that `command` consumes as its primary argument.
    /// Used by tab-completion to filter irrelevant files — e.g.
    /// `pdflatex <TAB>` should show `.tex` / `.ltx` files, not every
    /// `.py` and `.md` in the directory. nil → no filter (show all).
    private static func extensionsForCommand(_ command: String) -> Set<String>? {
        switch command {
        case "pdflatex", "latex", "tex", "pdftex", "xelatex", "lualatex":
            return ["tex", "ltx"]
        case "python", "python3":
            return ["py"]
        case "bibtex", "biber":
            return ["aux", "bib", "bcf"]
        case "dvipdf", "dvipdfm", "dvipdfmx":
            return ["dvi"]
        case "pdftotext", "pdfinfo":
            return ["pdf"]
        case "git":
            return nil  // git has its own subcommand dispatch
        default:
            return nil
        }
    }

    private func completePath(partial: String,
                              extensions: Set<String>? = nil) -> [String] {
        let fm = FileManager.default

        // Split partial into directory portion + filename prefix.
        var dirPath: String
        var namePrefix: String
        // Expand leading ~ to HOME.
        var expanded = partial
        if expanded == "~" || expanded.hasPrefix("~/") {
            let home = NSHomeDirectory()
            expanded = expanded == "~"
                ? home
                : home + expanded.dropFirst(1)
        }

        if let slashRange = expanded.range(of: "/", options: .backwards) {
            dirPath = String(expanded[..<slashRange.upperBound])
            namePrefix = String(expanded[slashRange.upperBound...])
        } else {
            dirPath = fm.currentDirectoryPath
            if !dirPath.hasSuffix("/") { dirPath += "/" }
            namePrefix = expanded
        }

        let listDir = dirPath.hasSuffix("/") ? String(dirPath.dropLast()) : dirPath
        guard let entries = try? fm.contentsOfDirectory(atPath: listDir) else {
            return []
        }

        // Skip dotfiles unless user typed a dot themselves.
        let includeHidden = namePrefix.hasPrefix(".")
        var filtered = entries
            .filter { $0.hasPrefix(namePrefix) }
            .filter { includeHidden || !$0.hasPrefix(".") }
            .sorted()
        // If caller restricts to certain extensions (e.g. `pdflatex
        // <TAB>` → .tex only), keep only matching files AND dirs
        // (dirs still useful for navigation).
        if let exts = extensions {
            filtered = filtered.filter { name in
                let fullPath = listDir + "/" + name
                var isDir: ObjCBool = false
                let exists = fm.fileExists(atPath: fullPath,
                                           isDirectory: &isDir)
                if exists && isDir.boolValue { return true }
                return exts.contains(
                    (name as NSString).pathExtension.lowercased())
            }
        }

        // Rebuild full path with trailing / for directories. Preserve
        // the user's original dir-portion (with ~ etc.) so we don't
        // swap in the absolute path on them.
        let dirPrefix: String
        if let slashRange = partial.range(of: "/", options: .backwards) {
            dirPrefix = String(partial[..<slashRange.upperBound])
        } else {
            dirPrefix = ""
        }

        return filtered.map { name in
            var full = dirPrefix + name
            var isDir: ObjCBool = false
            let checkPath = listDir + "/" + name
            if fm.fileExists(atPath: checkPath, isDirectory: &isDir), isDir.boolValue {
                full += "/"
            }
            return full
        }
    }

    private func longestCommonPrefix(_ strs: [String]) -> String {
        guard let first = strs.first else { return "" }
        var prefix = first
        for s in strs.dropFirst() {
            while !s.hasPrefix(prefix) {
                prefix = String(prefix.dropLast())
                if prefix.isEmpty { return "" }
            }
        }
        return prefix
    }

    private func finishCompletion(partial: String, full: String,
                                  appendSpace: Bool,
                                  terminalView tv: TerminalView) {
        guard full.count >= partial.count else { return }
        let rest = String(full.dropFirst(partial.count))
        var insertion = Array(rest.utf8)
        if appendSpace {
            insertion.append(0x20) // space
        }
        if !insertion.isEmpty {
            insert(insertion, terminalView: tv)
        }
    }

    // MARK: - Commit

    private func commitLine(terminalView tv: TerminalView,
                            pipeWrite: @escaping ([UInt8]) -> Void) {
        // Visual newline
        echo([0x0D, 0x0A], tv)
        // Send to Python (include trailing \n so repl() sees a line).
        var out = buf
        out.append(0x0A)
        pipeWrite(out)
        // Add to history if non-empty and different from last.
        if let s = String(bytes: buf, encoding: .utf8), !s.trimmingCharacters(in: .whitespaces).isEmpty {
            if history.last != s {
                history.append(s)
                if history.count > 500 { history.removeFirst() }
            }
        }
        buf.removeAll(keepingCapacity: true)
        cursor = 0
        histIdx = history.count
        savedPartial.removeAll()
    }
}
