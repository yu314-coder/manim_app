// SystemView.swift — live system diagnostics.
//
// Was: a flat grid of twelve hardcoded strings ("Apple GPU", "Ready",
// "Documents/") behind a Refresh button that did nothing, with Disk Space
// permanently showing "—". Every value is now READ FROM THE DEVICE, so the
// tab is usable for diagnosing the render/OOM problems this app actually
// hits instead of being decoration.
//
// Cheap-on-appear by design: the Packages tab already taught us not to do
// heavy work when a tab opens (see "Packages tab opens instantly"). So the
// synchronous pass is only ProcessInfo + a couple of stat() calls, and the
// one expensive item (walking ToolOutputs to size the renders) runs off the
// main actor and fills in when it lands. No Python is started here.
import SwiftUI
import Combine
import Darwin
import UIKit

// MARK: - Snapshot model

/// One-shot device/app facts, re-gathered on appear and on Refresh.
/// Deliberately separate from RAMSampler, which polls continuously.
@MainActor
final class SystemInfoModel: ObservableObject {

    // Device
    @Published var modelIdentifier = "—"
    @Published var systemVersion   = "—"
    @Published var cpuCores        = 0
    @Published var totalRAMBytes: UInt64 = 0
    @Published var thermal: ProcessInfo.ThermalState = .nominal
    @Published var lowPower        = false

    // Storage
    @Published var diskFreeBytes:  Int64 = 0
    @Published var diskTotalBytes: Int64 = 0
    /// Filled asynchronously — nil until the ToolOutputs walk finishes.
    @Published var rendersBytes: Int64?
    @Published var rendersCount: Int?

    // Python environment
    @Published var pythonVersion   = "—"
    @Published var stdlibPresent   = false
    @Published var sitePackageDirs = 0

    private var walkTask: Task<Void, Never>?

    init() { refresh() }

    func refresh() {
        let pi = ProcessInfo.processInfo
        modelIdentifier = Self.deviceModelIdentifier()
        systemVersion   = UIDevice.current.systemVersion
        cpuCores        = pi.processorCount
        totalRAMBytes   = pi.physicalMemory
        thermal         = pi.thermalState
        lowPower        = pi.isLowPowerModeEnabled

        let (free, total) = Self.diskCapacity()
        diskFreeBytes  = free
        diskTotalBytes = total

        let env = Self.pythonEnvironment()
        pythonVersion   = env.version
        stdlibPresent   = env.stdlib
        sitePackageDirs = env.siteDirs

        // Expensive: size the render output dir off the main actor.
        rendersBytes = nil
        rendersCount = nil
        walkTask?.cancel()
        walkTask = Task { [weak self] in
            let (bytes, count) = await Self.measureRenders()
            guard !Task.isCancelled else { return }
            await MainActor.run {
                self?.rendersBytes = bytes
                self?.rendersCount = count
            }
        }
    }

    // MARK: gathering

    /// e.g. "iPad14,5" — the hardware identifier, more useful than
    /// UIDevice.model ("iPad") when chasing a device-specific OOM.
    private static func deviceModelIdentifier() -> String {
        var sys = utsname()
        uname(&sys)
        let id = withUnsafeBytes(of: &sys.machine) { raw -> String in
            String(decoding: raw.prefix { $0 != 0 }, as: UTF8.self)
        }
        return id.isEmpty ? UIDevice.current.model : id
    }

    /// Free / total for the volume holding the app container.
    /// `volumeAvailableCapacityForImportantUsage` is what iOS actually lets
    /// an app write (it accounts for purgeable space), so it matches what a
    /// render will really have available.
    private static func diskCapacity() -> (free: Int64, total: Int64) {
        let url = URL(fileURLWithPath: NSHomeDirectory())
        let vals = try? url.resourceValues(forKeys: [
            .volumeAvailableCapacityForImportantUsageKey,
            .volumeTotalCapacityKey,
        ])
        let free  = vals?.volumeAvailableCapacityForImportantUsage ?? 0
        let total = Int64(vals?.volumeTotalCapacity ?? 0)
        return (free, total)
    }

