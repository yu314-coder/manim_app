// RenderLibrary.swift — the list of past renders, shared by the Present
// cover and anything else that needs to offer "play an earlier clip".
//
// Renders land in Documents/ToolOutputs/ (same tree HistoryView lists).
// This is the video-only view of that tree, newest first, plus a
// thumbnail cache.
//
// Thumbnailing is deliberately SERIAL. AVAssetImageGenerator decodes at
// the asset's native resolution regardless of `maximumSize` — that cap
// only bounds the image it hands back. With 16K on the quality ladder a
// single decoded frame is ~506 MB, so generating a screenful of
// thumbnails concurrently would be several gigabytes in flight and a
// certain jetsam. Funnelling every request through one actor means at
// most one full-size frame exists at a time.
import Foundation
import AVFoundation
import UIKit
import Combine

// MARK: - Item

struct RenderItem: Identifiable, Hashable {
    let url: URL
    let modified: Date
    let size: Int64

    var id: URL { url }
    var name: String { url.lastPathComponent }

    /// "Today 14:32 · 12.4 MB" — the caption under a filmstrip thumbnail.
    var subtitle: String {
        let d = DateFormatter()
        if Calendar.current.isDateInToday(modified) {
            d.dateFormat = "'Today' HH:mm"
        } else if Calendar.current.isDateInYesterday(modified) {
            d.dateFormat = "'Yesterday' HH:mm"
        } else {
            d.dateFormat = "d MMM HH:mm"
        }
        let bytes = ByteCountFormatter.string(fromByteCount: size, countStyle: .file)
        return "\(d.string(from: modified)) · \(bytes)"
    }
}

// MARK: - Store

/// Newest-first list of every playable render on disk. A singleton so the
/// header (which decides whether to show the Present button) and the
/// presentation cover (which lists them) agree without rescanning twice.
final class RenderLibraryStore: ObservableObject {
    static let shared = RenderLibraryStore()

    @Published private(set) var videos: [RenderItem] = []
    private var scanning = false

    private init() {}

    // `nonisolated` so the off-main scan below can read them: with
    // SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor these would otherwise be
    // MainActor-bound, which is a warning today and an error under the
    // Swift 6 language mode. Both are immutable/Sendable, so there is
    // nothing to race on.
    nonisolated static let videoExtensions: Set<String> = ["mp4", "mov", "m4v"]

    nonisolated static var outputDir: URL? {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
            .first?.appendingPathComponent("ToolOutputs", isDirectory: true)
    }

    /// Rescan off the main thread. Cheap enough to call on every appear.
    func refresh() {
        guard !scanning else { return }
        scanning = true
        Task.detached(priority: .utility) {
            let found = Self.scan()
            await MainActor.run {
                self.videos = found
                self.scanning = false
            }
        }
    }

    /// `nonisolated` because FileManager's enumerator is not usable from an
    /// actor-isolated async context — it has to run on a plain thread.
    nonisolated static func scan() -> [RenderItem] {
        guard let dir = outputDir,
              let walker = FileManager.default.enumerator(
                at: dir,
                includingPropertiesForKeys: [.contentModificationDateKey, .fileSizeKey,
                                             .isRegularFileKey],
                options: [.skipsHiddenFiles])
        else { return [] }

        var found: [RenderItem] = []
        for case let url as URL in walker {
            // Skip manim's per-animation scratch files. A 30-animation
            // render leaves dozens of `uncached_NNNNN.mp4` fragments next
            // to the real output; listing them would bury the finished
            // clip the user actually wants to present.
            if url.pathComponents.contains("partial_movie_files") { continue }
            if url.lastPathComponent.hasPrefix("uncached_") { continue }

            guard videoExtensions.contains(url.pathExtension.lowercased()) else { continue }
            let vals = try? url.resourceValues(forKeys: [
                .isRegularFileKey, .contentModificationDateKey, .fileSizeKey])
            guard vals?.isRegularFile == true else { continue }
            // A file still being written has no useful frames yet.
            let bytes = Int64(vals?.fileSize ?? 0)
            guard bytes > 0 else { continue }

            found.append(RenderItem(url: url,
                                    modified: vals?.contentModificationDate ?? .distantPast,
                                    size: bytes))
        }
        return found.sorted { $0.modified > $1.modified }
    }
}

