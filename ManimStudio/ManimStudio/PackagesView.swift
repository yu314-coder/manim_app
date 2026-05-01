// PackagesView.swift — Live introspection via PackageInspector.
import SwiftUI

struct PackagesView: View {
    @StateObject private var inspector = PackageInspector()
    @State private var query = ""

    private var filtered: [PackageInfo] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return inspector.packages }
        return inspector.packages.filter {
            $0.name.lowercased().contains(q) ||
            ($0.summary?.lowercased().contains(q) ?? false)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Packages").font(.system(size: 22, weight: .bold))
                    .foregroundStyle(Theme.textPrimary)
                if inspector.isLoading {
                    ProgressView().scaleEffect(0.7)
                } else if !inspector.packages.isEmpty {
                    Text("(\(inspector.packages.count))")
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                }
                Spacer()
                Button { inspector.refresh() } label: {
                    Label("Refresh", systemImage: "arrow.triangle.2.circlepath")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .background(Capsule().fill(Theme.signatureGradient))
                }
                .buttonStyle(.plain)
                .disabled(inspector.isLoading)
            }

            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(Theme.textDim)
                TextField("Filter installed packages…", text: $query)
                    .textFieldStyle(.plain).foregroundStyle(Theme.textPrimary)
                if !query.isEmpty {
                    Button { query = "" } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.textDim)
                    }.buttonStyle(.plain)
                }
            }
            .padding(10).glassCard(padding: 4)

            Group {
                if let err = inspector.error {
                    errorState(err)
                } else if inspector.packages.isEmpty && !inspector.isLoading {
                    emptyState
                } else {
                    list
                }
            }
        }
        .padding(16).background(Theme.bgPrimary)
        .onAppear {
            if inspector.packages.isEmpty && !inspector.isLoading { inspector.refresh() }
        }
    }

    @ViewBuilder
    private var list: some View {
        ScrollView {
            LazyVStack(spacing: 6) {
                ForEach(filtered) { pkg in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "shippingbox.fill")
                            .foregroundStyle(Theme.accentSecondary).padding(.top, 2)
                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 8) {
                                Text(pkg.name)
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundStyle(Theme.textPrimary)
                                Text("v\(pkg.version)")
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(Theme.textDim)
                                    .padding(.horizontal, 5).padding(.vertical, 1)
                                    .background(Capsule().fill(Theme.bgTertiary))
                            }
                            if let s = pkg.summary, !s.isEmpty {
                                Text(s).font(.system(size: 11))
                                    .foregroundStyle(Theme.textSecondary).lineLimit(2)
                            }
                        }
                        Spacer()
                    }
                    .padding(10).glassCard(padding: 4)
                }
            }
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "shippingbox").font(.system(size: 40)).foregroundStyle(Theme.textDim)
            if inspector.isLoading {
                Text("Booting Python interpreter…")
                    .font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
                Text("First run takes ~2 s").font(.system(size: 10)).foregroundStyle(Theme.textDim)
            } else {
                Text("No packages found")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private func errorState(_ msg: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Theme.warning)
                Text("Python introspection failed")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
            }
            ScrollView {
                Text(msg).font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
        }
        .padding(12).glassCard(padding: 4)
    }
}
