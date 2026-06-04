// MenuCommands.swift — iPadOS menu-bar entries (visible when a Magic
// Keyboard or external keyboard is attached, also reachable by holding
// the Globe key on iPad). Built with SwiftUI's .commands modifier.
//
// Commands fire NSNotifications. ContentView listens and dispatches to
// the appropriate handler — this indirection keeps the @main scene from
// having to thread @State through every menu item, and it lets the
// editor / sidebar receive their own notifications independently.
import SwiftUI

extension Notification.Name {
    static let menuFileNew    = Notification.Name("menu.file.new")
    static let menuFileOpen   = Notification.Name("menu.file.open")
    static let menuFileSave   = Notification.Name("menu.file.save")

    static let menuEditFind         = Notification.Name("menu.edit.find")
    static let menuEditFindReplace  = Notification.Name("menu.edit.findReplace")
    static let menuEditComment      = Notification.Name("menu.edit.comment")
    static let menuEditIndent       = Notification.Name("menu.edit.indent")
    static let menuEditOutdent      = Notification.Name("menu.edit.outdent")
    static let menuEditMoveUp       = Notification.Name("menu.edit.moveUp")
    static let menuEditMoveDown     = Notification.Name("menu.edit.moveDown")
    static let menuEditFormat       = Notification.Name("menu.edit.format")
    static let menuEditDuplicate    = Notification.Name("menu.edit.duplicate")
    static let menuEditTriggerSuggest = Notification.Name("menu.edit.triggerSuggest")

    static let menuRenderRender    = Notification.Name("menu.render.render")
    static let menuRenderPreview   = Notification.Name("menu.render.preview")
    static let menuRenderStop      = Notification.Name("menu.render.stop")
    static let menuRenderGPU       = Notification.Name("menu.render.gpu")
    static let menuRenderClearOutputs = Notification.Name("menu.render.clearOutputs")

    static let menuViewTab          = Notification.Name("menu.view.tab") // userInfo: AppTab.rawValue
    static let menuViewToggleSidebar = Notification.Name("menu.view.toggleSidebar")

    /// Editor diagnostic markers (render error gutter).
    static let editorSetMarkers   = Notification.Name("editor.setMarkers")
    static let editorClearMarkers = Notification.Name("editor.clearMarkers")

    static let menuHelpShortcuts    = Notification.Name("menu.help.shortcuts")
    static let menuHelpOpenHelp     = Notification.Name("menu.help.open")
    static let menuHelpOpenLog      = Notification.Name("menu.help.openLog")
    static let menuHelpOpenSettings = Notification.Name("menu.help.openSettings")
}

