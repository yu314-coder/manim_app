// RenderResolution.swift — the quality ladder and its pixel dimensions.
//
// This was RenderMemoryGuard, which estimated peak footprint before a render
// and offered a lower quality when it looked too big. That estimate modelled
// the encoder hand-off queue as 32 full-resolution frames — true when it was
// written, but python-ios-lib 709ae8dd made the queue byte-bounded, so 8K now
// queues 2 frames rather than 32. The guard was over-predicting by roughly 4x
// and warning about renders that complete comfortably: 8K at 120 fps measured
// under 2 GB on an iPad Air M3.
//
// A pre-flight that refuses work the device can actually do is worse than no
// pre-flight, and the memory watchdog in the render path is the real safety
// net either way, so the estimate is gone and only the resolution table — the
// part other code actually needs — remains.
import Foundation

enum RenderResolution {

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
}
