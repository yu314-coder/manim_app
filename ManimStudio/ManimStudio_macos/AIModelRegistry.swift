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
                            detail: nil)
        }
        return sorted
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

    /// Reads ~/.codex/models_cache.json. The CLI fetches the user's
    /// account-available model list and caches it there. Each entry
    /// has { slug, display_name, description, … }. We surface every
    /// non-internal slug (filter out "codex-auto-review" — it's an
    /// internal review-only model not user-pickable).
    private nonisolated static func scanCodex() -> [DiscoveredModel] {
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
            let display = (m["display_name"] as? String) ?? slug
            let detail  = m["description"] as? String
            out.append(DiscoveredModel(id: slug,
                                       display: display.isEmpty ? slug : display,
                                       detail: detail))
        }
        return out
    }
}
