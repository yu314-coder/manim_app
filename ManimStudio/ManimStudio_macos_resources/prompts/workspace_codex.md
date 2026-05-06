# Workspace Rules

Edit `scene.py` only. No explanations.
Do NOT use plan mode. Just read, think, then edit directly.

## CRITICAL: Follow this exact order

1. **Read `scene.py` FIRST** — use cat. Never guess contents.
2. **Summarize** what the current code does (animations, objects, flow).
3. **Read the user instruction** and understand what needs to change.
4. **Check for asset references** — if `scene.py` uses any files from `./assets/`
   (e.g. ImageMobject, SVGMobject, or any file path), read those asset files
   too so you understand what they contain.
5. **Then edit** `scene.py` with the changes.

## NOT Allowed
- Do NOT run pip, python, manim, or any execution commands
- Do NOT create files other than `scene.py`
- Do NOT use plan mode
- Do NOT read assets that are NOT referenced in `scene.py`

## Manim Context
- Always include `from manim import *`
- Must have a Scene class with `construct(self)` method
- Common: Text, MathTex, Circle, Square, Arrow, VGroup, NumberPlane, SVGMobject, ImageMobject
- Animations: Write, FadeIn, FadeOut, Transform, ReplacementTransform, Create, GrowFromCenter, MoveToTarget
- Use `self.play(...)` to animate, `self.wait()` to pause
- Position: `.to_edge()`, `.to_corner()`, `.next_to()`, `.shift()`, `.move_to()`
- Colors: WHITE, YELLOW, BLUE, RED, GREEN, PURPLE, ORANGE
- Keep text readable (font_size=36+), don't overlap objects
