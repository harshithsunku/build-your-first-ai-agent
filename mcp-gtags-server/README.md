# mcp-gtags-server

**A drop-in replacement for grep-based code search in AI coding agents**, built on [GNU Global (gtags)](https://www.gnu.org/software/global/) and exposed over [MCP](https://modelcontextprotocol.io/).

When an AI agent (Claude Code, Cursor, Codex, ...) needs to answer "where is this function defined?" or "who calls this?", it typically greps the tree — a full scan on every question. On large C/C++ codebases that's slow, and worse, it floods the model's context with every textual occurrence: comments, strings, unrelated matches. This server replaces those scans with indexed lookups that return a **narrow, precise** set of lines.

The server manages the index entirely by itself: the first query builds it, and every query incrementally refreshes it. The agent never has to think about indexing.

## Why not just grep?

Measured on a Linux kernel checkout (65,163 C/C++ files, 37.1M lines), warm page cache:

| Query | grep -rn (scan) | global (indexed) | Output lines: grep vs global |
|---|---|---|---|
| `tcp_v4_rcv` definition | 1.40 s | **0.01 s** | 8 vs **1** |
| `kmalloc` definition | 1.62 s | **0.01 s** | 7,873 vs **5** |
| `kmalloc` references | 1.62 s | **0.10 s** | 7,873 vs 2,744 (real call sites only) |
| `ext4_readdir` definition | 1.48 s | **0.01 s** | 2 vs **1** |

One-time index build: 66.5 s for the whole kernel; after that, incremental updates take well under a second. The speedup per query is ~100×, but the bigger win for an agent is **precision**: a definition lookup returns the definition, not 7,873 lines of noise eating the context window.

Reproduce with [`scripts/benchmark.sh`](scripts/benchmark.sh):

```bash
./scripts/benchmark.sh /path/to/linux tcp_v4_rcv kmalloc ext4_readdir
```

## Tools

All query tools take optional `limit` (default 100) and `offset` parameters for pagination, and `project_root` may be omitted (defaults to the server's working directory, or `--root` / `GTAGS_MCP_ROOT` if configured). Indexing happens automatically on first use.

| Tool | What it does | Underlying command |
|---|---|---|
| `find_definition` | Where is this symbol defined? (`case_insensitive` opt.) | `global -x` |
| `find_references` | Who calls/uses this symbol? (`case_insensitive` opt.) | `global -rx` |
| `find_symbol_usages` | Usages of symbols with no in-tree definition (e.g. libc calls) | `global -sx` |
| `grep_project` | Regex search across indexed files (`case_insensitive` opt.) | `global -gx` |
| `list_file_symbols` | All symbols defined in one file (a file's API surface) | `global -fx` |
| `complete_symbol` | Symbols starting with a prefix | `global -c` |
| `find_files` | Indexed files whose path matches a regex | `global -P` |
| `index_project` | Force a full index rebuild (rarely needed) | `gtags` |
| `update_index` | Force an incremental refresh (rarely needed) | `global -u` |

## Prerequisites

- Python 3.10+
- GNU Global on PATH:
  - Debian/Ubuntu: `sudo apt install global`
  - Fedora: `sudo dnf install global`
  - macOS: `brew install global`

## Installation

```bash
# with uv (recommended)
uv tool install mcp-gtags-server

# or from a local checkout
uv pip install -e .
# or: pip install -e .
```

This installs the `gtags-mcp` command, which speaks MCP over stdio.

## Using with Claude Code

```bash
claude mcp add gtags -- gtags-mcp
```

Or in your project's `.mcp.json` (the server inherits the project directory as its default root):

```json
{
  "mcpServers": {
    "gtags": {
      "command": "gtags-mcp"
    }
  }
}
```

To pin a specific tree regardless of where the server is launched:

```json
{
  "mcpServers": {
    "gtags": {
      "command": "gtags-mcp",
      "args": ["--root", "/home/me/src/linux"]
    }
  }
}
```

## Using with Claude Desktop

Add to `claude_desktop_config.json`:

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

## Example session

Once connected, ask the assistant things like:

> "Where is `tcp_v4_rcv` defined and who calls it?"

The first query auto-builds the index; every question after that is answered in milliseconds from the index — no grep scans, no context-window flooding.

## Development

```bash
uv pip install -e ".[dev]"
pytest
```

Tests build a tiny C project in a temp directory and exercise auto-indexing, auto-refresh, pagination, and the full query flow (skipped automatically if GNU Global isn't installed).

Poke at the server interactively with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector gtags-mcp
```

## Future work

- Languages beyond gtags' native set (C, C++, Yacc, Java, PHP, assembly) via the Pygments/ctags plugin parsers.
- Structured (JSON) result variants for clients that want machine-readable output.

## License

MIT
