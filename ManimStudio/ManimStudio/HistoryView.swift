// HistoryView.swift — Render history tab. Scans Documents/ToolOutputs/
// for video/image files produced by manim renders, lists them with
// thumbnails + dates, and lets the user share or delete them.
import SwiftUI
import UIKit
import AVKit

struct HistoryView: View {
    @State private var entries: [Entry] = []
    @State private var shareURL: URL? = nil
    @State private var playerURL: URL? = nil
    @State private var confirmClear = false

    struct Entry: Identifiable, Hashable {
        let url: URL
        let modified: Date
        let size: Int64
        var id: URL { url }
        var name: String { url.lastPathComponent }
        var ext: String { url.pathExtension.lowercased() }
        var icon: String {
            switch ext {
            case "mp4","mov","m4v","webm": return "film"
            case "gif":                    return "photo.stack"
            case "png","jpg","jpeg","webp": return "photo"
            case "svg":                    return "scribble"
            default:                       return "doc"
            }
        }
        var isVideo: Bool { ["mp4","mov","m4v","webm"].contains(ext) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Render History").font(.system(size: 22, weight: .bold))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                Button { reload() } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Theme.textPrimary)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .background(Capsule().fill(Theme.bgTertiary))
                }.buttonStyle(.plain)
                Button { confirmClear = true } label: {
                    Label("Clear All", systemImage: "trash")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .background(Capsule().fill(Theme.error))
                }
                .buttonStyle(.plain)
                .disabled(entries.isEmpty)
            }

            if entries.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "clock.arrow.circlepath")
                        .font(.system(size: 48))
                        .foregroundStyle(Theme.textDim)
                    Text("No renders yet")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.textSecondary)
                    Text("Hit Render or Preview to start")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.textDim)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(entries) { e in
                            row(e)
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Theme.bgPrimary)
        .onAppear { reload() }
        .sheet(item: Binding(
            get: { shareURL.map { ShareItem(url: $0) } },
            set: { shareURL = $0?.url }
        )) { item in
            ShareSheet(items: [item.url])
        }
        .sheet(item: Binding(
            get: { playerURL.map { ShareItem(url: $0) } },
            set: { playerURL = $0?.url }
        )) { item in
            VideoPlayer(player: AVPlayer(url: item.url))
                .ignoresSafeArea()
        }
        .confirmationDialog("Delete every render?",
                            isPresented: $confirmClear,
                            titleVisibility: .visible) {
            Button("Delete \(entries.count) file(s)", role: .destructive) { clearAll() }
            Button("Cancel", role: .cancel) {}
        }
    }

    @ViewBuilder
    private func row(_ e: Entry) -> some View {
        HStack(spacing: 12) {
            Image(systemName: e.icon)
                .font(.system(size: 22))
                .foregroundStyle(Theme.accentPrimary)
                .frame(width: 44, height: 44)
                .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgTertiary))
            VStack(alignment: .leading, spacing: 2) {
                Text(e.name)
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1).truncationMode(.middle)
                Text("\(Self.df.string(from: e.modified))  ·  \(Self.formatBytes(e.size))")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            if e.isVideo {
                iconBtn("play.circle") { playerURL = e.url }
            }
            iconBtn("square.and.arrow.up") { shareURL = e.url }
            iconBtn("trash") { delete(e) }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.bgSecondary))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.borderSubtle, lineWidth: 1))
    }

    @ViewBuilder
    private func iconBtn(_ name: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: name)
                .font(.system(size: 14))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 30, height: 30)
                .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
        }
        .buttonStyle(.plain)
    }

    // MARK: storage

    private static let allowedExt: Set<String> = ["mp4","mov","m4v","webm","gif","png","jpg","jpeg","webp","svg"]

    private static var outputDir: URL? {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
            .first?.appendingPathComponent("ToolOutputs", isDirectory: true)
    }

    private func reload() {
        guard let dir = Self.outputDir,
              let walker = FileManager.default.enumerator(
                at: dir,
                includingPropertiesForKeys: [.contentModificationDateKey, .fileSizeKey, .isRegularFileKey],
                options: [.skipsHiddenFiles])
        else { entries = []; return }
        var found: [Entry] = []
        for case let url as URL in walker {
            let vals = try? url.resourceValues(forKeys: [
                .isRegularFileKey, .contentModificationDateKey, .fileSizeKey
            ])
            guard vals?.isRegularFile == true,
                  Self.allowedExt.contains(url.pathExtension.lowercased())
            else { continue }
            found.append(Entry(
                url: url,
                modified: vals?.contentModificationDate ?? .distantPast,
                size: Int64(vals?.fileSize ?? 0)
            ))
        }
        entries = found.sorted { $0.modified > $1.modified }
    }

    private func delete(_ e: Entry) {
        try? FileManager.default.removeItem(at: e.url)
        reload()
    }

    private func clearAll() {
        for e in entries { try? FileManager.default.removeItem(at: e.url) }
        reload()
    }

    private static let df: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .short
        f.timeStyle = .short
        return f
    }()
    private static func formatBytes(_ n: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: n, countStyle: .file)
    }
}

// Wraps a URL so .sheet(item:) can identify it.
private struct ShareItem: Identifiable {
    let url: URL
    var id: URL { url }
}

/// UIActivityViewController bridge for the share sheet.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
