// RAMMonitorView.swift — live memory HUD (iPad only).
//
// A small floating panel in the bottom-right that samples the app's
// physical-memory footprint once a second and plots a rolling graph of
// used RAM against the device's total RAM. Intended as a debugging aid
// for the jetsam / out-of-memory crashes that only reproduce on device
// (the Simulator has a much larger ceiling). `phys_footprint` is the
// same accounting iOS jetsam uses and roughly matches Xcode's memory
// gauge, so the number here lines up with what Xcode shows.
//
// Shown only in the regular horizontal size class (iPad). On iPhone the
// screen is too small to spare the corner, and the crash repro is an
// iPad-RAM-ceiling issue anyway.

import SwiftUI
import Combine
import Darwin

// MARK: - Sampler

/// Polls memory every second and keeps a rolling window of samples.
final class RAMSampler: ObservableObject {
    /// Most recent app footprint, in bytes.
    @Published private(set) var usedBytes: UInt64 = 0
    /// Rolling history of footprints (bytes), oldest → newest.
    @Published private(set) var history: [Double] = []
    /// Peak footprint seen this session, in bytes.
    @Published private(set) var peakBytes: UInt64 = 0

    /// Device total physical RAM, in bytes (constant for the session).
    let totalBytes: UInt64 = ProcessInfo.processInfo.physicalMemory

    private var timer: Timer?
    private let windowSize = 90          // 90 s of history at 1 Hz

    init() {
        sample()                          // immediate first point
        let t = Timer(timeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.sample()
        }
        // .common so it keeps firing during scroll / interaction.
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    deinit { timer?.invalidate() }

    private func sample() {
        let used = Self.appFootprint() ?? usedBytes
        usedBytes = used
        if used > peakBytes { peakBytes = used }
        history.append(Double(used))
        if history.count > windowSize {
            history.removeFirst(history.count - windowSize)
        }
    }

    /// App physical-memory footprint via TASK_VM_INFO.phys_footprint —
    /// the metric iOS jetsam uses to decide what to kill.
    static func appFootprint() -> UInt64? {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
        let kr = withUnsafeMutablePointer(to: &info) { ptr in
            ptr.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        guard kr == KERN_SUCCESS else { return nil }
        return info.phys_footprint
    }
}

// MARK: - HUD

struct RAMMonitorView: View {
    @StateObject private var sampler = RAMSampler()
    @Environment(\.horizontalSizeClass) private var hSizeClass

    private static let mb = 1024.0 * 1024.0
    private static let gb = 1024.0 * 1024.0 * 1024.0

    var body: some View {
        // iPad / regular width only.
        if hSizeClass == .regular {
            panel
                .frame(width: 196)
                .padding(.trailing, 12)
                .padding(.bottom, 12)
        }
    }

    private var usedMB: Double { Double(sampler.usedBytes) / Self.mb }
    private var totalGB: Double { Double(sampler.totalBytes) / Self.gb }
    private var peakMB: Double { Double(sampler.peakBytes) / Self.mb }
    private var pct: Double {
        guard sampler.totalBytes > 0 else { return 0 }
        return Double(sampler.usedBytes) / Double(sampler.totalBytes) * 100
    }

    /// Tint shifts amber→red as the footprint climbs toward the rough
    /// jetsam neighbourhood (iOS kills apps well before 100% of device
    /// RAM — typically once a single app passes ~50-60% on smaller
    /// devices — so we warn early).
    private var tint: Color {
        switch pct {
        case ..<25: return Theme.green
        case ..<45: return Theme.amber
        default:    return Theme.red
        }
    }

    private var panel: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "memorychip")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(tint)
                Text("RAM")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .tracking(1.5)
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                Text(String(format: "%.0f%%", pct))
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(tint)
            }

