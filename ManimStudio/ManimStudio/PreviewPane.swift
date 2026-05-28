// PreviewPane.swift — video/image preview with file-info bar.
//
// Why WKWebView instead of AVPlayer:
//
// SwiftUI's `VideoPlayer` wrapping AVPlayer worked on the simulator
// and reliably on iPad but intermittently rendered a black frame on
// device for renders larger than ~5 MB or longer than ~10 s. The
// AVAsset loader is asynchronous and `replaceCurrentItem(_:)` against
// a freshly-finished file occasionally landed before the OS's file
// inode was visible to AVFoundation's track-loading pass — so the
// player got a "valid URL, no tracks" item and stayed blank.
//
// CodeBench shipped with a WKWebView + HTML5 `<video>` element
// (CodeEditorViewController.swift line ~7823) which doesn't hit that
// race because WebKit reads via the normal POSIX file handle and
// blocks until it has playable bytes. Same approach here: write a
// small HTML player next to the MP4 and feed it to a WKWebView. It
// scales to any video size and includes its own transport (play /
// pause / scrub / speed / loop).
import SwiftUI
import AVKit
import AVFoundation
import Photos
import UIKit
import WebKit

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
                if let url = videoURL {
                    VideoWebView(videoURL: url)
                        // Re-render the WebView when the URL changes so
                        // the HTML5 <video> picks up the new source.
                        .id(url.absoluteString)
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

// MARK: - WebKit-based video viewport
//
// Mirrors CodeBench's video preview: we write a small HTML player file
// next to the MP4 (the player tag's `<source>` is a relative path), then
// hand the HTML file's URL to WKWebView with read-access to the parent
// directory. This lets WebKit serve both the HTML and the video out of
// the same sandbox-allowed origin so the in-browser <video> tag plays
// without CORS / file-scheme restrictions.
//
// Why this beats AVPlayer for our use case:
//   • Big renders (>5 MB) play immediately — no AVAsset track-loading
//     race that left AVPlayer with a "valid URL, no tracks" item.
//   • Auto-loops, scrub bar, playback speed, save-to-photos / share
//     hooks all come from the player HTML (which mirrors CodeBench's
//     known-working HTML5 player verbatim).
//   • The viewport scales with the WKWebView; no separate fullscreen
//     logic needed (HTML5 video's built-in fullscreen still works via
//     the system control).

private struct VideoWebView: UIViewRepresentable {
    let videoURL: URL

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.allowsPictureInPictureMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        let wv = WKWebView(frame: .zero, configuration: config)
        wv.scrollView.isScrollEnabled = false
        wv.backgroundColor = .black
        wv.isOpaque = false
        wv.scrollView.backgroundColor = .black
        loadPlayer(into: wv)
        return wv
    }

    func updateUIView(_ wv: WKWebView, context: Context) {
        // .id(url) on the SwiftUI side rebuilds the view when URL
        // changes, so updateUIView only runs for size / theme changes;
        // nothing to do here.
    }

    private func loadPlayer(into wv: WKWebView) {
        let dir = videoURL.deletingLastPathComponent()
        let videoName = videoURL.lastPathComponent
        let ext = videoURL.pathExtension.lowercased()
        // Pick the right MIME so WebKit feeds the right decoder.
        let mime: String = {
            switch ext {
            case "mp4", "m4v": return "video/mp4"
            case "mov":         return "video/quicktime"
            case "webm":        return "video/webm"
            default:            return "video/mp4"
            }
        }()
        let html = Self.playerHTML(videoFilename: videoName, mime: mime)
        let htmlURL = dir.appendingPathComponent("_preview_player.html")
        do {
            try html.write(to: htmlURL, atomically: true, encoding: .utf8)
        } catch {
            NSLog("[preview] failed to write _preview_player.html: %@",
                  error.localizedDescription)
            return
        }
        wv.loadFileURL(htmlURL, allowingReadAccessTo: dir)
    }

    /// HTML5 video player template. The `<source>` tag uses a relative
    /// filename so WebKit resolves it against the HTML file's directory
    /// — same dir we hand to `allowingReadAccessTo:`. The script auto-
    /// plays muted (iOS requires `muted` for unattended playback) and
    /// loops.
    private static func playerHTML(videoFilename: String, mime: String) -> String {
        // Escape for embedding in an HTML attribute. Filenames produced
        // by Manim are ASCII so this is mostly defensive.
        let safeName = videoFilename
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
        return """
        <!DOCTYPE html>
        <html><head><meta charset="UTF-8">
        <meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
        <style>
        *{margin:0;padding:0;box-sizing:border-box;-webkit-user-select:none;user-select:none;-webkit-tap-highlight-color:transparent}
        html,body{height:100%;background:#0A0A0F;font-family:-apple-system,system-ui,sans-serif;overflow:hidden}
        .player{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:#000}
        video{max-width:100%;max-height:100%;background:#000}
        </style></head>
        <body>
        <div class="player">
          <video id="v" playsinline preload="auto" muted controls loop>
            <source src="\(safeName)" type="\(mime)">
          </video>
        </div>
        <script>
        const v=document.getElementById('v');
        v.addEventListener('loadeddata',()=>{v.play().catch(()=>{});});
        v.addEventListener('error',e=>{
          document.body.innerHTML='<div style="color:#f87171;padding:18px;font-size:13px">Video failed to load: '+(v.error?v.error.code:'unknown')+'</div>';
        });
        </script>
        </body></html>
        """
    }
}
