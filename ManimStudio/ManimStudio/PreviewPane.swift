// PreviewPane.swift — video/image preview with file-info bar.
import SwiftUI
import AVKit
import Photos
import UIKit

struct PreviewPane: View {
    @Binding var videoURL: URL?
    /// Stable AVPlayer instance kept across SwiftUI redraws. Building
    /// `AVPlayer(url:)` inline in `body` recreates the player on
    /// every state change (e.g. each terminalText update during a
    /// render) — that drops in-flight asset loading and sometimes
    /// shows a black screen even though the URL is valid. Holding
    /// the player in @State and only swapping the AVPlayerItem when
    /// the URL changes keeps playback steady.
    @State private var player = AVPlayer()
    @State private var loadedURL: URL? = nil
    @State private var showFullscreen = false
    @State private var shareItems: [Any] = []
    @State private var showShare = false
    @State private var toast: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "play.rectangle")
                    .font(.system(size: 11)).foregroundStyle(Theme.accentSecondary)
                Text("Preview").font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                toolBtn("camera", "Screenshot") { takeScreenshot() }
                toolBtn("arrow.up.left.and.arrow.down.right", "Fullscreen") {
                    guard videoURL != nil else { return }
                    showFullscreen = true
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Theme.bgSecondary)
            .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1), alignment: .bottom)

            // File info bar
            HStack {
                Image(systemName: "doc").font(.system(size: 10)).foregroundStyle(Theme.textDim)
                Text(videoURL?.lastPathComponent ?? "—")
                    .font(.system(size: 10)).foregroundStyle(Theme.textSecondary)
                Spacer()
                if let url = videoURL,
                   let size = try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int64 {
                    Text(ByteCountFormatter.string(fromByteCount: size, countStyle: .file))
                        .font(.system(size: 10)).foregroundStyle(Theme.textDim)
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(Theme.bgTertiary)

            // Viewport
            Group {
                if videoURL != nil {
                    VideoPlayer(player: player)
                        .onAppear { syncPlayer() }
                        .onChange(of: videoURL) { _, _ in syncPlayer() }
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "film")
                            .font(.system(size: 56))
                            .foregroundStyle(Theme.textDim)
                        Text("No Preview")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Theme.textSecondary)
                        Text("Render or preview an animation")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.textDim)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Theme.bgPrimary)
                }
            }
        }
        .background(Theme.bgPrimary)
        .overlay(alignment: .top) {
            if let t = toast {
                Text(t)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14).padding(.vertical, 8)
                    .background(RoundedRectangle(cornerRadius: 10)
                        .fill(Color.black.opacity(0.78)))
                    .padding(.top, 56)
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .fullScreenCover(isPresented: $showFullscreen) {
            FullscreenPlayerView(url: videoURL) {
                showFullscreen = false
            }
        }
        .sheet(isPresented: $showShare) {
            ShareSheet(items: shareItems)
        }
    }

    /// Replace the player's currentItem when the URL changes,
    /// rather than rebuilding the AVPlayer itself. Kicks off
    /// playback immediately on the new file. If the URL points at
    /// a deleted file (e.g. a partial that was cleaned up after
    /// concat), clear the binding so the empty state re-renders.
    private func syncPlayer() {
        guard let url = videoURL else {
            player.replaceCurrentItem(with: nil)
            loadedURL = nil
            return
        }
        if loadedURL == url { return }
        guard FileManager.default.fileExists(atPath: url.path) else {
            DispatchQueue.main.async { videoURL = nil }
            return
        }
        let item = AVPlayerItem(asset: AVURLAsset(url: url))
        player.replaceCurrentItem(with: item)
        player.seek(to: .zero)
        player.play()
        loadedURL = url
    }

    // MARK: - Screenshot
    //
    // Grab a single frame from the currently-playing video at the
    // player's current time, save it to the Photos library, and offer
    // a share fallback. For still images (.png / .jpg) we just share
    // the image file directly. AVAssetImageGenerator runs off-main
    // so the UI doesn't stutter on a 1080p frame extract.
    private func takeScreenshot() {
        guard let url = videoURL else {
            flash("No preview loaded")
            return
        }
        let ext = url.pathExtension.lowercased()
        // Still image — no need to extract a frame.
        if ["png", "jpg", "jpeg", "gif"].contains(ext) {
            saveImageURLToPhotos(url)
            return
        }
        // Video — extract the current frame.
        let time = player.currentTime()
        let asset = AVURLAsset(url: url)
        let gen = AVAssetImageGenerator(asset: asset)
        gen.appliesPreferredTrackTransform = true
        gen.requestedTimeToleranceBefore = .zero
        gen.requestedTimeToleranceAfter = .zero
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let cg = try gen.copyCGImage(at: time, actualTime: nil)
                let ui = UIImage(cgImage: cg)
                DispatchQueue.main.async {
                    savePhoto(ui) { ok in
                        if ok { flash("✓ Saved screenshot to Photos") }
                        else  { fallbackShareImage(ui) }
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    flash("Couldn't capture frame")
                }
            }
        }
    }

    private func saveImageURLToPhotos(_ url: URL) {
        guard let ui = UIImage(contentsOfFile: url.path) else {
            flash("Couldn't load image")
            return
        }
        savePhoto(ui) { ok in
            if ok { flash("✓ Saved to Photos") }
            else  { fallbackShareImage(ui) }
        }
    }

    private func savePhoto(_ image: UIImage, completion: @escaping (Bool) -> Void) {
        let status = PHPhotoLibrary.authorizationStatus(for: .addOnly)
        let proceed = { (granted: Bool) in
            guard granted else { completion(false); return }
            UIImageWriteToSavedPhotosAlbum(image, nil, nil, nil)
            completion(true)
        }
        switch status {
        case .authorized, .limited:
            proceed(true)
        case .notDetermined:
            PHPhotoLibrary.requestAuthorization(for: .addOnly) { s in
                DispatchQueue.main.async {
                    proceed(s == .authorized || s == .limited)
                }
            }
        default:
            completion(false)
        }
    }

    /// Photos denied → fall back to the system share sheet so the user
    /// can still get the screenshot out (AirDrop / Mail / Files / etc.).
    private func fallbackShareImage(_ image: UIImage) {
        shareItems = [image]
        showShare = true
        flash("Photos access denied — using share sheet")
    }

    private func flash(_ message: String) {
        withAnimation(.easeOut(duration: 0.2)) { toast = message }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) {
            withAnimation(.easeIn(duration: 0.25)) { toast = nil }
        }
    }

    @ViewBuilder
    private func toolBtn(_ icon: String, _ tooltip: String,
                         action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 24, height: 24)
                .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
        }
        .buttonStyle(.plain).help(tooltip)
    }
}

