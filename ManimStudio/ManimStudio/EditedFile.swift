// EditedFile.swift — a file the terminal asked the editor to open.
//
// `cmd new` / `cmd edit` (python-ios-lib's shell)
// write the file's path to $TMPDIR/latex_signals/open_in_editor.txt.
// ManimStudio's editor holds the scene code ("manim_source"), not a file, so
// opening one puts the scene aside, shows the file, and writes every change
// back to it. Done in the editor's bar brings the scene back. Loading other
// code (Gallery, New, Open) ends it too, leaving the file as last saved.
import Combine
import Foundation
import SwiftUI

extension Notification.Name {
    /// Posted when a file opens in the editor, so the phone layout can
    /// switch to its Editor pane.
    static let editorShowsFile = Notification.Name("editor.showsFile")
}

@MainActor
final class EditedFile: ObservableObject {
    static let shared = EditedFile()

    private static let sourceKey = "manim_source"
    private static let pathKey = "manim_edited_file"
    private static let stashKey = "manim_edited_file_scene"

    /// The file being edited, or nil while the editor shows the scene.
    @Published private(set) var url: URL?

    private var written: String?
    private var pendingWrite: DispatchWorkItem?

    private init() {
        let d = UserDefaults.standard
        guard let path = d.string(forKey: Self.pathKey) else { return }
        if FileManager.default.fileExists(atPath: path) {
            url = URL(fileURLWithPath: path)
            written = d.string(forKey: Self.sourceKey)
        } else {
            // The file went away while the app was closed: back to the scene.
            restoreScene()
        }
    }

    /// The name shown in the editor: the folder it's in and its own name.
    var displayName: String {
        guard let url else { return "" }
        return "\(url.deletingLastPathComponent().lastPathComponent)/\(url.lastPathComponent)"
    }

    func open(path: String) {
        let file = URL(fileURLWithPath: path)
        guard let text = try? String(contentsOf: file, encoding: .utf8) else { return }
        let d = UserDefaults.standard
        if url == nil {
            d.set(d.string(forKey: Self.sourceKey) ?? "", forKey: Self.stashKey)
        } else {
            flush()
        }
        url = file
        written = text
        d.set(file.path, forKey: Self.pathKey)
        d.set(text, forKey: Self.sourceKey)
        NotificationCenter.default.post(name: .menuViewTab, object: nil,
                                        userInfo: ["tab": AppTab.workspace.rawValue])
        NotificationCenter.default.post(name: .editorShowsFile, object: nil)
    }

    /// The editor's text changed: save it to the file a moment later.
    func sourceChanged(_ text: String) {
        guard let url, text != written else { return }
        pendingWrite?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.url == url else { return }
            self.write(text, to: url)
        }
        pendingWrite = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4, execute: work)
    }

    /// Done: save the file and show the scene again.
    func close() {
        guard url != nil else { return }
        flush()
        restoreScene()
    }

    /// Other code is about to replace the editor's text (Gallery, New,
    /// Open): the file keeps what was saved, and that code becomes the scene.
    func release() {
        guard url != nil else { return }
        flush()
        url = nil
        written = nil
        let d = UserDefaults.standard
        d.removeObject(forKey: Self.pathKey)
        d.removeObject(forKey: Self.stashKey)
    }

    private func flush() {
        pendingWrite?.cancel()
        pendingWrite = nil
        guard let url, let text = UserDefaults.standard.string(forKey: Self.sourceKey),
              text != written else { return }
        write(text, to: url)
    }

    private func write(_ text: String, to file: URL) {
        do {
            try text.write(to: file, atomically: true, encoding: .utf8)
            written = text
        } catch {
            NSLog("[editor] couldn't save %@: %@", file.path, error.localizedDescription)
        }
    }

    private func restoreScene() {
        let d = UserDefaults.standard
        let scene = d.string(forKey: Self.stashKey)
        url = nil
        written = nil
        d.removeObject(forKey: Self.pathKey)
        d.removeObject(forKey: Self.stashKey)
        if let scene { d.set(scene, forKey: Self.sourceKey) }
    }
}
