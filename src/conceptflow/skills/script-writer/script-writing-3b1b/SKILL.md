---
name: script-writing-3b1b
description: How to write a short 3Blue1Brown-style narration plus a single animatable scene plan, and persist it to /script.md. Read before writing a script.
---

# Script Writing (3Blue1Brown Style)

## Scene Count Calibration

Scale scenes to the topic's complexity:

  Narrow concept  (e.g. "what is a derivative")          → 1–2 scenes
  Moderate concept (e.g. "how gradient descent works")   → 3–4 scenes
  Broad concept   (e.g. "how neural networks learn")     → 5–6 scenes

Never exceed 6 scenes. If the topic requires more, reduce its scope and
note the tradeoff in the optional `# Notes` section of /script.md.

## Narration Length

Target ~60–80 words per scene:

  1–2 scenes  →  ~80–150 words
  3–4 scenes  →  ~200–300 words
  5–6 scenes  →  ~350–500 words

## Style
- Build each idea intuition-first, formalism second. Conversational, warm.
- Drive every sentence toward something visual: motion, transformation, color.
- Per scene: name concrete Manim mobjects and animations at each beat.

## Visuals To Prefer (Avoid LaTeX Where Possible)
- Use `Text`, `Square`, `Circle`, `Arrow`, `Line`, `Dot`, `NumberPlane`, `Axes`.
- Use `MathTex` / `Tex` ONLY when a formula is essential to the idea.

## Narration Must Be Split Per Scene

Each scene is rendered independently and gets its own spoken voiceover, so
every scene MUST carry its own narration line. The full `# Narration` block
is the verbatim concatenation, in order, of every scene's `- Narration:`
line. Keep each scene's narration to 1–3 sentences that can be comfortably
spoken within that scene's ~10–20 second duration.

## Required Output: Write /script.md With EXACTLY This Structure

```markdown
# Topic

<topic verbatim>

# Narration

<one continuous narration block, length scaled to scene count>

# Scene Plan

## Scene 1: <PascalCase class name>
- Duration: ~10–20 seconds
- Narration: <1–3 sentences spoken during this scene>
- Visual beats:
  1. <beat>
  2. <beat>
  3. <beat>

## Scene 2: <PascalCase class name>   ← repeat block for each scene
- Duration: ~10–20 seconds
- Narration: <1–3 sentences spoken during this scene>
- Visual beats:
  1. <beat>
  2. <beat>
  3. <beat>

# Notes   ← optional; omit entirely if scope was not reduced

<explain any narrowing here>
