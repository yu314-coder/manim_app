// AIReviewer.swift — extract frames from a rendered manim preview
// at 1 fps and write them to disk so the AI agent can read them
// back as a visual-QA pass. Mirrors the Windows desktop app's
// "Review" → "Improve" agent loop from prompts/claude_agent.md:
//   1. render preview
//   2. extract N frames @ 1fps as PNGs into the workspace
//   3. ask claude to view each frame and either SATISFIED or
//      IMPROVE: <feedback>
//   4. (next turn) run "Improve" prompt with the feedback as fuel
//
// Why AVAssetImageGenerator: same framework used elsewhere in the
// app for the preview viewport, no extra deps. Returns CGImages we
// just dump to PNG.
import Foundation
import AVFoundation
import AppKit

@MainActor
enum AIReviewer {

    /// Where review frames land. One subdir per video so concurrent
    /// reviews don't clobber each other; reused across iterations of
    /// the same render so claude can `ls` it from the workspace.
    static func framesDir(for videoURL: URL) -> URL {
        let workspace = AIEditService.workspaceURL
        let stem = videoURL.deletingPathExtension().lastPathComponent
        let dir = workspace.appendingPathComponent(
            "review-frames/\(stem)", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// Extracts frames at 1 fps from `videoURL`. Returns the saved
    /// PNG paths in chronological order. Caps at 24 frames so we
    /// don't blow the LLM token budget on long renders.
    static func extractFrames(from videoURL: URL,
                              maxFrames: Int = 24) async throws -> [URL] {
        let asset = AVURLAsset(url: videoURL)
        let duration = try await asset.load(.duration)
        let totalSec = Int(duration.seconds.rounded(.down))
        guard totalSec > 0 else { return [] }

        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true
        // Tolerate +/- 0.5s so we get the keyframe nearest each
        // 1-second mark — fast and avoids decode jitter.
        generator.requestedTimeToleranceBefore = CMTime(seconds: 0.5,
                                                         preferredTimescale: 600)
        generator.requestedTimeToleranceAfter  = CMTime(seconds: 0.5,
                                                         preferredTimescale: 600)
        // Downsize to 720p max — manim renders can be 4K but the
        // visual QA only needs enough detail to spot layout / text
        // problems. Keeps each PNG small.
        generator.maximumSize = CGSize(width: 1280, height: 720)

        let dir = framesDir(for: videoURL)
        // Clear any prior iteration's frames.
        if let old = try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: nil) {
            for u in old { try? FileManager.default.removeItem(at: u) }
        }

        let stride = max(1, totalSec / maxFrames)
        var saved: [URL] = []
        var fileIdx = 0
        for second in Swift.stride(from: 0, to: totalSec, by: stride) {
            if saved.count >= maxFrames { break }
            let cmtime = CMTime(seconds: Double(second),
                                preferredTimescale: 600)
            do {
                let cgImage = try generator.copyCGImage(at: cmtime,
                                                         actualTime: nil)
                fileIdx += 1
                let outURL = dir.appendingPathComponent(
                    String(format: "frame_%02d.png", fileIdx))
                if writePNG(cgImage, to: outURL) {
                    saved.append(outURL)
                }
            } catch {
                // Skip individual frames that fail; e.g. very last
                // frame at duration boundary sometimes errors.
                continue
            }
        }
        return saved
    }

    private static func writePNG(_ image: CGImage, to url: URL) -> Bool {
        let nsImage = NSBitmapImageRep(cgImage: image)
        guard let data = nsImage.representation(using: .png, properties: [:])
        else { return false }
        do { try data.write(to: url); return true }
        catch { return false }
    }

    /// Builds the visual-QA review prompt. Substitutes the same
    /// {{NUM_FRAMES}} / {{DESCRIPTION}} placeholders the bundled
    /// claude_agent.md "Review" section uses, and tells claude the
    /// directory path so its Read tool can pull them.
    static func buildReviewPrompt(originalGoal: String,
                                  framesDir: URL,
                                  framePaths: [URL]) -> String {
        let listing = framePaths.enumerated().map { i, url in
            "  \(i + 1). \(url.lastPathComponent)"
        }.joined(separator: "\n")
        return """
        Visual-QA pass on the rendered manim animation you just made.

        GOAL: \"\(originalGoal)\"

        Review frames are PNG images at 1 fps in this directory:
          \(framesDir.path)

        Files:
        \(listing)

        STEP 1. Read every image at that path with the Read tool.
        STEP 2. For each frame, describe what you see in one sentence.
        STEP 3. Check for these problems:
          - DOESN'T MATCH GOAL — missing key elements requested
          - UNNATURAL/STRANGE — looks weird or wrong
          - OVERLAPPING — objects or text piled on each other
          - OFF SCREEN — objects cut off at edges
          - WRONG TEXT — typos, wrong words, garbled math
          - DISCONNECTED — broken connections between elements
        IGNORE: colors, fonts, spacing, timing, speed, style.

        STEP 4. Final line — exactly ONE of:
          SATISFIED
          IMPROVE: <specific description of what's wrong>

        Do not edit scene.py in this turn. Only review.
        """
    }
}