            graph
                .frame(height: 40)

            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(String(format: "%.0f", usedMB))
                    .font(.system(size: 16, weight: .bold, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                Text("MB")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textDim)
                Spacer()
                Text(String(format: "/ %.1f GB", totalGB))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textDim)
            }
            Text(String(format: "peak %.0f MB", peakMB))
                .font(.system(size: 8.5, design: .monospaced))
                .foregroundStyle(Theme.textDim)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.black.opacity(0.82))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Theme.borderSubtle, lineWidth: 1))
        )
        .shadow(color: .black.opacity(0.4), radius: 10, y: 3)
    }

    /// Rolling line graph. Y-axis is autoscaled to the peak sample (with
    /// headroom) so small fluctuations stay visible — the absolute
    /// vs-device-total context is in the numeric readout below. A faint
    /// dashed line marks the peak.
    private var graph: some View {
        Canvas { ctx, size in
            let samples = sampler.history
            guard samples.count > 1 else { return }
            let maxV = max(samples.max() ?? 1, 1) * 1.15
            let n = samples.count
            let dx = size.width / CGFloat(max(n - 1, 1))

            func pt(_ i: Int) -> CGPoint {
                let v = samples[i]
                let y = size.height - CGFloat(v / maxV) * size.height
                return CGPoint(x: CGFloat(i) * dx, y: y)
            }

            // Filled area under the curve.
            var area = Path()
            area.move(to: CGPoint(x: 0, y: size.height))
            for i in 0..<n { area.addLine(to: pt(i)) }
            area.addLine(to: CGPoint(x: CGFloat(n - 1) * dx, y: size.height))
            area.closeSubpath()
            ctx.fill(area, with: .linearGradient(
                Gradient(colors: [tint.opacity(0.35), tint.opacity(0.02)]),
                startPoint: .zero, endPoint: CGPoint(x: 0, y: size.height)))

            // The line itself.
            var line = Path()
            line.move(to: pt(0))
            for i in 1..<n { line.addLine(to: pt(i)) }
            ctx.stroke(line, with: .color(tint),
                       style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))

            // Newest-value dot.
            let last = pt(n - 1)
            ctx.fill(Path(ellipseIn: CGRect(x: last.x - 2.5, y: last.y - 2.5,
                                            width: 5, height: 5)),
                     with: .color(tint))
        }
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.white.opacity(0.03))
        )
        .accessibilityHidden(true)
    }
}

// MARK: - Compact inline RAM graph (iPhone header)

/// A small live RAM sparkline + MB readout sized to sit INLINE in the
/// compact (iPhone) header, between the scene picker and the Run button.
/// iPhone has no room for the floating iPad HUD, so this is the phone's
/// equivalent. Reuses `RAMSampler` and the same amber→red jetsam tint.
struct CompactRAMGraph: View {
    @StateObject private var sampler = RAMSampler()
    private static let mb = 1024.0 * 1024.0

    private var usedMB: Double { Double(sampler.usedBytes) / Self.mb }
    private var pct: Double {
        guard sampler.totalBytes > 0 else { return 0 }
        return Double(sampler.usedBytes) / Double(sampler.totalBytes) * 100
    }
    private var tint: Color {
        switch pct {
        case ..<25: return Theme.green
        case ..<45: return Theme.amber
        default:    return Theme.red
        }
    }

    var body: some View {
        HStack(spacing: 5) {
            sparkline.frame(width: 34, height: 16)
            Text(String(format: "%.0f", usedMB))
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(tint)
                .monospacedDigit()
        }
        .padding(.horizontal, 7).padding(.vertical, 4)
        .background(
            Capsule().fill(Theme.bgTertiary)
                .overlay(Capsule().stroke(Theme.borderSubtle, lineWidth: 1))
        )
        .fixedSize()
        .accessibilityLabel("Memory \(Int(usedMB)) megabytes, \(Int(pct)) percent")
    }

    private var sparkline: some View {
        Canvas { ctx, size in
            let s = sampler.history
            guard s.count > 1 else { return }
            let maxV = max(s.max() ?? 1, 1) * 1.15
            let n = s.count
            let dx = size.width / CGFloat(max(n - 1, 1))
            func pt(_ i: Int) -> CGPoint {
                CGPoint(x: CGFloat(i) * dx,
                        y: size.height - CGFloat(s[i] / maxV) * size.height)
            }
            var area = Path()
            area.move(to: CGPoint(x: 0, y: size.height))
            for i in 0..<n { area.addLine(to: pt(i)) }
            area.addLine(to: CGPoint(x: CGFloat(n - 1) * dx, y: size.height))
            area.closeSubpath()
            ctx.fill(area, with: .linearGradient(
                Gradient(colors: [tint.opacity(0.35), tint.opacity(0.02)]),
                startPoint: .zero, endPoint: CGPoint(x: 0, y: size.height)))
            var line = Path()
            line.move(to: pt(0))
            for i in 1..<n { line.addLine(to: pt(i)) }
            ctx.stroke(line, with: .color(tint),
                       style: StrokeStyle(lineWidth: 1.3, lineCap: .round, lineJoin: .round))
            let last = pt(n - 1)
            ctx.fill(Path(ellipseIn: CGRect(x: last.x - 2, y: last.y - 2, width: 4, height: 4)),
                     with: .color(tint))
        }
        .accessibilityHidden(true)
    }
}
