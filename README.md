<p align="center">
  <a href="#quick-start"><img alt="quick start" src="https://img.shields.io/badge/quick_start-60s-3fb950?style=flat-square"/></a>
  <img alt="license" src="https://img.shields.io/badge/license-MIT-blue?style=flat-square"/>
  <img alt="python" src="https://img.shields.io/badge/python-3.8%2B-58a6ff?style=flat-square"/>
  <img alt="notebooks" src="https://img.shields.io/badge/notebooks-6-c084fc?style=flat-square"/>
  <img alt="provider" src="https://img.shields.io/badge/provider-any_OpenAI--compatible-d29922?style=flat-square"/>
  <img alt="deps" src="https://img.shields.io/badge/core-openai_only-f85149?style=flat-square"/>
</p>

# Build Your First AI Agent

A hands-on, six-notebook walk-through that builds an AI agent **from scratch** — starting
with a single chat completion and ending with tool-using agents that explore a codebase,
triage logs, and query a database. Each notebook maps to one layer of the "agent stack",
using a network-operations theme as the running example.

The whole point fits in one sentence: **an agent is just a loop plus a capability table.**
You build that loop by hand in ~35 lines (notebook 02), then watch it stay *identical* while
you swap the tools to point it at three completely different resources (notebooks 04–06).

No frameworks required for the core idea — notebooks 01, 02, 04, 05 and 06 use only the
`openai` client. Notebook 03 then shows the same agent in LangChain/LangGraph so you can see
exactly what a framework gives you "for free".

---

## What you'll learn

| Notebook | Teaches | Stack layer |
|---|---|---|
| [`01_chat_completions_basics.ipynb`](01_chat_completions_basics.ipynb) | One stateless forward pass; the model has no memory; "memory" is just re-feeding the transcript; temperature/sampling | LLM + Provider SDK |
| [`02_agent_from_scratch.ipynb`](02_agent_from_scratch.ipynb) | The agent loop, hand-rolled (~35 lines) as an explicit state machine with tool calling | Agent = control plane |
| [`03_agent_with_langchain.ipynb`](03_agent_with_langchain.ipynb) | The same agent via LangChain/LangGraph in one line — and what the framework adds | Model layer (HAL) + framework |
| [`04_codebase_explainer_agent.ipynb`](04_codebase_explainer_agent.ipynb) | The same loop with read-only filesystem tools (`ls`/`cat`/`grep`/`find`) that explains a project from its source | Agent = control plane (new resource) |
| [`05_log_triage_agent.ipynb`](05_log_triage_agent.ipynb) | The same loop with read-only log tools (`ls`/`tail`/`grep`/`count`) that triages failures | Agent = control plane (new resource) |
| [`06_sql_data_agent.ipynb`](06_sql_data_agent.ipynb) | The same loop with read-only SQL (`list`/`describe`/`SELECT`) over a SQLite database | Agent = control plane (new resource) |

Notebooks **04–06 reuse the exact control loop from notebook 02** — only the capability
table changes. That repetition *is* the lesson.

---

## The agent loop

Everything from notebook 02 onward is the same finite state machine:

```
        ┌─────────────────────────────────────────────┐
        │                                             │
        ▼                                             │
  prompt the model  ──►  did it ask for a tool?       │
                              │                        │
                ┌─────────────┴─────────────┐          │
                │ yes                        │ no       │
                ▼                            ▼          │
          call the tool              FINAL ANSWER ► stop│
                │                                       │
                └────────── feed result back ───────────┘
```

`max_iterations` is the **TTL / hop count** — it stops a runaway loop. The model only ever
*requests* a tool by name + JSON arguments; **your** code executes it and feeds the result
back. The model talks; your loop acts.

---

## Highlights

- **From zero to agent** — start at a single `chat.completions.create` call and build up to a
  multi-step, tool-using agent without hand-waving over any step.
- **One loop, four resources** — the same ~35-line loop drives a (mocked) network, a
  filesystem, log files, and a SQL database. Swap the tools, keep the loop.
- **Framework contrast** — notebook 03 collapses the hand-rolled loop into one line of
  LangGraph, so the value a framework adds (retries, streaming, memory, checkpointing) is
  concrete, not abstract.
- **Read-only and sandboxed by design** — filesystem/log tools can't escape their root; the
  SQL tool only permits a single `SELECT`. Safe to run against real data and safe to demo live.
- **Self-contained** — notebooks 05 and 06 generate their own sample data
  (`sample_logs/`, `inventory.db`); nothing external to set up.
- **Any OpenAI-compatible provider** — OpenAI, OpenRouter, LiteLLM, or a local Ollama server,
  selected entirely through a `.env` file.
- **Minimal dependencies** — the core agent notebooks need only the `openai` client. LangChain
  is required for notebook 03 alone.

---

## Quick Start

```bash
git clone https://github.com/harshithsunku/build-your-first-ai-agent.git
cd build-your-first-ai-agent

pip install -r requirements.txt

cp .env.example .env        # then edit .env with your provider + key

jupyter lab                 # open notebook 01 and run top to bottom
```

