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
    /// The freshest render from this session, if any. The cover opens on it,
    /// but the user can switch to any earlier clip from the library strip.
    let url: URL?
    var onDismiss: () -> Void

    @StateObject private var model = PresentationPlayerModel()
    @ObservedObject private var external = ExternalDisplayManager.shared
    @ObservedObject private var library  = RenderLibraryStore.shared
    @ObservedObject private var thumbs   = RenderThumbnailCache.shared
    @ObservedObject private var media    = RenderMediaInfoCache.shared

    @State private var controlsVisible = true
    @State private var libraryVisible  = false
    /// Set once the user picks a clip from the strip. While it stays nil the
    /// cover tracks `url`, so a render finishing mid-presentation takes over
    /// the screen the way it always has; once the user has deliberately
    /// chosen an older clip, it pins there and a new render only joins the
    /// strip.
    @State private var selected: URL?
    @State private var hideTask: DispatchWorkItem?

    /// What is on screen: an explicit pick, else this session's render, else
    /// the newest thing on disk (which is what makes Present useful on a
    /// cold launch, before anything has been rendered this session).
    private var current: URL? { selected ?? url ?? library.videos.first?.url }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if external.isConnected {
                controlSurface          // external screen has the video
            } else if current != nil {
                PresentationAVPlayer(player: model.player, showsControls: false)
                    .ignoresSafeArea()
                    .onTapGesture { tapBackdrop() }
            } else {
                emptyState
            }

            overlayChrome
        }
        .statusBarHidden(true)
        .persistentSystemOverlays(.hidden)   // hide home indicator while presenting
        .onAppear {
            library.refresh()
            if let c = current {
                model.load(c)
                media.request(for: c)
            }
            if external.isConnected { ExternalDisplayManager.shared.attachPlayer(model.player) }
            scheduleAutoHide()
        }
        // Drives playback off whatever `current` resolves to, so this covers
        // all three paths: the initial clip, a pick from the strip, and the
        // library scan landing after the cover is already up.
        .onChange(of: current) { _, c in
            if let c {
                model.load(c)
                media.request(for: c)
            }
        }
        // A render finished while presenting — make sure it shows up in the
        // strip even if the user is pinned to an older clip.
        .onChange(of: url) { _, _ in
            library.refresh()
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
            Text(current?.lastPathComponent ?? "—")
                .font(.system(size: 12, design: .monospaced)).foregroundStyle(.white.opacity(0.6))
            if let c = current, let m = media.info(for: c) {
                Text(m.summary)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.accentPrimary.opacity(0.9))
            }
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
            Button { library.refresh() } label: {
                Label("Look again", systemImage: "arrow.clockwise")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14).padding(.vertical, 7)
                    .background(Capsule().fill(Color.white.opacity(0.14)))
            }
            .buttonStyle(.plain)
            .padding(.top, 4)
        }
    }

    private var overlayChrome: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                if let c = current {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(c.lastPathComponent)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.white.opacity(0.8))
                            .lineLimit(1).truncationMode(.middle)
                        // Resolution / codec / fps / bitrate, read back off
                        // the file itself rather than from the settings that
                        // were used — those aren't stored with the mp4, and
                        // the two can differ (a hardware-encode fallback, an
                        // odd custom size rounded to even).
                        if let m = media.info(for: c) {
                            Text(m.summary)
                                .font(.system(size: 9.5, design: .monospaced))
                                .foregroundStyle(Theme.accentPrimary.opacity(0.9))
                                .lineLimit(1)
                        }
                    }
                    .padding(.horizontal, 10).padding(.vertical, 7)
                    .background(RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(.black.opacity(0.5)))
                }
                Spacer()
                if !library.videos.isEmpty {
                    Button { toggleLibrary() } label: {
                        Label("\(library.videos.count)",
                              systemImage: "rectangle.stack.fill")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(libraryVisible ? Theme.accentPrimary : .white)
                            .padding(.horizontal, 12).padding(.vertical, 8)
                            .background(Capsule().fill(.black.opacity(0.55)))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Render library, \(library.videos.count) clips")
                }
                Button(action: onDismiss) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 30))
                        .foregroundStyle(.white, .black.opacity(0.55))
                }
                .buttonStyle(.plain)
            }
            .padding(16)
            .opacity(controlsVisible ? 1 : 0)

            Spacer()

            if !external.isConnected && current != nil {
                HStack(spacing: 28) {
                    bigControl(model.isPlaying ? "pause.fill" : "play.fill") { model.togglePlay() }
                    bigControl("gobackward") { model.restart() }
                }
                .padding(.bottom, libraryVisible ? 16 : 40)
                .opacity(controlsVisible ? 1 : 0)
            }

            if libraryVisible {
                filmstrip
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: controlsVisible)
        .animation(.easeInOut(duration: 0.25), value: libraryVisible)
    }

    // MARK: Library strip

    private var filmstrip: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Text("RENDER LIBRARY")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .tracking(1.5)
                    .foregroundStyle(.white.opacity(0.55))
                Spacer()
                Button { library.refresh() } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.75))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Rescan renders")
                Button { toggleLibrary() } label: {
                    Image(systemName: "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.75))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Hide library")
            }

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 10) {
                    ForEach(library.videos) { item in
                        thumbCell(item)
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(height: 108)
        }
        .padding(.horizontal, 16)
        .padding(.top, 12)
        .padding(.bottom, 20)
        .background(
            LinearGradient(colors: [.black.opacity(0.0), .black.opacity(0.85), .black.opacity(0.92)],
                           startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea(edges: .bottom)
        )
    }

    private func thumbCell(_ item: RenderItem) -> some View {
        let isCurrent = item.url == current
        return Button { pick(item.url) } label: {
            VStack(alignment: .leading, spacing: 5) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.07))
                    if let img = thumbs.image(for: item.url) {
                        Image(uiImage: img)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    } else {
                        Image(systemName: "film")
                            .font(.system(size: 18))
                            .foregroundStyle(.white.opacity(0.3))
                    }
                    VStack {
                        // Quality rung in the top-right, so the strip is
                        // scannable by resolution without opening anything.
                        HStack {
                            Spacer()
                            if let m = media.info(for: item.url) {
                                Text(m.badge)
                                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 4).padding(.vertical, 2)
                                    .background(Capsule().fill(.black.opacity(0.65)))
                            }
                        }
                        Spacer()
                        HStack {
                            if isCurrent {
                                // Playing marker, so the current clip is
                                // obvious even when two renders share a
                                // thumbnail.
                                Image(systemName: "play.fill")
                                    .font(.system(size: 8, weight: .bold))
                                    .foregroundStyle(.black)
                                    .padding(3)
                                    .background(Circle().fill(Theme.accentPrimary))
                            }
                            Spacer()
                        }
                    }
                    .padding(5)
                }
                .frame(width: 132, height: 74)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isCurrent ? Theme.accentPrimary : Color.white.opacity(0.16),
                                lineWidth: isCurrent ? 2 : 1)
                )

                Text(item.name)
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundStyle(isCurrent ? .white : .white.opacity(0.7))
                    .lineLimit(1).truncationMode(.middle)
                Text(media.info(for: item.url).map { "\($0.resolutionText) · \($0.codec)" }
                     ?? item.subtitle)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.42))
                    .lineLimit(1)
            }
            .frame(width: 132, alignment: .leading)
        }
        .buttonStyle(.plain)
        // Lazy: only cells that scroll into view decode a frame. Media
        // details are cheap by comparison (container parse, no decode).
        .task {
            thumbs.request(for: item.url)
            media.request(for: item.url)
        }
        .accessibilityLabel("\(item.name), \(item.subtitle)")
    }

    // MARK: Interaction

    private func pick(_ u: URL) {
        guard u != current else { return }
        Haptics.impact(.light)
        selected = u
    }

    private func toggleLibrary() {
        Haptics.selection()
        libraryVisible.toggle()
        if libraryVisible {
            // Keep the chrome up while browsing — the close button and the
            // strip share the same fade.
            hideTask?.cancel()
            controlsVisible = true
        } else {
            scheduleAutoHide()
        }
    }

    /// A tap on the video dismisses the library if it is open, otherwise it
    /// toggles the transport chrome.
    private func tapBackdrop() {
        if libraryVisible { toggleLibrary() } else { flashControls() }
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
        let task = DispatchWorkItem {
            // Never fade the chrome out from under an open library.
            guard !libraryVisible else { return }
            withAnimation { controlsVisible = false }
        }
        hideTask = task
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.5, execute: task)
    }
}
