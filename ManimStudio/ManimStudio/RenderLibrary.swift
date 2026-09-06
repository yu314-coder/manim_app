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
