## Project Overview

ConceptFlow is an open-source, self-hostable educational video generation
system. A user provides a topic or question in plain language; the system
orchestrates specialized agents to produce a short animated explanatory video
in the style of 3Blue1Brown.

---

## Tech Stack

- **Runtime**: Python 3.14+
- **Orchestration**: [LangGraph](https://github.com/langchain-ai/langgraph) & [Deep Agents](https://github.com/langchain-ai/deepagents)
- **Execution**: `langchain-modal` (`ModalSandbox`) for sandboxed shell execution in ephemeral Modal microVMs
- **Models**: Anthropic (default), OpenAI, or Google GenAI via LangChain `init_chat_model`
- **Research**: `langchain-tavily` for web search plus a direct MediaWiki (Wikipedia) client over `httpx`
- **Safety**: LLM-as-judge input/output content moderation (reuses the "small" model)
- **Voiceover**: `manim-voiceover` in-sandbox with gTTS-primary, pyttsx3-fallback
- **Skills**: per-agent Deep Agents skill packages (`SKILL.md`) under `src/conceptflow/skills/`
- **Environment**: `uv` for dependency management, `pydantic-settings` for configuration

---

## Project Structure

```text
.
|-- AGENTS.md                            # Agent-facing project instructions
|-- README.md                            # Short project description
|-- langgraph.json                       # LangGraph Studio/dev entrypoint
|-- pyproject.toml                       # Project metadata, deps, tool config
|-- uv.lock                              # Locked uv dependency graph
|-- docs/superpowers/                    # Design specs and implementation plans
|-- src/conceptflow/
|   |-- agent.py                         # Root deep agent (make_graph)
|   |-- config.py                        # Settings and model factories
|   |-- paths.py                         # Per-thread workspace/skills path helpers
|   |-- prompts.py                       # Orchestrator/subagent system prompts
|   |-- subagents.py                     # Deep Agents SubAgent definitions
|   |-- render.py                        # render_manim + stitch_videos Modal tools
|   |-- sandbox_middleware.py            # Per-subagent Modal sandbox lifecycle
|   |-- sandbox_tts.py                   # In-sandbox gTTS/pyttsx3 voiceover helper
|   |-- research.py                      # Tavily + Wikipedia research tools
|   |-- research_middleware.py           # Research search-budget enforcement
|   |-- qa.py                            # Vision-LLM scene QA tool
|   |-- qa_middleware.py                 # QA-round budget enforcement
|   |-- moderation.py                    # LLM-as-judge content moderation
|   |-- input_moderation_middleware.py   # Moderates the input topic
|   |-- output_moderation_middleware.py  # Moderates the generated script
|   |-- skills/                          # Per-agent skill packages (SKILL.md)
|   `-- *_test.py                        # Co-located tests for each module
`-- outputs/                             # Generated rendered videos; not source
```

`langgraph.json` exposes the graph named `conceptflow` from
`./src/conceptflow/agent.py:make_graph`.

The orchestrator runs four subagents in sequence over a shared per-thread
workspace: `research-agent` (→ `/research.md`), `script-writer`
(→ `/script.md`), `manim-coder` (→ `/scene.py`, renders and stitches the
video), and `qa-agent` (→ `/qa.json`).

Runtime/generated directories such as `outputs/`, `.langgraph_api/`,
`.ruff_cache/`, `.pytest_cache/`, and `__pycache__/` are not source. Do not
base architectural decisions on their contents.

---

## Common Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .

# Type checking
uv run ty check

# Run LangGraph dev server / Studio backend
uv run langgraph dev

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>
```

---

## Code Conventions

### General
- Python **3.14+** minimum.
- **Async-first where applicable** — use `async def` for I/O-bound functions (Modal sandbox calls, LLM calls, file operations).
- **Strict type hints** on every function signature, including return types. No bare `Any` unless unavoidable.
- **Docstrings on every function and class** using Google-style format.

### Environment Variables
- Configuration is loaded by `load_environment()` from OS environment first,
  then project-local `./.env`, then `~/.config/conceptflow/config.env`.
- Access config only through the `Settings` object in `config.py` (Pydantic `BaseSettings`).
- Never hardcode secrets, API keys, or connection strings.
- `.env.example` documents expected local variables, including model provider
  keys, LangSmith settings, Modal credentials, the optional Tavily research key
  (`TAVILY_API_KEY`), the Wikipedia `User-Agent`, TTS backend, and QA/research
  budget and content-safety (`SAFETY_ENABLED`) toggles.

---

## Testing

- Test runner: `uv run pytest`
- Always follow Red–Green–Refactor TDD
- Use `pytest-asyncio` with `asyncio_mode = "auto"` in `pyproject.toml`.
- **Tests are co-located with their target** — a test for `config.py` lives at `config_test.py`, a test for `render.py` lives at `render_test.py`, not in a separate `tests/` directory.
- Test files are named `<module>_test.py` and live in the same directory as the module they test.
- Mock all external services (Modal, Anthropic/OpenAI/Google) in unit tests — never hit live APIs in tests.
- Integration tests that require a live sandbox should be marked `@pytest.mark.integration`; if added, configure pytest so they are skipped by default.
- Shared fixtures live in `conftest.py` at the project root (or a local `conftest.py` for directory-scoped fixtures).

---

## Linting & Formatting

Ruff is the single tool for both linting and formatting.

CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -v
```

Pre-commit is configured for `uv-lock`, Ruff check/format, `ty`, and manual
pytest.

---

## What NOT to Do

- Do not commit `.env` (it is in `.gitignore`)
- Do not use `pip install` — always use `uv add`
- Do not use bare `except:` — always catch specific exceptions
