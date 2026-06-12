# ConceptFlow

ConceptFlow is an open-source, self-hostable educational video generation
system. A user provides a topic or question in plain language; ConceptFlow
orchestrates specialized agents to produce a short animated explanatory video
in the style of 3Blue1Brown.

The current implementation is a proof of concept built with LangGraph and
Deep Agents. The root agent delegates to:

- `script-writer`, which creates a short narration and one-scene visual plan.
- `manim-coder`, which writes a Manim CE scene, renders it in a Modal sandbox,
  and saves the MP4 locally.

Rendered videos are written to:

```text
./outputs/<thread_id>/video.mp4
```

## Requirements

- Python 3.14+
- `uv`
- Modal credentials for rendering
- At least one supported model provider API key: Anthropic, OpenAI, or Google

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
|-- agent.py          # Root Deep Agents graph
|-- config.py         # Settings and model factories
|-- prompts.py        # Orchestrator and subagent prompts
|-- render.py         # Modal-backed Manim render tool
`-- subagents.py      # Subagent definitions
```
