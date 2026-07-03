# ConceptFlow

ConceptFlow is an open-source, self-hostable educational video generation
system. A user provides a topic or question in plain language; ConceptFlow
orchestrates specialized agents to produce a short animated explanatory video
in the style of 3Blue1Brown.

The implementation is built with LangGraph and Deep Agents. The root
orchestrator delegates to four subagents in sequence, each persisting its
output to a shared per-thread workspace:

- `research-agent`, which gathers grounded facts, examples, and sources via web
  search (Tavily) and Wikipedia, writing `/research.md`. Without a Tavily key it
  falls back to Wikipedia-only research.
- `script-writer`, which turns the topic into a short narration and visual plan,
  writing `/script.md`.
- `manim-coder`, which writes `/scene.py` as a Manim CE module, renders it in a
  Modal sandbox (with gTTS/pyttsx3 voiceover), and stitches per-scene clips into
  the final video. It self-corrects on render errors.
- `qa-agent`, which reviews each rendered scene with a vision model for visual
  defects (off-screen mobjects, caption overflow/overlap, blank frames) and
  writes structured findings to `/qa.json`.

The pipeline is wrapped with LLM-as-judge content moderation of the input topic
and generated script (enabled by default), a QA-round budget, model retry and
fallback middleware, and per-subagent Modal sandbox lifecycle management. Each
subagent is guided by a bundled agent skill (`SKILL.md`).

Rendered videos and intermediate artifacts are written under:

```text
./outputs/<thread_id>/
```

## Showcase

Two example videos from the current pipeline (research-grounded, voiced, and
QA-reviewed):

**What is a neural network?**

https://github.com/user-attachments/assets/26a368dc-5699-4272-89fd-0ae04a076331

**What is a Fourier series?**

https://github.com/user-attachments/assets/032ec67c-8cee-4502-b69a-9e822889ce2b

See [SHOWCASE.md](./SHOWCASE.md) for how output quality evolved across
milestones.

## Requirements

- Python 3.14+
- `uv`
- Modal credentials for rendering
- At least one supported model provider API key: Anthropic, OpenAI, or Google
- Optional: a Tavily API key for web-search research (falls back to
  Wikipedia-only when absent)

## Setup

Install dependencies:

```bash
uv sync
```

Create local configuration:

```bash
cp .env.example .env
```

Then fill in `.env` with the model and credentials you want to use. Runtime
configuration is loaded from OS environment variables first, then `./.env`,
then `~/.config/conceptflow/config.env`.

## Run

Start the LangGraph development server:

```bash
uv run langgraph dev
```

The graph is exposed as `conceptflow` from `./src/conceptflow/agent.py:make_graph`
via `langgraph.json`.

## Development

Run tests:

```bash
uv run pytest
```

Run linting, formatting, and type checking:

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
```

## Project Layout

```text
src/conceptflow/
|-- agent.py                          # Root Deep Agents graph (make_graph)
|-- config.py                         # Settings and model factories
|-- paths.py                          # Per-thread workspace/skills path helpers
|-- prompts.py                        # Orchestrator and subagent prompts
|-- subagents.py                      # Subagent definitions
|-- render.py                         # Modal-backed Manim render + stitch tools
|-- sandbox_middleware.py             # Per-subagent Modal sandbox lifecycle
|-- sandbox_tts.py                    # In-sandbox gTTS/pyttsx3 voiceover helper
|-- research.py                       # Tavily + Wikipedia research tools
|-- research_middleware.py            # Research search-budget enforcement
|-- qa.py                             # Vision-LLM scene QA tool
|-- qa_middleware.py                  # QA-round budget enforcement
|-- moderation.py                     # LLM-as-judge content moderation
|-- input_moderation_middleware.py    # Moderates the input topic
|-- output_moderation_middleware.py   # Moderates the generated script
`-- skills/                           # Per-agent skill packages (SKILL.md)
```
