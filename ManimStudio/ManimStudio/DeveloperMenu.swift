// DeveloperMenu.swift — hidden developer menu, unlocked Android-style.
//
// Why hidden: Settings → About shows only the marketing version ("1.4").
// The build number and the low-level diagnostics live behind seven taps on
// that row — the same gesture Android uses for Developer options. Nothing
// in here is needed for normal use, and the destructive actions (wiping
// renders) would cost someone real work on a stray tap, so the whole menu
// stays out of the way until it is deliberately unlocked.
//
// Reuses SystemInfoModel + RAMSampler rather than re-deriving device facts,
// so the dev menu and the System tab can never disagree.
import SwiftUI
import Combine
import Darwin
import UIKit

// MARK: - Unlock state

/// Tracks the seven-tap unlock and persists the result. Shared so the
/// Settings sheet and the menu itself see the same state.
@MainActor
final class DevMode: ObservableObject {
    static let shared = DevMode()

    private static let key = "manim_dev_mode_unlocked"
    private static let tapsRequired = 7

    @Published private(set) var isUnlocked: Bool
    /// Transient hint mirroring Android's "You are now N steps away…".
    @Published private(set) var toast: String?

    private var taps = 0
    private var lapse: DispatchWorkItem?
    /// Guards against an older toast's timer clearing a newer toast.
    private var toastGeneration = 0

    private init() {
        isUnlocked = UserDefaults.standard.bool(forKey: Self.key)
    }

    /// Call once per tap on the version row.
    func registerTap() {
        guard !isUnlocked else {
            show("Developer mode is already on")
            return
        }
        taps += 1
        let remaining = Self.tapsRequired - taps
        if remaining <= 0 {
            unlock()
            return
        }
        // Android stays silent for the first couple of taps so the gesture
        // isn't discoverable by accident.
        if remaining <= 4 {
            Haptics.selection()
            show("You are now \(remaining) step\(remaining == 1 ? "" : "s") away from being a developer")
        }
        // Taps lapse if the user stops — prevents a slow accidental unlock.
        lapse?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.taps = 0 }
        lapse = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 3, execute: work)
    }

    func unlock() {
        isUnlocked = true
        UserDefaults.standard.set(true, forKey: Self.key)
        taps = 0
        Haptics.notify(.success)
        show("Developer mode unlocked")
    }

    func lock() {
        isUnlocked = false
        UserDefaults.standard.set(false, forKey: Self.key)
        taps = 0
        toast = nil
    }

    private func show(_ message: String) {
        toastGeneration += 1
        let gen = toastGeneration
        toast = message
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) { [weak self] in
            guard let self, self.toastGeneration == gen else { return }
            self.toast = nil
        }
    }
}

// MARK: - Reclaimable storage

/// The clearable buckets. `renders` is user data and is never touched by
/// "Free up space" — it only clears on an explicit, confirmed tap.
enum StorageBucket: String, CaseIterable, Identifiable {
    case caches, temp, pycache, logs, renders
    var id: String { rawValue }

    var title: String {
        switch self {
        case .caches:  return "Caches"
        case .temp:    return "Temporary files"
        case .pycache: return "Python bytecode"
        case .logs:    return "Log file"
        case .renders: return "Rendered outputs"
        }
    }

    var detail: String {
        switch self {
        case .caches:  return "Library/Caches — package index, thumbnails. Rebuilt on demand."
        case .temp:    return "tmp/ — LaTeX signals and scratch files from renders."
        case .pycache: return "__pycache__ in Documents. Regenerated on next import."
        case .logs:    return "Crash + render log. Clear after you've shared it."
        case .renders: return "Documents/ToolOutputs — your renders. Cannot be recovered."
        }
    }

    var icon: String {
        switch self {
        case .caches:  return "shippingbox"
        case .temp:    return "clock.badge.xmark"
        case .pycache: return "chevron.left.forwardslash.chevron.right"
        case .logs:    return "doc.text"
        case .renders: return "film.stack"
        }
    }

    /// True for buckets safe to wipe without losing anything the user made.
    var isSafeToAutoClear: Bool { self != .renders }
}

/// Measures and clears the buckets. All filesystem work happens off the
/// main actor — a Documents walk can cover thousands of render frames.
@MainActor
final class StorageScanner: ObservableObject {
    @Published private(set) var sizes: [String: Int64] = [:]
    @Published private(set) var scanning = false

    func scan() {
        scanning = true
        // CrashLogger is main-actor isolated, so resolve its URL here and
        // hand the plain value to the off-main workers.
        let logURL = CrashLogger.shared.fileURL
        Task { [weak self] in
            let result = await Self.measureAll(logURL: logURL)
            guard let self else { return }
            self.sizes = result
            self.scanning = false
        }
    }

    /// Bytes that "Free up space" would reclaim (safe buckets only).
    var reclaimable: Int64 {
        StorageBucket.allCases
            .filter(\.isSafeToAutoClear)
            .compactMap { sizes[$0.rawValue] }
            .reduce(0, +)
    }

