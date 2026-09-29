// BackgroundTaskGuard.swift — keeps an active manim render running
// when the user switches to another app or locks the iPad.
//
// iOS 26 and later: each render submits a continued-processing task
// (BGContinuedProcessingTask), the system's way to let work the user just
// started keep running after they leave the app. iOS shows it as a Live
// Activity with the render's progress and a Cancel button, and keeps the
// whole process running until the render ends — see RenderContinuedTask.
//
// Earlier iOS, or when the system won't start that task: the standard
// UIApplication.beginBackgroundTask grace window, about 30 s, after which
// iOS suspends the app and the render pauses until it's reopened. The
// expiration handler ends the token cleanly so iOS doesn't kill the whole
// app for misbehaving.
//
// History: an earlier version also activated an `.ambient` /
// `mixWithOthers` AVAudioSession so the app would qualify for the
// "audio" UIBackgroundMode and stay alive longer. App Review 2.5.4
// rejected build 74 because we declared the audio mode without
// having a real audio feature. Removed both the Info.plist `audio`
// key AND the AVAudioSession activation.
import UIKit
import BackgroundTasks

final class BackgroundTaskGuard {
    static let shared = BackgroundTaskGuard()

    private var token: UIBackgroundTaskIdentifier = .invalid
    /// True while we hold the screen awake, so end() only clears the flag
    /// it actually set (never stomps a hold taken by something else).
    private var heldIdleTimer = false
    /// The render's continued-processing task on iOS 26+ (a
    /// RenderContinuedTask; typed AnyObject so the stored property needs no
    /// availability annotation).
    private var continued: AnyObject?

    /// Default-on preference, surfaced in Settings → Rendering.
    private var keepAwakeEnabled: Bool {
        UserDefaults.standard.object(forKey: "manim_keep_awake") as? Bool ?? true
    }

    /// Call when a render starts, from the user's action while the app is in
    /// the foreground. `title` names it in the system's progress UI;
    /// `onExpire` stops it when the user cancels there or iOS ends the task.
    /// Idempotent — nested begins are coalesced into the existing one.
    func begin(label: String = "render", title: String, onExpire: @escaping () -> Void) {
        guard token == .invalid else { return }
        token = UIApplication.shared.beginBackgroundTask(withName: label) { [weak self] in
            // Expiration handler: iOS is about to suspend us. End the token
            // gracefully — leaving it open would mark the app as misbehaving
            // and shorten future grace periods. A continued-processing task,
            // if one is running, keeps the render going regardless.
            self?.endGraceWindow()
        }
        // Auto-lock ends a render as surely as a crash: the screen sleeps,
        // iOS suspends us, and a 10-minute 4K render dies at 90%. Hold the
        // idle timer for the duration. Paired with end() below, which every
        // render exit path (success, failure, user stop) already calls.
        if keepAwakeEnabled {
            UIApplication.shared.isIdleTimerDisabled = true
            heldIdleTimer = true
        }
        if #available(iOS 26.0, *) {
            // The previous render's progress mustn't show up in this one's.
            if let url = PythonRuntime.shared.renderProgressURL() {
                try? FileManager.default.removeItem(at: url)
            }
            let task = RenderContinuedTask(title: title, onExpire: onExpire)
            if task.submit() { continued = task }
        }
    }

    /// Call when the render finishes, fails, or is stopped. `success` is what
    /// the system's progress UI reports.
    func end(success: Bool = false) {
        endGraceWindow()
        if heldIdleTimer {
            UIApplication.shared.isIdleTimerDisabled = false
            heldIdleTimer = false
        }
        if #available(iOS 26.0, *), let task = continued as? RenderContinuedTask {
            task.finish(success: success)
        }
        continued = nil
    }

    private func endGraceWindow() {
        if token != .invalid {
            UIApplication.shared.endBackgroundTask(token)
            token = .invalid
        }
    }
}

/// One render carried by an iOS 26 continued-processing task.
///
/// The system shows the task as a Live Activity — title, subtitle, progress
/// bar and a Cancel button — and keeps the process running while it's
/// active. It ends a task that stops reporting progress, so progress comes
/// from `_render_progress.json`, which the render wrapper rewrites as frames
/// are produced (PythonRuntime.renderProgressURL). Manim discovers its
/// animations as construct() runs, so only the current one's length is
/// known: the total grows as the render goes, and the subtitle names the
/// animation and how far through it is.
@available(iOS 26.0, *)
final class RenderContinuedTask {
    /// Info.plist BGTaskSchedulerPermittedIdentifiers holds "<prefix>.*".
    /// Every render uses its own suffix: registering an identifier twice
    /// terminates the app.
    private static let identifierPrefix = "euleryu.ManimStudio.render"

