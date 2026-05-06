// PreviewPane.swift — video/image preview with file-info bar.
import SwiftUI
import AVKit

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

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "play.rectangle")
                    .font(.system(size: 11)).foregroundStyle(Theme.accentSecondary)
                Text("Preview").font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                toolBtn("camera", "Screenshot")
                toolBtn("arrow.up.left.and.arrow.down.right", "Fullscreen")
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

    @ViewBuilder
    private func toolBtn(_ icon: String, _ tooltip: String) -> some View {
        Button {} label: {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 24, height: 24)
                .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
        }
        .buttonStyle(.plain).help(tooltip)
    }
}
