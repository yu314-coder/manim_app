// Haptics.swift — thin wrapper over UIFeedbackGenerator for tactile
// feedback on key actions (tab/pane switches, Run/Preview/Stop, render
// finished). UIFeedbackGenerator no-ops automatically on devices without
// a Taptic Engine (most iPads), so call sites don't need to gate on
// device or size class. Generators are cheap to create per-event; for
// the low call rate here that's fine and avoids retaining state.
import UIKit

enum Haptics {
    /// Light tick for selection changes — tab and pane switches.
    static func selection() {
        let g = UISelectionFeedbackGenerator()
        g.selectionChanged()
    }

    /// Physical "tap" for committing an action (Run / Preview / Stop).
    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .medium) {
        let g = UIImpactFeedbackGenerator(style: style)
        g.impactOccurred()
    }

    /// Success / warning / error notification feedback (render finished).
    static func notify(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        let g = UINotificationFeedbackGenerator()
        g.notificationOccurred(type)
    }
}
