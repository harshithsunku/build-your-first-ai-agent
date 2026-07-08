"""MCP server that wraps GNU Global (gtags) for C/C++ code navigation.

Designed as a drop-in replacement for grep-based code search in AI coding
agents: instead of scanning the whole tree on every question, queries hit a
gtags index and return a narrow, precise set of lines. The server manages the
index automatically — it builds it on first query and incrementally refreshes
it before each query — so agents never have to think about indexing.

GNU Global must be installed and on PATH (binaries: ``gtags``, ``global``).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gtags")

DEFAULT_LIMIT = 100
MAX_LINE_CHARS = 200
QUERY_TIMEOUT_SECONDS = 120
INDEX_TIMEOUT_SECONDS = 600
# Skip the incremental freshness check when the same root was updated this
# recently — agent turns often fire many queries back to back.
UPDATE_DEBOUNCE_SECONDS = 5.0

# Default root set by --root / GTAGS_MCP_ROOT; falls back to the server cwd.
_default_root: str | None = None
_last_update: dict[Path, float] = {}


def _check_global_installed() -> str | None:
    if shutil.which("global") is None or shutil.which("gtags") is None:
        return (
            "Error: GNU Global is not installed or not on PATH. "
            "Install it first (e.g. `apt install global`, `brew install global`)."
        )
    return None


def _effective_root(project_root: str | None) -> tuple[Path | None, str | None]:
    """Resolve the project root: explicit arg > --root/env default > cwd."""
    raw = project_root or _default_root or os.getcwd()
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        return None, f"Error: project_root is not a directory: {raw}"
    return root, None


def _run(args: list[str], cwd: Path, timeout: int = QUERY_TIMEOUT_SECONDS) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, returncode)."""
    proc = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.stdout, proc.stderr, proc.returncode


def _ensure_index(root: Path) -> str | None:
    """Build the index if missing, else incrementally refresh it (debounced)."""
    if not (root / "GTAGS").is_file():
        stdout, stderr, code = _run(["gtags"], root, timeout=INDEX_TIMEOUT_SECONDS)
        if code != 0:
            return (
                f"Error: automatic indexing failed (gtags exited {code}): "
                f"{stderr.strip() or stdout.strip()}"
            )
        _last_update[root] = time.monotonic()
        return None
    now = time.monotonic()
    if now - _last_update.get(root, 0.0) < UPDATE_DEBOUNCE_SECONDS:
        return None
    _, stderr, code = _run(["global", "-u"], root, timeout=INDEX_TIMEOUT_SECONDS)
    if code != 0:
        return f"Error: index refresh failed (global -u exited {code}): {stderr.strip()}"
    _last_update[root] = time.monotonic()
    return None


def _paginate(text: str, limit: int, offset: int) -> str:
    lines = [
        line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS] + " ..."
        for line in text.splitlines()
    ]
    total = len(lines)
    limit = max(1, limit)
    offset = max(0, offset)
    page = lines[offset : offset + limit]
    if not page:
        return f"No results in range: offset {offset} is past the last of {total} matches."
    body = "\n".join(page)
    end = offset + len(page)
    if offset == 0 and end == total:
        return body
    footer = f"— showing {offset + 1}-{end} of {total} matches"
    if end < total:
        footer += f"; pass offset={end} to continue"
    return f"{body}\n{footer}"


