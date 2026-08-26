// RenderMemoryGuard.swift — refuse-to-crash check before a render starts.
//
// Jetsam OOM is this app's signature failure: a 1440p/4K render climbs past
// the per-app memory limit and iOS kills the process mid-encode, losing the
// entire run. The RAM HUD only *reports* that while it happens — by then
// the work is already lost. This estimates the peak footprint BEFORE the
// render starts and offers a quality that actually fits.
//
// The numbers are heuristics, deliberately conservative, and easy to tune:
// they only decide whether to show a warning the user can override.
import Foundation
import UIKit

enum RenderMemoryGuard {

    /// What we'd warn about. `quick` remembers which render to resume.
    struct Warning: Identifiable {
        let id = UUID()
        let quick: Bool
        let quality: String
        let width: Int
        let height: Int
        let needBytes: UInt64
        let availableBytes: UInt64
        /// Highest quality that fits right now, or nil if nothing does.
        let saferQuality: String?
    }

    /// Quality ladder, high → low (matches ControlsSidebar's picker).
    static let ladder = ["8K", "4K", "1440p", "1080p", "720p", "480p"]

    /// manim's preset pixel dimensions.
    static func pixelSize(forQuality label: String) -> (w: Int, h: Int) {
        switch label {
        case "480p":  return (854, 480)
        case "720p":  return (1280, 720)
        case "1080p": return (1920, 1080)
        case "1440p": return (2560, 1440)
        case "4K":    return (3840, 2160)
        case "8K":    return (7680, 4320)
        case "Custom":
            let d = UserDefaults.standard
            let w = d.integer(forKey: "manim_custom_width")
            let h = d.integer(forKey: "manim_custom_height")
            return (w > 0 ? w : 1080, h > 0 ? h : 1920)
        default:      return (1920, 1080)
        }
    }

    /// Interpreter + manim + fonts before any frame work — the floor cost
    /// of starting a render at all.
    static let baselineBytes: UInt64 = 420 * 1024 * 1024

    /// How many full RGBA frames can be alive at once.
    ///
    /// Not a guess: python-ios-lib's scene_file_writer caps the encoder
    /// hand-off queue at `Queue(maxsize=32)` — a fixed frame COUNT. Its own
    /// comment budgets "≈ 256 MB", which is only true at 1080p (~8 MB a
    /// frame); the same 32 slots hold ~4 GB of 8K frames (126 MB each).
    /// Plus the cairo surface and manim's working copy → 34.
    static let liveFrames: UInt64 = 34

    /// Rough peak footprint for one render: the frame queue is what
    /// actually decides whether a high-resolution render survives.
    static func estimatedBytes(w: Int, h: Int) -> UInt64 {
        let frame = UInt64(max(w, 1)) * UInt64(max(h, 1)) * 4
        return baselineBytes + frame * liveFrames
    }

    /// iOS jetsams a single app well before device RAM is exhausted — the
    /// RAM HUD already warns from ~45%. Treat 55% of physical memory as the
    /// practical ceiling for this process.
    static var budgetBytes: UInt64 {
        UInt64(Double(ProcessInfo.processInfo.physicalMemory) * 0.55)
    }

    /// Headroom left for a render right now (budget minus what we already
    /// hold — an editor full of history and a warm Python leave less).
    static var availableBytes: UInt64 {
        let used = RAMSampler.appFootprint() ?? 0
        let budget = budgetBytes
        return used >= budget ? 0 : budget - used
    }

    /// Highest ladder entry that fits in the current headroom.
    static func safestQuality() -> String? {
        let avail = availableBytes
        return ladder.first { q in
            let s = pixelSize(forQuality: q)
            return estimatedBytes(w: s.w, h: s.h) <= avail
        }
    }

    /// nil → safe to render. Non-nil → show the warning.
    static func check(quality: String, quick: Bool) -> Warning? {
        let size = pixelSize(forQuality: quality)
        let need = estimatedBytes(w: size.w, h: size.h)
        let avail = availableBytes
        guard need > avail else { return nil }
        let safer = safestQuality()
        return Warning(quick: quick,
                       quality: quality,
                       width: size.w, height: size.h,
                       needBytes: need,
                       availableBytes: avail,
                       // Don't offer what we were already asked to render.
                       saferQuality: safer == quality ? nil : safer)
    }

    /// Human-readable size, matching the System tab's formatting.
    static func bytes(_ n: UInt64) -> String { SystemView.bytes(Int64(n)) }
}
