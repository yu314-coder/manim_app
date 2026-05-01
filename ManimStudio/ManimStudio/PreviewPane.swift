// PreviewPane.swift — video/image preview with file-info bar.
import SwiftUI
import AVKit

struct PreviewPane: View {
    @Binding var videoURL: URL?

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
                if let url = videoURL {
                    VideoPlayer(player: AVPlayer(url: url))
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
