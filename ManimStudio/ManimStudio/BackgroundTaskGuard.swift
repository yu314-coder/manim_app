// BackgroundTaskGuard.swift — keeps an active manim render running
// when the user switches to another app.
//
// iOS 26 and later: each render submits a continued-processing task
// (BGContinuedProcessingTask), the system's way to let work the user just
// started keep running after they leave the app. iOS shows it as a Live
// Activity with the render's progress and a Cancel button, and keeps the
// whole process running while the task lasts — see RenderContinuedTask.
//
// iOS can end that task at any time: Cancel in the Live Activity, a render
// that looks stalled, or a device that needs its resources back. It never
// says which, so an ended task doesn't end the render: the app is suspended,
// the render pauses, and it carries on when the user returns (Stop in the
// app ends it). Coming back re-arms the task, so they can leave again.
//
// Earlier iOS, or until iOS starts the task: the standard
// UIApplication.beginBackgroundTask grace window, about 30 s, after which
// iOS suspends the app and the render pauses until it's reopened. The
// expiration handler ends the token cleanly so iOS doesn't kill the whole
// app for misbehaving.
//
// iOS also closes background apps outright when memory runs short. That
// leaves nothing to handle, so a marker file records a running render and
// the next launch says in the terminal that it didn't finish — see
// UnfinishedRender.
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
    /// The render being carried: its background-task name, its title in the
    /// system UI and when it started. Nil between renders.
    private var render: (label: String, title: String, started: Date)?
    private var observers: [NSObjectProtocol] = []

    /// Default-on preference, surfaced in Settings → Rendering.
    private var keepAwakeEnabled: Bool {
        UserDefaults.standard.object(forKey: "manim_keep_awake") as? Bool ?? true
    }

    /// Call when a render starts, from the user's action while the app is in
    /// the foreground. `title` names it in the system's progress UI.
    /// Idempotent — nested begins are coalesced into the existing one.
    func begin(label: String = "render", title: String) {
        guard render == nil else { return }
        let started = Date()
        render = (label, title, started)
        takeGraceWindow()
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
            submitContinuedTask()
        }
        UnfinishedRender.mark(title: title, started: started, inBackground: false)
        observeAppState()
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
        render = nil
        UnfinishedRender.clear()
        observers.forEach { NotificationCenter.default.removeObserver($0) }
        observers = []
    }

    /// The ~30 s of background time every app gets. Taken again when the
    /// user comes back, since iOS ends it each time they leave.
    private func takeGraceWindow() {
        guard token == .invalid, let render else { return }
        token = UIApplication.shared.beginBackgroundTask(withName: render.label) { [weak self] in
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
    }

    private func endGraceWindow() {
        if token != .invalid {
            UIApplication.shared.endBackgroundTask(token)
            token = .invalid
        }
    }

    @available(iOS 26.0, *)
    private func submitContinuedTask() {
        guard let render else { return }
        let task = RenderContinuedTask(title: render.title) { [weak self] in
            // iOS ended the task. With the app on screen the render simply
            // goes on, so re-arm now; otherwise when the user comes back.
            if UIApplication.shared.applicationState == .active {
                self?.rearm()
            }
        }
        if task.submit() { continued = task }
    }

    /// While a render runs: note when the app leaves (for UnfinishedRender)
    /// and re-arm the background task when it comes back.
    private func observeAppState() {
        guard observers.isEmpty else { return }
        let center = NotificationCenter.default
        observers.append(center.addObserver(
            forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: .main
        ) { [weak self] _ in
            guard let render = self?.render else { return }
            UnfinishedRender.mark(title: render.title, started: render.started, inBackground: true)
        })
        observers.append(center.addObserver(
            forName: UIApplication.didBecomeActiveNotification, object: nil, queue: .main
        ) { [weak self] _ in
            guard let self, let render = self.render else { return }
            UnfinishedRender.mark(title: render.title, started: render.started, inBackground: false)
            self.rearm()
        })
    }

    /// Back in the app with the render still going: take back the grace
    /// window and, if iOS ended the continued-processing task, submit a new
    /// one — the user can leave again and the render keeps going.
    private func rearm() {
        guard render != nil else { return }
        takeGraceWindow()
        if #available(iOS 26.0, *),
           let task = continued as? RenderContinuedTask, task.expiredByIOS {
            Self.note("Rendering again. Background rendering is back on, so you can leave ManimStudio again.")
            submitContinuedTask()
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
/// active. It ends a task whose progress stops moving, and a render has long
/// stretches that write no frames: setup, typesetting a formula, one slow
/// high-resolution frame, writing the video. So progress comes from
/// `_render_progress.json`, which the render wrapper rewrites as frames and
/// formulas are done (PythonRuntime.renderProgressURL), and in between it
/// keeps creeping for as long as the render shows signs of life.
@available(iOS 26.0, *)
final class RenderContinuedTask {
    /// Info.plist BGTaskSchedulerPermittedIdentifiers holds "<prefix>.*".
    /// Every task uses its own suffix: registering an identifier twice
    /// terminates the app.
    private static let identifierPrefix = "euleryu.ManimStudio.render"

    /// How long progress keeps creeping with nothing new from the render —
    /// no frame, formula or phase. Well past the slowest formula (300 s) or
    /// frame; past it, a stuck render is left for iOS to end, which pauses
    /// it rather than burning battery.
    private static let stallLimit: TimeInterval = 15 * 60

    private let identifier = "\(identifierPrefix).\(UUID().uuidString)"
    private var title: String
    private let onExpired: () -> Void
    private var task: BGContinuedProcessingTask?
    /// Set once the task is over; a task that starts after that is
    /// completed straight away.
    private var outcome: Bool?
    /// True once iOS ended the task before the render did.
    private(set) var expiredByIOS = false
    private var poller: Timer?
    private var subtitle = "Starting…"
    /// The render's last reported phase (see readProgress).
    private var phase = ""
    /// The fraction the progress bar shows. It never goes back: manim finds
    /// its animations as it goes, and each new one would otherwise pull the
    /// bar back — which is what a stalled task looks like.
    private var shown = 0.0
    private var lastSignature = ""
    private var lastChange = Date()

    init(title: String, onExpired: @escaping () -> Void) {
        self.title = title
        self.onExpired = onExpired
    }

    /// Whether iOS has started the task and it is still carrying the render.
    var isRunning: Bool { task != nil && outcome == nil }

    /// Registers the launch handler and submits the request. False when iOS
    /// refuses it outright; on iOS 27 a refusal arrives later instead. Either
    /// way the terminal says so, and the render relies on the grace window.
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
        // If iOS is busy, wait for room rather than give up: the render is
        // already running, and the task helps whenever it starts.
        request.strategy = .queue
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
        // A queued task hasn't started, and until it does leaving the app
        // pauses the render — worth knowing.
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) {
            MainActor.assumeIsolated {
                if self.task == nil && self.outcome == nil && !self.reportedNotStarted {
                    self.reportedNotStarted = true
                    BackgroundTaskGuard.note("iOS hasn't started this render's background task yet; it may be busy. Until it does, leaving ManimStudio pauses the render after about 30 seconds.")
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
        guard let task else {
            // Still queued: withdraw it, so it doesn't start for nothing.
            BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: identifier)
            return
        }
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
        bgTask.progress.totalUnitCount = 1_000_000
        bgTask.progress.completedUnitCount = 0
        lastChange = Date()
        bgTask.expirationHandler = { [weak self] in
            DispatchQueue.main.async {
                MainActor.assumeIsolated { self?.expired() }
            }
        }
        poller = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.readProgress() }
        }
    }

    /// Cancel in the Live Activity, a task iOS judged stalled, or a device
    /// that needs its resources back — iOS doesn't say which. None of them
    /// is a reason to throw the render away: it pauses with the app and
    /// carries on when the user returns, where Stop ends it.
    private func expired() {
        guard outcome == nil else { return }
        expiredByIOS = true
        if UIApplication.shared.applicationState != .active {
            if phase == "waiting" {
                BackgroundTaskGuard.note("iOS ended the render's background time. The video will be written when you return to ManimStudio.")
            } else {
                BackgroundTaskGuard.note("iOS ended the render's background time. The render pauses and carries on when you return to ManimStudio; tap Stop there to end it.")
                RenderNotifier.renderPaused()
            }
        }
        finish(success: false)
        onExpired()
    }

    private func readProgress() {
        guard let task else { return }
        let info = PythonRuntime.shared.renderProgressURL()
            .flatMap { try? Data(contentsOf: $0) }
            .flatMap { (try? JSONSerialization.jsonObject(with: $0)) as? [String: Any] }
            ?? [:]
        let frames = info["frames"] as? Int ?? 0
        let newPhase = info["phase"] as? String ?? ""
        let play = info["play"] as? Int ?? -1
        let playFrames = info["play_frames"] as? Int ?? 0
        let playExpected = info["play_expected"] as? Int ?? 0
        let formulas = info["tex"] as? Int ?? 0
        let typesetting = info["tex_pending"] as? Bool ?? false
        let joined = info["joined"] as? Int ?? 0
        if newPhase == "waiting" && phase != "waiting" {
            RenderNotifier.needsApp(scene: info["scene"] as? String)
        }
        phase = newPhase

        // Any of these changing means the render moved.
        let signature = "\(newPhase)|\(frames)|\(play)|\(formulas)|\(typesetting)|\(joined)"
        if signature != lastSignature {
            lastSignature = signature
            lastChange = Date()
        }
        let alive = Date().timeIntervalSince(lastChange) < Self.stallLimit

        // Frames written count as done; what's left of the current animation,
        // plus a margin for writing the file, is still to do. Later
        // animations aren't known yet, so the bar never goes back for them.
        if newPhase == "render" {
            let left = max(playExpected - playFrames, 0)
            let estimate = Double(frames) / Double(frames + left + max(frames / 10, 1))
            shown = max(shown, min(estimate, 0.95))
        }
        // Between frames — setup, a formula, one slow frame, writing the
        // video — keep creeping toward the end while the render is alive,
        // slower the closer it gets, never arriving.
        if alive {
            shown += (0.99 - shown) * 0.0005
        }
        let progress = task.progress
        progress.completedUnitCount = max(progress.completedUnitCount,
                                          Int64(shown * Double(progress.totalUnitCount)))

        let newSubtitle: String
        switch newPhase {
        case "render":
            let pct = playExpected > 0 ? 100 * min(playFrames, playExpected) / playExpected : 0
            newSubtitle = typesetting
                ? "Animation \(play + 1) · typesetting a formula…"
                : "Animation \(play + 1) · \(pct)%"
        case "finishing":
            newSubtitle = "Writing the video…"
        case "waiting":
            // Every frame is rendered, but a video this size can only be
            // written with the hardware encoder, which iOS gives an app on
            // screen (manimstudio_encoder.py).
            newSubtitle = "Open ManimStudio to finish the video"
        default:
            newSubtitle = typesetting ? "Typesetting formulas…" : "Setting up…"
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

/// A render that was running when the app last stopped. iOS closes
/// background apps without warning when memory runs short, and a crash ends
/// the app the same way; either way the render just vanishes. A marker file
/// written while a render runs survives that, and the next launch reports it.
enum UnfinishedRender {
    private static var url: URL? {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
            .appendingPathComponent("render-in-progress.plist")
    }

    static func mark(title: String, started: Date, inBackground: Bool) {
        guard let url else { return }
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                 withIntermediateDirectories: true)
        let info: [String: Any] = ["title": title, "started": started, "background": inBackground]
        if let data = try? PropertyListSerialization.data(fromPropertyList: info,
                                                          format: .binary, options: 0) {
            try? data.write(to: url, options: .atomic)
        }
    }

    static func clear() {
        if let url { try? FileManager.default.removeItem(at: url) }
    }

    /// Called once at launch: says in the terminal if the last render never
    /// ended, and how the app was left when it stopped.
    static func reportIfAny() {
        guard let url, let data = try? Data(contentsOf: url) else { return }
        clear()
        let info = (try? PropertyListSerialization.propertyList(from: data, format: nil)) as? [String: Any] ?? [:]
        let title = info["title"] as? String ?? "The last render"
        let when = (info["started"] as? Date).map {
            " (started \($0.formatted(date: .abbreviated, time: .shortened)))"
        } ?? ""
        let text = (info["background"] as? Bool ?? false)
            ? "\(title)\(when) didn't finish: ManimStudio was closed while it was in the background — by iOS, usually to free memory for another app, or from the app switcher. Keeping ManimStudio open, or a lower quality, avoids it."
            : "\(title)\(when) didn't finish: ManimStudio quit while it was rendering."
        NSLog("%@", "[render] \(text)")
        BackgroundTaskGuard.note(text)
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

    /// iOS suspended the app mid-render: its background time ran out, or it
    /// ended the continued-processing task. The render resumes on return.
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
