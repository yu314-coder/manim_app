// AIEditService.swift — drives Claude Code or OpenAI Codex CLIs to
// perform AI edits on the user's scene buffer. Mirrors the Windows
// desktop app's ai_edit.py provider split (claude / codex) plus an
// agent vs. non-agent mode toggle drawn from the bundled
// Resources/prompts/ markdown templates.
//
// Why two providers: Claude Code's stream-json + session-resume flow
// is excellent for surgical edits; Codex's --full-auto + JSONL flow
// is better at multi-file changes and following long agentic plans.
// The user picks per-task.
//
// Why agent vs. edit mode:
//   • Edit (claude_non_agent.md): one-shot scene.py mutation. Fast.
//   • Agent (claude_agent.md): multi-step plan-and-execute. Used for
//     "Generate from description", "Fix render errors", "Improve
//     visual quality based on screenshots".
//
// Resolved model names: each turn's stream contains the actual
// model the CLI picked (e.g. claude-opus-4-6, gpt-5-codex). We
// cache it per alias in UserDefaults so the dropdown can show
// "Opus → claude-opus-4-6" instead of just "Opus (latest)".
import Foundation
import Combine

final class AIEditService: ObservableObject {

    // ── provider + mode

    enum Provider: String, CaseIterable, Identifiable, Equatable {
        case claude, codex
        var id: String { rawValue }
        var label: String {
            switch self {
            case .claude: return "Claude"
            case .codex:  return "Codex"
            }
        }
    }

    enum Mode: String, CaseIterable, Identifiable, Equatable {
        /// One-shot edit → claude_non_agent.md / codex_non_agent.md.
        case edit
        /// Multi-step plan-and-execute → claude_agent.md /
        /// codex_agent.md, plus claude --permission-mode acceptEdits
        /// / codex --full-auto so tool calls don't pause for prompts.
        case agent
        var id: String { rawValue }
        var label: String {
            switch self {
            case .edit:  return "Edit"
            case .agent: return "Agent"
            }
        }
    }

    enum Phase: Equatable {
        case idle
        case running
        case done(applied: Bool)
        case failed(String)
    }

    /// One assistant turn. Streamed text, tool calls, and metadata
    /// land here so the chat UI can render a rich message instead of
    /// a monospace text blob.
    struct Turn: Identifiable, Equatable {
        let id: UUID
        let prompt: String
        var text: String
        /// Streamed reasoning / thinking text from the model. Claude
        /// emits this as content type=thinking; codex as item
        /// type=reasoning. Rendered as a collapsible thought block
        /// distinct from the regular reply.
        var thinking: String
        var toolCalls: [ToolCall]
        /// Code blocks captured live from Edit/Write tool_use
        /// payloads, so the UI can show the file content as it's
        /// being written. Each entry is one tool call.
        var codeBlocks: [CodeBlock]
        var model: String
        var inputTokens: Int
        var outputTokens: Int
        var costUSD: Double
        var startedAt: Date
        var finishedAt: Date?
        var errorMessage: String?
    }

    struct ToolCall: Identifiable, Equatable {
        let id: UUID
        let name: String      // "Edit", "Read", "Bash", "Glob", "patch_apply"…
        let detail: String    // human-readable summary
    }

    struct CodeBlock: Identifiable, Equatable {
        let id: UUID
        let toolName: String   // "Edit" | "Write" | "patch_apply"
        let path: String       // file the agent is writing
        var content: String    // streaming buffer
    }

    @Published var provider: Provider = .claude
    @Published var mode: Mode = .edit
    @Published private(set) var phase: Phase = .idle
    /// One entry per send() — the chat history rendered as message
    /// bubbles in the UI. The most recent turn streams in place.
    @Published private(set) var turns: [Turn] = []
    @Published private(set) var editedCode: String? = nil
    /// Set in agent mode when the run finishes with a modified
    /// scene.py — bypasses the Accept/Reject UI so the chat panel
    /// can auto-apply the edit and trigger a preview render. Read
    /// once and cleared via consumePendingAutoApply().
    @Published private(set) var pendingAutoApply: PendingApply? = nil

