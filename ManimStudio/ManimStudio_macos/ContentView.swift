// ContentView.swift — macOS root view. Hosts WebHost which loads
// Resources/web/index.html (the unmodified frontend from the desktop
// app on `main`). Eventually a Python subprocess driven by
// PythonHost will respond to window.pywebview.api.* calls.
//
// This file is the *macOS-only* ContentView and shadows nothing on
// the iOS side — by design the two targets share zero Swift code,
// only the AppIcon asset.
import SwiftUI

struct ContentView: View {
    var body: some View {
        WebHost()
            .frame(minWidth: 1100, minHeight: 700)
            .background(Color(white: 0.06))
    }
}

#Preview { ContentView() }
