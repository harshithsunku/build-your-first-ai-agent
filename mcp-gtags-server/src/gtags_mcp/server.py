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

mcp = FastMCP(
    "gtags-code-navigator",
    instructions=(
        "Indexed C/C++ code navigation backed by GNU Global (gtags). "
        "ALWAYS prefer these tools over grep/text search for code questions: "
        "they answer from a prebuilt index in milliseconds and return only "
        "the relevant lines, even on codebases with millions of lines. "
        "Typical flow: find_definition or get_symbol_body to see a symbol's "
        "implementation; find_callers for the call graph; "
        "summarize_references first for very widely used symbols. "
        "The index is built and refreshed automatically — never worry about it."
    ),
)

DEFAULT_LIMIT = 100
MAX_LINE_CHARS = 200
MAX_BODY_LINES = 300
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


def _raw_global(
    flags: list[str], project_root: str | None
) -> tuple[str | None, Path | None, str | None]:
    """Resolve root, ensure the index, run `global`. Returns (stdout, root, error)."""
    if err := _check_global_installed():
        return None, None, err
    root, err = _effective_root(project_root)
    if err:
        return None, None, err
    if err := _ensure_index(root):
        return None, root, err
    stdout, stderr, code = _run(["global", *flags], cwd=root)
    # `global` exits non-zero both for real errors and for "no match found";
    # only the former writes to stderr.
    if code != 0 and stderr.strip():
        return None, root, f"Error: global exited with code {code}: {stderr.strip()}"
    return stdout, root, None