    /// Bundle of "what to apply" + "what to render" for agent mode's
    /// hands-off pipeline. The view layer consumes this and pushes
    /// the edit into AppState + posts the render notification.
    struct PendingApply: Equatable {
        let code: String
        /// Scene name the agent suggested to render, or nil to fall
        /// back to AppState.detectedScenes.first.
        let suggestedScene: String?
    }
    @Published private(set) var sessionId: String = UUID().uuidString
    @Published private(set) var elapsed: TimeInterval = 0
    /// The exact model name the CLI used on the last turn —
    /// "claude-opus-4-6[1m]" / "gpt-5-codex" / etc. Drawn from each
    /// provider's own initial event in the stream.
    @Published private(set) var resolvedModel: String = ""
    /// CLI version strings, populated by probeCLI().
    @Published private(set) var claudeCLIVersion: String = ""
    @Published private(set) var codexCLIVersion: String = ""
    /// Cached `alias → resolvedModel` mappings so the dropdown can
    /// show real names without an extra probe round.
    @Published private(set) var cachedResolved: [String: String] = [:]

    private var firstMessage = true
    private var process: Process?
    private var startedAt: Date = .distantPast
    private var elapsedTimer: Timer?
    private var originalCode: String = ""
    private var lastAlias: String = ""

    private let cacheKey = "ai_edit_resolved_models"

    init() {
        // Restore cached alias→model mappings from disk.
        if let dict = UserDefaults.standard
            .dictionary(forKey: cacheKey) as? [String: String] {
            self.cachedResolved = dict
        }
    }

    // MARK: - probes

    static func locateCLI(_ name: String) -> URL? {
        for dir in ["/opt/homebrew/bin", "/usr/local/bin",
                    "\(NSHomeDirectory())/.bun/bin",
                    "\(NSHomeDirectory())/.npm-global/bin"] {
            let url = URL(fileURLWithPath: dir).appendingPathComponent(name)
            if FileManager.default.isExecutableFile(atPath: url.path) {
                return url
            }
        }
        return nil
    }

    func probeCLI() {
        Task.detached(priority: .utility) { [weak self] in
            let claudeV = Self.runVersion(cli: "claude") ?? ""
            let codexV  = Self.runVersion(cli: "codex")  ?? ""
            await MainActor.run {
                self?.claudeCLIVersion = claudeV
                self?.codexCLIVersion  = codexV
            }
        }
    }

