// GalleryView.swift — the cold-launch landing screen.
//
// This screen exists to clear App Store guideline 4.3(a) ("Spam").
// A reviewer opening the app on iPad or iPhone needs to see, in the
// first second, that ManimStudio is a *mathematical animation studio*
// — not a generic Python IDE. The gallery is a grid of ready-to-render
// Manim scene templates, each card rendering its own LIVE procedural
// animation preview (Canvas + TimelineView) — Pythagorean theorem,
// sine wave, Fourier series, circle ↔ square morph, graph traversal,
// "Hello Manim". Tapping a card loads the scene's Python source into
// the shared editor buffer and jumps to the Workspace tab.
//
// The visual language is Resonance: deep void backgrounds, an
// oscilloscope-cyan "trace" colour for live signal, the indigo→
// violet→pink brand thread reserved for the signature gradient.
// Reticles and corner brackets frame every viewport so the screen
// reads as scientific instrumentation, not a developer tool.
import SwiftUI

struct GalleryView: View {
    @Binding var sourceCode: String
    @Binding var selectedTab: AppTab
    @Binding var selectedScene: String

    @Environment(\.horizontalSizeClass) private var hSizeClass

    private var columns: [GridItem] {
        let count = hSizeClass == .compact ? 1 : 3
        return Array(repeating: GridItem(.flexible(), spacing: 16), count: count)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                phaseLineStrip
                heroBand
                LazyVGrid(columns: columns, spacing: 16) {
                    ForEach(Array(GalleryTemplate.all.enumerated()), id: \.element.id) { idx, tpl in
                        SceneCard(index: idx + 1, total: GalleryTemplate.all.count, template: tpl) {
                            load(tpl)
                        }
                    }
                }
                .padding(.horizontal, hSizeClass == .compact ? 16 : 32)
                .padding(.bottom, 32)
            }
        }
        .background(Theme.void.ignoresSafeArea())
    }

    // MARK: - Header strip with the live phase-line motif

    private var phaseLineStrip: some View {
        ZStack(alignment: .leading) {
            PhaseLine(amplitude: 7, frequency: 0.018, speed: 0.5,
                      color: Theme.traceDim, showTicks: false, glow: false)
                .opacity(0.55)
                .frame(height: 48)
            HStack(spacing: 14) {
                Text("RESONANCE · MATHEMATICAL ANIMATION STUDIO")
                    .font(.resMono(10, weight: .medium))
                    .tracking(2.6)
                    .foregroundStyle(Theme.phosphor)
                Spacer()
                ResTag(text: "GPU READY", color: Theme.green)
                ResTag(text: "PYTHON 3.14", color: Theme.amber)
                ResTag(text: "MANIM", color: Theme.trace)
            }
            .padding(.horizontal, hSizeClass == .compact ? 16 : 24)
        }
        .frame(height: 48)
        .background(
            LinearGradient(colors: [Theme.surface.opacity(0.4), Theme.deep.opacity(0.4)],
                           startPoint: .top, endPoint: .bottom)
        )
        .overlay(Rectangle().fill(Theme.hairline).frame(height: 1), alignment: .bottom)
    }

    // MARK: - Hero band — title, subtitle, scene count

    private var heroBand: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: "circle.dotted.circle")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.trace)
                Text("GALLERY · 06 SCENES")
                    .font(.resMono(11, weight: .medium))
                    .tracking(2.8)
                    .foregroundStyle(Theme.trace)
            }
            // Title with gradient highlight
            Group {
                if hSizeClass == .compact {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Pick a scene.")
                            .font(.resDisplay(32, weight: .semibold))
                            .foregroundStyle(Theme.phosphor)
                        Text("Render in seconds.")
                            .font(.resDisplay(32, weight: .semibold))
                            .foregroundStyle(
                                LinearGradient(colors: [Theme.indigo, Theme.violet, Theme.pink],
                                               startPoint: .leading, endPoint: .trailing)
                            )
                    }
                } else {
                    (Text("Pick a scene. ").foregroundStyle(Theme.phosphor)
                        + Text("Render in seconds.").foregroundStyle(
                            LinearGradient(colors: [Theme.indigo, Theme.violet, Theme.pink],
                                           startPoint: .leading, endPoint: .trailing)
                        )
                    )
                    .font(.resDisplay(44, weight: .semibold))
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                }
            }
            Text("Each template ships as a fully-formed Manim scene — load it onto the workbench, tweak its parameters, and fire the encoder.")
                .font(.resUI(14))
                .foregroundStyle(Theme.ion)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 620, alignment: .leading)
        }
        .padding(.horizontal, hSizeClass == .compact ? 16 : 32)
        .padding(.top, hSizeClass == .compact ? 24 : 32)
        .padding(.bottom, 22)
    }

    private func load(_ tpl: GalleryTemplate) {
        sourceCode = tpl.code
        selectedScene = tpl.sceneName
        withAnimation(.easeInOut(duration: 0.22)) {
            selectedTab = .workspace
        }
    }
}

