---
name: orchestrator-workflow
description: Coordination discipline for ConceptFlow - the fixed script-writer then manim-coder pipeline, todo tracking, and fail-fast error surfacing. Read when orchestrating a video generation run.
---

# Orchestrator Workflow

## Pipeline (strict order)

1. Call:
     write_todos(["research the topic",
                  "plan narration script",
                  "write and render Manim scene",
                  "review rendered scenes",
                  "deliver MP4 path to user"])
2. Call:
     task(subagent="research-agent",
          description="Research this topic and write /research.md: <user topic verbatim>")
   Wait for it to return. If research-agent reports it could not gather
   research, continue anyway — research is best-effort and the script-writer
   works without it.
3. Call:
     task(subagent="script-writer",
          description="Create an explainer script for: <user topic verbatim>")
   Wait for it to return.
4. Call:
     task(subagent="manim-coder",
          description="Read /script.md and produce a rendered MP4.")
   Wait for it to return.
5. QA loop (bounded by the QA budget — see below):
   a. Call ONE QA pass for the whole video:
        task(subagent="qa-agent",
             description="Review every rendered video_<Scene>.mp4 and write
                          /qa.json.")
      Wait for it to return. (One delegation = one round. Never delegate the
      qa-agent once per scene.)
   b. If the qa-agent reports NO blocking issues, exit the loop.
   c. If the qa-agent reports blocking issues, call:
        task(subagent="manim-coder",
             description="Read /qa.json, fix the blocking issues in the
                          named scenes, re-render those scenes, and re-stitch.")
      Wait for it to return, then go back to step 5a.
   d. If a QA delegation comes back saying the QA budget is
      exhausted, STOP the loop and accept the current /video.mp4.
6. Deliver the MP4 path to the user using the Final Message Format below.

## QA Budget

The number of QA rounds is capped in code (the system rejects further
`qa-agent` delegations once the cap is reached and tells you so). Do not try
to work around it: when the budget is exhausted, finalize the current
`/video.mp4` even if minor issues remain.

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
