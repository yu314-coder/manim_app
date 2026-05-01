// SystemView.swift — System tab info grid.
import SwiftUI

struct SystemView: View {
    @State private var infos: [(String, String, String)] = [
        ("Python",          "3.14",        "chevron.left.forwardslash.chevron.right"),
        ("Platform",        "iOS / iPadOS","ipad"),
        ("GPU",             "Apple GPU",   "cpu"),
        ("Disk Space",      "—",           "internaldrive"),
        ("FFmpeg",          "PyAV native", "film"),
        ("Terminal",        "PTY",         "terminal"),
        ("Venv",            "embedded",    "shippingbox"),
        ("Python exe",      "embedded",    "doc"),
        ("Media dir",       "Documents/",  "folder"),
        ("Project root",    "Documents/",  "folder.fill"),
        ("Env Status",      "Ready",       "checkmark.seal"),
        ("LaTeX",           "busytex",     "function"),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("System").font(.system(size: 22, weight: .bold))
                        .foregroundStyle(Theme.textPrimary)
                    Spacer()
                    Button {} label: {
                        HStack(spacing: 5) {
                            Image(systemName: "arrow.clockwise")
                            Text("Refresh")
                        }
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .background(Capsule().fill(Theme.signatureGradient))
                    }.buttonStyle(.plain)
                }

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 200), spacing: 12)], spacing: 12) {
                    ForEach(infos.indices, id: \.self) { i in
                        infoCard(label: infos[i].0, value: infos[i].1, icon: infos[i].2)
                    }
                }
            }
            .padding(16)
        }
        .background(Theme.bgPrimary)
    }

    @ViewBuilder
    private func infoCard(label: String, value: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .font(.system(size: 14)).foregroundStyle(Theme.accentPrimary)
                Text(label.uppercased())
                    .font(.system(size: 10, weight: .semibold)).tracking(0.7)
                    .foregroundStyle(Theme.textDim)
                Spacer()
            }
            Text(value).font(.system(size: 14, weight: .medium))
                .foregroundStyle(Theme.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard(padding: 14)
    }
}