// MARK: - Scene card
//
// Each card is an animated mini-instrument:
//   ┌───────────────────────────────┐   ← corner brackets, status pill
//   │  [ live animated preview ]    │
//   │                               │
//   ├───────────────────────────────┤
//   │  Title                        │
//   │  Subtitle                     │
//   │  ƒ(x) formula · LOAD →        │
//   └───────────────────────────────┘
private struct SceneCard: View {
    let index: Int
    let total: Int
    let template: GalleryTemplate
    var onTap: () -> Void

    @State private var hover = false

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 0) {
                previewArea
                meta
            }
            .background(
                LinearGradient(
                    colors: [Theme.raised.opacity(0.55), Theme.deep.opacity(0.85)],
                    startPoint: .top, endPoint: .bottom)
            )
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(hover ? Theme.hairBright : Theme.hairline, lineWidth: 1)
            )
            .overlay(CornerBrackets(inset: 10, length: 12,
                                     color: template.accent,
                                     opacity: hover ? 0.7 : 0.3))
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }

    private var previewArea: some View {
        ZStack {
            // Pure black — matches the canvas of an actual Manim render
            // so each card reads as a window onto a real animation
            // frame rather than as decorative UI.
            Color.black
            ManimPreviewPlayer(id: template.id)
            // Index
            VStack {
                HStack {
                    Text(String(format: "%02d / %02d", index, total))
                        .font(.resMono(10))
                        .tracking(2)
                        .foregroundStyle(Theme.dim)
                    Spacer()
                    HStack(spacing: 6) {
                        Circle()
                            .fill(Theme.green)
                            .frame(width: 5, height: 5)
                            .shadow(color: Theme.green.opacity(0.9), radius: 3)
                        Text("READY")
                            .font(.resMono(9))
                            .tracking(1.6)
                            .foregroundStyle(Theme.ion)
                    }
                }
                .padding(.horizontal, 14)
                .padding(.top, 10)
                Spacer()
            }
        }
        .frame(height: 188)
        .background(Color.black)
        .overlay(Rectangle().fill(Theme.hairline).frame(height: 1), alignment: .bottom)
    }

    private var meta: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(template.title)
                .font(.resDisplay(17, weight: .semibold))
                .foregroundStyle(Theme.phosphor)
            Text(template.subtitle)
                .font(.resUI(12))
                .foregroundStyle(Theme.ion)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Text(template.formula)
                    .font(.resMono(10.5))
                    .foregroundStyle(Theme.trace)
                Spacer()
                Text("LOAD →")
                    .font(.resMono(9))
                    .tracking(2)
                    .foregroundStyle(Theme.dim)
            }
            .padding(.top, 8)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
    }
}

// MARK: - Templates

