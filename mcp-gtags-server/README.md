# mcp-gtags-server

An [MCP](https://modelcontextprotocol.io/) server that gives AI assistants (Claude Code, Claude Desktop, or any MCP client) fast, index-backed code navigation for **C and C++ codebases** using [GNU Global (gtags)](https://www.gnu.org/software/global/).

Instead of grepping a large codebase from scratch on every question, the assistant can query a prebuilt gtags index: jump to definitions, find all references, list symbols in a file, and more — the same workflow kernel and systems developers use every day.

## Tools

| Tool | What it does | Underlying command |
|---|---|---|
| `index_project` | Build/rebuild the gtags index for a source tree | `gtags` |
| `update_index` | Incrementally refresh the index after edits | `global -u` |
| `find_definition` | Where is this symbol defined? | `global -x` |
| `find_references` | Who calls/uses this symbol? | `global -rx` |
| `find_symbol_usages` | Usages of symbols with no in-tree definition (e.g. libc calls) | `global -sx` |
| `grep_project` | Regex search across all indexed files | `global -gx` |
| `list_file_symbols` | All symbols defined in one file | `global -fx` |
| `complete_symbol` | Symbols starting with a prefix | `global -c` |
| `find_files` | Indexed files whose path matches a regex | `global -P` |

All query tools take a `project_root` argument, so one server instance can serve multiple indexed projects.

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

Or add it to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "gtags": {
      "command": "gtags-mcp"
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
      "command": "gtags-mcp"
    }
  }
}
```

## Example session

Once connected, ask the assistant things like:

> "Index /home/me/src/linux, then show me where `kmalloc` is defined and list every caller of `tcp_v4_rcv`."

The assistant will call `index_project` once, then use `find_definition` / `find_references` for near-instant answers, even on very large trees.

## Development

```bash
uv pip install -e ".[dev]"
pytest
```

Tests build a tiny C project in a temp directory and exercise the full index → query flow (skipped automatically if GNU Global isn't installed).

You can also poke at the server interactively with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector gtags-mcp
```

## License

MIT
