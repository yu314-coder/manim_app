// AssetsView.swift — file browser for the user's Documents/Assets/
// folder, with drag-drop to import + reveal-in-Finder + delete.
import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct AssetsView: View {
    @State private var entries: [AssetEntry] = []
    @State private var query = ""
    @State private var selection: AssetEntry?

    static let assetsDir: URL = {
        let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask).first!
        let dir = docs.appendingPathComponent("ManimStudio/Assets",
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
        .onDrop(of: [.fileURL], isTargeted: nil, perform: handleDrop)
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "folder.fill")
                .foregroundStyle(Theme.indigo)
                .font(.system(size: 16))
            Text("Assets").font(.system(size: 18, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            TextField("Search…", text: $query)
                .textFieldStyle(.roundedBorder)
                .frame(width: 220)
            Button { importViaPanel() } label: {
                Label("Import", systemImage: "tray.and.arrow.down")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 7)
                        .fill(Theme.signatureGradient))
            }
            .buttonStyle(.plain)
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([Self.assetsDir])
            } label: {
                Image(systemName: "magnifyingglass.circle")
            }
            .buttonStyle(.plain)
            .help("Reveal Assets folder")
        }
        .padding(.horizontal, 18).padding(.vertical, 14)
    }

    @ViewBuilder
    private var content: some View {
        if entries.isEmpty {
            VStack(spacing: 8) {
                Image(systemName: "tray")
                    .font(.system(size: 36))
                    .foregroundStyle(Theme.textDim)
                Text("Drop files here to add them")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                Text("Documents/ManimStudio/Assets/")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textDim)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)],
                          spacing: 10) {
                    ForEach(filtered) { tile($0) }
                }
                .padding(14)
            }
        }
    }

    @ViewBuilder
    private func tile(_ e: AssetEntry) -> some View {
        VStack(spacing: 6) {
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(Theme.bgTertiary)
                Image(systemName: e.icon)
                    .font(.system(size: 28))
                    .foregroundStyle(Theme.indigo)
            }
            .frame(height: 84)
            Text(e.url.lastPathComponent)
                .font(.system(size: 11))
                .lineLimit(1).truncationMode(.middle)
                .foregroundStyle(Theme.textPrimary)
            Text(formatSize(e.size))
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Theme.textDim)
        }
        .padding(8)
        .glassCard()
        .contextMenu {
            Button("Reveal in Finder") {
                NSWorkspace.shared.activateFileViewerSelecting([e.url])
            }
            Button("Copy path") {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(e.url.path, forType: .string)
            }
            Divider()
            Button("Delete", role: .destructive) { delete(e) }
        }
    }

    // MARK: data

    private var filtered: [AssetEntry] {
        guard !query.isEmpty else { return entries }
        let q = query.lowercased()
        return entries.filter { $0.url.lastPathComponent.lowercased().contains(q) }
    }

    private func reload() {
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: Self.assetsDir,
            includingPropertiesForKeys: [.fileSizeKey, .isRegularFileKey],
            options: [.skipsHiddenFiles])) ?? []
        entries = urls.compactMap { u in
            let v = try? u.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
            guard v?.isRegularFile == true else { return nil }
            return AssetEntry(url: u, size: Int64(v?.fileSize ?? 0))
        }.sorted { $0.url.lastPathComponent < $1.url.lastPathComponent }
    }

    private func importViaPanel() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        guard panel.runModal() == .OK else { return }
        for src in panel.urls { copyIn(src) }
        reload()
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                if let url { Task { @MainActor in copyIn(url); reload() } }
            }
        }
        return true
    }

    private func copyIn(_ src: URL) {
        var dst = Self.assetsDir.appendingPathComponent(src.lastPathComponent)
        var n = 2
        while FileManager.default.fileExists(atPath: dst.path) {
            let stem = (src.lastPathComponent as NSString).deletingPathExtension
            let ext  = (src.lastPathComponent as NSString).pathExtension
            dst = Self.assetsDir.appendingPathComponent(
                ext.isEmpty ? "\(stem) (\(n))" : "\(stem) (\(n)).\(ext)")
            n += 1
        }
        _ = try? FileManager.default.copyItem(at: src, to: dst)
    }

    private func delete(_ e: AssetEntry) {
        try? FileManager.default.removeItem(at: e.url)
        reload()
    }

    private func formatSize(_ n: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: n, countStyle: .file)
    }
}

struct AssetEntry: Identifiable, Hashable {
    let url: URL
    let size: Int64
    var id: URL { url }
    var icon: String {
        switch url.pathExtension.lowercased() {
        case "mp4", "mov", "m4v": return "film"
        case "gif":               return "photo.stack"
        case "png", "jpg", "jpeg", "webp", "heic": return "photo"
        case "mp3", "wav", "m4a", "aac", "flac":   return "music.note"
        case "ttf", "otf":        return "textformat"
        case "py":                return "chevron.left.forwardslash.chevron.right"
        default:                  return "doc"
        }
    }
}