    private let identifier = "\(identifierPrefix).\(UUID().uuidString)"
    private var title: String
    private let onExpire: () -> Void
    private var task: BGContinuedProcessingTask?
    /// Set once the render has ended; a task that starts after that is
    /// completed straight away.
    private var outcome: Bool?
    private var poller: Timer?
    private var subtitle = "Starting…"

    init(title: String, onExpire: @escaping () -> Void) {
        self.title = title
        self.onExpire = onExpire
    }

    /// Registers the launch handler and submits the request. False when iOS
    /// won't run the task now; the render then relies on the ordinary
    /// grace window.
    func submit() -> Bool {
        // The handler keeps a strong reference: it can run after the render
        // has ended, and must still complete the task.
        let registered = BGTaskScheduler.shared.register(
            forTaskWithIdentifier: identifier, using: .main
        ) { task in
            MainActor.assumeIsolated { self.started(task) }
        }
        guard registered else {
            NSLog("%@", "[render] background task identifier not permitted: \(identifier)")
            return false
        }
        let request = BGContinuedProcessingTaskRequest(
            identifier: identifier, title: title, subtitle: subtitle)
        // Start now or not at all: a render queued behind other work would
        // begin its background life long after the user has moved on.
        request.strategy = .fail
        do {
            try BGTaskScheduler.shared.submit(request)
            return true
        } catch {
            NSLog("%@", "[render] background task not started: \(error)")
            return false
        }
    }

    /// Completes the task with the render's result. Safe to call more than once.
    func finish(success: Bool) {
        guard outcome == nil else { return }
        outcome = success
        poller?.invalidate()
        poller = nil
        guard let task else { return }
        if success {
            task.progress.completedUnitCount = task.progress.totalUnitCount
        }
        task.setTaskCompleted(success: success)
        self.task = nil
    }

    private func started(_ bgTask: BGTask) {
        guard let bgTask = bgTask as? BGContinuedProcessingTask else {
            bgTask.setTaskCompleted(success: false)
            return
        }
        if let outcome {
            bgTask.setTaskCompleted(success: outcome)
            return
        }
        task = bgTask
        bgTask.progress.totalUnitCount = 1
        bgTask.progress.completedUnitCount = 0
        bgTask.expirationHandler = { [weak self] in
            DispatchQueue.main.async {
                MainActor.assumeIsolated { self?.expired() }
            }
        }
        poller = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.readProgress() }
        }
    }

    /// The user cancelled from the system UI, or iOS is ending the task.
    private func expired() {
        guard outcome == nil else { return }
        onExpire()
        finish(success: false)
    }

    private func readProgress() {
        guard let task, let url = PythonRuntime.shared.renderProgressURL(),
              let data = try? Data(contentsOf: url),
              let info = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        else { return }
        let progress = task.progress
        let frames = Int64(info["frames"] as? Int ?? 0)
        let newSubtitle: String
        switch info["phase"] as? String {
        case "render":
            let play = (info["play"] as? Int ?? 0) + 1
            let playFrames = Int64(info["play_frames"] as? Int ?? 0)
            let playExpected = Int64(info["play_expected"] as? Int ?? 0)
            // Frames written count as done; what's left of the current
            // animation, plus a margin for writing the final file, is still
            // to do. Later animations aren't known yet.
            let left = max(playExpected - playFrames, 0)
            progress.totalUnitCount = frames + left + max(frames / 10, 1)
            progress.completedUnitCount = frames
            let pct = playExpected > 0 ? Int(100 * min(playFrames, playExpected) / playExpected) : 0
            newSubtitle = "Animation \(play) · \(pct)%"
        case "finishing":
            // Combining and writing the video has no frame count. Keep
            // moving toward the end — a task that stops moving is ended.
            let step = max((progress.totalUnitCount - progress.completedUnitCount) / 50, 1)
            progress.completedUnitCount += step
            if progress.completedUnitCount >= progress.totalUnitCount {
                progress.totalUnitCount = progress.completedUnitCount + 1
            }
            newSubtitle = "Writing the video…"
        default:
            newSubtitle = "Setting up…"
        }
        var newTitle = title
        if let scene = info["scene"] as? String, !scene.isEmpty {
            newTitle = title.hasPrefix("Previewing") ? "Previewing \(scene)" : "Rendering \(scene)"
        }
        if newTitle != title || newSubtitle != subtitle {
            title = newTitle
            subtitle = newSubtitle
            task.updateTitle(newTitle, subtitle: newSubtitle)
        }
    }
}
