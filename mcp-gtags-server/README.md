# ⚡ mcp-gtags-server

> **Stop letting your AI agent grep. Give it an index.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-8A2BE2)](https://modelcontextprotocol.io/)
[![Powered by GNU Global](https://img.shields.io/badge/powered%20by-GNU%20Global-orange)](https://www.gnu.org/software/global/)

Every AI coding agent — Claude Code, Cursor, Codex, you name it — answers *"where is this function defined?"* the same way: **grep the entire tree**. On a million-line C/C++ codebase that's a full scan per question, and the output is a firehose: every comment, string literal, and unrelated match, dumped straight into the model's context window.

**mcp-gtags-server** replaces those scans with indexed lookups powered by [GNU Global (gtags)](https://www.gnu.org/software/global/) — the same tags engine kernel and systems developers have trusted for decades — exposed to agents over the [Model Context Protocol](https://modelcontextprotocol.io/).

- 🚀 **~100× faster per query** — milliseconds instead of seconds, at any codebase size
- 🎯 **Radically less noise** — the definition, not 7,873 lines of matches
- 🧠 **Zero index management** — first query builds the index, every query auto-refreshes it
- 🔌 **Works everywhere MCP does** — Claude Code, Claude Desktop, Cursor, any MCP client

## 📊 The numbers (real Linux kernel, not a toy)

Measured on a full Linux kernel checkout — **65,163 C/C++ files, 37.1 million lines** — warm page cache:

| Question an agent asks | `grep -rn` | gtags (this server) | Context consumed |
|---|---|---|---|
| Where is `tcp_v4_rcv` defined? | 1.40 s | **0.01 s** | 8 lines → **1 line** |
| Where is `kmalloc` defined? | 1.62 s | **0.01 s** | 7,873 lines → **5 lines** |
| Who references `kmalloc`? | 1.62 s | **0.10 s** | 7,873 noisy lines → 2,744 real sites (or a **ranked per-file summary**) |
| Show me `tcp_v4_rcv`'s implementation | *read a 3,500-line file* | **`get_symbol_body`** | **exactly the 271-line function** |
| Who calls `ext4_mark_inode_dirty`? | 245 raw match lines | **`find_callers`** | **62 deduped caller functions, with counts** |

One-time index build: **66 s** for the whole kernel. Incremental refresh after edits: well under a second. Reproduce it yourself with [`scripts/benchmark.sh`](scripts/benchmark.sh):

```bash
./scripts/benchmark.sh /path/to/linux tcp_v4_rcv kmalloc ext4_readdir
```

The speed is nice. The real win is **precision**: an agent that gets 5 exact lines instead of 7,873 noisy ones keeps its context window for actual reasoning.

## 🚀 Quick start (60 seconds)

**1. Install GNU Global** (the `gtags`/`global` binaries):

```bash
sudo apt install global      # Debian/Ubuntu
sudo dnf install global      # Fedora
brew install global          # macOS
```

**2. Install the server:**

```bash
uv tool install mcp-gtags-server        # or: pip install mcp-gtags-server
```

**3. Hook it up to your agent:**

```bash
# Claude Code — one command:
claude mcp add gtags -- gtags-mcp
```

Or in your project's `.mcp.json` (Claude Code, Cursor, and most MCP clients):

```json
{
  "mcpServers": {
    "gtags": {
      "command": "gtags-mcp"
    }
  }
}
```

That's it. No indexing step, no configuration. Ask your agent *"who calls `tcp_v4_rcv`?"* — the first query builds the index automatically, and every query after that is answered in milliseconds.

<details>
<summary><b>Claude Desktop</b> config</summary>

Add to `claude_desktop_config.json` (pin the project since Desktop doesn't launch in your repo):

```json
{
  "mcpServers": {
    "gtags": {
      "command": "gtags-mcp",
      "args": ["--root", "/absolute/path/to/your/project"]
    }
  }
}
```

</details>

<details>
<summary><b>Pin a project root</b> explicitly</summary>

The default project root is the server's working directory. Override with `--root /path` or the `GTAGS_MCP_ROOT` env var — or pass `project_root` on any individual tool call to query a different tree.

</details>

## 🧰 The tools

### Symbol-level tools — the noise killers

The pattern proven out by semantic-code servers like [Serena](https://github.com/oraios/serena): **give the agent the symbol, not the file.**

| Tool | What the agent gets |
|---|---|
| `symbol_info` | **A one-shot overview card** — definitions, reference count, hottest files, and which tool to use next. The best first query for any unfamiliar symbol. |
| `get_symbol_body` | **Just the source of a definition.** The 271-line `tcp_v4_rcv` function — not the 3,500-line file it lives in. Handles functions, structs, and multi-line macros. |
| `find_callers` | **The call graph, deduplicated.** Every reference mapped to its enclosing function with call counts: 245 raw lines for `ext4_mark_inode_dirty` collapse to 62 callers. |
| `call_hierarchy` | **Multi-level impact analysis.** Who calls X, who calls *those*, up to 5 levels — a cycle-safe, capped tree instead of N rounds of grep. |
| `find_callees` | **The outgoing call graph.** What does this function call? Body-extracted call sites, each verified against the index, split into in-tree (with locations) and external. |
| `summarize_references` | **A ranked per-file count.** The cheap first move for hot symbols — `kmalloc`'s 2,744 references become one screen of "where usage concentrates". |
| `project_overview` | **Orientation in an unfamiliar repo** — file counts by top-level directory and language, straight from the index. |
| `find_dead_symbols` | **Dead-code candidates** — every symbol a file defines that nothing references. |
| `find_includers` | **Header blast radius** — every file that `#include`s a header, matched by basename. |

A two-level `call_hierarchy` on the kernel's `ext4_mark_inode_dirty` — 87 compact lines instead of dozens of grep rounds:

```text
ext4_mark_inode_dirty  (definition: fs/ext4/ext4_jbd2.h:138)
├─ ext4_rename  fs/ext4/namei.c  (6 sites)
│  └─ ext4_rename2  fs/ext4/namei.c  (1 site)
├─ swap_inode_boot_loader  fs/ext4/ioctl.c  (5 sites)
│  └─ __ext4_ioctl  fs/ext4/ioctl.c  (1 site)
├─ ext4_mkdir  fs/ext4/namei.c  (3 sites)
│  └─ ext4_rename2  fs/ext4/namei.c  (1 site)
...
```

### Core lookups

| Tool | What it does | Underlying command |
|---|---|---|
| `find_definition` | Where is this symbol defined? | `global -x` |
| `find_references` | Raw reference lines for a symbol | `global -rx` |
| `find_symbol_usages` | Usages of symbols with no in-tree definition (libc calls etc.) | `global -sx` |
| `grep_project` | Regex search across indexed files | `global -gx` |
| `list_file_symbols` | A file's API surface — every symbol it defines | `global -fx` |
| `complete_symbol` | Symbols starting with a prefix | `global -c` |
| `find_files` | Indexed files whose path matches a regex | `global -P` |
| `index_project` / `update_index` | Force rebuild / refresh (rarely needed — it's automatic) | `gtags` / `global -u` |

Every query tool supports `limit`/`offset` pagination with a continuation footer, long-line truncation, and (where it makes sense) `case_insensitive` — output is *engineered* to never flood a context window.

### The flow that saves your context window

```text
0. project_overview()                       → orient in an unfamiliar repo (12 lines)
1. symbol_info("kmalloc")                   → definitions + usage spread + next step (12 lines)
2. call_hierarchy("ext4_mark_inode_dirty")  → multi-level impact tree (1 line/caller)
3. get_symbol_body("tcp_v4_rcv")            → read the ONE function that matters
4. find_callees("tcp_v4_rcv")               → what it depends on, with locations
```

A few hundred lines of context total — versus tens of thousands for the grep-and-read-files equivalent.

## 🌍 Multi-language projects (C + Python + more)

Real projects mix languages — a C core with Python tooling, JS frontends, Go services. The server handles this automatically:

- **Native languages** (C, C++, Java, PHP, Yacc, assembly) use GNU Global's fast built-in parser.
- **Everything else** (Python, Go, Rust, JavaScript, TypeScript, Ruby, ... ~150 languages) is indexed through Global's **ctags + Pygments plugin parsers** — same index, same tools, same queries.

Enable it by installing two extra packages; the server detects them and switches to the `native-pygments` parser label on its own:

```bash
sudo apt install exuberant-ctags python3-pygments   # Debian/Ubuntu
sudo dnf install ctags python3-pygments             # Fedora
brew install ctags && pip install pygments          # macOS
```

Now `find_definition("py_util")`, `get_symbol_body` (indentation-aware for Python), `find_callees`, `call_hierarchy` — all work across every language in the tree, in one index.

Force a specific parser label with `--label` or `GTAGS_MCP_LABEL` (e.g. `--label default` for native-only, `--label pygments` for plugin-everything).

**Honest caveats:** for plugin-parsed languages, *definitions* are as accurate as ctags, but *references* are token-based — every occurrence of the name counts, without C-grade semantic reference tracking or local-scope awareness. For C/C++ nothing changes: the native parser still does that part.

## ⚙️ How it works

```text
agent question ──► MCP tool ──► GTAGS index (built once, ~66s for the kernel)
                                    │
                 background auto-refresh (global -u, adaptive debounce)
                                    │
                              narrow answer ──► agent context
```

- **First query on a tree?** The index is built automatically (the only operation that ever blocks — and only once).
- **Files changed?** A debounced incremental refresh runs **in the background**: queries always answer instantly from the current index while `global -u` catches up behind the scenes. Measured on the kernel: queries return in 0.02s while the 25s freshness check runs invisibly. Staleness is bounded by the debounce window; call `update_index` for a synchronous, guaranteed-fresh barrier right after edits.
- **Huge result?** Pagination footers tell the agent exactly how to fetch the next page — or the tool itself suggests a narrower one (`find_callers` on a symbol used in 500+ files points to `summarize_references`).

## ❓ FAQ

**Why gtags instead of a language server (LSP)?**
LSP servers give richer semantics but need a working build configuration, per-editor setup, and serious warm-up time on large trees. gtags indexes 37M lines in about a minute with *zero* configuration, handles the kernel-scale codebases LSPs choke on, and its fuzzy parser doesn't care whether the code currently compiles. For C/C++ navigation questions — definition, references, callers — it's the pragmatic sweet spot.

**What languages?**
C, C++, Yacc, Java, PHP, and assembly natively — plus Python, Go, Rust, JS/TS, Ruby, and ~150 others via the ctags/Pygments plugin parsers (see [Multi-language projects](#-multi-language-projects-c--python--more)).

**Does the agent have to manage the index?**
No. That's the point. Build-on-first-query, background refresh with adaptive debounce, zero blocking — queries never wait for index maintenance. The explicit `index_project`/`update_index` tools exist only as escape hatches (`update_index` doubles as a synchronous freshness barrier after edits).

**Will it fight my agent's built-in tools?**
The tool descriptions are written to steer the model: they say *when* to use indexed lookups instead of grep. In practice agents pick the faster, narrower tool naturally.

## 🛠️ Development

```bash
git clone https://github.com/harshithsunku/mcp-gtags-server
cd mcp-gtags-server
uv venv && uv pip install -e ".[dev]"
pytest                        # 21 tests; auto-skip if GNU Global is absent
npx @modelcontextprotocol/inspector gtags-mcp    # poke at it interactively
```

Tests build a real C project in a temp dir and exercise auto-indexing, auto-refresh, caller mapping, body extraction, and pagination end-to-end.

## 🗺️ Roadmap

- [x] Multi-level call hierarchy (`call_hierarchy`, depth 1–5) for transitive impact analysis
- [x] Outgoing call graph (`find_callees`), symbol overview cards (`symbol_info`), project orientation (`project_overview`)
- [x] Dead-code candidates (`find_dead_symbols`) and header blast radius (`find_includers`)
- [x] Multi-language projects (Python, Go, Rust, JS, ... via ctags/Pygments plugin parsers, auto-detected)
- [ ] Structured (JSON) result variants for machine-readable output
- [ ] Published benchmarks vs LSP-based MCP servers

Contributions welcome — open an issue or PR.

## 📄 License

[MIT](LICENSE) © Harshith Sunku
