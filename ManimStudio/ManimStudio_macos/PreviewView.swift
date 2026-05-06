// PreviewView.swift — AVKit player for the rendered MP4 / MOV.
// Falls back to an icon + filename when the URL points at a GIF
// or PNG, since AVPlayer doesn't decode those.
import SwiftUI
import AVKit
import AppKit

struct PreviewView: View {
    let url: URL?

    var body: some View {
        ZStack {
            Theme.bgPrimary.ignoresSafeArea()
            if let url = url {
                content(for: url)
            } else {
                emptyState
            }
        }
    }

    @ViewBuilder
    private func content(for url: URL) -> some View {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "mp4", "mov", "m4v", "webm":
            VideoPlayer(player: AVPlayer(url: url))
        case "png", "jpg", "jpeg", "gif":
            // NSImage handles each of these including animated GIF
            // (with the right tweaks; SwiftUI's Image will at least
            // show the first frame).
            if let nsImg = NSImage(contentsOf: url) {
                Image(nsImage: nsImg)
                    .resizable()
                    .scaledToFit()
                    .padding()
            } else {
                emptyState
            }
        default:
            VStack(spacing: 8) {
                Image(systemName: "doc")
                    .font(.system(size: 28))
                Text(url.lastPathComponent)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "play.rectangle")
                .font(.system(size: 44))
                .foregroundStyle(Theme.textDim)
            Text("No preview yet")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
            Text("Hit Render or Preview")
                .font(.system(size: 11))
                .foregroundStyle(Theme.textDim)
        }
    }
}
