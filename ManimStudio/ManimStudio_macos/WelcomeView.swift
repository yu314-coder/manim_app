// WelcomeView.swift — first-run wizard. Glassmorphic, phased,
// with a real-time package checklist + step indicator + scrolling
// pip log. Shown until the per-app venv reaches .ready or the user
// explicitly skips.
import SwiftUI

struct WelcomeView: View {
    @ObservedObject var venv: VenvManager

    @State private var pickedPython: URL? = nil
    @State private var hostCandidates: [URL] = []
    @State private var installKokoro = false
    @State private var page: Page = .intro

    enum Page: Int, CaseIterable { case intro, picker, installing, done, failed }

    var body: some View {
        ZStack {
            // ── animated bg
            LinearGradient(
                colors: [Theme.bgDeepest, Theme.bgPrimary, Theme.bgSecondary],
                startPoint: .topLeading, endPoint: .bottomTrailing
            ).ignoresSafeArea()
            GeometryReader { geo in
                ZStack {
                    Circle()
                        .fill(Theme.indigo.opacity(0.18))
                        .blur(radius: 90)
                        .offset(x: -geo.size.width * 0.30,
                                y: -geo.size.height * 0.32)
                    Circle()
                        .fill(Theme.violet.opacity(0.20))
                        .blur(radius: 110)
                        .offset(x: geo.size.width * 0.32,
                                y: geo.size.height * 0.30)
                    Circle()
                        .fill(Theme.pink.opacity(0.10))
                        .blur(radius: 80)
                        .offset(x: 0, y: geo.size.height * 0.45)
                }
            }.ignoresSafeArea()

            // ── glass card
            VStack(spacing: 0) {
                stepIndicator
                    .padding(.top, 22)
                    .padding(.horizontal, 30)

                content
                    .padding(.horizontal, 28)
                    .padding(.vertical, 18)

                Spacer(minLength: 0)
                actionBar
                    .padding(.horizontal, 24)
                    .padding(.bottom, 22)
            }
            .frame(maxWidth: 720, maxHeight: 600)
            .glassCard(cornerRadius: 22)
            .shadow(color: Theme.glowPrimary.opacity(0.35), radius: 50, y: 8)
            .padding(40)
        }
        .onAppear {
            scanHostCandidates()
            Task { await venv.probe() }
        }
        .onChange(of: venv.phase) { _, newValue in
            switch newValue {
            case .ready:                                page = .done
            case .failed:                               page = .failed
            case .creatingVenv, .upgradingPip,
                 .installingPackages, .verifying:       page = .installing
            default: break
            }
        }
    }

    // MARK: step indicator

    private var stepIndicator: some View {
        HStack(spacing: 0) {
            stepDot(idx: 0, label: "Welcome",  active: page.rawValue >= 0,
                    current: page == .intro)
            stepLine(active: page.rawValue >= 1)
            stepDot(idx: 1, label: "Python",   active: page.rawValue >= 1,
                    current: page == .picker)
            stepLine(active: page.rawValue >= 2)
            stepDot(idx: 2, label: "Install",  active: page.rawValue >= 2,
                    current: page == .installing)
            stepLine(active: page.rawValue >= 3)
            stepDot(idx: 3, label: "Done",     active: page == .done,
                    current: page == .done)
        }
    }

