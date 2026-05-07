// AIEditService.swift — drives the `claude` CLI in stream-json mode
// to perform AI edits on the user's scene buffer. Inspired by the
// Windows desktop app's ai_edit.py but rewritten for Swift / AppKit.
//
// Flow:
//   1. Write app.sourceCode to ~/Library/Application Support/
//      ManimStudio/ai-edit-workspace/scene.py
//   2. Spawn `claude -p <instruction> --output-format stream-json
//      --verbose --session-id <uuid> --allowedTools Read,Write,Edit,
//      Bash,Glob,Grep,WebSearch,WebFetch [--model <id>]` with that
//      workspace as CWD. claude can Read/Edit scene.py directly.
//   3. Read stdout line-by-line. Each line is a JSON event; we
//      extract user-facing text deltas and append to `output`.
//   4. On exit, read scene.py back. If changed, expose it via
//      `editedCode` so the UI can show Accept / Reject.
//   5. Subsequent prompts use --resume <uuid> instead of --session-id
//      so claude keeps the conversation context.
import Foundation
import Combine

final class AIEditService: ObservableObject {

    enum Phase: Equatable {
        case idle
        case running
        case done(applied: Bool)
        case failed(String)
    }

    @Published private(set) var phase: Phase = .idle
    /// Concatenated user-facing text from claude's stream — not raw
    /// JSON. Rendered in the output pane as it streams.
    @Published private(set) var output: String = ""
    /// Set when the post-run scene.py differs from the original.
    @Published private(set) var editedCode: String? = nil
    /// Session UUID — re-used across turns so `--resume` works.
    @Published private(set) var sessionId: String = UUID().uuidString
    /// Per-turn token + cost stats from the system message.
    @Published private(set) var lastCostUSD: Double = 0
    @Published private(set) var lastInputTokens: Int = 0
    @Published private(set) var lastOutputTokens: Int = 0
    /// Live elapsed seconds during a run; reset on each send.
    @Published private(set) var elapsed: TimeInterval = 0

    private var firstMessage = true
    private var process: Process?
    private var startedAt: Date = .distantPast
    private var elapsedTimer: Timer?
    private var originalCode: String = ""

    // MARK: - public API

    /// Picks a sensible default of the bundled `claude` CLI. Returns
    /// nil if not on PATH — UI shows an install hint in that case.
    static func locateClaudeCLI() -> URL? {
        for dir in ["/opt/homebrew/bin", "/usr/local/bin",
                    "/Users/\(NSUserName())/.bun/bin",
                    "/Users/\(NSUserName())/.npm-global/bin"] {
            let url = URL(fileURLWithPath: dir).appendingPathComponent("claude")
            if FileManager.default.isExecutableFile(atPath: url.path) {
                return url
            }
        }
        return nil
    }

    static var workspaceURL: URL {
        let dir = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("ManimStudio/ai-edit-workspace",
                                    isDirectory: true)
        try? FileManager.default.createDirectory(
            at: dir, withIntermediateDirectories: true)
        return dir
    }

    func newSession() {
        guard phase != .running else { return }
        sessionId = UUID().uuidString
        firstMessage = true
        output = ""
        editedCode = nil
        phase = .idle
    }

    func stop() {
        process?.terminate()
        process = nil
        elapsedTimer?.invalidate()
        if case .running = phase {
            phase = .failed("Stopped by user")
        }
    }

    /// Returns the suggested edit (clearing it so it doesn't get
    /// applied twice) and flips `phase` to `.done(applied: true)`.
    /// Returns nil if there's nothing to apply.
    @discardableResult
    func acceptEdit() -> String? {
        guard let edited = editedCode else { return nil }
        editedCode = nil
        if case .done = phase { phase = .done(applied: true) }
        return edited
    }

    func rejectEdit() {
        editedCode = nil
        if case .done = phase { phase = .done(applied: false) }
    }

