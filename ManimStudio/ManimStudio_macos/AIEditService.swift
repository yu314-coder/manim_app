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
    /// Model name as reported by the CLI's stream-json `system/init`
    /// event — e.g. "claude-opus-4-7[1m]". Lets the UI show the
    /// real, current model resolved from your local Claude install
    /// instead of a hardcoded version string.
    @Published private(set) var resolvedModel: String = ""
    /// Claude CLI version string discovered at probe time.
    @Published private(set) var cliVersion: String = ""

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

    /// Probe `claude --version` to populate `cliVersion`. Cheap and
    /// safe to call on view appear.
    func probeCLI() {
        Task.detached(priority: .utility) { [weak self] in
            let v = Self.runVersion() ?? ""
            await MainActor.run { self?.cliVersion = v }
        }
    }

    private nonisolated static func runVersion() -> String? {
        guard let cli = locateClaudeCLI() else { return nil }
        let proc = Process()
        proc.executableURL = cli
        proc.arguments = ["--version"]
        let out = Pipe()
        proc.standardOutput = out
        proc.standardError = Pipe()
        do { try proc.run() } catch { return nil }
        proc.waitUntilExit()
        return String(data: out.fileHandleForReading.readDataToEndOfFile(),
                      encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
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

        // 2. Compose the instruction from the bundled prompt files
        // (same templates the Windows desktop app uses, dropped into
        // Resources/prompts/). Falls back to a minimal inline string
        // if the bundle resource is missing — keeps the feature
        // working even on dev builds before the resources land.
        let instruction = Self.composeInstruction(prompt: prompt)

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
            // Init / config messages. Surface the model name once
            // — and store it so the UI can show the live, resolved
            // model name instead of guessing from the alias the user
            // picked. This is the dynamic-discovery path: the CLI
            // tells us exactly which model handled the turn.
            if let model = obj["model"] as? String {
                DispatchQueue.main.async {
                    svc.resolvedModel = model
                    svc.output += "[claude · \(model)]\n"
                }
            }
        default:
            break
        }
    }

    /// Loads `claude_non_agent.md` from the app bundle's Resources/
    /// prompts/ folder, extracts the `## Without Selection` section,
    /// and substitutes `{{PROMPT}}`. Mirrors the Windows app's
    /// _build_ai_instruction() / _load_prompt_section() pair.
    private static func composeInstruction(prompt: String) -> String {
        // The "Without Selection" section is the one we want for
        // full-file edits (no selection range support yet on macOS).
        if let template = loadPromptSection(file: "claude_non_agent",
                                            section: "Without Selection") {
            return template.replacingOccurrences(of: "{{PROMPT}}", with: prompt)
                + "\n\n" + workspaceRules()
        }
        // Fallback if Resources/prompts/ isn't in the bundle yet.
        return """
        Read `scene.py` first, then edit it.
        This is a Manim file.

        Instruction: \(prompt)

        Apply changes and write back to scene.py.

        \(workspaceRules())
        """
    }

    /// Loads `workspace_claude.md` and returns its full content (no
    /// section split). Appended to every instruction so claude knows
    /// the rules of the sandbox: no pip / python / manim execution,
    /// only edit scene.py, etc. Same file the Windows app uses.
    private static func workspaceRules() -> String {
        if let url = Bundle.main.url(forResource: "workspace_claude",
                                     withExtension: "md",
                                     subdirectory: "prompts"),
           let body = try? String(contentsOf: url, encoding: .utf8) {
            return body
        }
        return ""
    }

    /// Pulls a `## Header` section out of one of the prompt
    /// templates. Returns nil if the file or section is missing.
    private static func loadPromptSection(file: String,
                                          section: String) -> String? {
        guard let url = Bundle.main.url(forResource: file,
                                        withExtension: "md",
                                        subdirectory: "prompts"),
              let body = try? String(contentsOf: url, encoding: .utf8)
        else { return nil }
        // Walk markdown headers and return the body of the matching
        // ## section, stopping at the next ## header.
        var capturing = false
        var lines: [String] = []
        for raw in body.components(separatedBy: .newlines) {
            if raw.hasPrefix("## ") {
                if capturing { break }
                let title = raw
                    .dropFirst(3)
                    .trimmingCharacters(in: .whitespaces)
                if title.caseInsensitiveCompare(section) == .orderedSame {
                    capturing = true
                    continue
                }
            } else if capturing {
                lines.append(raw)
            }
        }
        let result = lines.joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return result.isEmpty ? nil : result
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
