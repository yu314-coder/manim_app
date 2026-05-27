// AppTab.swift — top-level tab pills.
// Gallery is first (and the default landing tab) so the app reads as
// "mathematical animation studio" on cold launch, not "code editor".
import SwiftUI

enum AppTab: String, CaseIterable, Identifiable {
    case gallery, workspace, assets, packages, history, system
    var id: String { rawValue }

    var title: String {
        switch self {
        case .gallery:   return "Gallery"
        case .workspace: return "Workspace"
        case .system:    return "System"
        case .assets:    return "Assets"
        case .packages:  return "Packages"
        case .history:   return "History"
        }
    }

    var icon: String {
        switch self {
        case .gallery:   return "sparkles.rectangle.stack"
        case .workspace: return "rectangle.split.3x1"
        case .system:    return "cpu"
        case .assets:    return "folder"
        case .packages:  return "shippingbox"
        case .history:   return "clock.arrow.circlepath"
        }
    }
}
