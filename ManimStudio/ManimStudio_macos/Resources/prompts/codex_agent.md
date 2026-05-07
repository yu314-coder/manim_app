# Agent Mode Prompts

## Generate
Create a Manim animation for:

{{DESCRIPTION}}

Write the complete animation code to scene.py.
Use smooth animations (Write, FadeIn, Transform, etc.) and add self.wait() between animations.
Make sure text is readable, objects don't overlap, and colors have good contrast against a black background.

## Fix
Read `scene.py` first. It has a render error:

{{ERROR}}

Fix the bug and write the corrected code back to scene.py.

## Review
You are a visual QA reviewer for Manim animations.

GOAL: "{{DESCRIPTION}}"

STEP 1: Examine EVERY screenshot frame image attached.
There are {{NUM_FRAMES}} frames captured at 1 frame per second from the rendered animation.

STEP 2: For each frame, describe what you see.

STEP 3: Check for these problems:
1. DOESN'T MATCH GOAL -- missing key elements that were requested
2. UNNATURAL/STRANGE -- things that look weird or wrong
3. OVERLAPPING -- objects or text piled on each other, unreadable
4. OFF SCREEN -- objects cut off at edges
5. WRONG TEXT -- typos, wrong words, wrong math, garbled text
6. DISCONNECTED -- elements that should be connected look broken

IGNORE: colors, fonts, spacing, timing, speed, style.

STEP 4: Give your verdict:
SATISFIED -- if animation looks correct and matches the goal
IMPROVE: <specific description of what is wrong and needs fixing>

## Improve
Read `scene.py` first, then fix these visual problems found by reviewing the rendered animation frame by frame:

{{REVIEW_FEEDBACK}}

Fix the code and write the result back to scene.py.