    private nonisolated static func runVersion(cli: String) -> String? {
        guard let url = locateCLI(cli) else { return nil }
        let proc = Process()
        proc.executableURL = url
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

    // MARK: - control

    func newSession() {
        guard phase != .running else { return }
        sessionId = UUID().uuidString
        firstMessage = true
        turns = []
        editedCode = nil
        phase = .idle
    }

    func stop() {
        process?.terminate()
        process = nil
        elapsedTimer?.invalidate()
        if case .running = phase { phase = .failed("Stopped by user") }
    }

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

    /// Called by the view after it has applied the auto-apply bundle
    /// and posted the render notification. Resets the flag so a
    /// stale value can't re-fire.
    func consumePendingAutoApply() {
        pendingAutoApply = nil
    }

    // MARK: - send

    /// Kick off a run. Routes to the active provider's CLI and uses
    /// the active mode's prompt template. Streams events into
    /// `output`; on exit sets `editedCode` if scene.py was modified.
    func send(prompt: String, originalCode: String, modelAlias: String) {
        guard phase != .running else { return }

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
        self.lastAlias = modelAlias

        // Append a new turn to the chat history — the streamer
        // mutates this entry in place as events arrive.
        let newTurn = Turn(id: UUID(), prompt: prompt, text: "",
                           thinking: "",
                           toolCalls: [], codeBlocks: [], model: "",
                           inputTokens: 0, outputTokens: 0, costUSD: 0,
                           startedAt: Date(), finishedAt: nil,
                           errorMessage: nil)
        self.turns.append(newTurn)

        // 2. Compose the instruction from the bundled prompt files
        // for the active (provider, mode) pair.
        let instruction = Self.composeInstruction(prompt: prompt,
                                                  provider: provider,
                                                  mode: mode)

        // 3. Spawn the right CLI.
        switch provider {
        case .claude: spawnClaude(workspace: workspace,
                                  instruction: instruction,
                                  modelAlias: modelAlias)
        case .codex:  spawnCodex(workspace: workspace,
                                 instruction: instruction,
                                 modelAlias: modelAlias)
        }
    }

    // MARK: - claude path

    private func spawnClaude(workspace: URL, instruction: String,
                             modelAlias: String)
    {
        guard let cli = Self.locateCLI("claude") else {
            phase = .failed("`claude` CLI not found. Install Claude Code: " +
                            "https://claude.com/download")
            return
        }
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
        if !modelAlias.isEmpty {
            args.append(contentsOf: ["--model", modelAlias])
        }
        // Agent mode: skip permission prompts so multi-step plans
        // don't hang waiting for an "approve Bash?" answer.
        if mode == .agent {
            args.append(contentsOf: ["--permission-mode", "acceptEdits"])
        }

        spawn(executable: cli, args: args, workspace: workspace,
              extraEnv: ["CLAUDECODE": nil, "CLAUDE_CODE": nil],
              parser: { [weak self] line in
                  guard let self = self else { return }
                  Self.parseClaudeStreamJSON(line, into: self,
                                             alias: modelAlias)
              })
    }

    // MARK: - codex path

    private func spawnCodex(workspace: URL, instruction: String,
                            modelAlias: String)
    {
        guard let cli = Self.locateCLI("codex") else {
            phase = .failed("`codex` CLI not found. " +
                            "Install with: npm install -g @openai/codex")
            return
        }
        // --full-auto enables the workspace-write sandbox; without
        // it codex falls back to read-only and silently can't edit
        // scene.py. The Windows desktop app passes it
        // unconditionally for both edit and agent modes — we do the
        // same so edit mode for codex actually changes the file.
        var args: [String] = [
            "exec", "-",                  // read prompt from stdin
            "--full-auto",
            "--skip-git-repo-check",
            "--json",
        ]
        // Agent mode also enables web search via codex's config knob
        // so plans that need to look up library docs work.
        if mode == .agent {
            args.append(contentsOf: ["-c", "web_search=live"])
        }
        if !modelAlias.isEmpty {
            args.append(contentsOf: ["-m", modelAlias])
        }

        // codex reads the prompt from stdin since we passed `-`.
        spawn(executable: cli, args: args, workspace: workspace,
              stdin: instruction,
              extraEnv: [:],
              parser: { [weak self] line in
                  guard let self = self else { return }
                  Self.parseCodexJSONL(line, into: self,
                                       alias: modelAlias)
              })
    }

    // MARK: - generic spawn

    private func spawn(executable: URL, args: [String],
                       workspace: URL, stdin: String? = nil,
                       extraEnv: [String: String?],
                       parser: @escaping (String) -> Void)
    {
        let proc = Process()
        proc.executableURL = executable
        proc.arguments = args
        proc.currentDirectoryURL = workspace

        var env = ProcessInfo.processInfo.environment
        for (k, v) in extraEnv {
            if let v = v { env[k] = v } else { env.removeValue(forKey: k) }
        }
        let extras = ["/opt/homebrew/bin", "/usr/local/bin"]
        env["PATH"] = (extras + (env["PATH"] ?? "").split(separator: ":")
                                                   .map(String.init))
            .joined(separator: ":")
        proc.environment = env

        let outPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = outPipe

        if stdin != nil {
            proc.standardInput = Pipe()
        } else {
            proc.standardInput = FileHandle(forReadingAtPath: "/dev/null")
        }

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
        if let t = elapsedTimer { RunLoop.main.add(t, forMode: .common) }

        do { try proc.run() }
        catch {
            phase = .failed("Failed to launch: \(error.localizedDescription)")
            return
        }
        self.process = proc
        self.phase = .running
        self.resolvedModel = ""

        // Push stdin if provided (codex prompt).
        if let stdinStr = stdin,
           let inHandle = (proc.standardInput as? Pipe)?.fileHandleForWriting {
            DispatchQueue.global(qos: .utility).async {
                inHandle.write(stdinStr.data(using: .utf8) ?? Data())
                try? inHandle.close()
            }
        }

        DispatchQueue.global(qos: .userInitiated).async {
            Self.streamLines(from: outPipe.fileHandleForReading, parser: parser)
        }

        let scenePath = workspace.appendingPathComponent("scene.py")
        DispatchQueue.global(qos: .utility).async { [weak self] in
            proc.waitUntilExit()
            DispatchQueue.main.async {
                self?.finalize(scenePath: scenePath,
                               exitCode: proc.terminationStatus)
            }
        }
    }

    // MARK: - line streaming

    private static func streamLines(from fh: FileHandle,
                                    parser: (String) -> Void)
    {
        var buffer = Data()
        while true {
            let chunk = fh.availableData
            if chunk.isEmpty { break }
            buffer.append(chunk)
            while let nl = buffer.firstIndex(of: 0x0A) {
                let lineData = buffer.subdata(in: 0..<nl)
                buffer.removeSubrange(0...nl)
                guard let line = String(data: lineData, encoding: .utf8)?
                    .trimmingCharacters(in: .whitespaces),
                    !line.isEmpty else { continue }
                parser(line)
            }
        }
        if !buffer.isEmpty,
           let line = String(data: buffer, encoding: .utf8)?
            .trimmingCharacters(in: .whitespaces),
            !line.isEmpty {
            parser(line)
        }
    }

    // MARK: - claude parser (stream-json)

    private static func parseClaudeStreamJSON(_ jsonLine: String,
                                              into svc: AIEditService,
                                              alias: String)
    {
        guard let data = jsonLine.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data)
                  as? [String: Any]
        else { return }
        let type = (obj["type"] as? String) ?? ""
        switch type {
        case "assistant":
            if let msg = obj["message"] as? [String: Any],
               let content = msg["content"] as? [[String: Any]] {
                for part in content {
                    let kind = (part["type"] as? String) ?? ""
                    if kind == "text", let t = part["text"] as? String {
                        DispatchQueue.main.async {
                            svc.appendText(t)
                        }
                    } else if kind == "thinking" || kind == "redacted_thinking" {
                        // Extended-thinking blocks. Body is in
                        // "thinking" (or "data" for redacted variants
                        // — we render redacted as italic placeholder).
                        let body = (part["thinking"] as? String)
                            ?? (kind == "redacted_thinking"
                                ? "[redacted reasoning]" : "")
                        if !body.isEmpty {
                            DispatchQueue.main.async {
                                svc.appendThinking(body + "\n")
                            }
                        }
                    } else if kind == "tool_use" {
                        let name = (part["name"] as? String) ?? "tool"
                        let input = part["input"] as? [String: Any] ?? [:]
                        let summary = describeToolUse(name: name, input: input)
                        DispatchQueue.main.async {
                            svc.appendToolCall(name: name, detail: summary)
                        }
                        // For Edit / Write — capture the actual file
                        // body so the UI can show what's being
                        // generated, not just the file name.
                        if name == "Write" {
                            let path = (input["file_path"] as? String) ?? ""
                            let content = (input["content"] as? String) ?? ""
                            if !content.isEmpty {
                                DispatchQueue.main.async {
                                    svc.appendCodeBlock(toolName: name,
                                                         path: path,
                                                         content: content)
                                }
                            }
                        } else if name == "Edit" || name == "MultiEdit" {
                            let path = (input["file_path"] as? String) ?? ""
                            let new = (input["new_string"] as? String) ?? ""
                            if !new.isEmpty {
                                DispatchQueue.main.async {
                                    svc.appendCodeBlock(toolName: name,
                                                         path: path,
                                                         content: new)
                                }
                            }
                        }
                    }
                }
            }
        case "result":
            let usage = obj["usage"] as? [String: Any]
            let inT  = (usage?["input_tokens"]  as? Int) ?? 0
            let outT = (usage?["output_tokens"] as? Int) ?? 0
            let cost = (obj["total_cost_usd"]   as? Double) ?? 0
            DispatchQueue.main.async {
                svc.updateUsage(inT: inT, outT: outT, cost: cost)
            }
        case "system":
            if let model = obj["model"] as? String {
                DispatchQueue.main.async {
                    svc.resolvedModel = model
                    svc.updateTurnModel(model)
                    svc.cacheResolved(alias: alias.isEmpty ? "default" : alias,
                                      to: model)
                }
            }
        default:
            break
        }
    }

