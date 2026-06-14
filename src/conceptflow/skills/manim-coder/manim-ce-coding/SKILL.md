---
name: manim-ce-coding
description: Manim Community Edition coding rules, LaTeX-avoidance, and a render-error to fix playbook for writing /scene.py and rendering it via render_manim. Read before writing or fixing a scene.
---

# Manim CE Coding

## Overview
Read `/script.md`, write a single-Scene `/scene.py`, render it with
`render_manim`, and self-correct render failures within the budget.

## Hard Rules For /scene.py
- First line MUST be: `from manim import *`
- Manim **Community Edition** syntax, NOT ManimGL.
- Exactly one `Scene` subclass; its name MUST match the script's
  "Scene class name:" line.
- Always include `self.play(...)` and `self.wait(...)` so something renders.
- Keep it to 10-20 seconds of animation.
- Do NOT add an `if __name__ == "__main__"` block; the renderer calls `manim`.

## Avoid LaTeX Unless The Plan Demands Math
- Prefer `Text("...")` over `Tex`/`MathTex`. LaTeX needs a TeX install that may
  be absent in the sandbox and is the most common render failure.
- If math is required, keep `MathTex` expressions minimal and valid.

## API Gotchas (CE)
- Construct then animate: `c = Circle(); self.play(Create(c))`.
- Use `Create`, `Write`, `FadeIn/FadeOut`, `Transform`, `.animate` - not
  ManimGL `ShowCreation`.
- Position with `.shift()`, `.next_to()`, `.to_edge()`; avoid overlaps.
- Colors are constants like `BLUE`, `RED`, `YELLOW`.

## Render-Error To Fix Playbook
Call `render_manim(scene_class="<ClassName>")`, then act on the result:
- `ok=True` -> final reply is `mp4_path` and NOTHING else.
- `ok=False, kind="render"` -> read `stderr`, `edit_file("/scene.py", ...)` to fix,
  retry. Common causes: missing `from manim import *`, LaTeX/`MathTex` errors
  (replace with `Text`), wrong class name, typo'd mobject/animation, NameError.
- `ok=False, kind="exhausted"` -> budget gone; return the last `stderr` and STOP.
  Do NOT call `render_manim` again.
- `ok=False, kind="infra"` -> return `message` verbatim and STOP. Do NOT retry.
- `ok=False, kind="logic"` -> report `message` and STOP. Do NOT retry.