    func size(_ bucket: StorageBucket) -> Int64? { sizes[bucket.rawValue] }

    func clear(_ bucket: StorageBucket) {
        let logURL = CrashLogger.shared.fileURL
        Task { [weak self] in
            await Self.wipe(bucket, logURL: logURL)
            self?.scan()
        }
    }

    /// Clears every safe bucket; never touches renders.
    func freeUpSpace() {
        let logURL = CrashLogger.shared.fileURL
        Task { [weak self] in
            for bucket in StorageBucket.allCases where bucket.isSafeToAutoClear {
                await Self.wipe(bucket, logURL: logURL)
            }
            self?.scan()
        }
    }

    // MARK: filesystem work (off-main)

    private static func measureAll(logURL: URL?) async -> [String: Int64] {
        await Task.detached(priority: .utility) { () -> [String: Int64] in
            var out: [String: Int64] = [:]
            for bucket in StorageBucket.allCases {
                out[bucket.rawValue] = measure(bucket, logURL: logURL)
            }
            return out
        }.value
    }

    private static func wipe(_ bucket: StorageBucket, logURL: URL?) async {
        await Task.detached(priority: .utility) { clear(bucket, logURL: logURL) }.value
    }

    private nonisolated static func measure(_ bucket: StorageBucket, logURL: URL?) -> Int64 {
        switch bucket {
        case .caches:  return directorySize(cachesDir)
        case .temp:    return directorySize(URL(fileURLWithPath: NSTemporaryDirectory()))
        case .pycache: return pycacheDirs().reduce(0) { $0 + directorySize($1) }
        case .logs:    return logURL.map(fileSize) ?? 0
        case .renders: return directorySize(rendersDir)
        }
    }

    private nonisolated static func clear(_ bucket: StorageBucket, logURL: URL?) {
        let fm = FileManager.default
        switch bucket {
        case .caches:  emptyContents(of: cachesDir)
        case .temp:    emptyContents(of: URL(fileURLWithPath: NSTemporaryDirectory()))
        case .pycache: pycacheDirs().forEach { try? fm.removeItem(at: $0) }
        case .logs:    if let url = logURL { try? Data().write(to: url) }
        case .renders: emptyContents(of: rendersDir)
        }
    }

    // MARK: paths

    private nonisolated static var cachesDir: URL? {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
    }
    private nonisolated static var documentsDir: URL? {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
    }
    private nonisolated static var rendersDir: URL? {
        documentsDir?.appendingPathComponent("ToolOutputs", isDirectory: true)
    }

    /// Every __pycache__ directory under Documents (user-installed packages
    /// and workspace scripts leave these behind).
    private nonisolated static func pycacheDirs() -> [URL] {
        guard let root = documentsDir,
              let walker = FileManager.default.enumerator(
                at: root,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles])
        else { return [] }
        var found: [URL] = []
        for case let url as URL in walker where url.lastPathComponent == "__pycache__" {
            found.append(url)
            walker.skipDescendants()
        }
        return found
    }

    // MARK: helpers

    private nonisolated static func fileSize(_ url: URL) -> Int64 {
        Int64((try? url.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? 0)
    }

    private nonisolated static func directorySize(_ dir: URL?) -> Int64 {
        guard let dir,
              let walker = FileManager.default.enumerator(
                at: dir,
                includingPropertiesForKeys: [.fileSizeKey, .isRegularFileKey],
                options: [])
        else { return 0 }
        var total: Int64 = 0
        for case let url as URL in walker {
            let v = try? url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
            guard v?.isRegularFile == true else { continue }
            total += Int64(v?.fileSize ?? 0)
        }
        return total
    }

    private nonisolated static func emptyContents(of dir: URL?) {
        guard let dir,
              let entries = try? FileManager.default.contentsOfDirectory(
                at: dir, includingPropertiesForKeys: nil)
        else { return }
        for url in entries { try? FileManager.default.removeItem(at: url) }
    }
}

// MARK: - The menu

struct DeveloperMenuView: View {
    @ObservedObject private var dev = DevMode.shared
    /// Pops this screen before developer mode is switched off — see
    /// lockSection for why the order matters.
    @Environment(\.dismiss) private var dismiss
    @StateObject private var info = SystemInfoModel()
    @StateObject private var ram = RAMSampler()
    @StateObject private var storage = StorageScanner()

    @State private var confirmBucket: StorageBucket?
    @State private var confirmFreeSpace = false