struct ManimStudioCommands: Commands {
    var body: some Commands {
        // ── File ────────────────────────────────────────────────
        CommandGroup(replacing: .newItem) {
            Button("New File") { post(.menuFileNew) }
                .keyboardShortcut("n", modifiers: [.command])
            Button("Open File…") { post(.menuFileOpen) }
                .keyboardShortcut("o", modifiers: [.command])
            Divider()
            Button("Save…") { post(.menuFileSave) }
                .keyboardShortcut("s", modifiers: [.command])
        }

        // ── Edit ────────────────────────────────────────────────
        CommandMenu("Code") {
            Button("Find")              { post(.menuEditFind) }
                .keyboardShortcut("f", modifiers: [.command])
            Button("Find & Replace")    { post(.menuEditFindReplace) }
                .keyboardShortcut("f", modifiers: [.command, .option])
            Divider()
            Button("Toggle Line Comment") { post(.menuEditComment) }
                .keyboardShortcut("/", modifiers: [.command])
            Button("Indent")            { post(.menuEditIndent) }
                .keyboardShortcut("]", modifiers: [.command])
            Button("Outdent")           { post(.menuEditOutdent) }
                .keyboardShortcut("[", modifiers: [.command])
            Divider()
            Button("Move Line Up")      { post(.menuEditMoveUp) }
                .keyboardShortcut(.upArrow,   modifiers: [.option])
            Button("Move Line Down")    { post(.menuEditMoveDown) }
                .keyboardShortcut(.downArrow, modifiers: [.option])
            Button("Duplicate Selection") { post(.menuEditDuplicate) }
                .keyboardShortcut("d", modifiers: [.command, .shift])
            Divider()
            Button("Format Document")   { post(.menuEditFormat) }
                .keyboardShortcut("i", modifiers: [.command, .option])
            Button("Trigger Completion") { post(.menuEditTriggerSuggest) }
                .keyboardShortcut(.space, modifiers: [.control])
        }

        // ── Render ──────────────────────────────────────────────
        CommandMenu("Render") {
            Button("Render (Final)")    { post(.menuRenderRender) }
                .keyboardShortcut("r", modifiers: [.command])
            Button("Preview (Quick)")   { post(.menuRenderPreview) }
                .keyboardShortcut("r", modifiers: [.command, .shift])
            Button("Stop")              { post(.menuRenderStop) }
                .keyboardShortcut(".", modifiers: [.command])
            Divider()
            Button("Toggle GPU Encode") { post(.menuRenderGPU) }
                .keyboardShortcut("g", modifiers: [.command, .option])
            Divider()
            Button("Delete All Renders") { post(.menuRenderClearOutputs) }
        }

        // ── View ────────────────────────────────────────────────
        // NOTE: each tab maps to a current AppTab case (Gallery was added
        // after this menu was first written — keep them in sync). The
        // ⌘1–⌘6 / ⌘\ shortcuts are declared exactly once here; declaring
        // the same key elsewhere (or twice) makes UIKit log duplicate
        // UIKeyCommand identifiers and is undefined behavior.
        CommandMenu("View") {
            Button("Gallery")   { post(.menuViewTab, ["tab": "gallery"]) }
                .keyboardShortcut("1", modifiers: [.command])
            Button("Workspace") { post(.menuViewTab, ["tab": "workspace"]) }
                .keyboardShortcut("2", modifiers: [.command])
            Button("Assets")    { post(.menuViewTab, ["tab": "assets"]) }
                .keyboardShortcut("3", modifiers: [.command])
            Button("Packages")  { post(.menuViewTab, ["tab": "packages"]) }
                .keyboardShortcut("4", modifiers: [.command])
            Button("History")   { post(.menuViewTab, ["tab": "history"]) }
                .keyboardShortcut("5", modifiers: [.command])
            Button("System")    { post(.menuViewTab, ["tab": "system"]) }
                .keyboardShortcut("6", modifiers: [.command])
            Divider()
            Button("Toggle Right Sidebar") { post(.menuViewToggleSidebar) }
                .keyboardShortcut("\\", modifiers: [.command])
        }

        // ── Help (also covered by the standard Help menu Apple
        // creates automatically; we add app-specific items.)
        CommandGroup(replacing: .help) {
            Button("ManimStudio Help") { post(.menuHelpOpenHelp) }
                .keyboardShortcut("?", modifiers: [.command])
            Button("Keyboard Shortcuts") { post(.menuHelpShortcuts) }
                .keyboardShortcut("k", modifiers: [.command, .shift])
            Divider()
            // No ⌘, here: that combo is owned by the system "Settings…"
            // command. Declaring it again triggers a duplicate
            // UIKeyCommand identifier and UB. The menu item still fires
            // the notification; it's just no longer bound to ⌘,.
            Button("Open Settings") { post(.menuHelpOpenSettings) }
            Button("Open Log File") { post(.menuHelpOpenLog) }
        }
    }

    private func post(_ name: Notification.Name,
                      _ userInfo: [AnyHashable: Any]? = nil) {
        NotificationCenter.default.post(name: name, object: nil, userInfo: userInfo)
    }
}
