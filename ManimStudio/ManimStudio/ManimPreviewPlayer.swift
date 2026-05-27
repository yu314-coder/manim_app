// ManimPreviewPlayer.swift — looped MP4 player for Gallery cards.
//
// Each Gallery card needs to show what a real Manim render of its
// scene looks like — not a procedural mock. The MP4s are pre-rendered
// once on a developer machine (via _preview_renders/scenes/preview_scenes.py)
// using the real Manim engine, and bundled into the app at
// Resources/GalleryPreviews/<id>.mp4. They are tiny (~25–60 KB each,
// ~220 KB total for all six) so they don't bloat the .ipa, and they
// loop seamlessly because each scene's `construct()` ends in the
// same visual state it would naturally return to at the start.
//
// We host AVPlayerLayer in a UIView via UIViewRepresentable so the
// frame fills the card cleanly without any UI chrome — no transport
// bar, no play button, no system gestures stealing taps from the
// card's own tap handler.

import SwiftUI
import AVFoundation
import UIKit

struct ManimPreviewPlayer: View {
    /// `id` is the GalleryTemplate id ("hello", "pythag", "sine",
    /// "fourier", "morph", "graph") — used to locate the bundled MP4.
    let id: String

    var body: some View {
        if let url = Bundle.main.url(forResource: id,
                                     withExtension: "mp4",
                                     subdirectory: "GalleryPreviews")
            ?? Bundle.main.url(forResource: id, withExtension: "mp4") {
            LoopingVideoView(url: url)
                .accessibilityHidden(true)
        } else {
            // Asset missing — should never happen in shipping builds,
            // but in dev (e.g. before adding the Resources folder to
            // the Xcode target) we render an explicit black frame
            // rather than crashing or showing a system "missing file"
            // placeholder.
            ZStack {
                Color.black
                Text("(\(id).mp4 missing)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.4))
            }
        }
    }
}

// MARK: - Looping AVPlayer host

private struct LoopingVideoView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> PlayerContainerView {
        let v = PlayerContainerView()
        v.configure(url: url)
        return v
    }
    func updateUIView(_ uiView: PlayerContainerView, context: Context) {
        // URL is captured at creation; nothing to update.
    }
    static func dismantleUIView(_ uiView: PlayerContainerView, coordinator: ()) {
        uiView.teardown()
    }
}

private final class PlayerContainerView: UIView {
    private var player: AVQueuePlayer?
    private var looper: AVPlayerLooper?
    private var playerLayer: AVPlayerLayer?

    override class var layerClass: AnyClass { CALayer.self }

    func configure(url: URL) {
        backgroundColor = .black
        // AVPlayerLooper requires AVQueuePlayer + a template item.
        // It silently inserts copies of the template at the end of the
        // queue as each one finishes, so playback is gapless.
        let item = AVPlayerItem(url: url)
        let q = AVQueuePlayer()
        q.isMuted = true
        q.actionAtItemEnd = .advance
        // Don't pause if the system says "uninterrupted audio
        // suspended" — these previews have no audio anyway, but
        // setting this avoids any chance of an audio-session conflict
        // with the Manim render pipeline that uses .ambient.
        q.allowsExternalPlayback = false
        looper = AVPlayerLooper(player: q, templateItem: item)
        player = q

        let layer = AVPlayerLayer(player: q)
        layer.videoGravity = .resizeAspect
        layer.frame = bounds
        self.layer.addSublayer(layer)
        playerLayer = layer

        q.play()

        // Re-start playback if the system briefly pauses us (scroll
        // off-screen, app backgrounded, etc.). Cheap to register.
        NotificationCenter.default.addObserver(
            self, selector: #selector(restartIfNeeded),
            name: UIApplication.didBecomeActiveNotification, object: nil)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        playerLayer?.frame = bounds
    }

    @objc private func restartIfNeeded() {
        if let p = player, p.rate == 0 { p.play() }
    }

    func teardown() {
        NotificationCenter.default.removeObserver(self)
        player?.pause()
        player = nil
        looper = nil
        playerLayer?.removeFromSuperlayer()
        playerLayer = nil
    }
}
