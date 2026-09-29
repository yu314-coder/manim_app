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
import UserNotifications

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
            // if one is running, keeps the render going regardless; without
            // one the render pauses here, so say so.
            guard let self else { return }
            if !self.continuedTaskRunning {
                Self.note("iOS paused the render in the background. It carries on when you return to ManimStudio.")
                RenderNotifier.renderPaused()
            }
            self.endGraceWindow()
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

    /// Whether iOS is running this render's continued-processing task.
    private var continuedTaskRunning: Bool {
        if #available(iOS 26.0, *), let task = continued as? RenderContinuedTask {
            return task.isRunning
        }
        return false
    }

    /// Writes a line into the terminal, where the render's own output goes.
    static func note(_ text: String) {
        let line = "\r\n\u{1b}[2m[background]\u{1b}[0m \(text)\r\n"
        line.withCString { cs in
            _ = Darwin.write(PTYBridge.shared.stdoutPipeWriteFD, cs, strlen(cs))
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
    /// The render's last reported phase (see readProgress).
    private var phase = ""

    init(title: String, onExpire: @escaping () -> Void) {
        self.title = title
        self.onExpire = onExpire
    }

    /// Whether iOS has started the task and it is still carrying the render.
    var isRunning: Bool { task != nil && outcome == nil }

    /// Registers the launch handler and submits the request. False when iOS
    /// refuses it outright; on iOS 27 a refusal arrives later instead. Either
    /// way the terminal says so, and the render relies on the ordinary grace
    /// window.
    func submit() -> Bool {
        // The handler keeps a strong reference: it can run after the render
        // has ended, and must still complete the task.
        let registered = BGTaskScheduler.shared.register(
            forTaskWithIdentifier: identifier, using: .main
        ) { task in
            MainActor.assumeIsolated { self.started(task) }
        }
        guard registered else {
            notStarted("its identifier isn't permitted")
            return false
        }
        let request = BGContinuedProcessingTaskRequest(
            identifier: identifier, title: title, subtitle: subtitle)
        // Start now or not at all: a render queued behind other work would
        // begin its background life long after the user has moved on.
        request.strategy = .fail
        if #available(iOS 27.0, *) {
            // submit(_:) couldn't report every way a submission fails, so on
            // iOS 26 some requests were silently never run. iOS 27's
            // replacement reports them all, and mustn't be called on the
            // main thread.
            DispatchQueue.global(qos: .userInitiated).async {
                BGTaskScheduler.shared.submitTaskRequest(request) { error in
                    guard let error else { return }
                    DispatchQueue.main.async {
                        MainActor.assumeIsolated { self.notStarted(error.localizedDescription) }
                    }
                }
            }
        } else {
            do {
                try BGTaskScheduler.shared.submit(request)
            } catch {
                notStarted(error.localizedDescription)
                return false
            }
        }
        // A task that iOS accepted but never started looks exactly like one
        // that is running, so check: with the .fail strategy it starts at once.
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) {
            MainActor.assumeIsolated {
                if self.task == nil && self.outcome == nil {
                    self.notStarted("it didn't start")
                }
            }
        }
        return true
    }

    /// iOS won't carry this render in the background. Only said once, and
    /// only while the render is still going.
    private var reportedNotStarted = false
    private func notStarted(_ reason: String) {
        NSLog("%@", "[render] background task not started: \(reason)")
        guard outcome == nil, task == nil, !reportedNotStarted else { return }
        reportedNotStarted = true
        let why = reason.trimmingCharacters(in: CharacterSet(charactersIn: ". "))
        BackgroundTaskGuard.note("iOS won't keep this render going in the background (\(why)). If you leave ManimStudio, it pauses until you come back.")
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
        if phase == "waiting" {
            // The frames are done and only the final video is left, which
            // needs the app on screen. Stopping would throw the render away;
            // left alone, it pauses with the app and finishes on return.
            BackgroundTaskGuard.note("iOS ended the render's background time. The video will be written when you return to ManimStudio.")
        } else {
            BackgroundTaskGuard.note("The render was cancelled from its Live Activity, or iOS ended its background time.")
            onExpire()
        }
        finish(success: false)
    }

    private func readProgress() {
        guard let task, let url = PythonRuntime.shared.renderProgressURL(),
              let data = try? Data(contentsOf: url),
              let info = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        else { return }
        let progress = task.progress
        let frames = Int64(info["frames"] as? Int ?? 0)
        let newPhase = info["phase"] as? String ?? ""
        if newPhase == "waiting" && phase != "waiting" {
            RenderNotifier.needsApp(scene: info["scene"] as? String)
        }
        phase = newPhase
        let newSubtitle: String
        switch newPhase {
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
        case "finishing", "waiting":
            // Combining and writing the video has no frame count. Keep
            // moving toward the end — a task that stops moving is ended.
            let step = max((progress.totalUnitCount - progress.completedUnitCount) / 50, 1)
            progress.completedUnitCount += step
            if progress.completedUnitCount >= progress.totalUnitCount {
                progress.totalUnitCount = progress.completedUnitCount + 1
            }
            // "waiting": every frame is rendered, but a video this size can
            // only be written with the hardware encoder, which iOS gives an
            // app on screen (manimstudio_encoder.py).
            newSubtitle = newPhase == "waiting"
                ? "Open ManimStudio to finish the video"
                : "Writing the video…"
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

/// Tells the user when a Final render ends while ManimStudio isn't on
/// screen. The save sheet is already waiting in the app, so the
/// notification's job is only to bring them back to it.
enum RenderNotifier {
    /// Asks for permission once, when the user starts a render — the moment
    /// the prompt makes sense, and while the app can still show it.
    static func requestPermissionIfNeeded() {
        Task {
            let center = UNUserNotificationCenter.current()
            guard await center.notificationSettings().authorizationStatus == .notDetermined
            else { return }
            _ = try? await center.requestAuthorization(options: [.alert, .sound])
        }
    }

    /// Posts "ready to save" or "didn't finish" if the app is in the
    /// background. `fileName` is the rendered file's name, when there is one.
    static func renderEnded(fileName: String?, success: Bool) {
        if success {
            post("Render finished",
                 "\(fileName ?? "Your video") is ready — open ManimStudio to save it to Files or Photos.")
        } else {
            post("Render didn't finish", "Open ManimStudio to see what went wrong in the terminal.")
        }
    }

    /// iOS suspended the app mid-render: no continued-processing task was
    /// carrying it (before iOS 26, or when the system declined one).
    static func renderPaused() {
        post("Render paused",
             "iOS paused ManimStudio in the background. Open it to carry on rendering.")
    }

    /// Every frame is rendered, but the video can only be written with the
    /// hardware encoder, which iOS gives an app on screen.
    static func needsApp(scene: String?) {
        post("Almost done",
             "Open ManimStudio to finish writing \(scene.map { "the \($0) video" } ?? "your video").")
    }

    /// One notification at a time: a newer state replaces the last one.
    private static func post(_ title: String, _ body: String) {
        guard UIApplication.shared.applicationState != .active else { return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        UNUserNotificationCenter.current().add(
            UNNotificationRequest(identifier: "render-status", content: content, trigger: nil))
    }
}

