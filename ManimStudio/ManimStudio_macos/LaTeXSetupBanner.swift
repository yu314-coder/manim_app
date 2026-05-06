// LaTeXSetupBanner.swift — the in-workspace banner that shows when
// the TeX pipeline isn't ready and offers a one-click full setup.
// Goal: a brand-new install on a brand-new machine should be a
// "click this once → wait a few minutes → done" experience, with no
// shell commands or env vars exposed to the user.
//
// Placement: a thin bar between the tab strip and the workspace
// content. Auto-dismisses when LaTeXFixer reports the pipeline
// is ready. Hides itself entirely if everything is already set up
// at app launch (no banner = no clutter for users who don't need
// TeX rendering).
import SwiftUI
import AppKit

struct LaTeXSetupBanner: View {
    @StateObject private var probe = LaTeXProbe.shared
    @StateObject private var fixer = LaTeXFixer.shared
    @State private var dismissed = false
    @State private var didInitialTest = false

    /// Banner shows when:
    ///   • probe says something's missing, OR
    ///   • the end-to-end test failed,
    /// AND the user hasn't manually dismissed it for this session,
    /// AND we're not already in the middle of a setup chain.
    private var shouldShow: Bool {
        if dismissed { return false }
        if fixer.setupPhase != .idle && fixer.setupPhase != .ready &&
           fixer.setupPhase != .failed {
            return true  // mid-install — keep it visible
        }
        if !probe.fullyReady { return true }
        if case .failed = fixer.test { return true }
        return false
    }

    var body: some View {
        Group {
            if shouldShow { content }
        }
        .onAppear {
            probe.probe()
            fixer.detectBrew()
            // First test — only run once per app launch, not on every
            // banner appear. Avoids re-spawning pdflatex every time
            // the user switches tabs.
            if !didInitialTest {
                didInitialTest = true
                fixer.runEndToEndTest()
            }
        }
        .animation(.spring(response: 0.35), value: shouldShow)
        .animation(.spring(response: 0.35), value: fixer.setupPhase)
    }

    @ViewBuilder
    private var content: some View {
        HStack(spacing: 12) {
            phaseIcon

            VStack(alignment: .leading, spacing: 2) {
                Text(headline)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                Text(detail)
                    .font(.system(size: 10))
                    .foregroundStyle(.white.opacity(0.85))
                    .lineLimit(2)
            }
            Spacer()

            actionButtons
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
        .background(banner)
        .transition(.move(edge: .top).combined(with: .opacity))
    }

    // ── pieces

    private var headline: String {
        switch fixer.setupPhase {
        case .idle:                return "TeX renders won't work yet"
        case .installingBasicTeX:  return "Installing BasicTeX…"
        case .installingDvisvgm:   return "Installing dvisvgm…"
        case .installingPackages:  return "Installing TeX packages…"
        case .testing:             return "Verifying TeX pipeline…"
        case .ready:               return "TeX ready"
        case .failed:              return "TeX setup failed"
        }
    }

    private var detail: String {
        if !fixer.setupDetail.isEmpty { return fixer.setupDetail }
        if !probe.status.isReady   { return "pdflatex isn't installed" }
        if !probe.dvisvgm.isReady  { return "dvisvgm isn't installed" }
        if case .failed(let stage, let msg) = fixer.test {
            return "\(stage.rawValue): \(msg)"
        }
        return "MathTex / Tex / Text mobjects need pdflatex + dvisvgm + a few CTAN packages."
    }

    @ViewBuilder
    private var phaseIcon: some View {
        switch fixer.setupPhase {
        case .installingBasicTeX, .installingDvisvgm,
             .installingPackages, .testing:
            ProgressView()
                .controlSize(.small)
                .tint(.white)
        case .ready:
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 16))
                .foregroundStyle(.white)
        case .failed:
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 16))
                .foregroundStyle(.white)
        case .idle:
            Image(systemName: "function")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(.white)
        }
    }

    private var banner: some View {
        let inProgress = fixer.setupPhase != .idle &&
                         fixer.setupPhase != .ready &&
                         fixer.setupPhase != .failed
        let tint: AnyShapeStyle = {
            if fixer.setupPhase == .ready { return AnyShapeStyle(Theme.signatureGradient) }
            if fixer.setupPhase == .failed { return AnyShapeStyle(LinearGradient(colors: [Theme.error, Theme.amber], startPoint: .leading, endPoint: .trailing)) }
            if inProgress { return AnyShapeStyle(LinearGradient(colors: [Theme.indigo, Theme.violet], startPoint: .leading, endPoint: .trailing)) }
            return AnyShapeStyle(LinearGradient(colors: [Theme.amber, Theme.error.opacity(0.7)], startPoint: .leading, endPoint: .trailing))
        }()
        return Rectangle().fill(tint)
    }

    @ViewBuilder
    private var actionButtons: some View {
        let inProgress = fixer.setupPhase != .idle &&
                         fixer.setupPhase != .ready &&
                         fixer.setupPhase != .failed
        if inProgress {
            // No buttons during install — user watches the terminal.
            EmptyView()
        } else if fixer.setupPhase == .failed {
            Button { runSetup() } label: {
                Text("Try again").font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(Capsule().fill(.white.opacity(0.22)))
            }.buttonStyle(.plain)
            dismissBtn
        } else if fixer.setupPhase == .ready {
            dismissBtn
        } else {
            // Idle — primary action: full auto setup.
            Button { runSetup() } label: {
                HStack(spacing: 5) {
                    Image(systemName: "wand.and.stars")
                        .font(.system(size: 11, weight: .semibold))
                    Text("Set up TeX automatically")
                        .font(.system(size: 11, weight: .semibold))
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 12).padding(.vertical, 5)
                .background(Capsule().fill(.white.opacity(0.22)))
            }
            .buttonStyle(.plain)
            .disabled(fixer.brewPath == nil)
            .help(fixer.brewPath == nil
                  ? "Install Homebrew first (brew.sh) — needed to run brew install."
                  : "Runs brew + tlmgr installs in the integrated terminal.")
            dismissBtn
        }
    }

    private var dismissBtn: some View {
        Button { dismissed = true } label: {
            Image(systemName: "xmark")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.white.opacity(0.85))
                .frame(width: 18, height: 18)
                .background(Circle().fill(.white.opacity(0.15)))
        }
        .buttonStyle(.plain)
        .help("Hide for this session")
    }

    private func runSetup() {
        fixer.runFullSetup(
            latex: probe.status,
            dvisvgm: probe.dvisvgm,
            onProbeRefresh: { probe.probe() })
    }
}
