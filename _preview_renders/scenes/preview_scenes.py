# preview_scenes.py — Real Manim scenes rendered as short looping
# previews for the Gallery cards.
#
# Each scene is intentionally short (~3 seconds) and renders at a
# small resolution so the bundled MP4 stays under 200 KB. The scenes
# mirror the six GalleryTemplate entries in the iOS app.
#
# Render with:
#   manim -ql -v WARNING --disable_caching preview_scenes.py SceneName

from manim import *


# ─────────────────────────────────────────────────────────────
# 1. Hello Manim
# ─────────────────────────────────────────────────────────────
class HelloPreview(Scene):
    def construct(self):
        title = Text("Hello, Manim").scale(0.95)
        self.play(Write(title), run_time=1.4)
        self.wait(0.2)
        self.play(title.animate.shift(UP * 0.4).set_color(BLUE), run_time=0.8)
        self.wait(0.6)


# ─────────────────────────────────────────────────────────────
# 2. Pythagorean theorem — three squares on the sides
# ─────────────────────────────────────────────────────────────
class PythagPreview(Scene):
    def construct(self):
        a, b = 2.0, 1.5
        # Right triangle with right angle at origin
        A = ORIGIN
        B = RIGHT * a
        C = RIGHT * a + UP * b
        tri = Polygon(A, B, C, color=WHITE, stroke_width=3).shift(LEFT * 0.7 + DOWN * 0.4)
        # Squares on the three sides
        sq_a = Square(side_length=a, color=BLUE, fill_opacity=0.25).next_to(
            tri.get_edge_center(DOWN), DOWN, buff=0
        ).shift(RIGHT * 0)
        sq_a = Polygon(
            tri.get_vertices()[0],
            tri.get_vertices()[1],
            tri.get_vertices()[1] + DOWN * a,
            tri.get_vertices()[0] + DOWN * a,
            color=BLUE, fill_opacity=0.25, stroke_width=3,
        )
        sq_b = Polygon(
            tri.get_vertices()[1],
            tri.get_vertices()[2],
            tri.get_vertices()[2] + RIGHT * b,
            tri.get_vertices()[1] + RIGHT * b,
            color=YELLOW, fill_opacity=0.25, stroke_width=3,
        )
        # Hypotenuse square (rotated)
        hyp_vec = tri.get_vertices()[2] - tri.get_vertices()[0]
        hyp_len = float(np.linalg.norm(hyp_vec))
        normal = np.array([-hyp_vec[1], hyp_vec[0], 0]) / hyp_len
        sq_c = Polygon(
            tri.get_vertices()[0],
            tri.get_vertices()[2],
            tri.get_vertices()[2] + normal * hyp_len,
            tri.get_vertices()[0] + normal * hyp_len,
            color=GREEN, fill_opacity=0.25, stroke_width=3,
        )
        formula = Text("a² + b² = c²", color=WHITE).scale(0.7).to_edge(UP, buff=0.4)

        self.play(Create(tri), run_time=0.5)
        self.play(GrowFromEdge(sq_a, UP), run_time=0.5)
        self.play(GrowFromEdge(sq_b, LEFT), run_time=0.5)
        self.play(FadeIn(sq_c, shift=normal * 0.2), run_time=0.6)
        self.play(Write(formula), run_time=0.7)
        self.wait(0.4)


# ─────────────────────────────────────────────────────────────
# 3. Sine wave
# ─────────────────────────────────────────────────────────────
class SinePreview(Scene):
    def construct(self):
        axes = Axes(
            x_range=[-PI, PI, PI / 2],
            y_range=[-1.4, 1.4, 0.5],
            x_length=6.5, y_length=3.2,
            tips=False,
            axis_config={"color": WHITE, "stroke_width": 2},
        )
        curve = axes.plot(lambda x: np.sin(x), color=YELLOW, stroke_width=4)
        label = Text("y = sin(x)", color=WHITE).scale(0.6).next_to(axes, UP, buff=0.2)
        self.play(Create(axes), run_time=0.4)
        self.play(Write(label), run_time=0.4)
        self.play(Create(curve), run_time=1.6)
        self.wait(0.4)


# ─────────────────────────────────────────────────────────────
# 4. Fourier square wave — partial sums
# ─────────────────────────────────────────────────────────────
class FourierPreview(Scene):
    def construct(self):
        axes = Axes(
            x_range=[-PI, PI, PI / 2],
            y_range=[-1.4, 1.4, 0.5],
            x_length=6.5, y_length=3.2,
            tips=False,
            axis_config={"color": WHITE, "stroke_width": 2},
        )
        self.play(Create(axes), run_time=0.4)
        partial = None
        for N in (1, 3, 5, 7, 11):
            def f(x, N=N):
                return sum((4 / (PI * k)) * np.sin(k * x) for k in range(1, N + 1, 2))
            new_curve = axes.plot(f, color=BLUE, stroke_width=4)
            if partial is None:
                self.play(Create(new_curve), run_time=0.5)
            else:
                self.play(Transform(partial, new_curve), run_time=0.4)
            partial = new_curve
        self.wait(0.4)


# ─────────────────────────────────────────────────────────────
# 5. Circle ↔ Square morph
# ─────────────────────────────────────────────────────────────
class MorphPreview(Scene):
    def construct(self):
        c = Circle(radius=1.2, color=BLUE, fill_opacity=0.4)
        s = Square(side_length=2.4, color=YELLOW, fill_opacity=0.4)
        self.play(Create(c), run_time=0.6)
        self.play(Transform(c, s), run_time=0.9)
        self.play(Transform(c, Circle(radius=1.2, color=PINK, fill_opacity=0.4)),
                  run_time=0.9)
        self.wait(0.3)


# ─────────────────────────────────────────────────────────────
# 6. Graph traversal — DFS walk
# ─────────────────────────────────────────────────────────────
class GraphPreview(Scene):
    def construct(self):
        vertices = [1, 2, 3, 4, 5, 6]
        edges = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 1), (2, 5), (3, 6)]
        g = Graph(vertices, edges, layout="circular",
                  vertex_config={"radius": 0.22, "color": WHITE, "fill_color": BLACK,
                                  "stroke_width": 2.5},
                  edge_config={"stroke_color": GREY_B, "stroke_width": 2})
        self.play(Create(g), run_time=0.6)
        path_seq = [1, 2, 3, 4, 5, 6]
        token = Dot(color=YELLOW, radius=0.16).move_to(g.vertices[path_seq[0]])
        self.play(FadeIn(token, scale=0.5), run_time=0.3)
        for v in path_seq[1:]:
            self.play(token.animate.move_to(g.vertices[v].get_center()),
                      run_time=0.32)
        self.wait(0.3)
