// AssetsView.swift — Assets tab. Manages files in Documents/Assets/.
// Upload via UIDocumentPicker, organize into folders, share or delete.
// The folder is exposed in iOS Files (UIFileSharingEnabled in Info.plist)
// so users can also drag files in/out of Files.app.
import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct AssetsView: View {
    @State private var entries: [Entry] = []
    @State private var currentDir: URL = AssetsView.assetsRoot()
    @State private var showImporter = false
    @State private var showNewFolder = false
    @State private var newFolderName = ""
    @State private var shareURL: URL? = nil

    struct Entry: Identifiable, Hashable {
        let url: URL
        let isDir: Bool
        let size: Int64
        var id: URL { url }
        var name: String { url.lastPathComponent }
        var icon: String {
            if isDir { return "folder.fill" }
            switch url.pathExtension.lowercased() {
            case "png","jpg","jpeg","webp","gif","heic": return "photo"
            case "mp4","mov","m4v","webm":               return "film"
            case "mp3","wav","m4a","aac","flac","ogg":   return "music.note"
            case "ttf","otf","woff","woff2":             return "textformat"
            case "py":                                   return "chevron.left.forwardslash.chevron.right"
            case "tex":                                  return "function"
            case "json","yml","yaml","toml":             return "doc.text"
            case "svg":                                  return "scribble"
            default:                                     return "doc"
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text("Assets").font(.system(size: 28, weight: .bold))
                        .foregroundStyle(Theme.textPrimary)
                    Spacer()
                    actionBtn(icon: "plus", label: "Upload")        { showImporter = true }
                    actionBtn(icon: "folder.badge.plus", label: "New Folder") { showNewFolder = true }
                }

                breadcrumbs

                Text("Files saved here are visible in the iOS Files app under \"On My iPad / Manim Studio / Assets\".")
                    .font(.system(size: 11)).foregroundStyle(Theme.textSecondary)

                if entries.isEmpty {
                    emptyState
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 12)], spacing: 12) {
                        ForEach(entries) { e in tile(e) }
                    }
                }
            }
            .padding(16)
        }
        .background(
            LinearGradient(colors: [Theme.bgPrimary, Theme.bgSecondary],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
        )
        .onAppear { reload() }
        // .fileImporter is unreliable when attached deep inside a
        // ScrollView (it sometimes silently fails to present on iPad
        // because the SwiftUI presentation controller can't find a
        // window). Use a direct UIDocumentPickerViewController bridge
        // instead — it always presents from the key window's root.
        .background(
            DocumentPicker(
                isPresented: $showImporter,
                onPick: { urls in handleImport(.success(urls)) }
            )
        )
        .alert("New folder", isPresented: $showNewFolder) {
            TextField("Folder name", text: $newFolderName)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            Button("Create") { createFolder() }
            Button("Cancel", role: .cancel) { newFolderName = "" }
        } message: {
            Text("Created inside the current location.")
        }
        .sheet(item: Binding(
            get: { shareURL.map { Identified($0) } },
            set: { shareURL = $0?.url }
        )) { item in
            ShareSheet(items: [item.url])
        }
    }

    // MARK: subviews

    @ViewBuilder
    private var breadcrumbs: some View {
        let root = AssetsView.assetsRoot()
        let crumbs = AssetsView.crumbs(from: root, to: currentDir)
        HStack(spacing: 4) {
            ForEach(crumbs.indices, id: \.self) { i in
                let crumb = crumbs[i]
                Button { currentDir = crumb.url; reload() } label: {
                    Text(crumb.name)
                        .font(.system(size: 11, weight: i == crumbs.count - 1 ? .bold : .regular))
                        .foregroundStyle(i == crumbs.count - 1 ? Theme.textPrimary : Theme.textSecondary)
                }.buttonStyle(.plain)
                if i < crumbs.count - 1 {
                    Image(systemName: "chevron.right").font(.system(size: 8))
                        .foregroundStyle(Theme.textDim)
                }
            }
            Spacer()
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "tray")
                .font(.system(size: 36)).foregroundStyle(Theme.textDim)
            Text("Empty folder")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
            Text("Tap Upload to import files from iCloud Drive, Files, or another app.")
                .font(.system(size: 11))
                .foregroundStyle(Theme.textDim)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 320)
        }
        .frame(maxWidth: .infinity, minHeight: 180)
    }

    @ViewBuilder
    private func tile(_ e: Entry) -> some View {
        VStack(spacing: 8) {
            Image(systemName: e.icon)
                .font(.system(size: 28))
                .foregroundStyle(Theme.accentPrimary)
                .frame(maxWidth: .infinity, minHeight: 80)
                .background(Theme.bgTertiary)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            Text(e.name).font(.system(size: 11))
                .foregroundStyle(Theme.textPrimary).lineLimit(1).truncationMode(.middle)
            if !e.isDir {
                Text(ByteCountFormatter.string(fromByteCount: e.size, countStyle: .file))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textDim)
            }
        }
        .glassCard(padding: 10)
        .contentShape(Rectangle())
        .onTapGesture {
            if e.isDir { currentDir = e.url; reload() }
            else { shareURL = e.url }
        }
        .contextMenu {
            if !e.isDir {
                Button { shareURL = e.url } label: { Label("Share", systemImage: "square.and.arrow.up") }
            }
            Button(role: .destructive) { delete(e) } label: { Label("Delete", systemImage: "trash") }
        }
    }

    @ViewBuilder
    private func actionBtn(icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: 11))
                Text(label).font(.system(size: 11, weight: .medium))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Capsule().fill(Theme.signatureGradient))
        }.buttonStyle(.plain)
    }

    // MARK: storage

    static func assetsRoot() -> URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let dir = docs.appendingPathComponent("Assets", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private static func crumbs(from root: URL, to dir: URL) -> [(name: String, url: URL)] {
        var out: [(String, URL)] = [("Assets", root)]
        let rootComps = root.standardizedFileURL.pathComponents
        let dirComps  = dir.standardizedFileURL.pathComponents
        guard dirComps.starts(with: rootComps) else { return out }
        var u = root
        for comp in dirComps.dropFirst(rootComps.count) {
            u.appendPathComponent(comp, isDirectory: true)
            out.append((comp, u))
        }
        return out
    }

    private func reload() {
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: currentDir,
            includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey],
            options: [.skipsHiddenFiles])) ?? []
        var list: [Entry] = []
        for u in urls {
            let vals = try? u.resourceValues(forKeys: [.isDirectoryKey, .fileSizeKey])
            list.append(Entry(
                url: u,
                isDir: vals?.isDirectory == true,
                size: Int64(vals?.fileSize ?? 0)))
        }
        entries = list.sorted {
            if $0.isDir != $1.isDir { return $0.isDir && !$1.isDir }
            return $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
        }
    }

    private func handleImport(_ result: Result<[URL], Error>) {
        guard case .success(let urls) = result else { return }
        for src in urls {
            let needsScope = src.startAccessingSecurityScopedResource()
            defer { if needsScope { src.stopAccessingSecurityScopedResource() } }
            let dst = uniqueDestination(for: src.lastPathComponent, in: currentDir)
            do { try FileManager.default.copyItem(at: src, to: dst) }
            catch { /* best-effort */ }
        }
        reload()
    }

    private func createFolder() {
        let trimmed = newFolderName
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "/", with: "-")
        defer { newFolderName = "" }
        guard !trimmed.isEmpty else { return }
        let dst = uniqueDestination(for: trimmed, in: currentDir)
        try? FileManager.default.createDirectory(at: dst, withIntermediateDirectories: true)
        reload()
    }

    private func delete(_ e: Entry) {
        try? FileManager.default.removeItem(at: e.url)
        reload()
    }

    private func uniqueDestination(for name: String, in dir: URL) -> URL {
        var u = dir.appendingPathComponent(name)
        guard FileManager.default.fileExists(atPath: u.path) else { return u }
        let stem = (name as NSString).deletingPathExtension
        let ext  = (name as NSString).pathExtension
        var i = 2
        while FileManager.default.fileExists(atPath: u.path) {
            let n = ext.isEmpty ? "\(stem) (\(i))" : "\(stem) (\(i)).\(ext)"
            u = dir.appendingPathComponent(n)
            i += 1
        }
        return u
    }
}