Run the notebooks **in order** (01 → 06). Each is self-contained and re-explains what it
needs, but the narrative builds on the previous one.

### Configure your provider

Every notebook reads its settings from a `.env` file at the repo root (loaded automatically
via `python-dotenv`, with a fallback to existing environment variables). Copy the template and
fill in one provider:

```bash
# .env  — any OpenAI-compatible endpoint works
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-your-key-here
MODEL=gpt-4o-mini
```

<details>
<summary>Other providers (OpenRouter, LiteLLM, local Ollama)</summary>

```bash
# OpenRouter
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-your-key-here
MODEL=openai/gpt-4o-mini

# LiteLLM gateway
OPENAI_BASE_URL=https://your-litellm-host/v1
OPENAI_API_KEY=sk-...
MODEL=openrouter/deepseek/deepseek-chat

# Local Ollama (chat works on tiny models; tool-calling needs a capable one)
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
MODEL=qwen2.5:7b
```
</details>

`.env` is git-ignored, so your key never gets committed.

### Prerequisites

| Component | Needs |
|-----------|-------|
| **Python** | 3.8+ |
| **Provider** | An API key for any OpenAI-compatible endpoint (OpenAI, OpenRouter, LiteLLM, Ollama…) |
| **Model** | Notebook 01 runs on anything; **notebooks 02–06 need a tool-capable model** (e.g. `gpt-4o-mini`, `qwen2.5`, `llama3.1`). A 1B model usually can't drive function-calling reliably. |

---

## The tools, notebook by notebook

Each agent's behaviour is defined entirely by its **capability table** — a handful of plain
Python functions plus a JSON schema describing them to the model. The control loop never
changes.

| Notebook | Resource | Tools | Safety gate |
|---|---|---|---|
| 02 from scratch | network (mocked) | `calculate_subnet`, `get_interface_status` | telemetry mocked & deterministic |
| 04 codebase explainer | filesystem | `list_dir`, `read_file`, `grep`, `find_files` | paths sandboxed under `ROOT` |
| 05 log triage | log files | `list_logs`, `tail`, `grep_logs`, `count_pattern` | paths sandboxed under `ROOT` |
| 06 SQL data | SQLite database | `list_tables`, `describe_table`, `run_select` | `SELECT`-only; writes & chained statements rejected |

Point notebook 04's `ROOT` at any source tree, 05's `ROOT` at any logs directory, or 06's
`DB_PATH` at any SQLite file to run the agents against your own data.

---

## Project layout

```
build-your-first-ai-agent/
├── 01_chat_completions_basics.ipynb     # one forward pass; statelessness; sampling
├── 02_agent_from_scratch.ipynb          # the hand-rolled agent loop (the core lesson)
├── 03_agent_with_langchain.ipynb        # the same agent via LangChain/LangGraph
├── 04_codebase_explainer_agent.ipynb    # same loop + read-only filesystem tools
├── 05_log_triage_agent.ipynb            # same loop + read-only log tools
├── 06_sql_data_agent.ipynb              # same loop + read-only SQL tools
├── .env.example                         # provider config template (copy to .env)
├── requirements.txt                     # openai, python-dotenv, langchain*, jupyterlab
├── AGENTS.md                            # guidance for AI coding agents in this repo
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── LICENSE                              # MIT
└── README.md                           # this file
```

---

## Troubleshooting

**`AuthenticationError` / 401.** Check `OPENAI_API_KEY` in `.env` and that `OPENAI_BASE_URL`
matches the provider that issued the key.

**The agent never calls a tool (notebooks 02–06).** Your model probably isn't tool-capable.
Switch `MODEL` to something like `gpt-4o-mini`, `qwen2.5`, or `llama3.1`. Tiny (≈1B) models
can chat but usually can't drive function-calling.

**`Stopped: hit max_iterations`.** The loop's TTL fired before the model produced a final
answer — usually a weak model looping. Try a stronger model or raise `max_iterations`.

**`.env` not picked up.** Make sure you launched Jupyter from the repo root, or that a `.env`
exists there. The notebooks also honour plain environment variables if you'd rather `export`
them.

**Model name rejected by the provider.** Provider-prefixed names differ (e.g.
`openai/gpt-4o-mini` on OpenRouter vs. `gpt-4o-mini` on OpenAI). Match the exact name your
endpoint expects.

---

## Design rules

These are the rules the notebooks are built to:

- **Pedagogy first** — the code is intentionally explicit. Notebook 02 spells out the loop by
  hand; notebook 03's one-liner only lands *because* you saw the long version first.
- **One loop, many tools** — the control plane is fixed; only the capability table changes
  across 02/04/05/06. Don't "simplify" the hand-rolled loop with a framework.
- **Read-only by default** — every tool only observes. Add an explicit confirmation gate
  before wiring any tool that mutates state.
- **Generic and secret-free** — no proprietary names or keys in code; all config comes from
  `.env`.

See [`AGENTS.md`](AGENTS.md) for the full internal reference and conventions.

---

## Contributing

Issues and PRs welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). The repo is meant to stay small, generic, and
secret-free.

---

## License

MIT. See [`LICENSE`](LICENSE).
