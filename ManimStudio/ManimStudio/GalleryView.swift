// GalleryView.swift — the cold-launch landing screen.
//
// This screen exists to clear App Store guideline 4.3(a) ("Spam").
// A reviewer opening the app on iPad or iPhone needs to see, in the
// first second, that ManimStudio is a *mathematical animation studio*
// — not a generic Python IDE. The gallery is a grid of ready-to-render
// Manim scene templates — "Hello Manim", the Pythagorean rearrangement
// proof, unit-circle sine, Fourier epicycles, a 3D ripple surface and a
// breadth-first search on a grid — each
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
            subtitle: "A gradient wordmark inside an orbiting ring of dots.",
            formula: "manim.Write(text)",
            accent: Theme.violet,
            sceneName: "HelloManim",
            code: """
            from manim import *


            class HelloManim(Scene):
                def construct(self):
                    title = Text("Hello, ManimStudio", font_size=64)
                    title.set_color_by_gradient(BLUE_C, PURPLE_B, PINK)
                    tagline = Text("math, animated", font_size=34, color=GREY_B)
                    tagline.next_to(title, DOWN, buff=0.35)
                    colors = color_gradient([BLUE_C, PURPLE_B, PINK, BLUE_C], 48)
                    ring = VGroup(*[
                        Dot(radius=0.07, color=c).move_to(np.array([4.9 * np.cos(a), 2.1 * np.sin(a), 0]))
                        for a, c in zip(np.linspace(0, TAU, 48, endpoint=False), colors)
                    ])
                    self.play(Write(title), run_time=1.6)
                    self.play(FadeIn(tagline, shift=UP * 0.3),
                              LaggedStart(*[GrowFromCenter(d) for d in ring], lag_ratio=0.03),
                              run_time=1.4)
                    self.play(Rotate(ring, TAU / 3, about_point=ORIGIN, rate_func=smooth),
                              title.animate.scale(1.08), run_time=1.6)
                    self.play(title.animate.scale(1 / 1.08),
                              Rotate(ring, TAU / 6, about_point=ORIGIN), run_time=0.8)
                    self.wait(0.6)
            """
        ),
        GalleryTemplate(
            id: "pythag",
            title: "Pythagorean Theorem",
            subtitle: "The rearrangement proof: four triangles slide and c² becomes a² + b².",
            formula: "a² + b² = c²",
            accent: Theme.indigo,
            sceneName: "Pythagorean",
            code: """
            from manim import *


            class Pythagorean(Scene):
                def construct(self):
                    a, b = 1.5, 2.5
                    s = a + b
                    o = np.array([-s / 2, -s / 2 - 0.45, 0])

                    def P(x, y):
                        return o + np.array([x, y, 0])

                    frame = Square(s, color=WHITE, stroke_width=3).move_to(P(s / 2, s / 2))
                    # Four right triangles (legs a, b) around a tilted square of side c ...
                    before = [
                        [P(0, 0), P(a, 0), P(0, b)],
                        [P(s, 0), P(s, a), P(a, 0)],
                        [P(s, s), P(b, s), P(s, a)],
                        [P(0, s), P(0, b), P(b, s)],
                    ]
                    # ... and the same four, paired into two rectangles beside a² and b².
                    after = [
                        [P(0, a), P(a, a), P(0, s)],
                        [P(s, 0), P(s, a), P(a, 0)],
                        [P(a, a), P(a, 0), P(s, a)],
                        [P(a, s), P(0, s), P(a, a)],
                    ]
                    tri_colors = [BLUE_D, TEAL_D, BLUE_D, TEAL_D]
                    triangles = VGroup(*[
                        Polygon(*pts, stroke_color=WHITE, stroke_width=2).set_fill(c, 0.85)
                        for pts, c in zip(before, tri_colors)
                    ])
                    c_sq = Polygon(P(a, 0), P(s, a), P(b, s), P(0, b), stroke_width=0).set_fill(PURPLE_B, 0.45)
                    c_lbl = MathTex("c^2", font_size=56).move_to(c_sq)
                    a_sq = Square(a, stroke_width=0).set_fill(BLUE_C, 0.45).move_to(P(a / 2, a / 2))
                    b_sq = Square(b, stroke_width=0).set_fill(PINK, 0.45).move_to(P(a + b / 2, a + b / 2))
                    a_lbl = MathTex("a^2", font_size=44).move_to(a_sq)
                    b_lbl = MathTex("b^2", font_size=56).move_to(b_sq)
                    formula = MathTex("a^2", "+", "b^2", "=", "c^2", font_size=56).to_edge(UP, buff=0.35)
                    formula[0].set_color(BLUE_C)
                    formula[2].set_color(PINK)
                    formula[4].set_color(PURPLE_B)

                    self.play(Create(frame))
                    self.play(LaggedStart(*[DrawBorderThenFill(t) for t in triangles], lag_ratio=0.2), run_time=1.4)
                    self.play(FadeIn(c_sq), Write(c_lbl))
                    self.play(TransformFromCopy(c_lbl, formula[4]))
                    self.play(FadeOut(c_sq), FadeOut(c_lbl))
                    self.play(*[t.animate.set_points_as_corners([*pts, pts[0]])
                                for t, pts in zip(triangles, after)], run_time=1.8)
                    self.play(FadeIn(a_sq), FadeIn(b_sq), Write(a_lbl), Write(b_lbl))
                    self.play(TransformFromCopy(a_lbl, formula[0]), TransformFromCopy(b_lbl, formula[2]),
                              Write(formula[1]), Write(formula[3]))
                    self.play(Circumscribe(formula, color=YELLOW))
                    self.wait(0.8)
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
                    r = 1.3
                    circle = Circle(radius=r, color=BLUE_C, stroke_width=4).shift(LEFT * 4.5)
                    center = circle.get_center()
                    cross = VGroup(Line(center + LEFT * (r + 0.3), center + RIGHT * (r + 0.3)),
                                   Line(center + DOWN * (r + 0.3), center + UP * (r + 0.3))).set_stroke(GREY_D, 2)
                    axes = Axes(x_range=[0, TAU, PI / 2], y_range=[-1, 1, 1], x_length=7.2,
                                y_length=2 * r, tips=False, axis_config={"color": GREY_B})
                    axes.shift(np.array([-2.4, center[1], 0]) - axes.c2p(0, 0))
                    ticks = VGroup(*[MathTex(t, font_size=30).next_to(axes.c2p(x, 0), DOWN)
                                     for t, x in [(r"\\pi", PI), (r"2\\pi", TAU)]])
                    title = MathTex(r"y = \\sin\\theta", font_size=52).to_edge(UP)

                    t = ValueTracker(0.001)
                    point = always_redraw(lambda: Dot(circle.point_at_angle(t.get_value()), color=YELLOW, radius=0.09))
                    arm = always_redraw(lambda: Line(center, point.get_center(), color=YELLOW, stroke_width=4))
                    drop = always_redraw(lambda: Line(
                        point.get_center(), [point.get_x(), center[1], 0], color=PINK, stroke_width=3))
                    arc = always_redraw(lambda: Arc(radius=0.35, angle=t.get_value(), arc_center=center,
                                                    color=PINK, stroke_width=3))
                    theta = always_redraw(lambda: MathTex(r"\\theta", font_size=34, color=PINK).move_to(
                        center + 0.62 * np.array([np.cos(t.get_value() / 2), np.sin(t.get_value() / 2), 0])))
                    trace = always_redraw(lambda: axes.plot(
                        np.sin, x_range=[0, t.get_value()], color=YELLOW, stroke_width=5))
                    tip = always_redraw(lambda: Dot(axes.c2p(t.get_value(), np.sin(t.get_value())),
                                                    color=YELLOW, radius=0.09))
                    link = always_redraw(lambda: DashedLine(point.get_center(), tip.get_center(),
                                                            color=GREY_B, stroke_width=2))

                    self.play(Create(cross), Create(circle), Create(axes), Write(ticks), Write(title))
                    self.add(trace, arc, theta, drop, arm, link, point, tip)
                    self.play(t.animate.set_value(TAU), run_time=5, rate_func=linear)
                    self.play(Indicate(title, color=YELLOW))
                    self.wait(0.5)
            """
        ),
        GalleryTemplate(
            id: "fourier",
            title: "Fourier Squares",
            subtitle: "Five rotating epicycles draw a square wave.",
            formula: "Σ (4/πn)·sin(nt)",
            accent: Theme.pink,
            sceneName: "FourierSquare",
            code: """
            from manim import *


            class FourierSquare(Scene):
                def construct(self):
                    orders = [1, 3, 5, 7, 9]
                    radii = [1.4 * 4 / (PI * n) for n in orders]
                    colors = color_gradient([BLUE_C, PURPLE_B, PINK], len(orders))
                    center = np.array([-4.3, -0.3, 0])
                    x0 = -1.6
                    speed = 0.45
                    t = ValueTracker(0)

                    def joints(time):
                        p = center.copy()
                        pts = [p.copy()]
                        for n, r in zip(orders, radii):
                            p = p + r * np.array([np.cos(n * time), np.sin(n * time), 0])
                            pts.append(p.copy())
                        return pts

                    def epicycles():
                        pts = joints(t.get_value())
                        group = VGroup()
                        for i, (r, c) in enumerate(zip(radii, colors)):
                            group.add(Circle(radius=r, color=c, stroke_width=2, stroke_opacity=0.6).move_to(pts[i]))
                            group.add(Line(pts[i], pts[i + 1], color=c, stroke_width=3))
                        return group

                    def wave():
                        now = t.get_value()
                        span = min(now, 7.0 / speed)
                        return ParametricFunction(
                            lambda s: np.array([x0 + speed * s, joints(now - s)[-1][1], 0]),
                            t_range=[0, max(span, 0.01), 0.02], color=YELLOW, stroke_width=4)

                    circles = always_redraw(epicycles)
                    curve = always_redraw(wave)
                    tip = always_redraw(lambda: Dot(joints(t.get_value())[-1], color=YELLOW, radius=0.07))
                    link = always_redraw(lambda: DashedLine(
                        joints(t.get_value())[-1], [x0, joints(t.get_value())[-1][1], 0],
                        color=GREY_B, stroke_width=2))
                    title = MathTex(r"\\sum_{n \\text{ odd}} \\frac{4}{\\pi n}\\, \\sin n t", font_size=46).to_edge(UP)
                    axis = Line([x0, center[1], 0], [6.6, center[1], 0], color=GREY_D, stroke_width=2)

                    self.play(Write(title), Create(axis), Create(circles))
                    self.add(curve, link, tip)
                    self.play(t.animate.set_value(3 * TAU / 2), run_time=7, rate_func=linear)
                    self.wait(0.4)
            """
        ),
        GalleryTemplate(
            id: "surface",
            title: "3D Ripple Surface",
            subtitle: "A rippling surface, coloured by height, under an orbiting camera.",
            formula: "z = cos(2.2r)·e^(−0.35r)",
            accent: Theme.violet,
            sceneName: "RippleSurface",
            code: """
            from manim import *


            class RippleSurface(ThreeDScene):
                def construct(self):
                    axes = ThreeDAxes(x_range=[-3, 3, 1], y_range=[-3, 3, 1], z_range=[-1, 1, 1],
                                      x_length=6, y_length=6, z_length=2.4,
                                      axis_config={"color": GREY_B, "stroke_width": 2})

                    def ripple(u, v):
                        r = np.sqrt(u * u + v * v)
                        return axes.c2p(u, v, np.cos(2.2 * r) * np.exp(-0.35 * r))

                    surface = Surface(ripple, u_range=[-3, 3], v_range=[-3, 3], resolution=(20, 20),
                                      stroke_width=0.4, stroke_color=BLACK, fill_opacity=0.9)
                    surface.set_fill_by_value(axes=axes, colorscale=[(BLUE_E, -0.6), (TEAL_C, 0), (YELLOW, 1)], axis=2)
                    title = MathTex(r"z = \\cos(2.2\\,r)\\,e^{-0.35\\,r}", font_size=44).to_corner(UL)
                    self.add_fixed_in_frame_mobjects(title)
                    title.set_opacity(0)

                    self.set_camera_orientation(phi=62 * DEGREES, theta=-50 * DEGREES, zoom=0.85)
                    self.play(Create(axes), title.animate.set_opacity(1))
                    self.play(Create(surface), run_time=1.5)
                    self.begin_ambient_camera_rotation(rate=0.45)
                    self.wait(3)
                    self.stop_ambient_camera_rotation()
            """
        ),
        GalleryTemplate(
            id: "graph",
            title: "Graph Traversal",
            subtitle: "Breadth-first search spreads from one node in coloured waves.",
            formula: "BFS(G, s)",
            accent: Theme.pink,
            sceneName: "GraphWalk",
            code: """
            from manim import *


            class GraphWalk(Scene):
                def construct(self):
                    rows, cols = 7, 11
                    vertices = [(r, c) for r in range(rows) for c in range(cols)]
                    edges = [((r, c), (r, c + 1)) for r in range(rows) for c in range(cols - 1)]
                    edges += [((r, c), (r + 1, c)) for r in range(rows - 1) for c in range(cols)]
                    layout = {(r, c): np.array([(c - (cols - 1) / 2) * 0.62, (r - (rows - 1) / 2) * 0.62 - 0.35, 0])
                              for r, c in vertices}
                    g = Graph(vertices, edges, layout=layout,
                              vertex_config={"radius": 0.08, "color": GREY_C},
                              edge_config={"stroke_color": GREY_D, "stroke_width": 2})
                    title = MathTex(r"\\mathrm{BFS}(G,\\ s)", font_size=48).to_edge(UP, buff=0.3)
                    self.play(Write(title), Create(g), run_time=1.5)

                    source = (3, 5)
                    dist = {v: abs(v[0] - source[0]) + abs(v[1] - source[1]) for v in vertices}
                    far = max(dist.values())
                    colors = color_gradient([YELLOW, PINK, PURPLE_B, BLUE_C], far + 1)
                    self.play(g.vertices[source].animate.set_color(YELLOW).scale(2), run_time=0.4)
                    for d in range(1, far + 1):
                        layer = [v for v in vertices if dist[v] == d]
                        reached = [e for e in edges if {dist[e[0]], dist[e[1]]} == {d - 1, d}]
                        self.play(*[g.vertices[v].animate.set_color(colors[d]).scale(1.6) for v in layer],
                                  *[g.edges[e].animate.set_stroke(colors[d], 4) for e in reached],
                                  run_time=0.28, rate_func=linear)
                    self.play(Indicate(title, color=YELLOW))
                    self.wait(0.6)
            """
        ),
    ]
}
