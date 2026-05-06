// WelcomeView.swift — first-run wizard. Shown when the per-app
// virtualenv at ~/Library/Application Support/ManimStudio/venv/
// doesn't exist or is missing manim. Walks the user through
// picking a host Python, optionally installing Kokoro TTS, and
// kicks off VenvManager.setupFromScratch with a live log.
import SwiftUI

struct WelcomeView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var venv: VenvManager

    @State private var pickedPython: URL? = PythonResolver.pythonURL
    @State private var hostCandidates: [URL] = []
    @State private var installKokoro = false
    @State private var page: Page = .intro

    enum Page { case intro, picker, installing, done, failed }

    var body: some View {
        ZStack {
            // Animated bg gradient.
            LinearGradient(
                colors: [Theme.bgDeepest, Theme.bgPrimary, Theme.bgSecondary],
                startPoint: .topLeading, endPoint: .bottomTrailing)
            .ignoresSafeArea()
            // Faint orb glows for the high-tech feel.
            GeometryReader { geo in
                ZStack {
                    Circle()
                        .fill(Theme.indigo.opacity(0.15))
                        .blur(radius: 80)
                        .offset(x: -geo.size.width * 0.25,
                                y: -geo.size.height * 0.30)
                    Circle()
                        .fill(Theme.violet.opacity(0.18))
                        .blur(radius: 90)
                        .offset(x: geo.size.width * 0.30,
                                y: geo.size.height * 0.30)
                }
            }
            .ignoresSafeArea()

            content
                .frame(maxWidth: 640, maxHeight: 560)
                .glassCard(cornerRadius: 18)
                .padding(40)
        }
        .onAppear {
            scanHostCandidates()
            Task { await venv.probe() }
        }
        .onChange(of: venv.status) { _, newValue in
            switch newValue {
            case .ready:  page = .done
            case .failed: page = .failed
            case .creating, .installing: page = .installing
            default: break
            }
        }
    }

    // MARK: pages

    @ViewBuilder
    private var content: some View {
        switch page {
        case .intro:      intro
        case .picker:     picker
        case .installing: installing
        case .done:       done
        case .failed:     failed
        }
    }

    private var intro: some View {
        VStack(spacing: 18) {
            Image(systemName: "wand.and.stars")
                .font(.system(size: 56))
                .symbolRenderingMode(.palette)
                .foregroundStyle(Theme.indigo, Theme.violet)
                .padding(.top, 18)
            Text("Welcome to ManimStudio")
                .font(.system(size: 26, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Text("Let's set up a private Python virtual environment for your renders.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)

            VStack(alignment: .leading, spacing: 10) {
                row(icon: "shippingbox.fill",   text: "manim, numpy, scipy, matplotlib, Pillow")
                row(icon: "textformat",          text: "manim-fonts (custom font support)")
                row(icon: "waveform",            text: "Kokoro TTS (optional auto-narration)",
                    isToggle: true)
                row(icon: "internaldrive",       text: "lives at ~/Library/Application Support/ManimStudio/venv/")
            }
            .padding(.horizontal, 24)
            .padding(.top, 8)

            Spacer(minLength: 0)
            HStack {
                Spacer()
                Button { page = .picker } label: {
                    HStack(spacing: 8) {
                        Text("Continue").font(.system(size: 14, weight: .semibold))
                        Image(systemName: "arrow.right").font(.system(size: 12, weight: .bold))
                    }
                    .foregroundStyle(.white)
                    .padding(.horizontal, 20).padding(.vertical, 11)
                    .background(RoundedRectangle(cornerRadius: 10)
                        .fill(Theme.signatureGradient))
                    .shadow(color: Theme.glowPrimary, radius: 12, y: 3)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 24).padding(.bottom, 20)
        }
    }

    @ViewBuilder
    private func row(icon: String, text: String, isToggle: Bool = false) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(Theme.indigo)
                .frame(width: 22)
            if isToggle {
                Toggle(isOn: $installKokoro) {
                    Text(text).font(.system(size: 13))
                        .foregroundStyle(Theme.textPrimary)
                }
                .toggleStyle(.switch)
                .controlSize(.small)
            } else {
                Text(text).font(.system(size: 13))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
            }
        }
    }

    // ── Picker

    private var picker: some View {
        VStack(spacing: 14) {
            Image(systemName: "ladybug")
                .font(.system(size: 44))
                .foregroundStyle(Theme.violet)
                .padding(.top, 22)
            Text("Choose a host Python")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Text("ManimStudio uses this Python to **create** the venv — once setup finishes, the venv runs independently.")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 30)

            ScrollView {
                VStack(spacing: 6) {
                    ForEach(hostCandidates, id: \.self) { url in
                        candidateRow(url)
                    }
                    if hostCandidates.isEmpty {
                        Text("No python3.* found on PATH or in the usual install locations. Install Python 3.14 from python.org or `brew install python@3.14`.")
                            .font(.system(size: 12))
                            .foregroundStyle(Theme.error)
                            .padding(20)
                    }
                }
            }
            .frame(maxHeight: 220)
            .padding(.horizontal, 24)

            HStack {
                Button("Back") { page = .intro }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                Button {
                    if let py = pickedPython {
                        page = .installing
                        Task { await venv.setupFromScratch(host: py, installKokoro: installKokoro) }
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "play.fill").font(.system(size: 11, weight: .bold))
                        Text("Set up venv").font(.system(size: 13, weight: .semibold))
                    }
                    .foregroundStyle(.white)
                    .padding(.horizontal, 18).padding(.vertical, 10)
                    .background(RoundedRectangle(cornerRadius: 10)
                        .fill(Theme.signatureGradient))
                    .shadow(color: Theme.glowPrimary, radius: 10, y: 2)
                }
                .buttonStyle(.plain)
                .disabled(pickedPython == nil)
                .opacity(pickedPython == nil ? 0.5 : 1)
            }
            .padding(.horizontal, 24).padding(.bottom, 18)
        }
    }

    @ViewBuilder
    private func candidateRow(_ url: URL) -> some View {
        let isPicked = (pickedPython == url)
        Button { pickedPython = url } label: {
            HStack(spacing: 10) {
                Image(systemName: isPicked ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isPicked ? Theme.indigo : Theme.textDim)
                VStack(alignment: .leading, spacing: 2) {
                    Text(url.path)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(Theme.textPrimary)
                        .lineLimit(1).truncationMode(.middle)
                    Text(probeVersion(url))
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.textDim)
                }
                Spacer()
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 8)
                .fill(isPicked ? Theme.indigo.opacity(0.18) : Color.clear))
            .overlay(RoundedRectangle(cornerRadius: 8)
                .stroke(isPicked ? Theme.indigo : Theme.borderSubtle, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // ── Installing

    private var installing: some View {
        VStack(spacing: 14) {
            Image(systemName: "gearshape.2")
                .font(.system(size: 40))
                .symbolEffect(.pulse, options: .repeating)
                .foregroundStyle(Theme.indigo)
                .padding(.top, 22)
            Text("Setting up environment…")
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(Theme.textPrimary)

            ProgressView(value: progress)
                .progressViewStyle(.linear)
                .tint(Theme.indigo)
                .padding(.horizontal, 32)

            ScrollViewReader { proxy in
                ScrollView {
                    Text(installLog)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .id("end")
                }
                .frame(height: 260)
                .padding(.horizontal, 24)
                .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgDeepest))
                .padding(.horizontal, 18)
                .onChange(of: installLog) { _, _ in
                    withAnimation { proxy.scrollTo("end", anchor: .bottom) }
                }
            }

            Spacer(minLength: 0)
        }
    }

    // ── Done / Failed

    private var done: some View {
        VStack(spacing: 14) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 56))
                .foregroundStyle(Theme.success)
                .shadow(color: Theme.glowSuccess, radius: 20)
                .padding(.top, 24)
            Text("All set!").font(.system(size: 26, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            VStack(spacing: 4) {
                Text("manim \(venv.manimVersion) installed")
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                if let py = venv.pythonInVenv {
                    Text(py.path)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                        .lineLimit(1).truncationMode(.middle)
                }
            }
            Spacer(minLength: 0)
            Button {
                NotificationCenter.default.post(name: .welcomeDone, object: nil)
            } label: {
                Text("Open ManimStudio")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 24).padding(.vertical, 11)
                    .background(RoundedRectangle(cornerRadius: 10)
                        .fill(Theme.signatureGradient))
                    .shadow(color: Theme.glowPrimary, radius: 12, y: 3)
            }
            .buttonStyle(.plain)
            .padding(.bottom, 22)
        }
    }

    private var failed: some View {
        VStack(spacing: 14) {
            Image(systemName: "xmark.octagon.fill")
                .font(.system(size: 48))
                .foregroundStyle(Theme.error)
                .padding(.top, 22)
            Text("Setup failed").font(.system(size: 22, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            ScrollView {
                Text(installLog)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
            }
            .frame(height: 260)
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgDeepest))
            .padding(.horizontal, 18)

            HStack {
                Button("Retry") { page = .picker }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.indigo)
                Spacer()
                Button("Skip for now") {
                    NotificationCenter.default.post(name: .welcomeDone, object: nil)
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.textSecondary)
            }
            .padding(.horizontal, 24).padding(.bottom, 18)
        }
    }

    // MARK: - state derivation

    private var progress: Double {
        switch venv.status {
        case .creating(let p, _), .installing(let p, _): return p
        case .ready: return 1
        default: return 0
        }
    }
    private var installLog: String {
        switch venv.status {
        case .creating(_, let l), .installing(_, let l), .failed(let l): return l
        default: return ""
        }
    }

    // MARK: - candidate scan

    private func scanHostCandidates() {
        var found: [URL] = []
        let probes = [
            "/usr/local/bin/python3.14",
            "/opt/homebrew/bin/python3.14",
            "/usr/local/bin/python3.13",
            "/opt/homebrew/bin/python3.13",
            "/usr/local/bin/python3.12",
            "/opt/homebrew/bin/python3.12",
            "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14",
        ]
        for p in probes {
            if FileManager.default.isExecutableFile(atPath: p) {
                found.append(URL(fileURLWithPath: p))
            }
        }
        // Also walk PATH for any pythonN.M binary.
        if let env = ProcessInfo.processInfo.environment["PATH"] {
            for dir in env.split(separator: ":") {
                for name in ["python3.14", "python3.13", "python3.12", "python3"] {
                    let url = URL(fileURLWithPath: String(dir))
                        .appendingPathComponent(name)
                    if FileManager.default.isExecutableFile(atPath: url.path),
                       !found.contains(url) {
                        found.append(url)
                    }
                }
            }
        }
        hostCandidates = found
        if pickedPython == nil { pickedPython = found.first }
    }

    private func probeVersion(_ url: URL) -> String {
        let p = Process()
        p.executableURL = url
        p.arguments = ["--version"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        do {
            try p.run()
            p.waitUntilExit()
            if let data = try? pipe.fileHandleForReading.readToEnd(),
               let s = String(data: data, encoding: .utf8) {
                return s.trimmingCharacters(in: .whitespacesAndNewlines)
            }
        } catch {}
        return "unknown"
    }
}

extension Notification.Name {
    static let welcomeDone = Notification.Name("manimstudio.welcome.done")
}