    private func stepDot(idx: Int, label: String, active: Bool, current: Bool) -> some View {
        VStack(spacing: 6) {
            ZStack {
                Circle()
                    .fill(current
                          ? AnyShapeStyle(Theme.signatureGradient)
                          : AnyShapeStyle(active ? Theme.indigo.opacity(0.50)
                                          : Theme.bgTertiary))
                    .frame(width: 28, height: 28)
                    .overlay(Circle().stroke(active ? Theme.indigo : Theme.borderSubtle,
                                             lineWidth: 1.2))
                    .shadow(color: current ? Theme.glowPrimary : .clear,
                            radius: current ? 10 : 0)
                if active && !current {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.white)
                } else {
                    Text("\(idx + 1)")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.white)
                }
            }
            Text(label)
                .font(.system(size: 10, weight: current ? .bold : .medium))
                .foregroundStyle(current ? Theme.textPrimary
                                : (active ? Theme.textSecondary : Theme.textDim))
        }
    }
    private func stepLine(active: Bool) -> some View {
        Rectangle()
            .fill(active ? Theme.indigo.opacity(0.50)
                  : Theme.borderSubtle)
            .frame(height: 2)
            .padding(.bottom, 18)
            .padding(.horizontal, 4)
    }

    // MARK: page content

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
        VStack(spacing: 14) {
            Image(systemName: "wand.and.stars")
                .font(.system(size: 48))
                .symbolRenderingMode(.palette)
                .foregroundStyle(Theme.indigo, Theme.violet)
                .padding(.top, 10)
            Text("Welcome to ManimStudio")
                .font(.system(size: 24, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Text("Let's set up a private Python environment for your renders. This stays sandboxed inside the app — your system Python is never modified.")
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 480)

            VStack(alignment: .leading, spacing: 8) {
                row(icon: "shippingbox.fill",  text: "manim, numpy, scipy, matplotlib, Pillow")
                row(icon: "textformat",        text: "manim-fonts (custom font support)")
                row(icon: "waveform",          text: "Kokoro TTS (auto-narration)", isToggle: true)
                row(icon: "internaldrive",     text: "Lives at ~/Library/Application Support/ManimStudio/venv/")
            }
            .padding(14)
            .glassCard()
            .padding(.top, 6)
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
        VStack(spacing: 12) {
            Image(systemName: "ladybug")
                .font(.system(size: 38))
                .foregroundStyle(Theme.violet)
                .padding(.top, 6)
            Text("Choose a host Python")
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Text("ManimStudio uses this Python only to **build** the venv. After setup, your venv is independent.")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)

            ScrollView {
                VStack(spacing: 6) {
                    ForEach(hostCandidates, id: \.self) { url in
                        candidateRow(url)
                    }
                    if hostCandidates.isEmpty {
                        VStack(spacing: 10) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 28))
                                .foregroundStyle(Theme.warning)
                            Text("No Python 3.x found")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(Theme.textPrimary)
                            Text("Install Python 3.14 from python.org or run `brew install python@3.14` in Terminal, then click Refresh.")
                                .font(.system(size: 11))
                                .foregroundStyle(Theme.textSecondary)
                                .multilineTextAlignment(.center)
                            Button("Refresh") { scanHostCandidates() }
                                .buttonStyle(.borderedProminent)
                                .tint(Theme.indigo)
                        }
                        .padding(20)
                    }
                }
                .padding(.vertical, 4)
            }
            .frame(maxHeight: 240)
            .padding(.horizontal, 4)
        }
    }

    @ViewBuilder
    private func candidateRow(_ url: URL) -> some View {
        let isPicked = (pickedPython == url)
        Button { pickedPython = url } label: {
            HStack(spacing: 12) {
                Image(systemName: isPicked ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 16))
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
            .padding(11)
            .background(RoundedRectangle(cornerRadius: 9)
                .fill(isPicked ? Theme.indigo.opacity(0.18) : Theme.bgTertiary.opacity(0.5)))
            .overlay(RoundedRectangle(cornerRadius: 9)
                .stroke(isPicked ? Theme.indigo : Theme.borderSubtle, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // ── Installing

    private var installing: some View {
        VStack(spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: phaseIcon)
                    .font(.system(size: 18, weight: .semibold))
                    .symbolEffect(.pulse, options: .repeating)
                    .foregroundStyle(Theme.indigo)
                Text(venv.phase.label)
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                Text("\(Int(venv.progress * 100))%")
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }

            ProgressView(value: venv.progress)
                .progressViewStyle(.linear)
                .tint(Theme.indigo)

            // Per-package checklist
            if !venv.packages.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    SectionHeader(title: "Packages")
                    ScrollView {
                        VStack(spacing: 4) {
                            ForEach(venv.packages) { pkg in
                                packageRow(pkg)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .frame(maxHeight: 130)
                }
                .padding(10)
                .glassCard()
            }

            // Live log tail
            VStack(alignment: .leading, spacing: 4) {
                SectionHeader(title: "Log", icon: "doc.text")
                ScrollViewReader { proxy in
                    ScrollView {
                        Text(venv.log.isEmpty ? "—" : venv.log)
                            .font(.system(size: 9.5, design: .monospaced))
                            .foregroundStyle(Theme.textSecondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                            .id("end")
                    }
                    .frame(maxHeight: 110)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgDeepest))
                    .onChange(of: venv.log) { _, _ in
                        proxy.scrollTo("end", anchor: .bottom)
                    }
                }
            }
        }
    }

    private var phaseIcon: String {
        switch venv.phase {
        case .creatingVenv:       return "hammer.fill"
        case .upgradingPip:       return "arrow.up.circle.fill"
        case .installingPackages: return "shippingbox.fill"
        case .verifying:          return "checkmark.shield.fill"
        case .ready:              return "checkmark.seal.fill"
        case .failed:             return "xmark.seal.fill"
        case .idle:               return "circle.dashed"
        }
    }

    @ViewBuilder
    private func packageRow(_ pkg: VenvManager.PackageProgress) -> some View {
        HStack(spacing: 9) {
            packageIcon(for: pkg.status)
            Text(pkg.name)
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(packageColor(for: pkg.status))
            Spacer()
            packageStatusLabel(pkg.status)
                .font(.system(size: 10))
                .foregroundStyle(Theme.textDim)
        }
        .padding(.horizontal, 8).padding(.vertical, 4)
    }

    @ViewBuilder
    private func packageIcon(for status: VenvManager.PackageStatus) -> some View {
        switch status {
        case .pending:
            Image(systemName: "circle")
                .foregroundStyle(Theme.textDim)
        case .installing:
            ProgressView().controlSize(.mini).tint(Theme.indigo)
                .frame(width: 14, height: 14)
        case .done:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(Theme.success)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(Theme.error)
        }
    }
    private func packageColor(for status: VenvManager.PackageStatus) -> Color {
        switch status {
        case .pending:    return Theme.textSecondary
        case .installing: return Theme.indigo
        case .done:       return Theme.textPrimary
        case .failed:     return Theme.error
        }
    }
    @ViewBuilder
    private func packageStatusLabel(_ status: VenvManager.PackageStatus) -> some View {
        switch status {
        case .pending:    Text("queued")
        case .installing: Text("installing…")
        case .done:       Text("installed")
        case .failed(let why): Text(why)
        }
    }

    // ── Done / Failed

    private var done: some View {
        VStack(spacing: 14) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 56))
                .foregroundStyle(Theme.success)
                .shadow(color: Theme.glowSuccess, radius: 20)
                .padding(.top, 8)
            Text("All set!").font(.system(size: 26, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            VStack(spacing: 6) {
                detailRow("manim", venv.manimVersion)
                if let py = venv.pythonInVenv {
                    detailRow("python", py.path)
                }
            }
            .padding(12)
            .glassCard()
        }
    }

    private var failed: some View {
        VStack(spacing: 12) {
            Image(systemName: "xmark.octagon.fill")
                .font(.system(size: 44))
                .foregroundStyle(Theme.error)
                .shadow(color: Theme.error.opacity(0.5), radius: 14)
                .padding(.top, 6)
            Text("Setup failed").font(.system(size: 20, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            if !venv.failureReason.isEmpty {
                Text(venv.failureReason)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 30)
            }
            // failed-package detail
            if let bad = venv.packages.first(where: {
                if case .failed = $0.status { return true } else { return false }
            }) {
                detailRow("failed", bad.name)
                    .padding(.horizontal, 14)
            }

            VStack(alignment: .leading, spacing: 4) {
                SectionHeader(title: "Last log lines", icon: "doc.text")
                ScrollView {
                    Text(venv.log)
                        .font(.system(size: 9.5, design: .monospaced))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
                .frame(maxHeight: 160)
                .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgDeepest))
            }
        }
    }

    private func detailRow(_ k: String, _ v: String) -> some View {
        HStack(spacing: 12) {
            Text(k.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .tracking(1)
                .foregroundStyle(Theme.textDim)
                .frame(width: 60, alignment: .leading)
            Text(v)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1).truncationMode(.middle)
            Spacer()
        }
    }

    // MARK: action bar

    @ViewBuilder
    private var actionBar: some View {
        HStack {
            switch page {
            case .intro:
                Button("Skip for now") {
                    NotificationCenter.default.post(name: .welcomeDone, object: nil)
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.textSecondary)
                Spacer()
                primaryButton(label: "Continue", icon: "arrow.right") {
                    page = .picker
                }
            case .picker:
                Button("Back") { page = .intro }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                primaryButton(label: "Set up venv", icon: "play.fill",
                              disabled: pickedPython == nil) {
                    if let py = pickedPython {
                        page = .installing
                        Task { await venv.setupFromScratch(host: py,
                                                          installKokoro: installKokoro) }
                    }
                }
            case .installing:
                Spacer()
                Text("This is the long step (~3 min for manim).")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textDim)
            case .done:
                Spacer()
                primaryButton(label: "Open ManimStudio", icon: "arrow.right") {
                    NotificationCenter.default.post(name: .welcomeDone, object: nil)
                }
            case .failed:
                Button("Retry") { page = .picker }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.indigo)
                Spacer()
                Button("Skip") {
                    NotificationCenter.default.post(name: .welcomeDone, object: nil)
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.textSecondary)
            }
        }
    }

    @ViewBuilder
    private func primaryButton(label: String, icon: String,
                               disabled: Bool = false,
                               action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(label).font(.system(size: 13, weight: .semibold))
                Image(systemName: icon).font(.system(size: 11, weight: .bold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 18).padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 10)
                .fill(Theme.signatureGradient))
            .shadow(color: Theme.glowPrimary, radius: 12, y: 2)
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.5 : 1)
    }

    // MARK: candidate scan

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
