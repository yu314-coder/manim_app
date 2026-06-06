// PackagesView.swift — bundled Python package browser.
//
// Reads the baked-in BundledPackages list ONLY — no Python boot, no
// importlib.metadata walk (which took 2-5 s and janked the tab on every
// open). The bundled package set is fixed per app build, so the static
// list is always correct; regenerate BundledPackages.swift when the
// python-ios-lib pin changes. Adds category filtering, counts, and a
// cleaner card layout.
import SwiftUI

struct PackagesView: View {
    @State private var query = ""
    @State private var selectedCategory: String? = nil   // nil = All

    private let allPackages = BundledPackages.all
    private var categories: [String] { BundledPackages.categories }

    private var filtered: [PackageInfo] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        return allPackages.filter { pkg in
            let catOK = selectedCategory == nil || pkg.category == selectedCategory
            guard catOK else { return false }
            guard !q.isEmpty else { return true }
            return pkg.name.lowercased().contains(q)
                || (pkg.summary?.lowercased().contains(q) ?? false)
        }
    }

    private func count(_ cat: String) -> Int {
        allPackages.filter { $0.category == cat }.count
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            searchField
            categoryChips
            content
        }
        .padding(16)
        .background(Theme.bgPrimary)
    }

    // MARK: header

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "shippingbox.fill")
                .font(.system(size: 18))
                .foregroundStyle(Theme.accentSecondary)
            Text("Packages")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            Text("\(allPackages.count) bundled · offline")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Theme.textDim)
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(Capsule().fill(Theme.bgTertiary))
        }
    }

    // MARK: search

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundStyle(Theme.textDim)
            TextField("Filter packages…", text: $query)
                .textFieldStyle(.plain).foregroundStyle(Theme.textPrimary)
                .autocorrectionDisabled()
            if !query.isEmpty {
                Button { query = "" } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.textDim)
                }.buttonStyle(.plain)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Theme.bgTertiary)
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Theme.borderSubtle, lineWidth: 1))
        )
    }

    // MARK: category chips

    private var categoryChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                chip(title: "All", count: allPackages.count, cat: nil)
                ForEach(categories, id: \.self) { cat in
                    chip(title: cat, count: count(cat), cat: cat)
                }
            }
            .padding(.vertical, 1)
        }
    }

    private func chip(title: String, count: Int, cat: String?) -> some View {
        let active = selectedCategory == cat
        return Button {
            withAnimation(.easeInOut(duration: 0.12)) { selectedCategory = cat }
        } label: {
            HStack(spacing: 5) {
                if let cat { Circle().fill(Self.color(cat)).frame(width: 6, height: 6) }
                Text(title).font(.system(size: 12, weight: .medium))
                Text("\(count)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(active ? .white.opacity(0.85) : Theme.textDim)
            }
            .foregroundStyle(active ? .white : Theme.textSecondary)
            .padding(.horizontal, 11).padding(.vertical, 6)
            .background(
                Capsule().fill(active
                    ? AnyShapeStyle(Theme.signatureGradient)
                    : AnyShapeStyle(Theme.bgTertiary))
                .overlay(Capsule().stroke(active ? Color.clear : Theme.borderSubtle, lineWidth: 1))
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: content

    @ViewBuilder
    private var content: some View {
        if filtered.isEmpty {
            emptyState
        } else {
            ScrollView {
                LazyVStack(spacing: 6) {
                    ForEach(filtered) { pkg in row(pkg) }
                }
                .padding(.bottom, 8)
            }
        }
    }

    private func row(_ pkg: PackageInfo) -> some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 3)
                .fill(Self.color(pkg.category ?? "Utility"))
                .frame(width: 3, height: 30)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 8) {
                    Text(pkg.name)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                    Text("v\(pkg.version)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.textDim)
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(Capsule().fill(Theme.bgTertiary))
                    if let c = pkg.category {
                        Text(c.uppercased())
                            .font(.system(size: 8, weight: .semibold, design: .monospaced))
                            .tracking(0.5)
                            .foregroundStyle(Self.color(c))
                    }
                }
                if let s = pkg.summary, !s.isEmpty {
                    Text(s).font(.system(size: 11))
                        .foregroundStyle(Theme.textSecondary).lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer()
        }
        .padding(10)
        // Solid card (no .ultraThinMaterial — 100+ live blurs janked the
        // tab; a flat fill is identical here and free).
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.bgCard)
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Theme.borderSubtle, lineWidth: 1))
        )
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "magnifyingglass").font(.system(size: 36)).foregroundStyle(Theme.textDim)
            Text(query.isEmpty ? "No packages in this category"
                               : "No packages match “\(query)”")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: category color

    static func color(_ cat: String) -> Color {
        switch cat {
        case "Animation":   return Theme.violet
        case "ML / AI":     return Theme.pink
        case "Scientific":  return Theme.trace
        case "Plotting":    return Theme.amber
        case "Media":       return Theme.indigo
        case "Web / HTTP":  return Theme.green
        case "Geo":         return Color(hex: 0x5CD0B3)
        case "Performance": return Color(hex: 0xF0AC5F)
        case "Data":        return Color(hex: 0x7B5FF1)
        default:            return Theme.dim
        }
    }
}
