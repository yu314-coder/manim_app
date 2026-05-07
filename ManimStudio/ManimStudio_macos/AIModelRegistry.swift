// AIModelRegistry.swift — passive model discovery for the AI Edit
// picker. Replaces the hardcoded alias list with real model IDs
// scraped from each CLI's local cache / session history.
//
// Sources, all on the user's filesystem:
//   • Claude Code:  ~/.claude/projects/<project>/<session-uuid>.jsonl
//                   (every system/init event includes "model":"…",
//                    every assistant message includes the model
//                    too). We scan recent files for distinct model
//                    IDs and surface them.
//   • Codex CLI:    ~/.codex/models_cache.json (the CLI fetches the
//                   ChatGPT account's available model list and
//                   caches it; { "models": [{ "slug", "display_name",
//                   "description", … }, … ] }).
//
// Why passive: spawning `claude --model X --print "."` for each
// alias to discover the resolution costs LLM tokens and time.
// Files the CLIs already wrote are free.
//
// Ranking: most-recently-seen models first for claude (so a user
// who's been using Opus 4.7 sees it at the top of the list).
import Foundation
import Combine

final class AIModelRegistry: ObservableObject {
    static let shared = AIModelRegistry()
    private init() {
        refresh()
    }

    /// Discovered model IDs, sorted with most-recently-used first.
    @Published private(set) var claudeModels: [DiscoveredModel] = []
    @Published private(set) var codexModels: [DiscoveredModel] = []

    struct DiscoveredModel: Identifiable, Hashable {
        let id: String         // e.g. "claude-opus-4-7", "gpt-5.4"
        let display: String    // human-readable label
        let detail: String?    // brief description (codex only)
        /// Reasoning effort levels this model accepts. Empty if the
        /// CLI / cache didn't report any. Used by the effort picker
        /// to keep options in sync — codex catalogs these per-model
        /// (gpt-5.5 supports xhigh; gpt-5.4 doesn't, etc.).
        let supportedEfforts: [String]
    }

    /// Re-scan the local caches. Call on view appear so the picker
    /// reflects fresh state — sessions / model_cache may have
    /// updated since launch.
    func refresh() {
        Task.detached(priority: .utility) { [weak self] in
            let claude = Self.scanClaude()
            let codex  = Self.scanCodex()
            await MainActor.run {
                self?.claudeModels = claude
                self?.codexModels  = codex
            }
        }
    }

    // MARK: - claude

    /// Walks ~/.claude/projects/*/*.jsonl, extracting distinct
    /// model strings. The JSONL is line-delimited JSON; each
    /// line that contains `"model":"…"` adds the value to the set.
    /// Synthetic models (e.g. "<synthetic>") are filtered out.
    private nonisolated static func scanClaude() -> [DiscoveredModel] {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let root = home.appendingPathComponent(".claude/projects",
                                                isDirectory: true)
        guard let walker = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: [.contentModificationDateKey]) else {
            return []
        }
        // Map model → most-recent mtime seen. Lets us sort by recency.
        var byMTime: [String: Date] = [:]
        let regex = try? NSRegularExpression(pattern: #""model"\s*:\s*"([^"]+)""#)
        let cutoff = Date().addingTimeInterval(-60 * 86400)  // 60 days
        var filesScanned = 0

        for case let url as URL in walker {
            guard url.pathExtension == "jsonl" else { continue }
            let mtime = (try? url.resourceValues(
                forKeys: [.contentModificationDateKey]))?
                .contentModificationDate ?? .distantPast
            if mtime < cutoff { continue }
            filesScanned += 1
            // Bail out after scanning ~150 files to keep this snappy.
            if filesScanned > 150 { break }
            guard let data = try? Data(contentsOf: url),
                  let body = String(data: data, encoding: .utf8) else {
                continue
            }
            let ns = body as NSString
            let matches = regex?.matches(
                in: body, range: NSRange(location: 0, length: ns.length))
                ?? []
            for m in matches where m.numberOfRanges > 1 {
                let model = ns.substring(with: m.range(at: 1))
                guard model.hasPrefix("claude-") else { continue }
                if let prev = byMTime[model], prev > mtime { continue }
                byMTime[model] = mtime
            }
        }
        // Sort newest-first.
        let sorted = byMTime.sorted { $0.value > $1.value }.map { entry -> DiscoveredModel in
            // "claude-opus-4-7" → "Opus 4.7"; "claude-haiku-4-5-20251001" → "Haiku 4.5"
            DiscoveredModel(id: entry.key,
                            display: prettyClaudeName(entry.key),
                            detail: nil,
                            // Claude's session JSONL doesn't list
                            // per-model effort levels; fall back to
                            // the CLI's universal --effort options.
                            supportedEfforts: claudeEffortLevels(
                                forModelID: entry.key))
        }
        return sorted
    }

