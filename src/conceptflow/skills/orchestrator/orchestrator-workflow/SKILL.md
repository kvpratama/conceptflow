---
name: orchestrator-workflow
description: Coordination discipline for ConceptFlow - the fixed script-writer then manim-coder pipeline, todo tracking, and fail-fast error surfacing. Read when orchestrating a video generation run.
---

# Orchestrator Workflow

## Overview
You turn one user topic into one short 3Blue1Brown-style explainer video by
delegating to two subagents in a fixed order. You never write scripts or Manim
code yourself.

## The Pipeline (Strict Order)
1. `write_todos` with exactly:
   `["plan narration script", "write and render Manim scene", "report result"]`.
2. `task(subagent="script-writer", description=<the user's topic>)`. Wait.
3. `task(subagent="manim-coder", description="read /script.md and produce a rendered MP4")`. Wait.
4. Final message: include the MP4 path returned by `manim-coder`, formatted so
   the user can open it.

## Rules
- Do the steps in order; do not skip or reorder.
- If a subagent reports failure, surface its error text verbatim and STOP.
  Do NOT retry the whole pipeline.
- Keep your own messages short; the subagents do the substantive work.
