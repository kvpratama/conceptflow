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
        caption = Text(narration, font_size=24).to_edge(DOWN)
        with self.voiceover(text=narration) as tracker:
            self.add(caption)
            circle = Circle()
            self.play(Create(circle), run_time=tracker.duration)
        self.remove(caption)
```

Rules:
- Pass the scene's narration to BOTH `self.voiceover(text=...)` and the
  caption `Text(...)`, so audio and on-screen text always match.
- Use `run_time=tracker.duration` (or split the duration across several
  `self.play` calls) so visuals fill the spoken line.
- Keep captions readable: `font_size=24`, `.to_edge(DOWN)`, and `self.remove`
  the caption after each block so they do not stack.
- A scene may contain multiple `self.voiceover` blocks if its narration has
  multiple sentences; show one caption per block.

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