    /// Effort levels claude's CLI accepts for `--effort`. The CLI
    /// itself ships these via its --help output as "(low, medium,
    /// high, max)" — we reflect that. Haiku family doesn't really
    /// benefit from effort tuning; it gets a smaller set so the UI
    /// doesn't expose levels the model will silently ignore.
    private nonisolated static func claudeEffortLevels(forModelID id: String)
        -> [String]
    {
        if id.contains("haiku") { return ["low", "medium"] }
        return ["low", "medium", "high", "max"]
    }

    private nonisolated static func prettyClaudeName(_ id: String) -> String {
        // Strip leading "claude-" + any trailing date suffix.
        var s = id
        if s.hasPrefix("claude-") { s.removeFirst("claude-".count) }
        // Drop trailing -<8 digits> date.
        let tail = s.suffix(9)  // -20251001
        if tail.count == 9, tail.hasPrefix("-"),
           tail.dropFirst().allSatisfy(\.isNumber) {
            s.removeLast(9)
        }
        // "opus-4-7" → "Opus 4.7"
        let parts = s.split(separator: "-")
        guard let family = parts.first?.capitalized else { return id }
        let nums = parts.dropFirst().joined(separator: ".")
        return nums.isEmpty ? family : "\(family) \(nums)"
    }

    // MARK: - codex

    /// Spawns `codex debug models` and parses its raw JSON catalog —
    /// this is what the codex CLI itself uses to render its own
    /// model picker, so it stays in sync with whatever the user's
    /// ChatGPT account has access to (including new models that
    /// haven't been written to ~/.codex/models_cache.json yet).
    /// Filters out entries with visibility != "list" (codex hides
    /// internal review-only models that way).
    ///
    /// Falls back to ~/.codex/models_cache.json if the CLI isn't on
    /// PATH or the subcommand fails for any reason — the cache file
    /// still has SOMETHING usable even if it's slightly stale.
    private nonisolated static func scanCodex() -> [DiscoveredModel] {
        if let live = scanCodexLive() { return live }
        return scanCodexCacheFile()
    }

    private nonisolated static func scanCodexLive() -> [DiscoveredModel]? {
        let candidates = ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"]
        guard let cli = candidates.first(where: {
            FileManager.default.isExecutableFile(atPath: $0)
        }) else { return nil }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: cli)
        proc.arguments = ["debug", "models"]
        let outPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = Pipe()  // discard

        do { try proc.run() } catch { return nil }

        // Hard timeout — codex debug models is local + fast (~50ms),
        // but a hung CLI shouldn't freeze the model picker.
        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async {
            proc.waitUntilExit()
            group.leave()
        }
        if group.wait(timeout: .now() + .seconds(5)) == .timedOut {
            proc.terminate()
            return nil
        }
        guard proc.terminationStatus == 0 else { return nil }
        let data = outPipe.fileHandleForReading.readDataToEndOfFile()
        guard let obj = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any],
              let arr = obj["models"] as? [[String: Any]]
        else { return nil }

        var out: [DiscoveredModel] = []
        for m in arr {
            guard let slug = m["slug"] as? String,
                  let visibility = m["visibility"] as? String,
                  visibility == "list" else { continue }
            out.append(DiscoveredModel(id: slug,
                                       display: extractDisplay(m, slug: slug),
                                       detail: m["description"] as? String,
                                       supportedEfforts: extractEfforts(m)))
        }
        return out.isEmpty ? nil : out
    }

    private nonisolated static func scanCodexCacheFile() -> [DiscoveredModel] {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let url = home.appendingPathComponent(".codex/models_cache.json")
        guard let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any],
              let arr = obj["models"] as? [[String: Any]]
        else { return [] }

        let exclude: Set<String> = ["codex-auto-review"]
        var out: [DiscoveredModel] = []
        for m in arr {
            guard let slug = m["slug"] as? String,
                  !exclude.contains(slug) else { continue }
            out.append(DiscoveredModel(id: slug,
                                       display: extractDisplay(m, slug: slug),
                                       detail: m["description"] as? String,
                                       supportedEfforts: extractEfforts(m)))
        }
        return out
    }

    private nonisolated static func extractDisplay(_ m: [String: Any],
                                                   slug: String) -> String {
        let display = (m["display_name"] as? String) ?? slug
        return display.isEmpty ? slug : display
    }

    /// Pulls supported_reasoning_levels[].effort from a codex model
    /// catalog entry. Returns ["low", "medium", "high", "xhigh"]
    /// for gpt-5.5, etc.
    private nonisolated static func extractEfforts(_ m: [String: Any])
        -> [String]
    {
        guard let levels = m["supported_reasoning_levels"]
                as? [[String: Any]] else { return [] }
        return levels.compactMap { $0["effort"] as? String }
    }
}
