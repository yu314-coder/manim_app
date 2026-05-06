// PackagesView.swift — visual package manager. Lists every package
// installed in the per-app venv with version + install path. Add /
// remove via the host pip subprocess. Mirrors the Windows desktop
// app's Visual Package Manager but native AppKit/SwiftUI.
import SwiftUI

struct PackagesView: View {
    @ObservedObject var venv: VenvManager

    @State private var packages: [PipPackage] = []
    @State private var query = ""
    @State private var loading = false
    @State private var pipLog: String = ""
    @State private var inputName: String = ""

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().background(Theme.borderSubtle)
            if loading && packages.isEmpty {
                loadingState
            } else if !canRun {
                noVenvState
            } else {
                content
            }
        }
        .background(Theme.bgPrimary)
        .onAppear { Task { await refresh() } }
    }

    // MARK: header

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "shippingbox.fill")
                .font(.system(size: 16))
                .foregroundStyle(Theme.violet)
            Text("Packages").font(.system(size: 18, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            StatusDot(state: venv.status == .ready ? .ok : .idle)
            Spacer()
            TextField("Search…", text: $query)
                .textFieldStyle(.roundedBorder)
                .frame(width: 220)
            Button { Task { await refresh() } } label: {
                Image(systemName: "arrow.clockwise")
            }.buttonStyle(.plain)
        }
        .padding(.horizontal, 18).padding(.vertical, 14)
    }

    // MARK: states

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView().controlSize(.large).tint(Theme.indigo)
            Text("Reading installed packages…")
                .foregroundStyle(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var noVenvState: some View {
        VStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 36))
                .foregroundStyle(Theme.warning)
            Text("Virtualenv not ready")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
            Text("Run the welcome wizard to set up the per-app venv before installing packages.")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var content: some View {
        HStack(spacing: 0) {
            // ── List
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 4) {
                    ForEach(filtered) { pkg in
                        row(pkg)
                    }
                    if filtered.isEmpty && !query.isEmpty {
                        Text("No matches for “\(query)”")
                            .foregroundStyle(Theme.textDim)
                            .padding()
                    }
                }
                .padding(12)
            }
            .frame(maxWidth: .infinity)

            Divider().background(Theme.borderSubtle)

            // ── Install panel
            installPanel.frame(width: 320)
        }
    }

    // MARK: row

    @ViewBuilder
    private func row(_ pkg: PipPackage) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "shippingbox")
                .foregroundStyle(Theme.indigo)
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 2) {
                Text(pkg.name)
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                Text(pkg.version)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.textDim)
            }
            Spacer()
            Button(role: .destructive) {
                Task { await uninstall(pkg.name) }
            } label: {
                Image(systemName: "trash")
                    .foregroundStyle(Theme.error)
            }
            .buttonStyle(.plain)
            .help("Uninstall \(pkg.name)")
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgSecondary))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderSubtle, lineWidth: 1))
    }

    // MARK: install panel

    private var installPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Install package", icon: "plus.circle")
                .padding(.top, 12).padding(.horizontal, 12)
            HStack {
                TextField("e.g. numpy or numpy==2.4.4", text: $inputName)
                    .textFieldStyle(.roundedBorder)
                Button {
                    let n = inputName.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !n.isEmpty else { return }
                    Task { await install(n) }
                } label: {
                    Text("Install")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .background(RoundedRectangle(cornerRadius: 7)
                            .fill(Theme.signatureGradient))
                }
                .buttonStyle(.plain)
                .disabled(inputName.isEmpty)
            }
            .padding(.horizontal, 12)

            Divider().padding(.horizontal, 12)

            SectionHeader(title: "pip log", icon: "doc.text")
                .padding(.horizontal, 12)
            ScrollView {
                Text(pipLog.isEmpty ? "—" : pipLog)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
            }
            .background(Theme.bgDeepest)
            .padding(12)
        }
    }

    // MARK: data

    private var canRun: Bool {
        if case .ready = venv.status { return true }
        return false
    }
    private var filtered: [PipPackage] {
        guard !query.isEmpty else { return packages }
        let q = query.lowercased()
        return packages.filter { $0.name.lowercased().contains(q) }
    }

    private func refresh() async {
        guard let py = VenvManager.venvPython else { packages = []; return }
        loading = true
        defer { loading = false }
        let proc = Process()
        proc.executableURL = py
        proc.arguments = ["-m", "pip", "list", "--format=json",
                          "--disable-pip-version-check"]
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = Pipe()
        do {
            try proc.run()
            proc.waitUntilExit()
            if proc.terminationStatus == 0,
               let data = try? pipe.fileHandleForReading.readToEnd() {
                struct Entry: Decodable {
                    let name: String; let version: String
                }
                let entries = (try? JSONDecoder().decode([Entry].self, from: data)) ?? []
                packages = entries.map { PipPackage(name: $0.name, version: $0.version) }
                    .sorted { $0.name.lowercased() < $1.name.lowercased() }
            }
        } catch {
            packages = []
        }
    }

    private func install(_ spec: String) async {
        guard let py = VenvManager.venvPython else { return }
        await run(py: py, args: ["-m", "pip", "install",
                                  "--disable-pip-version-check", spec])
        inputName = ""
        await refresh()
    }
    private func uninstall(_ name: String) async {
        guard let py = VenvManager.venvPython else { return }
        await run(py: py, args: ["-m", "pip", "uninstall", "-y",
                                  "--disable-pip-version-check", name])
        await refresh()
    }

    private func run(py: URL, args: [String]) async {
        pipLog += "\n$ pip \(args.dropFirst(2).joined(separator: " "))\n"
        let proc = Process()
        proc.executableURL = py
        proc.arguments = args
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty { return }
            let s = String(data: data, encoding: .utf8) ?? ""
            Task { @MainActor in pipLog += s }
        }
        do {
            try proc.run()
            await withCheckedContinuation { c in
                proc.terminationHandler = { _ in c.resume() }
            }
        } catch {
            pipLog += "[error] \(error)\n"
        }
        pipe.fileHandleForReading.readabilityHandler = nil
    }
}

struct PipPackage: Identifiable, Hashable {
    let name: String
    let version: String
    var id: String { name }
}