    /// Derive the embedded CPython version from the bundle instead of
    /// hardcoding it: lib-dynload holds files like
    /// `_ssl.cpython-314-iphoneos.so`, so "314" → "3.14". If the layout ever
    /// changes the tab says "unknown" rather than confidently lying.
    private static func pythonEnvironment()
    -> (version: String, stdlib: Bool, siteDirs: Int) {
        let fm = FileManager.default
        let bundle = Bundle.main.bundleURL
        let stdlib = bundle.appendingPathComponent("python-stdlib", isDirectory: true)
        let hasStdlib = fm.fileExists(atPath: stdlib.appendingPathComponent("os.py").path)

        var version = "unknown"
        let dynload = stdlib.appendingPathComponent("lib-dynload", isDirectory: true)
        if let names = try? fm.contentsOfDirectory(atPath: dynload.path) {
            for name in names {
                guard let r = name.range(of: "cpython-") else { continue }
                let digits = name[r.upperBound...].prefix { $0.isNumber }
                if digits.count >= 2 {
                    version = "\(digits.prefix(1)).\(digits.dropFirst())"
                    break
                }
            }
        }

        // site-packages roots the runtime puts on sys.path: the consolidated
        // app_packages dir plus any remaining python-ios-lib_*.bundle.
        var siteDirs = 0
        if fm.fileExists(atPath: bundle.appendingPathComponent("app_packages/site-packages").path) {
            siteDirs += 1
        }
        if let entries = try? fm.contentsOfDirectory(atPath: bundle.path) {
            siteDirs += entries.filter {
                $0.hasPrefix("python-ios-lib_") && $0.hasSuffix(".bundle")
            }.count
        }
        return (version, hasStdlib, siteDirs)
    }

    /// Total bytes + file count under Documents/ToolOutputs (where renders
    /// land). Runs off the main actor — this can be thousands of frames.
    private static func measureRenders() async -> (Int64, Int) {
        await Task.detached(priority: .utility) { walkRenders() }.value
    }

    /// Synchronous on purpose: a directory enumerator's iterator is
    /// unavailable from async contexts (an error in Swift 6), so the walk
    /// lives in a plain function that the detached task calls.
    private nonisolated static func walkRenders() -> (Int64, Int) {
        guard let dir = FileManager.default
            .urls(for: .documentDirectory, in: .userDomainMask).first?
            .appendingPathComponent("ToolOutputs", isDirectory: true),
              let walker = FileManager.default.enumerator(
                at: dir,
                includingPropertiesForKeys: [.fileSizeKey, .isRegularFileKey],
                options: [.skipsHiddenFiles])
        else { return (0, 0) }

        var bytes: Int64 = 0
        var count = 0
        for case let url as URL in walker {
            let v = try? url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
            guard v?.isRegularFile == true else { continue }
            bytes += Int64(v?.fileSize ?? 0)
            count += 1
        }
        return (bytes, count)
    }

    // MARK: diagnostics report

    /// Plain-text dump for bug reports — the reason this tab exists.
    func diagnosticsReport(usedRAM: UInt64, peakRAM: UInt64) -> String {
        let b = Bundle.main.infoDictionary
        let version = b?["CFBundleShortVersionString"] as? String ?? "?"
        // The build number is developer-only everywhere else in the UI, so
        // the report shows it only when developer mode is on — a normal
        // user's copied report reads "ManimStudio 1.4".
        let build   = DevMode.shared.isUnlocked
            ? " (\(b?["CFBundleVersion"] as? String ?? "?"))"
            : ""
        let d = UserDefaults.standard
        func f(_ n: Int64) -> String { SystemView.bytes(n) }

        return """
        ManimStudio \(version)\(build)
        Device      \(modelIdentifier) · iOS \(systemVersion)
        CPU         \(cpuCores) cores
        RAM         \(SystemView.bytes(Int64(usedRAM))) used · \
        peak \(SystemView.bytes(Int64(peakRAM))) · \
        \(SystemView.bytes(Int64(totalRAMBytes))) total
        Thermal     \(SystemView.thermalLabel(thermal))\(lowPower ? " · Low Power ON" : "")
        Disk        \(f(diskFreeBytes)) free of \(f(diskTotalBytes))
        Renders     \(rendersCount.map(String.init) ?? "?") files · \
        \(rendersBytes.map(f) ?? "?")
        Python      \(pythonVersion) · stdlib \(stdlibPresent ? "OK" : "MISSING") · \
        \(sitePackageDirs) site dirs
        GPU accel   \(d.object(forKey: "manim_gpu_on") as? Bool ?? true ? "on" : "off")
        Render      \(d.string(forKey: "manim_final_quality") ?? "1080p") @ \
        \(d.integer(forKey: "manim_final_fps") == 0 ? 30 : d.integer(forKey: "manim_final_fps"))fps · \
        \(d.string(forKey: "manim_format") ?? "mp4")
        """
    }
}

// MARK: - View

struct SystemView: View {
    @ObservedObject private var theme = ThemeManager.shared   // accent → live retint
    @StateObject private var info = SystemInfoModel()
    @StateObject private var ram  = RAMSampler()

