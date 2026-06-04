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
import Combine
import AVKit
import AVFoundation
import Photos
import UIKit
import WebKit

struct PreviewPane: View {
    @Binding var videoURL: URL?
    /// Holder for the live <video> WKWebView so the screenshot action
    /// can read the element's current playback time and capture the
    /// exact frame the user is looking at. The viewport is rendered by
    /// `VideoWebView` (HTML5 <video>), not by an AVPlayer, so there is
    /// no Swift-side player whose `currentTime()` reflects the screen.
    @StateObject private var webHolder = WebViewHolder()
    @State private var showFullscreen = false
    @State private var shareItems: [Any] = []
    @State private var showShare = false
    @State private var toast: String? = nil
    /// Cached, pre-formatted on-disk size for the file-info bar. Reading
    /// FileManager attributes + ByteCountFormatter on every `body` pass
    /// is wasteful — during a render `videoURL` changes each poll tick
    /// and `body` re-evaluates constantly. Recompute only on URL change.
    @State private var fileSizeText: String? = nil

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
                if let sizeText = fileSizeText {
                    Text(sizeText)
                        .font(.system(size: 10)).foregroundStyle(Theme.textDim)
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(Theme.bgTertiary)

            // Viewport
            Group {
                if let url = videoURL {
                    VideoWebView(videoURL: url, holder: webHolder)
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
        .task(id: videoURL) { refreshFileSize() }
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

    /// Recompute the cached, formatted file size for the info bar.
    /// Called only when `videoURL` changes (via `.task(id:)`) so we
    /// don't touch the filesystem on every `body` evaluation.
    private func refreshFileSize() {
        guard let url = videoURL,
              let size = try? FileManager.default
                .attributesOfItem(atPath: url.path)[.size] as? Int64 else {
            fileSizeText = nil
            return
        }
        fileSizeText = ByteCountFormatter.string(fromByteCount: size,
                                                 countStyle: .file)
    }

    // MARK: - Screenshot
    //
    // Grab the frame the user is currently looking at, save it to the
    // Photos library, and offer a share fallback. For still images
    // (.png / .jpg) we just share the image file directly.
    //
    // The viewport is an HTML5 <video> inside a WKWebView, not an
    // AVPlayer, so there is no Swift-side player whose `currentTime()`
    // reflects the screen. Instead we ask the live WebView for the
    // <video> element's `currentTime` via JavaScript, then extract that
    // exact frame from the same asset with AVAssetImageGenerator (which
    // runs off-main so the UI doesn't stutter on a 1080p frame).
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
        // Video — ask the WebView's <video> for its current playback
        // time, then extract that frame. If the WebView isn't reachable
        // (or JS fails), fall back to t=0 so the action still works.
        readCurrentVideoTime { seconds in
            let time = CMTime(seconds: max(0, seconds),
                              preferredTimescale: 600)
            extractFrame(from: url, at: time)
        }
    }

    /// Read the on-screen <video> element's currentTime (seconds) from
    /// the live WKWebView. Completion is delivered on the main queue;
    /// falls back to 0 when the WebView or the value isn't available.
    private func readCurrentVideoTime(_ completion: @escaping (Double) -> Void) {
        guard let wv = webHolder.webView else {
            completion(0)
            return
        }
        wv.evaluateJavaScript("document.getElementById('v').currentTime") { value, _ in
            let seconds = (value as? NSNumber)?.doubleValue ?? 0
            completion(seconds)
        }
    }

    private func extractFrame(from url: URL, at time: CMTime) {
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

/// Weak handle to the live video WKWebView so the screenshot action can
/// query the <video> element's current playback time. Held by PreviewPane
/// as a @StateObject and populated by VideoWebView when its WKWebView is
/// created.
final class WebViewHolder: ObservableObject {
    weak var webView: WKWebView?
}

private struct VideoWebView: UIViewRepresentable {
    let videoURL: URL
    let holder: WebViewHolder

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
        holder.webView = wv
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
        let name = videoURL.lastPathComponent
        let ext = videoURL.pathExtension.lowercased()
        // An .html output is a self-contained file with the video
        // base64-embedded as a data URI. Loading that multi-MB data URI
        // into WKWebView exhausts the WebContent memory limit and crashes
        // the app on iPad — so we DON'T preview the html itself. The
        // render writes the html next to its source .mp4 (same basename),
        // so play that lightweight sibling instead. The .html stays as the
        // export/save artifact (full size, no cap). Only if the sibling
        // mp4 is somehow missing do we fall back to loading the html.
        if ext == "html" {
            let siblingMP4 = dir.appendingPathComponent(
                videoURL.deletingPathExtension().lastPathComponent + ".mp4")
            if FileManager.default.fileExists(atPath: siblingMP4.path) {
                let phtml = Self.playerHTML(
                    videoFilename: siblingMP4.lastPathComponent, mime: "video/mp4")
                let htmlURL = dir.appendingPathComponent("_preview_player.html")
                if (try? phtml.write(to: htmlURL, atomically: true, encoding: .utf8)) != nil {
                    wv.loadFileURL(htmlURL, allowingReadAccessTo: dir)
                    return
                }
            }
            wv.loadFileURL(videoURL, allowingReadAccessTo: dir)
            return
        }
        // Images (gif / png / jpg) must render in an <img> tag — a GIF or
        // PNG shoved into <video> fails to load ("Video failed to load").
        // Manim outputs a .gif when the user picks the GIF format, so the
        // preview has to handle images too, not just video.
        let isImage = ["gif", "png", "jpg", "jpeg", "webp"].contains(ext)
        let mime: String = {
            switch ext {
            case "mp4", "m4v": return "video/mp4"
            case "mov":         return "video/quicktime"
            case "webm":        return "video/webm"
            default:            return "video/mp4"
            }
        }()
        let html = isImage
            ? Self.imageHTML(filename: name)
            : Self.playerHTML(videoFilename: name, mime: mime)
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

    /// Escape a filename for embedding in an HTML attribute. Manim names
    /// are ASCII so this is mostly defensive.
    private static func escapeAttr(_ s: String) -> String {
        s.replacingOccurrences(of: "\"", with: "&quot;")
         .replacingOccurrences(of: "<", with: "&lt;")
         .replacingOccurrences(of: ">", with: "&gt;")
    }

    /// HTML5 video player template. The `<source>` tag uses a relative
    /// filename so WebKit resolves it against the HTML file's directory
    /// — same dir we hand to `allowingReadAccessTo:`. The script auto-
    /// plays muted (iOS requires `muted` for unattended playback) and
    /// loops.
    private static func playerHTML(videoFilename: String, mime: String) -> String {
        let safeName = escapeAttr(videoFilename)
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

    /// Still / animated-image template (GIF, PNG, JPEG). An animated GIF
    /// loops on its own; a PNG is shown statically. Centered, letterboxed,
    /// pixel-art-friendly nearest-neighbour is avoided so anti-aliased
    /// Manim output stays smooth.
    private static func imageHTML(filename: String) -> String {
        let safeName = escapeAttr(filename)
        return """
        <!DOCTYPE html>
        <html><head><meta charset="UTF-8">
        <meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
        <style>
        *{margin:0;padding:0;box-sizing:border-box;-webkit-user-select:none;user-select:none;-webkit-tap-highlight-color:transparent}
        html,body{height:100%;background:#0A0A0F;overflow:hidden}
        .player{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:#000}
        img{max-width:100%;max-height:100%;object-fit:contain;background:#000}
        </style></head>
        <body>
        <div class="player"><img id="im" src="\(safeName)"></div>
        <script>
        const im=document.getElementById('im');
        im.addEventListener('error',()=>{
          document.body.innerHTML='<div style="color:#f87171;padding:18px;font-size:13px;font-family:-apple-system">Image failed to load</div>';
        });
        </script>
        </body></html>
        """
    }
}