    /// Append text to the latest turn's running assistant message.
    private func appendText(_ s: String) {
        guard !turns.isEmpty else { return }
        turns[turns.count - 1].text += s
    }
    private func appendToolCall(name: String, detail: String) {
        guard !turns.isEmpty else { return }
        let call = ToolCall(id: UUID(), name: name, detail: detail)
        turns[turns.count - 1].toolCalls.append(call)
    }
    /// Append text to the latest turn's reasoning / thinking buffer.
    /// Claude emits {"type":"thinking", "thinking":"…"} blocks when
    /// extended thinking is on; codex emits item.type=reasoning.
    private func appendThinking(_ s: String) {
        guard !turns.isEmpty else { return }
        turns[turns.count - 1].thinking += s
    }
    /// Capture the file content claude/codex is writing as part of an
    /// Edit/Write tool call, so the UI can render it as a streaming
    /// code block. For Edit, `content` is the new_string; for Write,
    /// it's the full file body.
    private func appendCodeBlock(toolName: String, path: String,
                                 content: String) {
        guard !turns.isEmpty else { return }
        let block = CodeBlock(id: UUID(), toolName: toolName,
                              path: path, content: content)
        turns[turns.count - 1].codeBlocks.append(block)
    }
    private func updateTurnModel(_ model: String) {
        guard !turns.isEmpty else { return }
        if turns[turns.count - 1].model.isEmpty {
            turns[turns.count - 1].model = model
        }
    }
    private func updateUsage(inT: Int, outT: Int, cost: Double) {
        guard !turns.isEmpty else { return }
        turns[turns.count - 1].inputTokens  = inT
        turns[turns.count - 1].outputTokens = outT
        turns[turns.count - 1].costUSD      = cost
    }