    @AppStorage("manim_gpu_on")        private var gpuOn = true
    @AppStorage("manim_final_quality") private var finalQuality = "1080p"
    @AppStorage("manim_final_fps")     private var finalFPS = 30
    @AppStorage("manim_format")        private var format = "mp4"

    @State private var copied = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                liveSection
                deviceSection
                pythonSection
                renderSection
                pathsSection
            }
            .padding(16)
        }
        .background(Theme.bgPrimary)
        // Cheap re-read whenever the tab comes back into view.
        .onAppear { info.refresh() }
    }

    // MARK: header

    private var header: some View {
        HStack(spacing: 10) {
            Text("System").font(.system(size: 22, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            copyButton
            refreshButton
        }
    }

    private var refreshButton: some View {
        Button {
            Haptics.selection()
            info.refresh()
        } label: {
            HStack(spacing: 5) {
                Image(systemName: "arrow.clockwise")
                Text("Refresh")
            }
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(.white)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Capsule().fill(Theme.signatureGradient))
        }
        .buttonStyle(.plain)
    }

    /// Copies a plain-text diagnostics report — what you actually want when
    /// filing "my render died on device".
    private var copyButton: some View {
        Button {
            UIPasteboard.general.string = info.diagnosticsReport(
                usedRAM: ram.usedBytes, peakRAM: ram.peakBytes)
            Haptics.notify(.success)
            withAnimation { copied = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
                withAnimation { copied = false }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: copied ? "checkmark" : "doc.on.doc")
                Text(copied ? "Copied" : "Copy report")
            }
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(copied ? Theme.green : Theme.textSecondary)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Capsule().fill(Theme.bgTertiary))
            .overlay(Capsule().stroke(Theme.borderSubtle, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // MARK: live

    private var ramPct: Double {
        guard ram.totalBytes > 0 else { return 0 }
        return Double(ram.usedBytes) / Double(ram.totalBytes)
    }
    /// Same amber→red jetsam scale the RAM HUD uses, so both surfaces agree.
    private var ramTint: Color {
        switch ramPct * 100 {
        case ..<25: return Theme.green
        case ..<45: return Theme.amber
        default:    return Theme.red
        }
    }
    private var diskPct: Double {
        guard info.diskTotalBytes > 0 else { return 0 }
        return Double(info.diskTotalBytes - info.diskFreeBytes) / Double(info.diskTotalBytes)
    }
    private var diskTint: Color {
        let freeFrac = info.diskTotalBytes > 0
            ? Double(info.diskFreeBytes) / Double(info.diskTotalBytes) : 1
        switch freeFrac {
        case ..<0.05: return Theme.red
        case ..<0.15: return Theme.amber
        default:      return Theme.green
        }
    }

    private var liveSection: some View {
        section("Live", icon: "waveform.path.ecg") {
            meter(label: "Memory",
                  detail: "\(Self.bytes(Int64(ram.usedBytes))) of \(Self.bytes(Int64(ram.totalBytes)))",
                  fraction: ramPct, tint: ramTint)
            Text("peak \(Self.bytes(Int64(ram.peakBytes))) this session")
                .font(.system(size: 9.5, design: .monospaced))
                .foregroundStyle(Theme.textDim)

            Divider().overlay(Theme.borderSubtle).padding(.vertical, 2)

            meter(label: "Storage",
                  detail: "\(Self.bytes(info.diskFreeBytes)) free of \(Self.bytes(info.diskTotalBytes))",
                  fraction: diskPct, tint: diskTint)

            HStack(spacing: 8) {
                statusChip(Self.thermalLabel(info.thermal),
                           icon: "thermometer.medium",
                           tint: Self.thermalTint(info.thermal))
                if info.lowPower {
                    statusChip("Low Power", icon: "battery.25", tint: Theme.amber)
                }
                Spacer()
            }
            .padding(.top, 2)
        }
    }

    // MARK: device / python / render / paths

    private var deviceSection: some View {
        section("Device", icon: "ipad") {
            row("Model", info.modelIdentifier)
            row("System", "iOS / iPadOS \(info.systemVersion)")
            row("CPU", "\(info.cpuCores) cores")
            row("Total RAM", Self.bytes(Int64(info.totalRAMBytes)))
            // Marketing version only — the build number lives in the
            // developer menu (Settings → About → tap Version 7×).
            row("App", Self.appVersion)
        }
    }

    private var pythonSection: some View {
        section("Python environment", icon: "chevron.left.forwardslash.chevron.right") {
            row("Python", info.pythonVersion, tint: info.pythonVersion == "unknown" ? Theme.amber : nil)
            row("Stdlib", info.stdlibPresent ? "embedded · OK" : "MISSING",
                tint: info.stdlibPresent ? Theme.green : Theme.red)
            row("Site-packages", "\(info.sitePackageDirs) \(info.sitePackageDirs == 1 ? "dir" : "dirs")")
            row("Venv", "embedded (no venv)")
            row("FFmpeg", "PyAV native")
            row("LaTeX", "busytex")
        }
    }

    private var renderSection: some View {
        section("Rendering", icon: "film") {
            row("GPU acceleration", gpuOn ? "CairoMetal · on" : "software · off",
                tint: gpuOn ? Theme.green : Theme.amber)
            row("Final quality", finalQuality)
            row("Frame rate", "\(finalFPS) fps")
            row("Format", format)
            row("Renders on disk", info.rendersBytes.map {
                "\(info.rendersCount ?? 0) files · \(Self.bytes($0))"
            } ?? "measuring…")
            row("Render log", "PTY")
        }
    }

    private var pathsSection: some View {
        section("Paths", icon: "folder") {
            pathRow("Documents", Self.documentsPath)
            pathRow("Renders", Self.documentsPath + "/ToolOutputs")
            pathRow("Bundle", Bundle.main.bundleURL.path)
        }
    }

    // MARK: building blocks

    @ViewBuilder
    private func section<C: View>(_ title: String, icon: String,
                                  @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 11)).foregroundStyle(Theme.accentPrimary)
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .semibold)).tracking(0.7)
                    .foregroundStyle(Theme.textDim)
            }
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard(padding: 14)
    }

    @ViewBuilder
    private func row(_ label: String, _ value: String, tint: Color? = nil) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
            Spacer(minLength: 12)
            Text(value)
                .font(.system(size: 12, weight: .medium, design: .monospaced))
                .foregroundStyle(tint ?? Theme.textPrimary)
                .multilineTextAlignment(.trailing)
        }
        .padding(.vertical, 1)
    }

    /// Long paths get their own line + tap-to-copy (they never fit inline).
    @ViewBuilder
    private func pathRow(_ label: String, _ path: String) -> some View {
        Button {
            UIPasteboard.general.string = path
            Haptics.selection()
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Text(label)
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.textSecondary)
                    Image(systemName: "doc.on.doc")
                        .font(.system(size: 8.5))
                        .foregroundStyle(Theme.textDim)
                    Spacer()
                }
                Text(path)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textDim)
                    .lineLimit(2)
                    .truncationMode(.middle)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .buttonStyle(.plain)
        .padding(.vertical, 1)
    }

    @ViewBuilder
    private func meter(label: String, detail: String,
                       fraction: Double, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(label)
                    .font(.system(size: 12)).foregroundStyle(Theme.textSecondary)
                Spacer()
                Text(String(format: "%.0f%%", fraction * 100))
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    .foregroundStyle(tint)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.bgTertiary)
                    Capsule().fill(tint)
                        .frame(width: max(0, min(1, fraction)) * geo.size.width)
                }
            }
            .frame(height: 6)
            Text(detail)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Theme.textDim)
        }
    }

    @ViewBuilder
    private func statusChip(_ text: String, icon: String, tint: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 9, weight: .semibold))
            Text(text).font(.system(size: 10, weight: .medium))
        }
        .foregroundStyle(tint)
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(Capsule().fill(tint.opacity(0.14)))
    }

    // MARK: formatting helpers

    nonisolated static var appVersion: String {
        (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "—"
    }
    nonisolated static var appBuild: String {
        (Bundle.main.infoDictionary?["CFBundleVersion"] as? String) ?? "—"
    }
    nonisolated static var documentsPath: String {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
            .first?.path ?? "—"
    }

    /// Byte formatting shared by the cards and the copyable report.
    nonisolated static func bytes(_ n: Int64) -> String {
        guard n > 0 else { return "0 MB" }
        let f = ByteCountFormatter()
        f.countStyle = .file
        f.allowedUnits = n < 1_000_000_000 ? [.useMB] : [.useGB]
        return f.string(fromByteCount: n)
    }

    nonisolated static func thermalLabel(_ s: ProcessInfo.ThermalState) -> String {
        switch s {
        case .nominal:  return "Thermals nominal"
        case .fair:     return "Thermals fair"
        case .serious:  return "Thermals serious"
        case .critical: return "Thermals critical"
        @unknown default: return "Thermals unknown"
        }
    }

    /// Returns Theme colours (main-actor state), so this one stays isolated.
    static func thermalTint(_ s: ProcessInfo.ThermalState) -> Color {
        switch s {
        case .nominal:  return Theme.green
        case .fair:     return Theme.green
        case .serious:  return Theme.amber
        case .critical: return Theme.red
        @unknown default: return Theme.textDim
        }
    }
}
