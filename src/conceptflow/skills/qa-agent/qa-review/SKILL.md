---
name: qa-review
description: How the qa-agent reviews each rendered scene for off-screen mobjects, caption overflow/overlap, and blank frames via qa_scene, and records structured findings to /qa.json. Read before reviewing rendered scenes.
---

# Video QA Review

## What You Do

Review every rendered scene for visual defects and record the results so the
manim-coder can fix them.

## Workflow

1. List the rendered scene videos in the shared workspace. They are named
   `video_<SceneClass>.mp4` (one per scene). Use `ls` / `glob`.
2. For EACH `video_<SceneClass>.mp4`, call:
     `qa_scene(scene_class="<SceneClass>")`
   `<SceneClass>` is the file name without the `video_` prefix and `.mp4`
   suffix (e.g. `video_Intro.mp4` -> `Intro`).
3. Each call returns `{"ok": True, "qa": {...}}` on success. Collect every
   returned `qa` object into one JSON array, in scene order.
4. Write that array to `/qa.json` with `write_file`. Write it verbatim —
   do not paraphrase, drop, or invent fields.

## qa_scene Result Handling

  ok=True
  -> append result["qa"] to your array.

  ok=False, kind="logic"
  -> the scene was not rendered or the name is wrong. Skip it and note it in
     your summary. Do NOT retry.

  ok=False, kind="infra"
  -> sandbox/ffmpeg problem. Record nothing for that scene and note the failure
     in your summary. Do NOT retry.

## /qa.json Shape

A JSON array of per-scene objects:

```json
[
  {
    "scene_class": "Intro",
    "passed": false,
    "issues": [
      {
        "category": "caption_overflow",
        "severity": "blocking",
        "frames": [1, 2],
        "description": "The caption runs past the right edge.",
        "suggestion": "Build the caption with make_caption so it is width-fitted."
      }
    ]
  }
]
```

Categories: `offscreen_mobject`, `caption_overflow`, `caption_overlap`,
`blank_frame`, `other`. Severity is `blocking` or `warning`. A scene `passed`
when it has no `blocking` issues.

## Final Reply

One line: which scenes passed and which have blocking issues. Do not paste the
full QA report into your reply — it lives in `/qa.json`.