// MARK: - Thumbnails

/// One-at-a-time frame extraction. See the file header for why this is an
/// actor rather than a pile of concurrent Tasks.
private actor ThumbnailGenerator {
    static let shared = ThumbnailGenerator()

    func thumbnail(for url: URL) async -> UIImage? {
        let asset = AVURLAsset(url: url)
        let gen = AVAssetImageGenerator(asset: asset)
        gen.appliesPreferredTrackTransform = true
        gen.maximumSize = CGSize(width: 480, height: 480)
        // Loose tolerance → the generator can use the nearest keyframe
        // instead of decoding forward to an exact time.
        gen.requestedTimeToleranceBefore = CMTime(seconds: 1, preferredTimescale: 600)
        gen.requestedTimeToleranceAfter  = CMTime(seconds: 1, preferredTimescale: 600)

        // Sample ~10% in: manim scenes routinely open on an empty frame,
        // and a wall of black thumbnails is useless for picking a clip.
        let duration = (try? await asset.load(.duration))?.seconds ?? 0
        let t = duration > 0.4
            ? CMTime(seconds: duration * 0.1, preferredTimescale: 600)
            : .zero

        guard let (cg, _) = try? await gen.image(at: t) else { return nil }
        return UIImage(cgImage: cg)
    }
}

/// Memory-only thumbnail cache. Views call `request(for:)` when a cell
/// appears and read `image(for:)` on redraw.
///
/// Bounded, because a long-lived studio accumulates renders: each cached
/// frame is a 480x270-ish CGImage (~0.5 MB), so an uncapped dictionary
/// over a few hundred clips would quietly cost more than the video being
/// presented. Oldest-inserted entries are dropped first; anything evicted
/// is regenerated if the user scrolls back to it.
final class RenderThumbnailCache: ObservableObject {
    static let shared = RenderThumbnailCache()

    private static let capacity = 40      // ~20 MB worst case

    @Published private var images: [URL: UIImage] = [:]
    /// Insertion order, oldest first — the eviction queue.
    private var order: [URL] = []
    private var inFlight: Set<URL> = []
    private var failed: Set<URL> = []

    private init() {}

    func image(for url: URL) -> UIImage? { images[url] }

    func request(for url: URL) {
        guard images[url] == nil, !inFlight.contains(url), !failed.contains(url) else { return }
        inFlight.insert(url)
        Task {
            let img = await ThumbnailGenerator.shared.thumbnail(for: url)
            self.inFlight.remove(url)
            guard let img else {
                // Don't retry forever on a file we can't decode.
                self.failed.insert(url)
                return
            }
            self.store(img, for: url)
        }
    }

    private func store(_ img: UIImage, for url: URL) {
        images[url] = img
        order.append(url)
        while order.count > Self.capacity {
            let oldest = order.removeFirst()
            // Guard against evicting a URL that was re-requested and
            // re-appended after this entry was queued.
            if !order.contains(oldest) { images.removeValue(forKey: oldest) }
        }
    }
}

// MARK: - Media details

/// What a finished render actually is, read back off the file. The render
/// settings that produced it aren't stored anywhere alongside the mp4, so
/// the container is the only evidence of what you got — which matters most
/// exactly when it disagrees with what you asked for (a 16K request that
/// fell back to software mpeg4, say, or a custom size rounded to even).
struct RenderMediaInfo: Equatable {
    var width: Int
    var height: Int
    var fps: Double
    var duration: Double        // seconds
    var codec: String
    var dataRateMbps: Double

    /// Ladder name ("4K", "16K") when the pixels match a rung exactly,
    /// else nil — a custom resolution has no name.
    var qualityLabel: String? { RenderResolution.qualityLabel(width: width, height: height) }

    var resolutionText: String { "\(width)×\(height)" }

    var durationText: String {
        let t = Int(duration.rounded())
        return String(format: "%d:%02d", t / 60, t % 60)
    }