    /// Kick off a run. Streams output into `output`; on exit sets
    /// `editedCode` if scene.py was modified.
    func send(prompt: String, originalCode: String, model: String?) {
        guard phase != .running else { return }
        guard let cli = Self.locateClaudeCLI() else {
            phase = .failed("`claude` CLI not found on PATH. " +
                            "Install Claude Code: https://claude.com/download")
            return
        }

        // 1. Stage scene.py.
        let workspace = Self.workspaceURL
        let scenePath = workspace.appendingPathComponent("scene.py")
        do {
            try originalCode.write(to: scenePath, atomically: true, encoding: .utf8)
        } catch {
            phase = .failed("Could not stage scene.py: \(error.localizedDescription)")
            return
        }
        self.originalCode = originalCode
        self.editedCode = nil

        // 2. Compose the instruction. Echo the file path so claude
        // knows what to edit; the prompt itself becomes the user's
        // request.
        let instruction = """
        You are editing a manim Python scene file located at scene.py
        in the current working directory. Read it, then perform the
        edit the user describes below. Use the Edit / Write tools
        to mutate scene.py directly. Do not output the full file
        contents back unless explicitly asked. When done, briefly
        summarize what you changed.

        USER REQUEST:
        \(prompt)
        """

        // 3. Build the argv.
        var args: [String] = [
            "-p", instruction,
            "--output-format", "stream-json",
            "--verbose",
            "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep,WebSearch,WebFetch",
        ]
        if firstMessage {
            args.append(contentsOf: ["--session-id", sessionId])
        } else {
            args.append(contentsOf: ["--resume", sessionId])
        }
        if let model = model, !model.isEmpty {
            args.append(contentsOf: ["--model", model])
        }

        // 4. Spawn.
        let proc = Process()
        proc.executableURL = cli
        proc.arguments = args
        proc.currentDirectoryURL = workspace

        var env = ProcessInfo.processInfo.environment
        // Avoid "nested session" error when launched from inside a
        // Claude Code agent (the user might be in a Claude Code
        // session right now).
        env.removeValue(forKey: "CLAUDECODE")
        env.removeValue(forKey: "CLAUDE_CODE")
        // Make sure the brew bin dirs are findable for any tools
        // claude wants to invoke (e.g. python).
        let extras = ["/opt/homebrew/bin", "/usr/local/bin"]
        env["PATH"] = (extras + (env["PATH"] ?? "").split(separator: ":")
                                                   .map(String.init))
            .joined(separator: ":")
        proc.environment = env

        let outPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = outPipe

        let startedAt = Date()
        self.startedAt = startedAt
        self.elapsed = 0
        self.elapsedTimer?.invalidate()
        self.elapsedTimer = Timer.scheduledTimer(
            withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.elapsed = Date().timeIntervalSince(startedAt)
            }
        }
        if let t = elapsedTimer {
            RunLoop.main.add(t, forMode: .common)
        }

        do {
            try proc.run()
        } catch {
            phase = .failed("Failed to launch claude: \(error.localizedDescription)")
            return
        }
        self.process = proc
        self.phase = .running
        self.output = ""