def _query_global(
    flags: list[str],
    project_root: str | None,
    empty_message: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Shared plumbing for all read-only `global` queries."""
    stdout, _, err = _raw_global(flags, project_root)
    if err:
        return err
    if not stdout.strip():
        return empty_message
    return _paginate(stdout.rstrip(), limit, offset)


def _parse_cxref(line: str) -> tuple[str, int, str, str] | None:
    """Parse one `global -x` output line: symbol, line-number, path, source."""
    parts = line.split(None, 3)
    if len(parts) < 3 or not parts[1].isdigit():
        return None
    symbol, lineno, path = parts[0], int(parts[1]), parts[2]
    source = parts[3] if len(parts) == 4 else ""
    return symbol, lineno, path, source


def _extract_body(file: Path, start_line: int) -> list[str]:
    """Extract a C/C++ definition body starting at start_line (1-based).

    Brace-counting heuristic: read until the block opened by the first `{`
    closes. Prototypes, typedefs, and macros without a block end at the first
    line not continued by a backslash that ends in `;` (or after a short
    window if no block ever opens).
    """
    lines = file.read_text(errors="replace").splitlines()
    i = start_line - 1
    if i < 0 or i >= len(lines):
        return []
    out: list[str] = []
    depth = 0
    seen_brace = False
    j = i
    while j < len(lines) and len(out) < MAX_BODY_LINES:
        line = lines[j]
        out.append(line)
        depth += line.count("{") - line.count("}")
        if "{" in line:
            seen_brace = True
        if seen_brace and depth <= 0:
            break
        if not seen_brace:
            stripped = line.rstrip()
            if stripped.endswith("\\"):  # continuation (macro or split declaration)
                j += 1
                continue
            if out[0].lstrip().startswith("#"):
                break  # preprocessor directive ends when continuations stop
            if stripped.endswith(";") or (j - i) >= 20:
                break  # prototype/typedef/one-liner, or no block in sight
        j += 1
    else:
        if len(out) >= MAX_BODY_LINES:
            out.append(f"... body truncated at {MAX_BODY_LINES} lines ...")
    return out


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
def get_symbol_body(
    symbol: str,
    project_root: str | None = None,
    max_definitions: int = 3,
) -> str:
    """Return the full source code of a symbol's definition — just the body.

    Use this INSTEAD of reading a whole file when you need to see how a
    function, struct, or macro is implemented. It jumps straight to the
    definition via the index and extracts only that definition's lines, so
    a one-screen function never costs you a 5000-line file read.

    Args:
        symbol: Exact symbol name, e.g. "tcp_v4_rcv".
        project_root: Project directory. Omit to use the server's default.
        max_definitions: If the symbol has multiple definitions, return at
            most this many bodies (default 3).
    """
    stdout, root, err = _raw_global(["-x", "--", symbol], project_root)
    if err:
        return err
    refs = [r for line in stdout.splitlines() if (r := _parse_cxref(line))]
    if not refs:
        return f"No definition found for symbol '{symbol}'."
    chunks: list[str] = []
    for _, lineno, path, _ in refs[:max_definitions]:
        body = _extract_body(root / path, lineno)
        chunks.append(f"=== {path}:{lineno} ===\n" + "\n".join(body))
    if len(refs) > max_definitions:
        chunks.append(
            f"... {len(refs) - max_definitions} more definition(s) not shown; "
            "use find_definition to list them all."
        )
    return "\n\n".join(chunks)


@mcp.tool()
def find_callers(
    symbol: str,
    project_root: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Find the FUNCTIONS that call a symbol, deduplicated, with call counts.

    Use this INSTEAD of find_references when you want the call graph rather
    than raw match lines: each reference site is mapped to its enclosing
    function, so 100 call sites inside one loop-heavy caller collapse to a
    single result line. This is the highest signal-to-noise view of "who
    uses this?" on a large codebase.

    Each result line has the format: caller-function  file  N call site(s) at lines ...

    Args:
        symbol: Exact symbol name whose callers you want.
        project_root: Project directory. Omit to use the server's default.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    stdout, root, err = _raw_global(["-rx", "--", symbol], project_root)
    if err:
        return err
    refs = [r for line in stdout.splitlines() if (r := _parse_cxref(line))]
    if not refs:
        return f"No references found for symbol '{symbol}'."

    by_file: dict[str, list[int]] = {}
    for _, lineno, path, _ in refs:
        by_file.setdefault(path, []).append(lineno)
    if len(by_file) > 500:
        return (
            f"'{symbol}' is referenced in {len(by_file)} files ({len(refs)} sites) — "
            "too broad for caller analysis. Use summarize_references to see the "
            "per-file distribution, then narrow down."
        )

    callers: dict[tuple[str, str], list[int]] = {}
    for path, ref_lines in by_file.items():
        defs_out, _, def_err = _raw_global(["-fx", "--", path], project_root)
        defs: list[tuple[int, str]] = []
        if defs_out and not def_err:
            defs = sorted(
                (d[1], d[0])
                for line in defs_out.splitlines()
                if (d := _parse_cxref(line))
            )
        for ref_line in sorted(ref_lines):
            enclosing = "(file scope)"
            for def_line, def_sym in defs:
                if def_line <= ref_line:
                    enclosing = def_sym
                else:
                    break
            callers.setdefault((enclosing, path), []).append(ref_line)

    rows = []
    for (caller, path), sites in sorted(
        callers.items(), key=lambda kv: (-len(kv[1]), kv[0])
    ):
        shown = ", ".join(str(n) for n in sites[:5])
        more = f", +{len(sites) - 5} more" if len(sites) > 5 else ""
        plural = "s" if len(sites) != 1 else ""
        rows.append(f"{caller}  {path}  {len(sites)} call site{plural} at line(s) {shown}{more}")
    return _paginate("\n".join(rows), limit, offset)


@mcp.tool()
def summarize_references(
    symbol: str,
    project_root: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """Per-file reference counts for a symbol — the cheapest wide view.

    Use this FIRST for very widely used symbols (thousands of references):
    it collapses the result to one line per file, sorted by count, so you
    can see where usage concentrates and then drill into a specific file
    with find_references or find_callers. Never floods the context window.

    Each result line has the format: count  file.

    Args:
        symbol: Exact symbol name.
        project_root: Project directory. Omit to use the server's default.
        limit: Maximum result lines to return (default 100).
        offset: Skip this many result lines (for pagination).
    """
    stdout, _, err = _raw_global(["-rx", "--", symbol], project_root)
    if err:
        return err
    refs = [r for line in stdout.splitlines() if (r := _parse_cxref(line))]
    if not refs:
        return f"No references found for symbol '{symbol}'."
    counts: dict[str, int] = {}
    for _, _, path, _ in refs:
        counts[path] = counts.get(path, 0) + 1
    rows = [
        f"{count:6d}  {path}"
        for path, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    header = f"{len(refs)} references across {len(counts)} files:"
    return header + "\n" + _paginate("\n".join(rows), limit, offset)


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