    /// "4K · 3840×2160 · H.264 · 60 fps · 0:24 · 12.4 Mb/s"
    var summary: String {
        var parts: [String] = []
        if let q = qualityLabel { parts.append(q) } else { parts.append("Custom") }
        parts.append(resolutionText)
        parts.append(codec)
        if fps > 0 { parts.append("\(Int(fps.rounded())) fps") }
        if duration > 0 { parts.append(durationText) }
        if dataRateMbps > 0 { parts.append(String(format: "%.1f Mb/s", dataRateMbps)) }
        return parts.joined(separator: " · ")
    }

    /// Short badge for a filmstrip thumbnail: the rung name, or the pixel
    /// height for anything off-ladder.
    var badge: String { qualityLabel ?? "\(height)p" }
}

/// Reads and caches track metadata. Cheap next to thumbnailing — this only
/// parses the container, it never decodes a frame — so it is not serialized.
final class RenderMediaInfoCache: ObservableObject {
    static let shared = RenderMediaInfoCache()

    @Published private var infos: [URL: RenderMediaInfo] = [:]
    private var inFlight: Set<URL> = []
    private var failed: Set<URL> = []

    private init() {}

    func info(for url: URL) -> RenderMediaInfo? { infos[url] }

    func request(for url: URL) {
        guard infos[url] == nil, !inFlight.contains(url), !failed.contains(url) else { return }
        inFlight.insert(url)
        Task {
            let got = await Self.load(url)
            self.inFlight.remove(url)
            if let got { self.infos[url] = got } else { self.failed.insert(url) }
        }
    }

    private static func load(_ url: URL) async -> RenderMediaInfo? {
        let asset = AVURLAsset(url: url)
        guard let track = try? await asset.loadTracks(withMediaType: .video).first,
              let size = try? await track.load(.naturalSize)
        else { return nil }

        // naturalSize ignores rotation; applying the transform gives the
        // dimensions as presented, which is what the pixel-size lookup and
        // the on-screen readout should both use.
        let transform = (try? await track.load(.preferredTransform)) ?? .identity
        let shown = size.applying(transform)
        let w = Int(abs(shown.width).rounded())
        let h = Int(abs(shown.height).rounded())

        let fps = Double((try? await track.load(.nominalFrameRate)) ?? 0)
        let rate = Double((try? await track.load(.estimatedDataRate)) ?? 0)
        let dur = (try? await asset.load(.duration))?.seconds ?? 0

        var codec = "—"
        if let fds = try? await track.load(.formatDescriptions), let fd = fds.first {
            codec = Self.codecName(CMFormatDescriptionGetMediaSubType(fd))
        }

        return RenderMediaInfo(
            width: w, height: h,
            fps: fps,
            duration: dur.isFinite ? dur : 0,
            codec: codec,
            dataRateMbps: rate > 0 ? rate / 1_000_000 : 0)
    }

    /// FourCC → the name the app's own encoder picker uses, so what the
    /// file says lines up with what you selected.
    private static func codecName(_ code: FourCharCode) -> String {
        switch code {
        case kCMVideoCodecType_H264:               return "H.264"
        case kCMVideoCodecType_HEVC:               return "HEVC"
        case kCMVideoCodecType_MPEG4Video:         return "mpeg4"
        case kCMVideoCodecType_Animation:          return "qtrle (alpha)"
        case kCMVideoCodecType_AppleProRes4444:    return "ProRes 4444"
        case kCMVideoCodecType_AppleProRes422:     return "ProRes 422"
        case kCMVideoCodecType_JPEG:               return "JPEG"
        default:
            // Print unknown types as their FourCC rather than "unknown" —
            // e.g. hev1 vs hvc1 is exactly the kind of tagging detail that
            // has bitten this app before.
            let b = [UInt8((code >> 24) & 0xff), UInt8((code >> 16) & 0xff),
                     UInt8((code >> 8) & 0xff), UInt8(code & 0xff)]
            let s = String(bytes: b, encoding: .ascii)?
                .trimmingCharacters(in: .whitespaces) ?? "?"
            return s.isEmpty ? "—" : s
        }
    }
}
