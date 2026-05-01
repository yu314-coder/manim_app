// SceneDetector.swift — scans Python source for `class X(...Scene...):`
// definitions so the user can pick which one to render.
import Foundation

enum SceneDetector {
    /// Returns the list of class names that look like manim Scene subclasses.
    /// Matches `class Foo(Scene):`, `class Foo(MovingCameraScene):`,
    /// `class Foo(ThreeDScene, Foo):`, etc.
    static func detect(in source: String) -> [String] {
        // Anchor at line start (multiline mode) and capture the class name.
        // Accept any base-class containing "Scene" — covers all manim Scene
        // subclasses (Scene, MovingCameraScene, ThreeDScene, ZoomedScene,
        // VectorScene, GraphScene, MovingCameraScene, etc.).
        let pattern = #"(?m)^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*:"#
        guard let re = try? NSRegularExpression(pattern: pattern) else { return [] }
        let ns = source as NSString
        var names: [String] = []
        var seen: Set<String> = []
        re.enumerateMatches(in: source,
                            range: NSRange(location: 0, length: ns.length)) { m, _, _ in
            guard let m, m.numberOfRanges >= 3 else { return }
            let name = ns.substring(with: m.range(at: 1))
            let bases = ns.substring(with: m.range(at: 2))
            // Heuristic: any base mentioning "Scene" counts.
            if bases.contains("Scene"), !seen.contains(name) {
                seen.insert(name)
                names.append(name)
            }
        }
        return names
    }
}