    // MARK: - codex parser (JSONL)

    private static func parseCodexJSONL(_ jsonLine: String,
                                        into svc: AIEditService,
                                        alias: String)
    {
        guard let data = jsonLine.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data)
                  as? [String: Any]
        else { return }
        let type = (obj["type"] as? String) ?? ""

        switch type {
        case "thread.started":
            if let model = obj["model"] as? String {
                DispatchQueue.main.async {
                    svc.resolvedModel = model
                    svc.updateTurnModel(model)
                    svc.cacheResolved(alias: alias.isEmpty ? "default" : alias,
                                      to: model)
                }
            }
        case "item.completed":
            // Items: agent_message (text), tool_call, shell_call,
            // patch_apply.
            guard let item = obj["item"] as? [String: Any] else { break }
            let itemType = (item["type"] as? String) ?? ""
            switch itemType {
            case "agent_message":
                if let text = item["text"] as? String, !text.isEmpty {
                    DispatchQueue.main.async { svc.appendText(text + "\n") }
                }
            case "reasoning", "thinking":
                // Codex emits reasoning content as a separate item
                // type. Render as a thinking block, not regular text.
                let body = (item["text"] as? String)
                    ?? (item["content"] as? String)
                    ?? (item["summary"] as? String)
                    ?? ""
                if !body.isEmpty {
                    DispatchQueue.main.async {
                        svc.appendThinking(body + "\n")
                    }
                }
            case "tool_call", "shell_call":
                let name = (item["name"] as? String) ?? itemType
                let summary: String
                if let cmd = item["command"] as? String {
                    summary = String(cmd.prefix(80))
                } else if let path = item["path"] as? String {
                    summary = (path as NSString).lastPathComponent
                } else {
                    summary = ""
                }
                DispatchQueue.main.async {
                    svc.appendToolCall(name: name, detail: summary)
                }
            case "patch_apply":
                let path = (item["path"] as? String) ?? "(file)"
                // Codex sometimes ships the new file body as
                // "content" or "after"; capture either so the UI can
                // render the streaming code block.
                let body = (item["content"] as? String)
                    ?? (item["after"] as? String)
                    ?? (item["new_text"] as? String)
                    ?? ""
                DispatchQueue.main.async {
                    svc.appendToolCall(name: "Edit",
                        detail: (path as NSString).lastPathComponent)
                    if !body.isEmpty {
                        svc.appendCodeBlock(toolName: "Edit",
                                             path: path,
                                             content: body)
                    }
                }
            default:
                break
            }
        case "turn.completed":
            let usage = obj["usage"] as? [String: Any]
            let inT  = (usage?["input_tokens"]  as? Int) ?? 0
            let outT = (usage?["output_tokens"] as? Int) ?? 0
            DispatchQueue.main.async {
                svc.updateUsage(inT: inT, outT: outT, cost: 0)
            }
        case "error", "turn.failed":
            let msg = (obj["message"] as? String)
                ?? ((obj["error"] as? [String: Any])?["message"] as? String)
                ?? "codex error"
            DispatchQueue.main.async {
                if !svc.turns.isEmpty {
                    svc.turns[svc.turns.count - 1].errorMessage = msg
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

    // MARK: - prompt loading

    /// Loads the right prompt template for the (provider, mode) pair
    /// from Resources/prompts/. Falls back to a minimal inline string
    /// if the bundle resource is missing.
    private static func composeInstruction(prompt: String,
                                           provider: Provider,
                                           mode: Mode) -> String {
        let baseFile: String
        let section: String
        switch (provider, mode) {
        case (.claude, .edit):  baseFile = "claude_non_agent"; section = "Without Selection"
        case (.claude, .agent): baseFile = "claude_agent";     section = "Generate"
        case (.codex,  .edit):  baseFile = "codex_non_agent";  section = "Without Selection"
        case (.codex,  .agent): baseFile = "codex_agent";      section = "Generate"
        }

        var instruction: String
        if let tpl = loadPromptSection(file: baseFile, section: section) {
            instruction = tpl
                .replacingOccurrences(of: "{{PROMPT}}",      with: prompt)
                .replacingOccurrences(of: "{{DESCRIPTION}}", with: prompt)
        } else {
            instruction = (mode == .agent)
                ? "Read scene.py, then implement: \(prompt)\n\nWrite the result to scene.py."
                : "Read scene.py, then edit it.\n\nInstruction: \(prompt)\n\nApply changes to scene.py."
        }
        if let rules = loadRules(provider: provider) {
            instruction += "\n\n" + rules
        }
        return instruction
    }

    private static func loadRules(provider: Provider) -> String? {
        let file = (provider == .claude) ? "workspace_claude" : "workspace_codex"
        guard let url = Bundle.main.url(forResource: file,
                                        withExtension: "md",
                                        subdirectory: "prompts"),
              let body = try? String(contentsOf: url, encoding: .utf8)
        else { return nil }
        return body
    }

    private static func loadPromptSection(file: String,
                                          section: String) -> String? {
        guard let url = Bundle.main.url(forResource: file,
                                        withExtension: "md",
                                        subdirectory: "prompts"),
              let body = try? String(contentsOf: url, encoding: .utf8)
        else { return nil }
        var capturing = false
        var lines: [String] = []
        for raw in body.components(separatedBy: .newlines) {
            if raw.hasPrefix("## ") {
                if capturing { break }
                let title = raw.dropFirst(3)
                    .trimmingCharacters(in: .whitespaces)
                if title.caseInsensitiveCompare(section) == .orderedSame {
                    capturing = true; continue
                }
            } else if capturing {
                lines.append(raw)
            }
        }
        let r = lines.joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return r.isEmpty ? nil : r
    }

    // MARK: - cache

    /// Records that `alias` resolved to `model` on the most recent
    /// turn. Persisted to UserDefaults so the picker can show the
    /// real model name on next launch.
    private func cacheResolved(alias: String, to model: String) {
        var dict = cachedResolved
        dict[alias] = model
        cachedResolved = dict
        UserDefaults.standard.set(dict, forKey: cacheKey)
    }

    /// Lookup helper for the UI.
    func resolvedName(for alias: String) -> String? {
        cachedResolved[alias.isEmpty ? "default" : alias]
    }

    /// First `class XYZ(Scene)` (or any …Scene subclass) in a manim
    /// source file, used by agent mode to pick the scene to render.
    /// Mirrors AppState.detectedScenes' regex but doesn't need the
    /// AppState instance (called from finalize()).
    private nonisolated static func firstSceneName(in source: String) -> String? {
        let pattern = #"^\s*class\s+([A-Za-z_]\w*)\s*\([^)]*Scene[^)]*\)"#
        guard let re = try? NSRegularExpression(pattern: pattern,
                                                options: [.anchorsMatchLines])
        else { return nil }
        let ns = source as NSString
        let matches = re.matches(in: source,
                                  range: NSRange(location: 0, length: ns.length))
        guard let m = matches.first, m.numberOfRanges > 1 else { return nil }
        return ns.substring(with: m.range(at: 1))
    }

    // MARK: - finalize

    private func finalize(scenePath: URL, exitCode: Int32) {
        elapsedTimer?.invalidate()
        elapsedTimer = nil
        process = nil
        firstMessage = false

        // Seal the last turn.
        if !turns.isEmpty {
            turns[turns.count - 1].finishedAt = Date()
        }

        let edited: String?
        do {
            let content = try String(contentsOf: scenePath, encoding: .utf8)
            edited = (content != originalCode && !content.isEmpty)
                ? content : nil
        } catch {
            edited = nil
        }

        if let edited = edited {
            // Agent mode: hands-off pipeline. Skip the Accept/Reject
            // gate, push the edit into the buffer + auto-render. Edit
            // mode keeps the manual gate so the user can review.
            if mode == .agent {
                let scene = Self.firstSceneName(in: edited)
                self.pendingAutoApply = PendingApply(code: edited,
                                                     suggestedScene: scene)
                self.editedCode = nil
                self.phase = .done(applied: true)
            } else {
                self.editedCode = edited
                self.phase = .done(applied: false)
            }
        } else {
            self.editedCode = nil
            if exitCode == 0 {
                self.phase = .done(applied: false)
                if !turns.isEmpty,
                   turns[turns.count - 1].text.isEmpty,
                   turns[turns.count - 1].toolCalls.isEmpty {
                    turns[turns.count - 1].text =
                        "(finished — no changes detected)"
                }
            } else {
                if !turns.isEmpty {
                    turns[turns.count - 1].errorMessage =
                        "\(provider.label) exited \(exitCode)"
                }
                self.phase = .failed("\(provider.label) exited \(exitCode)")
            }
        }
    }
}
