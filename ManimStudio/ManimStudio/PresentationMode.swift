// PresentationMode.swift — distraction-free looping playback for the latest
// render, mirrored to a TV via AirPlay / HDMI when a display is connected.
//
// Design:
//   • One AVPlayer is the source of truth, owned by PresentationPlayerModel.
//     It loops via an AVPlayerItemDidPlayToEndTime observer.
//   • The iPad shows the looping video full-bleed (tap-to-reveal transport).
//     Presenting to a TV is plain MIRRORING: the system duplicates the iPad's
//     Present screen onto the external display. The app deliberately does NOT
//     draw separate external content (see ExternalDisplayManager) — claiming
//     the external screen would replace the mirror with app UI.
import SwiftUI
import Combine
import AVKit
import AVFoundation
import UIKit

// MARK: - Playback model (single shared AVPlayer + loop)

final class PresentationPlayerModel: ObservableObject {
    let player = AVPlayer()
    @Published private(set) var isPlaying = false

    private var loopObserver: NSObjectProtocol?
    private var rateObserver: NSKeyValueObservation?
    private var statusObserver: NSKeyValueObservation?
    private var currentURL: URL?
    private var didRetry = false

    init() {
        try? AVAudioSession.sharedInstance().setCategory(
            .playback, mode: .moviePlayback,
            options: [.allowAirPlay, .mixWithOthers])
        try? AVAudioSession.sharedInstance().setActive(true)

        rateObserver = player.observe(\.rate, options: [.new]) { [weak self] p, _ in
            DispatchQueue.main.async { self?.isPlaying = p.rate != 0 }
        }
    }

    /// Point the player at `url` and auto-loop. Safe to call again with a
    /// new URL (e.g. a re-render happened while presenting).
    func load(_ url: URL) {
        guard url != currentURL else { play(); return }
        currentURL = url
        didRetry = false
        install(url)
    }

    /// Install a fresh AVPlayerItem for `url`, (re)arming the loop + status
    /// observers. Extracted so the failure-retry path can re-install.
    private func install(_ url: URL) {
        let item = AVPlayerItem(asset: AVURLAsset(url: url))
        player.replaceCurrentItem(with: item)

        if let o = loopObserver { NotificationCenter.default.removeObserver(o) }
        loopObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { [weak self] _ in
            self?.player.seek(to: .zero)
            self?.player.play()
        }

        // A re-render landing mid-presentation can briefly surface a
        // still-writing file → the item fails. Retry once after it finishes.
        statusObserver?.invalidate()
        statusObserver = item.observe(\.status, options: [.new]) { [weak self] it, _ in
            guard let self else { return }
            if it.status == .readyToPlay {
                self.didRetry = false
            } else if it.status == .failed, !self.didRetry, let u = self.currentURL {
                self.didRetry = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { [weak self] in
                    self?.install(u)
                }
            }
        }
        play()
    }

    func play()  { player.play() }
    func pause() { player.pause() }
    func togglePlay() { isPlaying ? pause() : play() }
    func restart() { player.seek(to: .zero); player.play() }

    func teardown() {
        player.pause()
        if let o = loopObserver { NotificationCenter.default.removeObserver(o) }
        loopObserver = nil
        rateObserver?.invalidate(); rateObserver = nil
        statusObserver?.invalidate(); statusObserver = nil
        player.replaceCurrentItem(with: nil)
    }

    deinit { teardown() }
}

// MARK: - AVPlayer surface

struct PresentationAVPlayer: UIViewControllerRepresentable {
    let player: AVPlayer
    var showsControls: Bool = true

    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let vc = AVPlayerViewController()
        vc.player = player
        vc.showsPlaybackControls = showsControls
        vc.allowsPictureInPicturePlayback = true
        vc.videoGravity = .resizeAspect             // letterbox, never crop
        vc.updatesNowPlayingInfoCenter = false
        return vc
    }
    func updateUIViewController(_ vc: AVPlayerViewController, context: Context) {
        if vc.player !== player { vc.player = player }
        vc.showsPlaybackControls = showsControls
    }
}

// MARK: - iPad presentation cover

struct PresentationCoverView: View {
    let url: URL?
    var onDismiss: () -> Void

    @StateObject private var model = PresentationPlayerModel()
    @ObservedObject private var external = ExternalDisplayManager.shared
    @State private var controlsVisible = true
    @State private var hideTask: DispatchWorkItem?

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if external.isConnected {
                controlSurface          // external screen has the video
            } else if url != nil {
                PresentationAVPlayer(player: model.player, showsControls: false)
                    .ignoresSafeArea()
                    .onTapGesture { flashControls() }
            } else {
                emptyState
            }

            overlayChrome
        }
        .statusBarHidden(true)
        .persistentSystemOverlays(.hidden)   // hide home indicator while presenting
        .onAppear {
            if let url { model.load(url) }
            if external.isConnected { ExternalDisplayManager.shared.attachPlayer(model.player) }
            scheduleAutoHide()
        }
        .onChange(of: url) { _, newURL in
            if let newURL { model.load(newURL) }
        }
        // External display attaches/detaches mid-session → hand the shared
        // player to / reclaim it from the external window.
        .onChange(of: external.isConnected) { _, connected in
            ExternalDisplayManager.shared.attachPlayer(connected ? model.player : nil)
        }
        .onDisappear {
            ExternalDisplayManager.shared.attachPlayer(nil)
            model.teardown()
        }
    }

    private var controlSurface: some View {
        VStack(spacing: 24) {
            Image(systemName: "tv.fill")
                .font(.system(size: 48)).foregroundStyle(Theme.accentPrimary)
            Text("Presenting on external display")
                .font(.system(size: 18, weight: .semibold)).foregroundStyle(.white)
            Text(url?.lastPathComponent ?? "—")
                .font(.system(size: 12, design: .monospaced)).foregroundStyle(.white.opacity(0.6))
            HStack(spacing: 28) {
                bigControl(model.isPlaying ? "pause.fill" : "play.fill") { model.togglePlay() }
                bigControl("gobackward") { model.restart() }
            }
            .padding(.top, 8)
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "film").font(.system(size: 56)).foregroundStyle(.white.opacity(0.4))
            Text("Nothing to present").font(.system(size: 15, weight: .semibold)).foregroundStyle(.white)
            Text("Render an animation first").font(.system(size: 12)).foregroundStyle(.white.opacity(0.5))
        }
    }

    private var overlayChrome: some View {
        VStack {
            HStack(spacing: 12) {
                Spacer()
                Button(action: onDismiss) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 30))
                        .foregroundStyle(.white, .black.opacity(0.55))
                }
            }
            .padding(16)
            .opacity(controlsVisible ? 1 : 0)

            Spacer()

            if !external.isConnected && url != nil {
                HStack(spacing: 28) {
                    bigControl(model.isPlaying ? "pause.fill" : "play.fill") { model.togglePlay() }
                    bigControl("gobackward") { model.restart() }
                }
                .padding(.bottom, 40)
                .opacity(controlsVisible ? 1 : 0)
            }
        }
        .animation(.easeInOut(duration: 0.25), value: controlsVisible)
    }

    @ViewBuilder
    private func bigControl(_ icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 26, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 60, height: 60)
                .background(Circle().fill(Color.white.opacity(0.14)))
        }
        .buttonStyle(.plain)
    }

    private func flashControls() {
        controlsVisible.toggle()
        if controlsVisible { scheduleAutoHide() }
    }
    private func scheduleAutoHide() {
        hideTask?.cancel()
        let task = DispatchWorkItem { withAnimation { controlsVisible = false } }
        hideTask = task
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.5, execute: task)
    }
}
