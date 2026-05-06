// SystemInfoView.swift — the "System info" tab inside Settings.
// Shows app/OS/CPU details + Python interpreter / manim / pdflatex
// / dvisvgm versions + the venv's installed package list. Useful
// for triaging "manim render fails" reports — the user can paste
// a copy-friendly report into a github issue.
import SwiftUI
import AppKit

struct SystemInfoView: View {
    @StateObject private var info = SystemInfo()
    @EnvironmentObject var venv: VenvManager

    var body: some View {
        VStack(spacing: 0) {
            header

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    section("App / System") {
                        kv("App",          "\(info.appName) \(info.appVersion) (\(info.appBuild))")
                        kv("OS",           "\(info.osName) \(info.osVersion)")
                        kv("Architecture", info.architecture)
                        kv("Locale",       info.locale)
                    }

                    section("Python & manim") {
                        kv("Interpreter", info.python.path ?? "—")
                        kv("Version",     info.python.version ?? info.python.error ?? "probing…")
                        kv("pip",         info.pip.version    ?? info.pip.error    ?? "probing…")
                        kv("manim",       info.manim.version  ?? info.manim.error  ?? "probing…")
                        kv("Venv path",   VenvManager.venvURL.path)
                    }

                    section("LaTeX / dvisvgm") {
                        kv("pdflatex path", info.pdflatex.path ?? "—")
                        kv("pdflatex version", info.pdflatex.version ?? info.pdflatex.error ?? "probing…")
                        kv("dvisvgm path",  info.dvisvgm.path  ?? "—")
                        kv("dvisvgm version", info.dvisvgm.version ?? info.dvisvgm.error ?? "probing…")
                    }

                    if !info.pipList.isEmpty {
                        section("Installed packages (\(info.pipList.count))") {
                            // Two-column grid keeps the list dense without
                            // sacrificing copy/paste fidelity.
                            LazyVGrid(columns: [
                                GridItem(.flexible(), alignment: .leading),
                                GridItem(.flexible(), alignment: .leading),
                            ], alignment: .leading, spacing: 4) {
                                ForEach(info.pipList, id: \.name) { p in
                                    HStack {
                                        Text(p.name)
                                            .font(.system(size: 11, design: .monospaced))
                                            .foregroundStyle(Theme.textPrimary)
                                        Spacer(minLength: 8)
                                        Text(p.version)
                                            .font(.system(size: 11, design: .monospaced))
                                            .foregroundStyle(Theme.textSecondary)
                                    }
                                    .padding(.horizontal, 6).padding(.vertical, 2)
                                    .background(RoundedRectangle(cornerRadius: 4)
                                        .fill(Theme.bgTertiary.opacity(0.5)))
                                }
                            }
                        }
                    }
                }
                .padding(16)
            }
        }
        .background(Theme.bgPrimary)
        .onAppear { info.refresh() }
    }

    // MARK: pieces

    private var header: some View {
        HStack {
            Image(systemName: "info.circle.fill")
                .foregroundStyle(Theme.indigo)
            Text("System info")
                .font(.system(size: 14, weight: .semibold))
            Spacer()
            if info.refreshing {
                ProgressView().controlSize(.small)
            }
            Button {
                let report = buildPlainTextReport()
                let pb = NSPasteboard.general
                pb.clearContents()
                pb.setString(report, forType: .string)
            } label: {
                Label("Copy report", systemImage: "doc.on.doc")
                    .font(.system(size: 11))
            }
            .buttonStyle(.plain)
            .foregroundStyle(Theme.indigo)
            .help("Copy a plain-text dump for triaging issues")

            Button { info.refresh() } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
            }
            .buttonStyle(.plain)
            .disabled(info.refreshing)
            .help("Re-probe everything")
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(Theme.bgSecondary)
        .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                 alignment: .bottom)
    }

    @ViewBuilder
    private func section<C: View>(_ title: String,
                                  @ViewBuilder body: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 11, weight: .semibold))
                .tracking(0.5)
                .foregroundStyle(Theme.textDim)
            VStack(alignment: .leading, spacing: 2) { body() }
                .padding(10)
                .background(RoundedRectangle(cornerRadius: 8)
                    .fill(Theme.bgSecondary))
        }
    }

    @ViewBuilder
    private func kv(_ key: String, _ val: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(key)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 130, alignment: .leading)
            Text(val)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .textSelection(.enabled)  // ⌘C copies the value
                .lineLimit(2).truncationMode(.middle)
            Spacer()
        }
    }

    private func buildPlainTextReport() -> String {
        var lines: [String] = []
        lines.append("# ManimStudio system report")
        lines.append("")
        lines.append("App:          \(info.appName) \(info.appVersion) (\(info.appBuild))")
        lines.append("OS:           \(info.osName) \(info.osVersion)")
        lines.append("Architecture: \(info.architecture)")
        lines.append("Locale:       \(info.locale)")
        lines.append("")
        lines.append("Python:   \(info.python.path ?? "—")")
        lines.append("          \(info.python.version ?? info.python.error ?? "")")
        lines.append("pip:      \(info.pip.version ?? info.pip.error ?? "")")
        lines.append("manim:    \(info.manim.version ?? info.manim.error ?? "")")
        lines.append("Venv:     \(VenvManager.venvURL.path)")
        lines.append("")
        lines.append("pdflatex: \(info.pdflatex.path ?? "—")")
        lines.append("          \(info.pdflatex.version ?? info.pdflatex.error ?? "")")
        lines.append("dvisvgm:  \(info.dvisvgm.path ?? "—")")
        lines.append("          \(info.dvisvgm.version ?? info.dvisvgm.error ?? "")")
        if !info.pipList.isEmpty {
            lines.append("")
            lines.append("# pip list")
            for p in info.pipList {
                lines.append("\(p.name)==\(p.version)")
            }
        }
        return lines.joined(separator: "\n")
    }
}
