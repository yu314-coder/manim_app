// BackgroundTaskGuard.swift — keeps an active manim render running
// when the user switches to another app or locks the iPad. iOS
// suspends an app's foreground execution ~5 s after it goes to the
// background; UIApplication.beginBackgroundTask asks the system for a
// "finishing" extension (typically up to 30 s, sometimes minutes).
// That's not unlimited — long renders may still get suspended — but
// it covers the common case of "lock the iPad while the render
// finishes". The expiration handler ends the token cleanly so iOS
// doesn't kill the whole app for misbehaving.
//
// We also activate an audio session so the render can survive longer
// if needed. No audio is actually played; setting an `.ambient` /
// `mixWithOthers` session is enough to qualify for the audio
// background mode without interrupting other apps' music. This is
// optional and only kicks in when UIBackgroundModes contains "audio"
// in Info.plist — without that key the AVAudioSession activation
// no-ops and we still get the begin/end-task cycle.
import UIKit
import AVFoundation

final class BackgroundTaskGuard {
    static let shared = BackgroundTaskGuard()

    private var token: UIBackgroundTaskIdentifier = .invalid
    private var audioActive = false

    /// Call when an interruptible long task starts. Idempotent —
    /// nested begins are coalesced into the existing token.
    func begin(label: String = "render") {
        guard token == .invalid else { return }
        token = UIApplication.shared.beginBackgroundTask(withName: label) { [weak self] in
            // Expiration handler: iOS is about to suspend us. End
            // gracefully — leaving the token open would mark the app
            // as misbehaving and shorten future grace periods.
            self?.end()
        }
        // Best-effort audio-session activation. Harmless if the
        // background-audio entitlement isn't enabled — the call just
        // returns false / throws and we fall through.
        if !audioActive {
            do {
                try AVAudioSession.sharedInstance().setCategory(
                    .ambient,
                    mode: .default,
                    options: [.mixWithOthers])
                try AVAudioSession.sharedInstance().setActive(true,
                                                              options: [])
                audioActive = true
            } catch {
                audioActive = false
            }
        }
    }

    /// Call when the task finishes (success, failure, or user stop).
    func end() {
        if token != .invalid {
            UIApplication.shared.endBackgroundTask(token)
            token = .invalid
        }
        if audioActive {
            try? AVAudioSession.sharedInstance().setActive(false,
                                                           options: [.notifyOthersOnDeactivation])
            audioActive = false
        }
    }
}