private struct Identified: Identifiable {
    let url: URL
    init(_ u: URL) { url = u }
    var id: URL { url }
}

/// UIDocumentPickerViewController bridge for file import.
/// Replaces SwiftUI's .fileImporter which has a long history of
/// silently no-op'ing when attached inside ScrollView / sheet
/// hierarchies on iPadOS. Presented from the host VC's hierarchy
/// every time, so it always shows up.
struct DocumentPicker: UIViewControllerRepresentable {
    @Binding var isPresented: Bool
    var contentTypes: [UTType] = [.item]
    var allowsMultiple: Bool = true
    let onPick: ([URL]) -> Void

    func makeCoordinator() -> Coord { Coord(self) }

    func makeUIViewController(context: Context) -> UIViewController {
        UIViewController()  // host view; we present off it
    }

    func updateUIViewController(_ host: UIViewController, context: Context) {
        guard isPresented, host.presentedViewController == nil else { return }
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: contentTypes, asCopy: true)
        picker.allowsMultipleSelection = allowsMultiple
        picker.delegate = context.coordinator
        // Defer to next runloop so SwiftUI has finished its layout pass —
        // presenting during updateUIViewController itself can be ignored.
        DispatchQueue.main.async {
            host.present(picker, animated: true)
        }
    }

    final class Coord: NSObject, UIDocumentPickerDelegate {
        let parent: DocumentPicker
        init(_ p: DocumentPicker) { parent = p }
        func documentPicker(_ controller: UIDocumentPickerViewController,
                            didPickDocumentsAt urls: [URL]) {
            parent.onPick(urls)
            parent.isPresented = false
        }
        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            parent.isPresented = false
        }
    }
}
