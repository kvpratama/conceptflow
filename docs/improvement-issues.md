# ConceptFlow Improvement Issues

Draft GitHub issues for proposed improvements. Each section below is ready to
paste into a new GitHub issue (title = heading, body = content).

---

## Issue 1: Close the quality loop — verify rendered video with a vision review step

**Labels:** `enhancement`, `quality`, `manim-coder`

### Problem

Rendering is currently blind. A render is considered successful when the Manim
subprocess exits `0` and an MP4 exists (see
`_run_render_blocking` in `src/conceptflow/render.py`). Nothing inspects the
*visual* result, so the most common 3Blue1Brown-style quality failures slip
through:

- captions overflowing or overlapping other mobjects
- elements drawn off-screen
- blank / empty frames
- audio narration desynced from on-screen animation

The `manim-coder` retry budget only protects against hard render errors, not
against videos that render fine but look wrong.

### Proposal

Add a verification step that lets the agent *see* its output:

1. After a successful render, extract a handful of keyframes with `ffmpeg`
   (already installed in `MANIM_IMAGE`) inside the same sandbox.
2. Feed the keyframes to a multimodal model with a rubric (off-screen content,
   overlapping text, blank frames, caption legibility).
3. Return a structured critique that `manim-coder` can act on within its
   existing per-scene retry budget.

This reuses existing infra (ffmpeg, the Modal sandbox, the model layer) and is
the single biggest lever on output quality.

### Affected code

- `src/conceptflow/render.py` (`render_manim`, `_run_render_blocking`)
- `src/conceptflow/skills/manim-coder/manim-ce-coding/SKILL.md` (render playbook)
- possibly a new reviewer tool/subagent

### Acceptance criteria

- A rendered scene is automatically checked for at least: off-screen mobjects,
  caption overflow/overlap, and blank frames.
- The critique is surfaced to `manim-coder` in a structured form it can act on.
- Retry budget semantics are preserved (no infinite review loops).

---

## Issue 2: Stop paying for a cold Modal sandbox per scene render

**Labels:** `enhancement`, `performance`, `cost`, `render`

### Problem

Both `_run_render_blocking` and `_stitch_blocking` in
`src/conceptflow/render.py` follow a `Sandbox.create … terminate` lifecycle on
**every** call. For a run with N scenes plus retries plus a final stitch, that
is N+ cold starts (image pull/boot) per video. This dominates latency and cost,
and gets worse as scene counts approach the 6-scene cap allowed by the
script-writer skill.

### Proposal

Reduce sandbox cold starts. Options, roughly in order of impact:

- **Reuse one warm sandbox across a run** — create the sandbox once, thread a
  handle through agent state, and reuse it for all scene renders + the stitch,
  terminating once at the end.
- **Batch render** all scene classes in a single sandbox invocation.
- At minimum, share a sandbox between the final render and the stitch step.

### Affected code

- `src/conceptflow/render.py` (`render_manim`, `stitch_videos`,
  `_run_render_blocking`, `_stitch_blocking`)
- sandbox lifecycle / state handling

### Acceptance criteria

- A multi-scene run no longer creates a fresh sandbox per `render_manim` call.
- Sandboxes are still reliably terminated (no leaks) on success and failure.
- Existing render/stitch tests still pass (and are updated for the new
  lifecycle).

### Notes / risks

- Must preserve the `modal_sandbox_timeout` wall-clock cap and clean teardown
  on errors.
- Reusing a sandbox across retries means scene state/artifacts must be reset
  between attempts to avoid stale-file pickup.

---

## Issue 3: Pipeline is one-shot and unidirectional — add a feedback/review path

**Labels:** `enhancement`, `architecture`, `orchestrator`

### Problem

The orchestrator runs a strict linear pipeline (see
`src/conceptflow/skills/orchestrator/orchestrator-workflow/SKILL.md`):
`script-writer` → `manim-coder` → deliver. There is:

- no review of `/script.md` before `manim-coder` starts coding, and
- no path for `manim-coder` to report back "scene 3 is unanimatable, revise the
  script" and trigger a script revision.

When the script is the root cause of a failure, the system burns render
attempts instead of fixing the script.

### Proposal

Introduce a lightweight feedback loop, e.g.:

- a feedback edge allowing `manim-coder` to request a script revision from the
  orchestrator, and/or
- a small reviewer step/subagent that sanity-checks `/script.md` for
  animatability before coding begins.

Keep it bounded (cap revision rounds) to avoid loops.

### Affected code

- `src/conceptflow/agent.py` (graph/subagent wiring)
- `src/conceptflow/subagents.py`
- `src/conceptflow/skills/orchestrator/orchestrator-workflow/SKILL.md`
- `src/conceptflow/prompts.py`

### Acceptance criteria

- `manim-coder` can signal a script-level problem back to the orchestrator.
- Script revision rounds are bounded by a configurable cap.
- Failures caused by a bad script are resolved by revising the script rather
  than exhausting render retries.

---

## Issue 4: Make render attempt-counting robust (don't reconstruct from message history)

**Labels:** `enhancement`, `reliability`, `render`

### Problem

`_count_prior_render_calls` in `src/conceptflow/render.py` derives the per-scene
retry budget by scanning the message history and correlating `AIMessage`
tool_calls with their `ToolMessage` responses on every render call. This is
fragile: history compaction/summarization or any reshaping of `state["messages"]`
can drop the prior tool-call records and silently reset or miscount the budget.

### Proposal

Track render attempts in durable agent state (a per-scene counter) rather than
recomputing them from raw message history each call. Update the budget check in
`render_manim` to read/write that counter.

### Affected code

- `src/conceptflow/render.py` (`render_manim`, `_count_prior_render_calls`)
- `src/conceptflow/render_test.py` (update/extend coverage)

### Acceptance criteria

- The per-scene retry budget is enforced from explicit state, not by scanning
  message history.
- Budget counting is unaffected by message-history compaction/summarization.
- Existing per-scene budget behavior (retries for Scene1 don't consume Scene2's
  budget) is preserved and covered by tests.
