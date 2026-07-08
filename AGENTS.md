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
| `07_rag_knowledge_agent.ipynb` | RAG: embeddings + a hand-rolled numpy vector store over generated `runbooks/`; retrieval as a tool (`search_docs`) in the same loop | Knowledge plane |
| `08_mcp_tool_server.ipynb` | MCP: notebook 02's tools served by a `FastMCP` stdio subprocess (`mcp_network_server.py`, written by `%%writefile`), discovered and called by the loop over the protocol | Capability table on the wire |
| `09_structured_outputs.ipynb` | JSON mode + Pydantic (`InterfaceReport`) + retry-with-the-validation-error; messy CLI text → validated object | Model ↔ machine data plane |
| `10_memory_and_context.ipynb` | A `Session` class (persistent transcript) around 02's loop; `compact()` summarization; checkpoint/resume via `.agent_checkpoint.json` | Session layer |
| `11_multi_agent_orchestration.ipynb` | `run_loop()` (02's FSM as a factory) + three condensed specialists (04/05/06 tools) exposed to a supervisor as tools (`ask_codebase`/`ask_logs`/`ask_database`) | Orchestration plane |
| `12_eval_and_guardrails.ipynb` | Eval set + LLM-as-judge (`judge`, JSON verdicts) + `guard_input`/`guard_output` regex ACLs against injection/leaks | Assurance plane |

Notebooks 04–06 deliberately reuse the exact control loop from notebook 02; only
the **capability table** (the tools) changes. That repetition *is* the lesson.
Notebooks 07–12 keep the same FSM (07/10/11 restate it; 11 parameterizes it as
`run_loop`) and layer the modern agent stack on top.

Each notebook also has a `*_with_ui.ipynb` twin: an exact copy of the core
notebook with a small Gradio app appended (a chat box for 01, a question form +
"agent trace" panel for 02–08 and 11, a text-in/JSON-out form for 09, a
persistent chat + session buttons for 10, and an eval-table + guarded-chat pair
of tabs for 12). The UI cells **reuse the already-defined functions**
(`chat`/`run_agent`/`explain`/`triage`/`ask_data`/`ask_docs`/`run_agent_mcp`/
`extract`/`Session.ask`/`supervise`/`run_evals`/`guarded_ask` and the LangGraph
`agent`) — they don't reimplement any logic. When you change a core notebook,
mirror the change into its `_with_ui` twin (and vice-versa). Keep the core
notebooks dependency-light; `gradio` is only imported in the twins.

There is no application code, package, build system, or test suite. The
deliverable is the notebooks themselves.

## Setup

Preferred (uv, uses `pyproject.toml` + `uv.lock`):

```bash
uv sync            # then: uv run jupyter lab
```

Classic pip:

```bash
pip install openai langchain langgraph langchain-openai python-dotenv numpy mcp pydantic
```

(`numpy` is for notebook 07 only, `mcp` for 08 only, `pydantic` for 09 only;
`gradio` only for the `*_with_ui` twins.) **Python 3.10+ uniformly** — all
notebooks target it, so modern syntax (builtin generics like `list[str]`,
`X | Y` unions) is fine anywhere. `pyproject.toml`, `uv.lock` and
`requirements.txt` must stay in sync when dependencies change.

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
- **`VERIFY_SSL` env var** (default `true`): when `false`, the config cell builds an
  `httpx.Client(verify=False)` (plus an `httpx.AsyncClient` for notebook 03's
  `ChatOpenAI`) and passes it via `http_client=` so the demos work behind
  TLS-intercepting firewalls. This same block is duplicated in all 24 notebooks —
  change it everywhere at once.
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
- **Notebooks 07–12 conventions**:
  - 07 RAG: generates fictional `runbooks/*.md` (git-ignored); the vector store is
    in-memory (a normalized numpy matrix); embeddings use the same `client` via
    `client.embeddings.create` with `EMBED_MODEL` (default `text-embedding-3-small`).
  - 08 MCP: the server file `mcp_network_server.py` is written by the notebook
    (`%%writefile`, git-ignored) and spawned as a **local stdio subprocess** — no
    network listener. Its tools are the same read-only/mocked pair from 02.
  - 09: `extract()` must keep all three layers — JSON mode, Pydantic validation,
    retry-with-the-error — the layering is the lesson.
  - 10: the checkpoint file `.agent_checkpoint.json` is git-ignored; transcripts may
    contain sensitive text and must never be committed.
  - 11: the condensed specialist tools must keep 04/05/06's guards (path sandboxes,
    `SELECT`-only gate) even though they are shorter.
  - 12: eval expectations must match the deterministic tools (e.g. the md5-seeded
    mock makes `leaf-01/ethernet1/0/1` **down**) — recompute before editing them.
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
- Tool-calling (notebooks 2–8 and 10–12) needs a tool-capable model
  (e.g. `gpt-4o-mini`, `qwen2.5`, `llama3.1`). A 1B model usually can't drive it.
  Notebooks 1 and 9 run on anything. Notebook 7 additionally needs an embeddings
  endpoint (`EMBED_MODEL`).
- **Secrets**: the API key lives in `.env`, which is git-ignored. Never commit
  `.env` or hard-code keys/endpoints in notebooks; rotate any shared key.

## Editing notebooks

- Preserve the layered narrative and the stack-layer mapping table.
- When changing the provider/config block, the tool definitions, or the agent
  loop, apply the same change consistently across the relevant notebooks.
- Don't commit API keys or real endpoints. Credentials come from env vars only.
- There are no automated tests; validate changes by running the notebook cells
  end to end against a configured provider.
