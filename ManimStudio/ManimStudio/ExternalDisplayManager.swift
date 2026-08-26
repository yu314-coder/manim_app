// ExternalDisplayManager.swift — intentionally inert: ManimStudio presents to
// a TV via plain AirPlay / HDMI MIRRORING, not separate external content.
//
// Why inert: the moment an app attaches its own UIWindow to a connected
// external-display scene, iOS STOPS mirroring the iPad and shows that window
// instead (which is how the "Manim Animation Studio" placeholder used to take
// over the TV). We want the opposite — the TV should mirror the iPad's
// full-screen Present view. So this manager deliberately does NOT observe
// scene connections and never creates an external window; iOS keeps mirroring.
//
// The singleton + isConnected / attachPlayer surface is kept so the
// presentation views compile unchanged. isConnected is permanently false
// (there is no separate external surface), which routes those views to the
// on-iPad full-screen path that the system mirrors.
import Combine
import AVFoundation

final class ExternalDisplayManager: ObservableObject {
    static let shared = ExternalDisplayManager()

    /// Permanently false: the app never draws separate external content, so a
    /// connected display simply mirrors the iPad.
    @Published private(set) var isConnected = false

    /// Kept for source compatibility with PresentationCoverView; unused while
    /// mirroring (there is no external surface to drive).
    @Published private(set) var externalPlayer: AVPlayer?

    private init() {}

    /// No-op while mirroring — retained so existing call sites compile.
    func attachPlayer(_ player: AVPlayer?) { externalPlayer = player }
}
