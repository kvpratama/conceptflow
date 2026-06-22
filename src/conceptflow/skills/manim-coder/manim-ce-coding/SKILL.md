---
name: manim-ce-coding
description: Manim Community Edition coding rules, LaTeX-avoidance, multi-scene layout, and a render-error to fix playbook for writing /scene.py and rendering it via render_manim. Read before writing or fixing a scene.
---

# Manim CE Coding

## Hard Rules For /scene.py
- The first three lines MUST be, in this order:
  - `from manim import *`
  - `from manim_voiceover import VoiceoverScene`
  - `from sandbox_tts import build_speech_service`
- Manim Community Edition syntax, NOT ManimGL.
- One scene class per planned scene; each subclasses `VoiceoverScene` (NOT
  `Scene`). Class names MUST match the `## Scene N: <ClassName>` headers in
  `/script.md`, in the same order.
- The FIRST statement in every `construct` MUST be:
  `self.set_speech_service(build_speech_service())`
- Every narration beat MUST be spoken inside a `self.voiceover(...)` block,
  with animations timed to the narration (see "Voiceover + Captions").
- Target 10–20 seconds of animation per scene.
- Do NOT add an `if __name__ == "__main__"` block.
- Do NOT define `build_speech_service` yourself; it is provided by the
  uploaded `sandbox_tts` module. Do NOT import or configure any TTS service
  class directly.

## Multi-Scene Layout
- All Scene subclasses live in one `/scene.py` file.
- Each class is self-contained: never reference objects defined in another class.
- `render_manim` is called once per class, in plan order.
- Each successful render saves to a separate `/video_<SceneClass>.mp4`.
- When fixing a failed scene, limit edits to that scene's class only —
  do not touch classes that have already rendered successfully.
- After all scenes render, call `stitch_videos` with the ordered list of
  paths to produce the final `/video.mp4`.

## Voiceover + Captions

Each scene speaks its `- Narration:` line from `/script.md` and shows it as a
burned-in caption. Wrap every beat like this so the animation runs for as
long as the narration takes:

```python
from manim import *
from manim_voiceover import VoiceoverScene
from sandbox_tts import build_speech_service


class Scene1(VoiceoverScene):
    def construct(self):
        self.set_speech_service(build_speech_service())

        narration = "Here is the idea, one sentence at a time."
        caption = make_caption(narration)
        with self.voiceover(text=narration) as tracker:
            self.add(caption)
            circle = Circle()
            self.play(Create(circle), run_time=tracker.duration)
        self.remove(caption)
```

Captions MUST fit on screen. Manim's `Text` does NOT wrap, so a 1–3 sentence
narration rendered as a single `Text` will run off both edges. Define this
helper at module level (after the imports) and use it for every caption:

```python
def make_caption(text):
    caption = Text(text, font_size=24).to_edge(DOWN)
    max_width = config.frame_width - 1
    if caption.width > max_width:
        caption.scale_to_fit_width(max_width)
    return caption
```

Rules:
- Pass the scene's narration to BOTH `self.voiceover(text=...)` and
  `make_caption(...)`, so audio and on-screen text always match.
- ALWAYS build captions via `make_caption(...)` so they are scaled to fit the
  frame width and never overflow the screen edges.
- Use `run_time=tracker.duration` (or split the duration across several
  `self.play` calls) so visuals fill the spoken line.
- Keep captions readable: `.to_edge(DOWN)` and `self.remove` the caption after
  each block so they do not stack.
- Prefer ONE caption per spoken sentence: a scene may contain multiple
  `self.voiceover` blocks, each with its own short narration and caption. This
  keeps every caption short enough to stay legible after width-fitting.

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

The retry budget is per scene_class — retries for Scene1 do not consume
budget for Scene2.

  ok=True
  -> collect mp4_path; move to the next scene (or stitch if last).

  ok=False, kind="render"
  -> read stderr and hold onto it — you will need it if budget runs out.
     Common causes:
       - missing `from manim import *`
       - LaTeX / MathTex error  ->  replace with Text
       - class name mismatch with /script.md header
       - typo'd mobject or animation name (NameError)
     Fix via `edit_file("/scene.py", ...)` scoped to that scene's class
     only, then retry.

  ok=False, kind="exhausted"
  -> budget gone for this scene. The exhausted response has no stderr
     field — surface the stderr from your most recent kind="render"
     failure for this scene instead. STOP.
     Do NOT call render_manim again.

  ok=False, kind="infra" or kind="logic"
  -> return message verbatim and STOP. Do NOT retry.

## Stitch-Error Playbook

  ok=True
  -> final reply is `/video.mp4` and NOTHING else.

  ok=False, kind="logic"
  -> a path in the list is wrong or a file is missing on disk. Verify
     that mp4_paths matches the collected render outputs exactly, then
     retry once.

  ok=False, kind="infra"
  -> return message verbatim and STOP. Do NOT retry.


## Visual-Critique Playbook

When the orchestrator asks you to act on a visual critique, read `/critique.json`
(a JSON array of per-scene critiques). For each scene with `passed: false`, fix
ONLY that scene's class, then re-render it and re-stitch.

Map each issue `category` to a fix:

  caption_overflow
  -> ensure the caption is built via `make_caption(...)` so it is width-fitted;
     split long narration into multiple shorter `self.voiceover` blocks.

  caption_overlap
  -> `self.remove(...)` the previous caption before showing the next; keep the
     caption at `.to_edge(DOWN)` and move other mobjects clear of it.

  offscreen_mobject
  -> reposition with `.move_to`, `.shift`, `.next_to`, or scale down with
     `.scale` / `.scale_to_fit_width(config.frame_width - 1)` so the element
     stays inside the frame.

  blank_frame
  -> ensure something is on screen for the whole scene; add/extend animations or
     hold a final state so no sampled frame is empty.

  other
  -> apply the issue's `suggestion`.

Only `blocking` issues require a fix; `warning`s are advisory. After fixing,
re-render each changed scene with `render_manim` and re-stitch with
`stitch_videos`. Respect the per-scene render budget exactly as in the
Render-Error Playbook.