// MARK: - Fullscreen presentation
//
// We use a UIViewControllerRepresentable wrapper around AVPlayerViewController
// so we get the system's built-in fullscreen chrome (transport bar, AirPlay,
// PiP, scrubbing). A bare SwiftUI VideoPlayer in a fullScreenCover has no
// affordance to dismiss on iPad — adding our own close button gives the user
// a way out.
private struct FullscreenPlayerView: View {
    let url: URL?
    var onDismiss: () -> Void

    @State private var player = AVPlayer()

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            if let url = url {
                AVPlayerControllerRepresented(player: player)
                    .ignoresSafeArea()
                    .onAppear {
                        player.replaceCurrentItem(
                            with: AVPlayerItem(asset: AVURLAsset(url: url)))
                        player.play()
                    }
                    .onDisappear { player.pause() }
            }
            Button(action: onDismiss) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(.white, .black.opacity(0.55))
                    .padding(16)
            }
        }
    }
}

private struct AVPlayerControllerRepresented: UIViewControllerRepresentable {
    let player: AVPlayer
    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let vc = AVPlayerViewController()
        vc.player = player
        vc.allowsPictureInPicturePlayback = true
        vc.showsPlaybackControls = true
        return vc
    }
    func updateUIViewController(_ vc: AVPlayerViewController, context: Context) {
        if vc.player !== player { vc.player = player }
    }
}