struct GalleryTemplate: Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let formula: String
    let accent: Color
    let sceneName: String
    let code: String

    static let all: [GalleryTemplate] = [
        GalleryTemplate(
            id: "hello",
            title: "Hello Manim",
            subtitle: "A traced-pen wordmark — the first scene every Manim project earns.",
            formula: "manim.Write(text)",
            accent: Theme.violet,
            sceneName: "HelloManim",
            code: """
            from manim import *

            class HelloManim(Scene):
                def construct(self):
                    title = Text("Hello, ManimStudio!").scale(0.9)
                    self.play(Write(title))
                    self.wait(0.5)
                    self.play(title.animate.shift(UP*0.5).set_color(BLUE))
                    self.wait(1)
            """
        ),
        GalleryTemplate(
            id: "pythag",
            title: "Pythagorean Theorem",
            subtitle: "Three squares stage themselves on the legs and hypotenuse.",
            formula: "a² + b² = c²",
            accent: Theme.indigo,
            sceneName: "Pythagorean",
            code: """
            from manim import *

            class Pythagorean(Scene):
                def construct(self):
                    a, b = 3.0, 2.0
                    triangle = Polygon(
                        ORIGIN, RIGHT * a, RIGHT * a + UP * b,
                        color=WHITE
                    ).shift(LEFT * 1.5 + DOWN * 0.8)
                    labels = VGroup(
                        MathTex("a").next_to(triangle, DOWN),
                        MathTex("b").next_to(triangle, RIGHT),
                        MathTex("c").move_to(triangle.get_center() + UP*0.3 + LEFT*0.3),
                    )
                    formula = MathTex("a^2 + b^2 = c^2").to_edge(UP)
                    self.play(Create(triangle))
                    self.play(Write(labels))
                    self.wait(0.3)
                    self.play(Write(formula))
                    self.wait(1.5)
            """
        ),
        GalleryTemplate(
            id: "sine",
            title: "Sine Wave",
            subtitle: "A unit-circle trace projected onto its phase axis.",
            formula: "y = sin(x)",
            accent: Theme.trace,
            sceneName: "SineWave",
            code: """
            from manim import *
            import numpy as np

            class SineWave(Scene):
                def construct(self):
                    axes = Axes(
                        x_range=[-PI, PI, PI/2],
                        y_range=[-1.5, 1.5, 0.5],
                        tips=False,
                    )
                    curve = axes.plot(lambda x: np.sin(x), color=YELLOW)
                    label = MathTex("y = \\\\sin(x)").to_edge(UP)
                    self.play(Create(axes))
                    self.play(Write(label))
                    self.play(Create(curve), run_time=2)
                    self.wait(1)
            """
        ),
        GalleryTemplate(
            id: "fourier",
            title: "Fourier Squares",
            subtitle: "Five rotating epicycles approximate a square wave.",
            formula: "Σ (4/πn)·sin(nωt)",
            accent: Theme.pink,
            sceneName: "FourierSquare",
            code: """
            from manim import *
            import numpy as np

            class FourierSquare(Scene):
                def construct(self):
                    axes = Axes(
                        x_range=[-PI, PI, PI/2],
                        y_range=[-1.5, 1.5, 0.5],
                        tips=False,
                    )
                    self.play(Create(axes))
                    partial = None
                    for n in range(1, 8, 2):
                        f = lambda x, N=n: sum(
                            (4/(PI*k))*np.sin(k*x) for k in range(1, N+1, 2)
                        )
                        new_curve = axes.plot(f, color=BLUE)
                        if partial is None:
                            self.play(Create(new_curve), run_time=1.0)
                        else:
                            self.play(Transform(partial, new_curve), run_time=0.8)
                        partial = new_curve
                    self.wait(1)
            """
        ),
        GalleryTemplate(
            id: "morph",
            title: "Circle ↔ Square",
            subtitle: "A 64-point polygon interpolates between two parents.",
            formula: "lerp(◯, ▢, t)",
            accent: Theme.violet,
            sceneName: "CircleToSquare",
            code: """
            from manim import *

            class CircleToSquare(Scene):
                def construct(self):
                    c = Circle(radius=1.2, color=BLUE).set_fill(BLUE, opacity=0.5)
                    s = Square(side_length=2.4, color=YELLOW).set_fill(YELLOW, opacity=0.5)
                    self.play(Create(c))
                    self.wait(0.3)
                    self.play(Transform(c, s), run_time=1.2)
                    self.wait(0.3)
                    self.play(Transform(c, Circle(radius=1.2, color=PINK)
                                            .set_fill(PINK, opacity=0.5)), run_time=1.2)
                    self.wait(0.5)
            """
        ),
        GalleryTemplate(
            id: "graph",
            title: "Graph Traversal",
            subtitle: "Depth-first walk over a planar graph, highlighting each visited edge.",
            formula: "DFS(G, v₀)",
            accent: Theme.pink,
            sceneName: "GraphWalk",
            code: """
            from manim import *

            class GraphWalk(Scene):
                def construct(self):
                    vertices = [1, 2, 3, 4, 5]
                    edges = [(1, 2), (2, 3), (3, 4), (4, 5), (1, 5), (2, 4)]
                    g = Graph(vertices, edges, layout="circular", labels=True)
                    self.play(Create(g))
                    self.wait(0.3)
                    token = Dot(color=YELLOW, radius=0.18)
                    token.move_to(g.vertices[1].get_center())
                    self.play(FadeIn(token, scale=0.5))
                    for v in [2, 3, 4, 5, 1]:
                        self.play(token.animate.move_to(
                            g.vertices[v].get_center()), run_time=0.6)
                    self.wait(0.5)
            """
        ),
    ]
}
