# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this project is

A teaching repo of Jupyter notebooks that build up an AI agent layer by
layer, using a network-operations theme. Each notebook maps to a layer of the
"agent stack" discussed in an accompanying talk:

| Notebook | Teaches | Stack layer |
|---|---|---|
| `01_chat_completions_basics.ipynb` | One stateless forward pass; memory = re-feeding the transcript; sampling/temperature | LLM + Provider SDK |
| `02_agent_from_scratch.ipynb` | The agent loop hand-rolled (~35 lines) as an explicit FSM with tool calling | Agent = control plane |
| `03_agent_with_langchain.ipynb` | The same agent via LangChain/LangGraph in one line | Model layer (HAL) + framework (FRR) |
| `04_codebase_explainer_agent.ipynb` | The same hand-rolled loop with read-only filesystem tools (ls/cat/grep/find) that explains a project from its source | Agent = control plane (new resource) |
| `05_log_triage_agent.ipynb` | The same loop with read-only log tools (ls/tail/grep/count) that triages failures | Agent = control plane (new resource) |
| `06_sql_data_agent.ipynb` | The same loop with read-only SQL (list/describe/SELECT) over a SQLite database | Agent = control plane (new resource) |

Notebooks 04–06 deliberately reuse the exact control loop from notebook 02; only
the **capability table** (the tools) changes. That repetition *is* the lesson.

There is no application code, package, build system, or test suite. The
deliverable is the notebooks themselves.

## Setup

```bash
pip install openai langchain langgraph langchain-openai python-dotenv
```

Configure the provider in a `.env` file at the repo root. Every notebook loads
it automatically via `python-dotenv` (with a manual-parse fallback) and otherwise
falls back to existing environment variables. Copy `.env.example` to get started:

```bash
# .env
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-...
MODEL=gpt-4o-mini
```

Any OpenAI-compatible endpoint works (OpenAI, OpenRouter, LiteLLM, local Ollama).

Run with `jupyter lab`.

## Conventions

- **Provider config is identical across notebooks**: read `OPENAI_BASE_URL`,
  `OPENAI_API_KEY`, `MODEL` from the environment with the same defaults
  (`https://api.openai.com/v1`, `set-me`, `gpt-4o-mini`). Every notebook loads
  `.env` first. Keep this block in sync if you change one notebook.
- **OpenAI-compatible only**: all HTTP access goes through the `openai` client
  (or `langchain-openai`), so any OpenAI-compatible endpoint works.
- **Two demo tools**, repeated in notebooks 2 and 3:
  - `calculate_subnet(cidr)` — pure, deterministic compute via `ipaddress`.
  - `get_interface_status(device, interface)` — **mocked** telemetry, made
    deterministic with an md5 hash so live demos are repeatable.
- **Notebooks 4–6 each swap in a new read-only, sandboxed capability table**
  while keeping notebook 2's loop verbatim:
  - 04 filesystem: `list_dir`/`read_file`/`grep`/`find_files`, paths sandboxed
    under `ROOT`.
  - 05 logs: `list_logs`/`tail`/`grep_logs`/`count_pattern`, paths sandboxed
    under a logs `ROOT`; generates `sample_logs/` if absent.
  - 06 database: `list_tables`/`describe_table`/`run_select`; `run_select` only
    permits a single `SELECT` (rejects writes and chained statements); generates
    `inventory.db`.
- **Pedagogy first**: code is intentionally explicit and minimal. Notebook 2
  spells out the agent loop by hand; do not "simplify" it with a framework —
  that contrast is the whole point of notebook 3.
- Keep the networking analogies and narrative markdown cells intact; they carry
  the lesson.

## Safety constraints (important)

- All tools are **read-only by design**. If you add a tool that mutates device
  config, you must add a confirmation gate before it runs.
- `get_interface_status` must stay mocked/deterministic unless explicitly asked
  to wire real I/O (netmiko / SNMP / gNMI / MCP).
- Filesystem/log tools (04, 05) must stay sandboxed under their `ROOT`; the SQL
  tool (06) must stay `SELECT`-only. Don't loosen these guards for convenience.
- Tool-calling (notebooks 2–6) needs a tool-capable model
  (e.g. `gpt-4o-mini`, `qwen2.5`, `llama3.1`). A 1B model usually can't drive it.
  Notebook 1 runs on anything.
- **Secrets**: the API key lives in `.env`, which is git-ignored. Never commit
  `.env` or hard-code keys/endpoints in notebooks; rotate any shared key.

## Editing notebooks

- Preserve the layered narrative and the stack-layer mapping table.
- When changing the provider/config block, the tool definitions, or the agent
  loop, apply the same change consistently across the relevant notebooks.
- Don't commit API keys or real endpoints. Credentials come from env vars only.
- There are no automated tests; validate changes by running the notebook cells
  end to end against a configured provider.