def _query_global(
    flags: list[str],
    project_root: str | None,
    empty_message: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Shared plumbing for all read-only `global` queries."""
    if err := _check_global_installed():
        return err
    root, err = _effective_root(project_root)
    if err:
        return err
    if err := _ensure_index(root):
        return err
    stdout, stderr, code = _run(["global", *flags], cwd=root)
    # `global` exits non-zero both for real errors and for "no match found";
    # only the former writes to stderr.
    if code != 0 and stderr.strip():
        return f"Error: global exited with code {code}: {stderr.strip()}"
    if not stdout.strip():
        return empty_message
    return _paginate(stdout.rstrip(), limit, offset)


@mcp.tool()
def find_definition(
    symbol: str,
    project_root: str | None = None,
    case_insensitive: bool = False,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Find where a C/C++ symbol (function, struct, macro, typedef, enum) is defined.

    Use this INSTEAD of grep or text search whenever you need a symbol's
    definition — it is an indexed lookup that returns only the definition
    site(s), not every textual occurrence, and stays fast on codebases with
    millions of lines. The index is built and refreshed automatically.

    Each result line has the format: symbol line-number file source-line.

    Args:
        symbol: Exact symbol name, e.g. "tcp_v4_rcv" or "list_head".
        project_root: Project directory. Omit to use the server's default
            (its working directory or the configured --root).
        case_insensitive: Match the symbol ignoring case.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    flags = ["-x"] + (["-i"] if case_insensitive else []) + ["--", symbol]
    return _query_global(
        flags,
        project_root,
        f"No definition found for symbol '{symbol}'.",
        limit,
        offset,
    )


@mcp.tool()
def find_references(
    symbol: str,
    project_root: str | None = None,
    case_insensitive: bool = False,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Find all call/usage sites of a defined C/C++ symbol.

    Use this INSTEAD of grep when you need who calls a function or uses a
    type — grep returns every textual match including comments and strings,
    while this returns only real reference sites from the index, instantly
    even on huge trees.

    Each result line has the format: symbol line-number file source-line.

    Args:
        symbol: Exact symbol name whose call/usage sites you want.
        project_root: Project directory. Omit to use the server's default.
        case_insensitive: Match the symbol ignoring case.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    flags = ["-rx"] + (["-i"] if case_insensitive else []) + ["--", symbol]
    return _query_global(
        flags,
        project_root,
        f"No references found for symbol '{symbol}'.",
        limit,
        offset,
    )


@mcp.tool()
def find_symbol_usages(
    symbol: str,
    project_root: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Find usages of symbols that have no definition inside the project.

    Use this when find_definition returns nothing — typically external or
    library identifiers (e.g. printf, malloc) and variables gtags did not
    record as definitions. Still an indexed lookup, not a scan.

    Args:
        symbol: Exact symbol name.
        project_root: Project directory. Omit to use the server's default.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    return _query_global(
        ["-sx", "--", symbol],
        project_root,
        f"No usages found for undefined symbol '{symbol}'.",
        limit,
        offset,
    )


@mcp.tool()
def grep_project(
    pattern: str,
    project_root: str | None = None,
    case_insensitive: bool = False,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Regex-search all indexed source files (POSIX extended regex).

    Prefer find_definition / find_references for symbol questions — they are
    indexed and far narrower. Use this only for arbitrary text that is not a
    symbol name (comments, string literals, TODO markers). It still beats
    plain grep: it searches only files the index knows about.

    Args:
        pattern: Regex to search for, e.g. "TODO|FIXME".
        project_root: Project directory. Omit to use the server's default.
        case_insensitive: Match the pattern ignoring case.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    flags = ["-gx"] + (["-i"] if case_insensitive else []) + ["--", pattern]
    return _query_global(
        flags,
        project_root,
        f"No matches for pattern '{pattern}'.",
        limit,
        offset,
    )


@mcp.tool()
def list_file_symbols(
    file_path: str,
    project_root: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """List every symbol defined in one source file.

    Use this INSTEAD of reading a whole file when you only need its API
    surface — functions, structs, macros it defines — as a compact list.

    Each result line has the format: symbol line-number file source-line.

    Args:
        file_path: Path to the source file, relative to the project root or absolute.
        project_root: Project directory. Omit to use the server's default.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    return _query_global(
        ["-fx", "--", file_path],
        project_root,
        f"No symbols found in '{file_path}' (is it inside the indexed tree?).",
        limit,
        offset,
    )


@mcp.tool()
def complete_symbol(
    prefix: str,
    project_root: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """List defined symbols that start with the given prefix.

    Use this when you know roughly what a function is called but not its
    exact name — then follow up with find_definition on the right match.

    Args:
        prefix: Symbol name prefix, e.g. "tcp_" or "init".
        project_root: Project directory. Omit to use the server's default.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    return _query_global(
        ["-c", "--", prefix],
        project_root,
        f"No symbols starting with '{prefix}'.",
        limit,
        offset,
    )


@mcp.tool()
def find_files(
    pattern: str,
    project_root: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Find indexed source files whose path matches a regex pattern.

    Use this INSTEAD of `find` or glob scans to locate files in a large
    tree — it queries the index rather than walking the filesystem.

    Args:
        pattern: Regex matched against file paths, e.g. "net/.*\\.c$".
        project_root: Project directory. Omit to use the server's default.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    return _query_global(
        ["-P", "--", pattern],
        project_root,
        f"No indexed files match '{pattern}'.",
        limit,
        offset,
    )


@mcp.tool()
def index_project(project_root: str | None = None) -> str:
    """Force a full (re)build of the gtags index.

    Normally unnecessary — every query tool indexes automatically on first
    use and refreshes incrementally. Call this only to force a from-scratch
    rebuild (e.g. after a large branch switch or if the index seems corrupt).

    Args:
        project_root: Project directory. Omit to use the server's default.
    """
    if err := _check_global_installed():
        return err
    root, err = _effective_root(project_root)
    if err:
        return err
    stdout, stderr, code = _run(["gtags"], root, timeout=INDEX_TIMEOUT_SECONDS)
    if code != 0:
        return f"Error: gtags exited with code {code}: {stderr.strip() or stdout.strip()}"
    _last_update[root] = time.monotonic()
    return f"Indexed {root} (GTAGS, GRTAGS, GPATH created)."


@mcp.tool()
def update_index(project_root: str | None = None) -> str:
    """Force an immediate incremental index refresh.

    Normally unnecessary — every query tool refreshes the index automatically
    before running. Call this only to refresh eagerly, e.g. right after a
    large batch of edits and before a burst of queries.

    Args:
        project_root: Project directory. Omit to use the server's default.
    """
    if err := _check_global_installed():
        return err
    root, err = _effective_root(project_root)
    if err:
        return err
    if not (root / "GTAGS").is_file():
        return f"Error: no GTAGS index found in {root}. Run index_project first."
    _, stderr, code = _run(["global", "-u"], root, timeout=INDEX_TIMEOUT_SECONDS)
    if code != 0:
        return f"Error: global -u exited with code {code}: {stderr.strip()}"
    _last_update[root] = time.monotonic()
    return f"Index updated for {root}."


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    global _default_root
    parser = argparse.ArgumentParser(
        prog="gtags-mcp",
        description="MCP server exposing GNU Global (gtags) code navigation over stdio.",
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("GTAGS_MCP_ROOT"),
        help="Default project root for all tools (overrides GTAGS_MCP_ROOT; "
        "falls back to the current working directory).",
    )
    args = parser.parse_args()
    _default_root = args.root
    mcp.run()


if __name__ == "__main__":
    main()
