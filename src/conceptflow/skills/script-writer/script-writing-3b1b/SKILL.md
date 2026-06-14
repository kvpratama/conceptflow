---
name: script-writing-3b1b
description: How to write a short 3Blue1Brown-style narration plus a single animatable scene plan, and persist it to /script.md. Read before writing a script.
---

# Script Writing (3Blue1Brown Style)

## Overview
Produce a SHORT narration (~80-150 words) and a ONE-scene visual plan that a
Manim CE coder can animate, then save it to `/script.md`.

## Style
- Build one idea from intuition first, formalism second. Conversational, warm.
- Drive every sentence toward something visual: motion, transformation, color.
- One scene, 10-20 seconds. Name concrete mobjects and animations per beat.

## Visuals To Prefer (Avoid LaTeX Where Possible)
- Use `Text`, `Square`, `Circle`, `Arrow`, `Line`, `Dot`, `NumberPlane`, `Axes`.
- Use `MathTex`/`Tex` ONLY when a formula is essential to the idea.

## Required Output: Write /script.md With EXACTLY This Structure
```
# Topic

<topic verbatim>

# Narration

<narration paragraphs>

# Scene Plan

- Scene class name: <PascalCase, no spaces - e.g. PythagoreanIntro>
- Duration: ~10-20 seconds
- Visual beats:
  1. <beat>
  2. <beat>
  3. <beat>
```

## Finish
Reply with a one-sentence confirmation that `/script.md` was written. Do NOT
paste the script content into your reply.
