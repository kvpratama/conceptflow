---
name: manim-ce-coding
description: Manim Community Edition coding rules, LaTeX-avoidance, multi-scene layout, and a render-error to fix playbook for writing /scene.py and rendering it via render_manim. Read before writing or fixing a scene.
---

# Manim CE Coding

## Hard Rules For /scene.py
- First line MUST be: `from manim import *`
- Manim Community Edition syntax, NOT ManimGL.
- One Scene subclass per planned scene; class names MUST match the
  `## Scene N: <ClassName>` headers in `/script.md`, in the same order.
- Every Scene MUST contain at least one `self.play(...)` and one
  `self.wait(...)` so something renders.
- Target 10–20 seconds of animation per scene.
- Do NOT add an `if __name__ == "__main__"` block.

## Multi-Scene Layout
- All Scene subclasses live in one `/scene.py` file.
- Each class is self-contained: never reference objects defined in another class.
- `render_manim` is called once per class, in plan order.
- Each call overwrites `/video.mp4` — rendering all scenes confirms they
  are error-free, but only the last one survives on disk.

## Avoid LaTeX Unless The Plan Demands Math
- Prefer `Text("...")` over `Tex` / `MathTex`.
- LaTeX requires a TeX install that may be absent and is the most common
  render failure.
- If math is required, keep `MathTex` expressions minimal and valid.

## API Gotchas (CE)
- Construct then animate: `c = Circle(); self.play(Create(c))`.
- Use `Create`, `Write`, `FadeIn`, `FadeOut`, `Transform`, `.animate` —
  not ManimGL's `ShowCreation`.
- Position with `.shift()`, `.next_to()`, `.to_edge()`; avoid overlaps.
- Colors are constants: `BLUE`, `RED`, `YELLOW`, etc.

## Render-Error Playbook

The retry budget is global — it depletes across every render_manim call
in this run, not per scene. For a 3-scene script, each scene's first
render is already attempt 1, 2, 3 globally.

For each `render_manim(scene_class="<ClassName>")` call:

  ok=True
  → move to the next scene (or finish if last).

  ok=False, kind="render"
  → read stderr and hold onto it — you will need it if the budget runs out.
    Common causes:
      - missing `from manim import *`
      - LaTeX / MathTex error → replace with Text
      - class name mismatch with /script.md header
      - typo'd mobject or animation name (NameError)
    Fix via `edit_file("/scene.py", ...)` scoped to that scene's class only,
    then retry. Do not touch classes that have already rendered successfully.

  ok=False, kind="exhausted"
  → budget gone. The exhausted response has no stderr field — surface the
    stderr from your most recent kind="render" failure instead. STOP.
    Do NOT call render_manim again.

  ok=False, kind="infra" or kind="logic"
  → return message verbatim and STOP. Do NOT retry.
