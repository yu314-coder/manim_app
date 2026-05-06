// HistoryView.swift — render history. Scans every per-render
// directory under Documents/ManimStudio/Renders/ for produced
// .mp4/.mov/.gif/.png files, lists them with size + mtime + a
// reveal/play/delete row.
import SwiftUI
import AppKit
import AVKit

struct HistoryView: View {
    @EnvironmentObject var app: AppState
    @State private var entries: [HistoryEntry] = []
    @State private var preview: URL?

    static let rendersDir: URL = {
        let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask).first!
        let dir = docs.appendingPathComponent("ManimStudio/Renders",
                                              isDirectory: true)
        try? FileManager.default.createDirectory(
            at: dir, withIntermediateDirectories: true)
        return dir
    }()

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().background(Theme.borderSubtle)
            content
        }
        .background(Theme.bgPrimary)
        .onAppear { reload() }
        .sheet(item: Binding(get: {
            preview.map { Wrap(url: $0) } },
            set: { preview = $0?.url })) { item in
            VStack {
                VideoPlayer(player: AVPlayer(url: item.url))
                    .frame(minWidth: 720, minHeight: 480)
                Button("Close") { preview = nil }
                    .padding(.bottom, 12)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "clock.arrow.circlepath")
                .font(.system(size: 16))
                .foregroundStyle(Theme.cyan)
            Text("Render History").font(.system(size: 18, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            Button { reload() } label: { Image(systemName: "arrow.clockwise") }
                .buttonStyle(.plain)
            Button(role: .destructive) { clearAll() } label: {
                Label("Clear all", systemImage: "trash")
                    .font(.system(size: 11))
            }
            .buttonStyle(.plain)
            .foregroundStyle(Theme.error)
            .disabled(entries.isEmpty)
        }
        .padding(.horizontal, 18).padding(.vertical, 14)
    }

    @ViewBuilder
    private var content: some View {
        if entries.isEmpty {
            VStack(spacing: 8) {
                Image(systemName: "film.stack")
                    .font(.system(size: 36)).foregroundStyle(Theme.textDim)
                Text("No renders yet")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.textSecondary)
                Text("Hit ⌘R or ⇧⌘R to render")
                    .font(.system(size: 11)).foregroundStyle(Theme.textDim)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(entries) { row($0) }
                }
                .padding(14)
            }
        }
    }

    @ViewBuilder
    private func row(_ e: HistoryEntry) -> some View {
        HStack(spacing: 12) {
            Image(systemName: e.icon)
                .font(.system(size: 22))
                .foregroundStyle(Theme.indigo)
                .frame(width: 44, height: 44)
                .background(RoundedRectangle(cornerRadius: 8)
                    .fill(Theme.bgTertiary))
            VStack(alignment: .leading, spacing: 2) {
                Text(e.url.lastPathComponent)
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1).truncationMode(.middle)
                Text("\(e.formattedDate)  ·  \(e.formattedSize)")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            if e.isVideo {
                Button { preview = e.url } label: {
                    Image(systemName: "play.circle")
                }.buttonStyle(.plain)
            }
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([e.url])
            } label: { Image(systemName: "folder") }
            .buttonStyle(.plain)
            Button(role: .destructive) {
                try? FileManager.default.removeItem(at: e.url)
                reload()
            } label: { Image(systemName: "trash") }
            .buttonStyle(.plain)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.bgSecondary))
        .overlay(RoundedRectangle(cornerRadius: 10)
            .stroke(Theme.borderSubtle, lineWidth: 1))
    }

    private func reload() {
        guard let walker = FileManager.default.enumerator(
            at: Self.rendersDir,
            includingPropertiesForKeys: [.contentModificationDateKey,
                                          .fileSizeKey,
                                          .isRegularFileKey],
            options: [.skipsHiddenFiles])
        else { entries = []; return }
        let exts: Set<String> = ["mp4", "mov", "m4v", "webm", "gif",
                                  "png", "jpg", "jpeg"]
        var items: [HistoryEntry] = []
        for case let url as URL in walker {
            let v = try? url.resourceValues(forKeys: [
                .isRegularFileKey, .contentModificationDateKey, .fileSizeKey])
            guard v?.isRegularFile == true,
                  exts.contains(url.pathExtension.lowercased())
            else { continue }
            items.append(HistoryEntry(
                url: url,
                modified: v?.contentModificationDate ?? .distantPast,
                size: Int64(v?.fileSize ?? 0)))
        }
        entries = items.sorted { $0.modified > $1.modified }
    }

    private func clearAll() {
        for e in entries { try? FileManager.default.removeItem(at: e.url) }
        reload()
    }
}

struct HistoryEntry: Identifiable, Hashable {
    let url: URL
    let modified: Date
    let size: Int64
    var id: URL { url }
    var icon: String {
        switch url.pathExtension.lowercased() {
        case "mp4", "mov", "m4v", "webm": return "film"
        case "gif":                       return "photo.stack"
        case "png", "jpg", "jpeg":        return "photo"
        default:                          return "doc"
        }
    }
    var isVideo: Bool {
        ["mp4", "mov", "m4v", "webm"].contains(url.pathExtension.lowercased())
    }
    var formattedSize: String {
        ByteCountFormatter.string(fromByteCount: size, countStyle: .file)
    }
    var formattedDate: String {
        let f = DateFormatter(); f.dateStyle = .short; f.timeStyle = .short
        return f.string(from: modified)
    }
}

private struct Wrap: Identifiable {
    let url: URL
    var id: URL { url }
}
