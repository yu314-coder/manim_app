// GalleryView.swift — the cold-launch landing screen.
//
// This screen exists to clear App Store guideline 4.3(a) ("Spam").
// A reviewer opening the app on iPad or iPhone needs to see, in the
// first second, that ManimStudio is a *mathematical animation studio*
// — not a generic Python IDE. The gallery is a grid of ready-to-render
// Manim scene templates — "Hello Manim", Pythagorean theorem, unit-circle
// sine, Fourier partial sums, shape morph, depth-first graph walk — each
// card looping a render of its own template code (ManimPreviewPlayer;
// scripts/gallery-previews.py makes the videos, so they match). Tapping a
// card loads the scene's Python source into the shared editor buffer and
// jumps to the Workspace tab.
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
        EditedFile.shared.release()
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
                    title = Text("Hello, ManimStudio", font_size=80)
                    title.set_color_by_gradient(BLUE_C, PURPLE_B, PINK)
                    underline = Line(LEFT, RIGHT, stroke_width=6).set_width(title.width)
                    underline.next_to(title, DOWN, buff=0.3).set_color_by_gradient(BLUE_C, PINK)
                    tagline = Text("math, animated", font_size=40, color=GREY_B)
                    tagline.next_to(underline, DOWN, buff=0.4)
                    self.play(Write(title), run_time=1.8)
                    self.play(GrowFromCenter(underline), FadeIn(tagline, shift=UP * 0.3))
                    self.wait(0.4)
                    self.play(Circumscribe(title, color=PURPLE_B, buff=0.25))
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
                    a, b = 2.0, 1.5
                    shift = LEFT * 0.9 + DOWN * 0.9
                    A, B, C = ORIGIN + shift, RIGHT * a + shift, RIGHT * a + UP * b + shift
                    triangle = Polygon(A, B, C, color=WHITE, stroke_width=4)
                    corner = RightAngle(Line(B, A), Line(B, C), length=0.25, color=GREY_B)
                    hyp = C - A
                    c = np.linalg.norm(hyp)
                    normal = np.array([-hyp[1], hyp[0], 0]) / c
                    squares = VGroup(
                        Polygon(A, B, B + DOWN * a, A + DOWN * a),
                        Polygon(B, C, C + RIGHT * b, B + RIGHT * b),
                        Polygon(A, C, C + normal * c, A + normal * c),
                    )
                    colors = [BLUE_C, TEAL_C, PURPLE_B]
                    labels = VGroup()
                    for square, color, tex in zip(squares, colors, ["a^2", "b^2", "c^2"]):
                        square.set_stroke(color, 4).set_fill(color, opacity=0.3)
                        labels.add(MathTex(tex, color=color).move_to(square))
                    formula = MathTex("a^2", "+", "b^2", "=", "c^2").scale(1.2).to_edge(UP)
                    for i, color in zip([0, 2, 4], colors):
                        formula[i].set_color(color)

                    self.play(Create(triangle), Create(corner))
                    self.play(GrowFromEdge(squares[0], UP), GrowFromEdge(squares[1], LEFT),
                              FadeIn(squares[2], shift=normal * 0.3), run_time=1.2)
                    self.play(Write(labels))
                    self.play(TransformFromCopy(labels[0], formula[0]),
                              TransformFromCopy(labels[1], formula[2]),
                              TransformFromCopy(labels[2], formula[4]),
                              Write(formula[1]), Write(formula[3]), run_time=1.4)
                    self.play(Circumscribe(formula, color=YELLOW))
                    self.wait(1)
            """
        ),
        GalleryTemplate(
            id: "sine",
            title: "Sine Wave",
            subtitle: "A unit-circle trace projected onto its phase axis.",
            formula: "y = sin(θ)",
            accent: Theme.trace,
            sceneName: "SineWave",
            code: """
            from manim import *


            class SineWave(Scene):
                def construct(self):
                    r = 1.2
                    circle = Circle(radius=r, color=BLUE_C).shift(LEFT * 4.6)
                    center = circle.get_center()
                    axes = Axes(x_range=[0, TAU, PI / 2], y_range=[-1.2, 1.2, 1.2],
                                x_length=7, y_length=2 * 1.2 * r, tips=False,
                                axis_config={"color": GREY_B})
                    axes.shift(np.array([-2.5, center[1], 0]) - axes.c2p(0, 0))
                    ticks = VGroup(*[MathTex(t, font_size=30).next_to(axes.c2p(x, 0), DOWN)
                                     for t, x in [(r"\\pi", PI), (r"2\\pi", TAU)]])
                    title = MathTex(r"y = \\sin\\theta", font_size=48).to_edge(UP)

                    t = ValueTracker(0)
                    point = always_redraw(lambda: Dot(circle.point_at_angle(t.get_value()), color=YELLOW))
                    radius = always_redraw(lambda: Line(center, point.get_center(), color=YELLOW))
                    trace = always_redraw(lambda: axes.plot(
                        np.sin, x_range=[0, t.get_value() + 1e-3], color=YELLOW, stroke_width=5))
                    tip = always_redraw(lambda: Dot(axes.c2p(t.get_value(), np.sin(t.get_value())), color=YELLOW))
                    link = always_redraw(lambda: DashedLine(point.get_center(), tip.get_center(),
                                                            color=GREY_B, stroke_width=2))

                    self.play(Create(circle), Create(axes), Write(ticks), Write(title))
                    self.add(trace, radius, link, point, tip)
                    self.play(t.animate.set_value(TAU), run_time=5, rate_func=linear)
                    self.wait(1)
            """
        ),
        GalleryTemplate(
            id: "fourier",
            title: "Fourier Squares",
            subtitle: "Odd sine harmonics add up, step by step, to a square wave.",
            formula: "Σ (4/πk)·sin(kx)",
            accent: Theme.pink,
            sceneName: "FourierSquare",
            code: """
            from manim import *


            class FourierSquare(Scene):
                def construct(self):
                    axes = Axes(x_range=[-PI, PI, PI / 2], y_range=[-1.5, 1.5, 0.5],
                                x_length=10, y_length=4.5, tips=False,
                                axis_config={"color": GREY_B}).shift(DOWN * 0.5)
                    target = VGroup(
                        DashedLine(axes.c2p(-PI, -1), axes.c2p(0, -1)),
                        DashedLine(axes.c2p(0, -1), axes.c2p(0, 1)),
                        DashedLine(axes.c2p(0, 1), axes.c2p(PI, 1)),
                    ).set_stroke(GREY_C, 2)
                    formula = MathTex(r"S_N(x) = \\sum_{k \\text{ odd}}^{N} \\frac{4}{\\pi k}\\,\\sin kx",
                                      font_size=40).to_edge(UP)

                    def partial(n):
                        return lambda x: sum(4 / (PI * k) * np.sin(k * x) for k in range(1, n + 1, 2))

                    orders = [1, 3, 5, 9, 15, 31]
                    colors = color_gradient([BLUE_C, PURPLE_B, PINK], len(orders))
                    curve = axes.plot(partial(1), x_range=[-PI, PI, 0.01], color=colors[0], stroke_width=4)
                    count = MathTex("N = 1", font_size=40).to_corner(UR).shift(DOWN * 0.9)

                    self.play(Create(axes), Create(target), Write(formula))
                    self.play(Create(curve), Write(count))
                    for n, color in zip(orders[1:], colors[1:]):
                        self.play(Transform(curve, axes.plot(partial(n), x_range=[-PI, PI, 0.01],
                                                             color=color, stroke_width=4)),
                                  Transform(count, MathTex(f"N = {n}", font_size=40).move_to(count)),
                                  run_time=0.8)
                    self.wait(1)
            """
        ),
        GalleryTemplate(
            id: "morph",
            title: "Circle ↔ Square",
            subtitle: "A circle morphs into a square, a triangle, and back.",
            formula: "lerp(A, B, t)",
            accent: Theme.violet,
            sceneName: "CircleToSquare",
            code: """
            from manim import *


            class CircleToSquare(Scene):
                def construct(self):
                    shapes = [
                        Circle(radius=1.6).set_stroke(BLUE_C, 6).set_fill(BLUE_C, 0.35),
                        Square(3.0).rotate(PI / 4).set_stroke(TEAL_C, 6).set_fill(TEAL_C, 0.35),
                        Triangle().scale(2.0).set_stroke(PINK, 6).set_fill(PINK, 0.35),
                    ]
                    for s in shapes:
                        s.shift(DOWN * 0.3)
                    title = MathTex(r"\\mathrm{lerp}(A, B, t)", font_size=44).to_edge(UP)
                    t = ValueTracker(0)
                    readout = always_redraw(lambda: VGroup(
                        MathTex("t =", font_size=40),
                        DecimalNumber(t.get_value(), num_decimal_places=2, font_size=40),
                    ).arrange(RIGHT).to_edge(DOWN))

                    shape = shapes[0].copy()
                    self.play(Write(title), DrawBorderThenFill(shape), FadeIn(readout))
                    for target in shapes[1:] + shapes[:1]:
                        t.set_value(0)
                        self.play(Transform(shape, target.copy()), t.animate.set_value(1),
                                  run_time=1.2, rate_func=smooth)
                        self.wait(0.3)
                    self.wait(0.5)
            """
        ),
        GalleryTemplate(
            id: "graph",
            title: "Graph Traversal",
            subtitle: "Depth-first walk over a planar graph, highlighting each visited edge.",
            formula: "DFS(G, 1)",
            accent: Theme.pink,
            sceneName: "GraphWalk",
            code: """
            from manim import *


            class GraphWalk(Scene):
                def construct(self):
                    vertices = [1, 2, 3, 4, 5, 6]
                    edges = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 1), (2, 5), (3, 6)]
                    g = Graph(vertices, edges, layout="circular", layout_scale=2.2, labels=True,
                              edge_config={"stroke_color": GREY_B, "stroke_width": 3}).shift(UP * 0.3)
                    title = MathTex(r"\\mathrm{DFS}(G,\\ 1)", font_size=44).to_edge(UP)
                    self.play(Write(title), Create(g))

                    neighbours = {v: [] for v in vertices}
                    for a, b in edges:
                        neighbours[a].append(b)
                        neighbours[b].append(a)

                    cursor = Circle(radius=0.38, color=YELLOW, stroke_width=6).move_to(g.vertices[1])
                    order = VGroup(MathTex("1", color=YELLOW)).to_edge(DOWN)
                    self.play(Create(cursor), Write(order))
                    visited = {1}

                    def visit(v):
                        for u in sorted(neighbours[v]):
                            if u in visited:
                                continue
                            visited.add(u)
                            edge = g.edges.get((v, u)) or g.edges.get((u, v))
                            step = VGroup(MathTex(r"\\to"), MathTex(str(u), color=YELLOW)).arrange(RIGHT, buff=0.15)
                            step.next_to(order, RIGHT, buff=0.15)
                            order.add(step)
                            self.play(edge.animate.set_stroke(YELLOW, 6),
                                      cursor.animate.move_to(g.vertices[u]),
                                      FadeIn(step, shift=LEFT * 0.2), run_time=0.6)
                            visit(u)
                            # Back the way it came, as a depth-first search does.
                            self.play(cursor.animate.move_to(g.vertices[v]), run_time=0.3)

                    visit(1)
                    self.play(order.animate.set_x(0))
                    self.wait(1)
            """
        ),
    ]
}
