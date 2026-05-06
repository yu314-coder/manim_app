// PreviewView.swift — AVPlayer-backed video preview with native
// transport controls (AVPlayerView's built-in inline scrubber +
// play/pause + volume + share) plus a custom overlay header
// showing the filename + reveal-in-Finder + open-in-default-app.
//
// AVPlayerView (NSView, AVKit) does the heavy lifting — controls
// auto-hide, scrubber works, fullscreen works. We just wrap and
// add the header strip on top.
import SwiftUI
import AVKit
import AppKit

struct PreviewView: View {
    @EnvironmentObject var app: AppState
    let url: URL?

    var body: some View {
        ZStack {
            Theme.bgDeepest.ignoresSafeArea()
            VStack(spacing: 0) {
                previewHeader(url)
                if let url = url {
                    content(for: url)
                } else {
                    emptyState
                }
            }
        }
    }

    @ViewBuilder
    private func content(for url: URL) -> some View {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "mp4", "mov", "m4v", "webm":
            AVPlayerViewRepresentable(url: url)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        case "png", "jpg", "jpeg", "gif", "webp", "heic":
            if let nsImg = NSImage(contentsOf: url) {
                Image(nsImage: nsImg)
                    .resizable()
                    .scaledToFit()
                    .padding(20)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                emptyState
            }
        default:
            VStack(spacing: 8) {
                Image(systemName: "doc")
                    .font(.system(size: 32))
                    .foregroundStyle(Theme.textDim)
                Text(url.lastPathComponent)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private func previewHeader(_ url: URL?) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "play.rectangle.fill")
                .foregroundStyle(Theme.indigo)
            Text(url?.lastPathComponent ?? "Preview")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1).truncationMode(.middle)
            Spacer()

            // Quality picker — applies to the next ⌘R render. Quick
            // Preview (⇧⌘R) ignores this and is hard-wired to 480p15.
            HStack(spacing: 4) {
                Image(systemName: "speedometer")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textDim)
                Picker("", selection: $app.renderQuality) {
                    ForEach(RenderQuality.allCases) { q in
                        Text(q.label).tag(q)
                    }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .controlSize(.small)
                .frame(width: 110)
                .tint(Theme.indigo)
                .help("Render quality (applies to ⌘R)")
            }

            if let url = url {
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([url])
                } label: {
                    Image(systemName: "magnifyingglass.circle")
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.textSecondary)
                }
                .buttonStyle(.plain)
                .help("Reveal in Finder")
                Button {
                    NSWorkspace.shared.open(url)
                } label: {
                    Image(systemName: "arrow.up.right.square")
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.textSecondary)
                }
                .buttonStyle(.plain)
                .help("Open with default app")
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 7)
        .background(Theme.bgSecondary)
        .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                 alignment: .bottom)
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "play.rectangle")
                .font(.system(size: 44))
                .foregroundStyle(Theme.textDim)
                .symbolEffect(.pulse, options: .repeating)
            Text("No preview yet")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
            Text("⌘R = Render  ·  ⇧⌘R = Preview")
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(Theme.textDim)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - AVPlayerView wrapper

/// Native NSView-backed `AVPlayerView` (AVKit) with the inline
/// transport bar — scrubber, time labels, play/pause/volume
/// controls, AirPlay, fullscreen. Significantly nicer than
/// SwiftUI's `VideoPlayer` for a desktop preview pane.
struct AVPlayerViewRepresentable: NSViewRepresentable {
    let url: URL
    func makeNSView(context: Context) -> AVPlayerView {
        let v = AVPlayerView()
        v.player = AVPlayer(url: url)
        v.controlsStyle = .inline
        v.showsFullScreenToggleButton = true
        v.showsTimecodes = false
        v.allowsPictureInPicturePlayback = true
        v.player?.isMuted = false
        // Auto-play on appear so the user sees the result immediately
        // after a render finishes.
        v.player?.play()
        return v
    }
    func updateNSView(_ v: AVPlayerView, context: Context) {
        // Replace the player when the URL changes (new render).
        if (v.player?.currentItem?.asset as? AVURLAsset)?.url != url {
            v.player = AVPlayer(url: url)
            v.player?.play()
        }
    }
}
