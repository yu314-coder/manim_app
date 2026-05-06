// LogViewerView.swift — in-app text viewer for the crash/render log.
// Shown from Settings → Diagnostics → "View log". Auto-tails when the
// log changes while the view is open so the user sees live render
// output without leaving the screen.
import SwiftUI

struct LogViewerView: View {
    let url: URL

    @State private var contents: String = ""
    @State private var lineCount: Int = 0
    @State private var sizeBytes: Int64 = 0
    @State private var autoScroll = true
    @State private var query = ""
    @State private var refreshTimer: Timer?

    var body: some View {
        VStack(spacing: 0) {
            // Header row — file stats + controls.
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(url.lastPathComponent)
                        .font(.system(size: 12, design: .monospaced))
                        .lineLimit(1).truncationMode(.middle)
                    Text("\(lineCount) lines · \(formattedSize)")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Toggle("Tail", isOn: $autoScroll)
                    .toggleStyle(.button)
                    .controlSize(.small)
                Button {
                    reload()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(Theme.bgSecondary)

            Divider()

            ScrollViewReader { proxy in
                ScrollView {
                    Text(filtered)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Theme.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .textSelection(.enabled)
                        .id("end")  // anchor for autoscroll
                }
                .background(Theme.bgPrimary)
                .onChange(of: contents) { _, _ in
                    if autoScroll {
                        withAnimation(.linear(duration: 0.1)) {
                            proxy.scrollTo("end", anchor: .bottom)
                        }
                    }
                }
                .onAppear {
                    proxy.scrollTo("end", anchor: .bottom)
                }
            }
        }
        .navigationTitle("Log")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $query, prompt: "Filter lines…")
        .onAppear {
            reload()
            // Tail every 0.8 s while the view is visible. Cheap — we
            // only re-read when mtime changes.
            refreshTimer = Timer.scheduledTimer(withTimeInterval: 0.8, repeats: true) { _ in
                reloadIfChanged()
            }
        }
        .onDisappear {
            refreshTimer?.invalidate()
            refreshTimer = nil
        }
    }

    private var filtered: String {
        guard !query.isEmpty else { return contents }
        let q = query.lowercased()
        return contents
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { $0.lowercased().contains(q) }
            .joined(separator: "\n")
    }

    private var formattedSize: String {
        ByteCountFormatter.string(fromByteCount: sizeBytes, countStyle: .file)
    }

    private var lastModified: Date {
        (try? FileManager.default.attributesOfItem(atPath: url.path)[.modificationDate] as? Date)
            ?? .distantPast
    }
    @State private var lastSeenMTime: Date = .distantPast

    private func reload() {
        // Cap to last ~256 KB so a 5 MB log doesn't freeze the
        // SwiftUI Text. Tail is what matters for live diagnosis.
        let s = (try? readTail(of: url, bytes: 256 * 1024)) ?? ""
        contents = s
        lineCount = s.reduce(into: 0) { acc, c in if c == "\n" { acc += 1 } }
        sizeBytes = Int64(((try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? UInt64) ?? 0))
        lastSeenMTime = lastModified
    }

    private func reloadIfChanged() {
        let mtime = lastModified
        if mtime != lastSeenMTime { reload() }
    }

    /// Read the last `bytes` of `url`. Avoids loading multi-MB logs
    /// into memory at once; we want the tail only.
    private func readTail(of url: URL, bytes: Int) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let total = (try? handle.seekToEnd()) ?? 0
        let want = UInt64(bytes)
        let start = total > want ? total - want : 0
        try handle.seek(toOffset: start)
        let data = (try handle.readToEnd()) ?? Data()
        let s = String(data: data, encoding: .utf8) ?? ""
        // If we sliced mid-line, drop the first partial line.
        if start > 0, let nl = s.firstIndex(of: "\n") {
            return String(s[s.index(after: nl)...])
        }
        return s
    }
}