        // 5. Read stdout line-by-line on a background queue,
        // dispatching parsed events back to the main actor.
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.readStream(from: outPipe.fileHandleForReading,
                             scenePath: scenePath)
        }

        // 6. Wait for termination on a background queue, then
        // finalize state on main.
        DispatchQueue.global(qos: .utility).async { [weak self] in
            proc.waitUntilExit()
            DispatchQueue.main.async {
                self?.finalize(scenePath: scenePath,
                               exitCode: proc.terminationStatus)
            }
        }
    }

    // MARK: - private

    private func readStream(from fh: FileHandle, scenePath: URL) {
        var buffer = Data()
        while true {
            let chunk = fh.availableData
            if chunk.isEmpty { break }
            buffer.append(chunk)
            // Split on newlines; keep the trailing partial line.
            while let nl = buffer.firstIndex(of: 0x0A) {
                let lineData = buffer.subdata(in: 0..<nl)
                buffer.removeSubrange(0...nl)
                guard let line = String(data: lineData, encoding: .utf8) else { continue }
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.isEmpty { continue }
                Self.parseAndDispatch(trimmed, into: self)
            }
        }
        // Flush any final partial line.
        if !buffer.isEmpty,
           let line = String(data: buffer, encoding: .utf8) {
            Self.parseAndDispatch(line.trimmingCharacters(in: .whitespaces),
                                  into: self)
        }
    }

    /// Best-effort decode of a stream-json event. We extract user-
    /// facing text from a few well-known shapes:
    ///   • {"type":"assistant","message":{"content":[
    ///       {"type":"text","text":"…"} | {"type":"tool_use",…}]}}
    ///   • {"type":"result","result":"…"}
    ///   • {"type":"system","subtype":"init",…}
    /// Everything else is silently dropped (we don't echo raw JSON).
    private static func parseAndDispatch(_ jsonLine: String,
                                         into svc: AIEditService) {
        guard let data = jsonLine.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }

        let type = (obj["type"] as? String) ?? ""

        switch type {
        case "assistant":
            if let msg = obj["message"] as? [String: Any],
               let content = msg["content"] as? [[String: Any]] {
                for part in content {
                    let kind = (part["type"] as? String) ?? ""
                    switch kind {
                    case "text":
                        if let t = part["text"] as? String {
                            DispatchQueue.main.async { svc.output += t }
                        }
                    case "tool_use":
                        let name = (part["name"] as? String) ?? "tool"
                        let input = part["input"] as? [String: Any] ?? [:]
                        let summary = describeToolUse(name: name,
                                                       input: input)
                        DispatchQueue.main.async {
                            svc.output += "\n\u{2022} \(summary)\n"
                        }
                    default:
                        break
                    }
                }
            }
        case "result":
            if let r = obj["result"] as? String {
                // Result is the final assistant text. Append once with
                // a separator so the user knows the run finished.
                DispatchQueue.main.async {
                    if !r.isEmpty {
                        svc.output += "\n\n— done —\n\(r)\n"
                    }
                }
            }
            // Capture totals if present.
            let usage = obj["usage"] as? [String: Any]
            let inT  = (usage?["input_tokens"]  as? Int) ?? 0
            let outT = (usage?["output_tokens"] as? Int) ?? 0
            let cost = (obj["total_cost_usd"]   as? Double) ?? 0
            DispatchQueue.main.async {
                svc.lastInputTokens  = inT
                svc.lastOutputTokens = outT
                svc.lastCostUSD      = cost
            }
        case "system":
            // Init / config messages. Surface the model name once.
            if let model = obj["model"] as? String {
                DispatchQueue.main.async {
                    svc.output += "[claude · \(model)]\n"
                }
            }
        default:
            break
        }
    }

    private static func describeToolUse(name: String,
                                        input: [String: Any]) -> String
    {
        switch name {
        case "Edit", "Write":
            let path = (input["file_path"] as? String) ?? "(unknown)"
            return "\(name) → \((path as NSString).lastPathComponent)"
        case "Read":
            let path = (input["file_path"] as? String) ?? "(unknown)"
            return "Read → \((path as NSString).lastPathComponent)"
        case "Bash":
            let cmd = (input["command"] as? String) ?? ""
            return "Bash → \(cmd.prefix(80))"
        case "Glob", "Grep":
            let pattern = (input["pattern"] as? String) ?? ""
            return "\(name): \(pattern)"
        default:
            return name
        }
    }

    private func finalize(scenePath: URL, exitCode: Int32) {
        elapsedTimer?.invalidate()
        elapsedTimer = nil
        process = nil
        firstMessage = false  // future turns use --resume

        // Read scene.py — if it changed, surface the edit.
        let edited: String?
        do {
            let content = try String(contentsOf: scenePath, encoding: .utf8)
            edited = (content != originalCode && !content.isEmpty)
                ? content : nil
        } catch {
            edited = nil
        }

        if let edited = edited {
            self.editedCode = edited
            self.phase = .done(applied: false)
        } else {
            self.editedCode = nil
            if exitCode == 0 {
                self.phase = .done(applied: false)
                if output.isEmpty {
                    self.output = "(claude finished — no changes detected)"
                }
            } else {
                self.phase = .failed("claude exited \(exitCode)")
            }
        }
    }
}
