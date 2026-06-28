---
name: research-method
description: How the research-agent gathers grounded facts, examples, and analogies for a topic via tavily_search and wikipedia within a capped search budget, and writes them to /research.md. Read before researching a topic.
---

# Research Method

## What You Do

Gather accurate, useful background for the topic so the script-writer can
ground its narration in real facts, vivid examples, and good analogies.

## Tools

- `tavily_search` — live web search. May be unavailable when no Tavily key is
  configured; if you do not have it, rely on `wikipedia` alone.
- `wikipedia` — reliable structured background. Always available.

## Workflow

1. Start with ONE `wikipedia` lookup for the core concept to anchor the
   definition and the standard framing.
2. Use `tavily_search` (when available) to fill gaps: current facts, concrete
   numbers, real-world examples, history, common misconceptions.
3. Your search budget is capped in code. Spend it frugally — prefer a few
   high-signal queries over many narrow ones. When the budget is exhausted the
   tool returns a "budget exhausted" message; stop searching immediately and
   write `/research.md` with what you have.
4. Deduplicate sources and keep only facts you can attribute to a source.

## Required Output: Write /research.md With EXACTLY This Structure

```markdown
# Topic

<topic verbatim>

# Key Facts

- <concise, verifiable fact> [n]

# Examples & Analogies

- <example or analogy useful for explaining visually>

# Common Misconceptions   ← optional; omit the section if you found none

- <misconception → correction>

# Sources

[1] <title> — <url>
[2] <Wikipedia article title> — <url>
```

Rules:
- Every fact in `# Key Facts` carries a `[n]` marker pointing at `# Sources`.
- Keep facts concise and verifiable; do not invent sources or URLs.
- Examples should be concrete and visual — things that can become Manim
  animations (motion, shapes, transformations).

## Final Reply

One sentence confirming `/research.md` was written. Do not paste the research
content into your reply — it lives in `/research.md`.