    var body: some View {
        Form {
            buildSection
            deviceSection
            memorySection
            pythonSection
            storageSection
            preferencesSection
            lockSection
        }
        .navigationTitle("Developer")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            info.refresh()
            storage.scan()
        }
        .confirmationDialog(
            confirmBucket.map { "Clear \($0.title.lowercased())?" } ?? "",
            isPresented: Binding(get: { confirmBucket != nil },
                                 set: { if !$0 { confirmBucket = nil } }),
            titleVisibility: .visible
        ) {
            Button("Clear", role: .destructive) {
                if let b = confirmBucket { storage.clear(b); Haptics.notify(.success) }
                confirmBucket = nil
            }
            Button("Cancel", role: .cancel) { confirmBucket = nil }
        } message: {
            Text(confirmBucket?.detail ?? "")
        }
        .confirmationDialog("Free up space?",
                            isPresented: $confirmFreeSpace,
                            titleVisibility: .visible) {
            Button("Free \(Self.bytes(storage.reclaimable))", role: .destructive) {
                storage.freeUpSpace()
                Haptics.notify(.success)
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Clears caches, temporary files and Python bytecode.\nYour renders are not touched.")
        }
    }

    // MARK: sections

    private var buildSection: some View {
        Section("Build") {
            LabeledContent("Version", value: SystemView.appVersion)
            // The build number is deliberately ONLY here — About shows just
            // the marketing version.
            LabeledContent("Build", value: SystemView.appBuild)
            LabeledContent("Bundle ID", value: Bundle.main.bundleIdentifier ?? "—")
                .font(.system(size: 12, design: .monospaced))
            LabeledContent("Built", value: Self.buildDate)
        }
    }

    private var deviceSection: some View {
        Section("Device") {
            LabeledContent("Model", value: info.modelIdentifier)
            LabeledContent("System", value: "iOS \(info.systemVersion)")
            LabeledContent("CPU cores", value: "\(info.cpuCores)")
            LabeledContent("Thermal state", value: SystemView.thermalLabel(info.thermal))
            LabeledContent("Low Power Mode", value: info.lowPower ? "On" : "Off")
        }
    }

    private var memorySection: some View {
        Section("Memory") {
            LabeledContent("Footprint", value: Self.bytes(Int64(ram.usedBytes)))
            LabeledContent("Session peak", value: Self.bytes(Int64(ram.peakBytes)))
            LabeledContent("Device total", value: Self.bytes(Int64(ram.totalBytes)))
            LabeledContent("Disk free", value: Self.bytes(info.diskFreeBytes))
        }
    }

    private var pythonSection: some View {
        Section("Python") {
            LabeledContent("Version", value: info.pythonVersion)
            LabeledContent("Stdlib", value: info.stdlibPresent ? "embedded · OK" : "MISSING")
            LabeledContent("Site-packages", value: "\(info.sitePackageDirs)")
        }
    }

    private var storageSection: some View {
        Section {
            ForEach(StorageBucket.allCases) { bucket in
                Button {
                    confirmBucket = bucket
                } label: {
                    HStack {
                        Label(bucket.title, systemImage: bucket.icon)
                            .foregroundStyle(bucket == .renders ? Color.red : Color.primary)
                        Spacer()
                        Text(storage.size(bucket).map(Self.bytes) ?? "…")
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
            }
            Button {
                confirmFreeSpace = true
            } label: {
                Label("Free up space (\(Self.bytes(storage.reclaimable)))",
                      systemImage: "sparkles")
            }
            .disabled(storage.scanning || storage.reclaimable == 0)
        } header: {
            Text("Storage & cache")
        } footer: {
            Text(storage.scanning
                 ? "Measuring…"
                 : "Tap an item to clear it. “Free up space” clears caches, temporary files and Python bytecode — never your renders.")
        }
    }

    /// Raw defaults dump — the fastest way to see why a render used the
    /// settings it did.
    private var preferencesSection: some View {
        Section("Raw preferences") {
            ForEach(Self.manimDefaults(), id: \.0) { key, value in
                LabeledContent(key) {
                    Text(value)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                .font(.system(size: 11, design: .monospaced))
            }
        }
    }

    private var lockSection: some View {
        Section {
            Button(role: .destructive) {
                Haptics.selection()
                // Order matters. This view is the destination of a
                // NavigationLink that Settings only renders `if
                // dev.isUnlocked`, so calling lock() first tears the link
                // out of the hierarchy while its destination is still on
                // screen — the pop breaks and the button looks dead. Pop
                // first, flip the flag once the animation has finished.
                dismiss()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                    DevMode.shared.lock()
                }
            } label: {
                Label("Turn off developer mode", systemImage: "lock")
            }
        } footer: {
            Text("Hides this menu again. Tap the version row seven times to bring it back.")
        }
    }

    // MARK: helpers

    nonisolated static func bytes(_ n: Int64) -> String { SystemView.bytes(n) }

    /// Executable timestamp — a reliable "when was this built".
    private static var buildDate: String {
        guard let exe = Bundle.main.executableURL,
              let date = (try? exe.resourceValues(forKeys: [.contentModificationDateKey]))?
                  .contentModificationDate
        else { return "—" }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        return f.string(from: date)
    }

    /// Every manim_* preference, sorted — the app's whole tunable surface.
    private static func manimDefaults() -> [(String, String)] {
        UserDefaults.standard.dictionaryRepresentation()
            .filter { $0.key.hasPrefix("manim_") }
            .map { ($0.key, String(describing: $0.value)) }
            .sorted { $0.0 < $1.0 }
    }
}
