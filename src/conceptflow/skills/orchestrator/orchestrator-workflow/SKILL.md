---
name: orchestrator-workflow
description: Coordination discipline for ConceptFlow - the fixed script-writer then manim-coder pipeline, todo tracking, and fail-fast error surfacing. Read when orchestrating a video generation run.
---

# Orchestrator Workflow

## Input Validation

Check the topic before starting the pipeline:

  Too vague (e.g. "math", "science")
  → Ask the user to name a specific concept.

  Too broad (e.g. "all of physics")
  → Ask the user to pick one concept that fits a short video.

  Off-limits (harmful, not a real concept, etc.)
  → Decline and briefly explain why.

If the topic passes, start the pipeline immediately — do not ask
clarifying questions for acceptable topics.
## Error Surfacing

"Surface verbatim" means: paste the subagent's exact output into your
reply, unedited. No summarising, no suggestions, no added context.

  Format:

    <subagent-name> reported a failure:

        <exact error output>

Then stop. Do not continue the pipeline.

## Final Message Format

Deliver the MP4 path exactly as returned by `manim-coder`:

    Your explainer video is ready:

        /path/to/output.mp4

No extra commentary unless the path itself is ambiguous.

## File Path Note

`/script.md` is a fixed, shared path. Concurrent runs will overwrite it.
This is a known limitation — do not attempt to work around it.
