// AppTab.swift — top-level tab pills (Workspace / System / Assets / Packages / History)
import SwiftUI

enum AppTab: String, CaseIterable, Identifiable {
    case workspace, system, assets, packages, history
    var id: String { rawValue }

    var title: String {
        switch self {
        case .workspace: return "Workspace"
        case .system:    return "System"
        case .assets:    return "Assets"
        case .packages:  return "Packages"
        case .history:   return "History"
        }
    }

    var icon: String {
        switch self {
        case .workspace: return "rectangle.split.3x1"
        case .system:    return "cpu"
        case .assets:    return "folder"
        case .packages:  return "shippingbox"
        case .history:   return "clock.arrow.circlepath"
        }
    }
}
