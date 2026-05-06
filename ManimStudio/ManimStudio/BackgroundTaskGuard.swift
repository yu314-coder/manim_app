// BackgroundTaskGuard.swift — keeps an active manim render running
// when the user switches to another app or locks the iPad. iOS
// suspends an app's foreground execution ~5 s after it goes to the
// background; UIApplication.beginBackgroundTask asks the system for
// a "finishing" extension (typically up to 30 s, sometimes minutes).
// That's not unlimited — long renders may still get suspended — but
// it covers the common case of "lock the iPad while the render
// finishes". The expiration handler ends the token cleanly so iOS
// doesn't kill the whole app for misbehaving.
//
// History: an earlier version also activated an `.ambient` /
// `mixWithOthers` AVAudioSession so the app would qualify for the
// "audio" UIBackgroundMode and stay alive longer. App Review 2.5.4
// rejected build 74 because we declared the audio mode without
// having a real audio feature. Removed both the Info.plist `audio`
// key AND the AVAudioSession activation — we now rely solely on
// the standard beginBackgroundTask grace window, which is the
// correct API for "finishing-up" work like a render.
import UIKit

final class BackgroundTaskGuard {
    static let shared = BackgroundTaskGuard()

    private var token: UIBackgroundTaskIdentifier = .invalid

    /// Call when an interruptible long task starts. Idempotent —
    /// nested begins are coalesced into the existing token.
    func begin(label: String = "render") {
        guard token == .invalid else { return }
        token = UIApplication.shared.beginBackgroundTask(withName: label) { [weak self] in
            // Expiration handler: iOS is about to suspend us. End
            // gracefully — leaving the token open would mark the
            // app as misbehaving and shorten future grace periods.
            self?.end()
        }
    }

    /// Call when the task finishes (success, failure, or user stop).
    func end() {
        if token != .invalid {
            UIApplication.shared.endBackgroundTask(token)
            token = .invalid
        }
    }
}
