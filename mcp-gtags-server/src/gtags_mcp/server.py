"""MCP server that wraps GNU Global (gtags) for C/C++ code navigation.

Exposes tools to index a codebase and query it for symbol definitions,
references, grep matches, per-file symbols, and completions. All tools run
the ``gtags`` / ``global`` binaries via subprocess, so GNU Global must be
installed and on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gtags")

# Cap tool output so a broad query can't blow up the model's context window.
MAX_RESULT_LINES = 200
COMMAND_TIMEOUT_SECONDS = 120


def _check_global_installed() -> str | None:
    if shutil.which("global") is None or shutil.which("gtags") is None:
        return (
            "Error: GNU Global is not installed or not on PATH. "
            "Install it first (e.g. `apt install global`, `brew install global`)."
        )
    return None


def _resolve_root(project_root: str) -> tuple[Path | None, str | None]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        return None, f"Error: project_root is not a directory: {project_root}"
    return root, None


def _run(args: list[str], cwd: Path) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, returncode)."""
    proc = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    return proc.stdout, proc.stderr, proc.returncode


def _truncate(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= MAX_RESULT_LINES:
        return text
    kept = "\n".join(lines[:MAX_RESULT_LINES])
    return (
        f"{kept}\n... truncated: showing {MAX_RESULT_LINES} of {len(lines)} lines. "
        "Narrow the query to see the rest."
    )


def _query_global(flags: list[str], project_root: str, empty_message: str) -> str:
    """Shared plumbing for all read-only `global` queries."""
    if err := _check_global_installed():
        return err
    root, err = _resolve_root(project_root)
    if err:
        return err
    if not (root / "GTAGS").is_file():
        return (
            f"Error: no GTAGS index found in {root}. "
            "Run the index_project tool first."
        )
    stdout, stderr, code = _run(["global", *flags], cwd=root)
    # `global` exits non-zero both for real errors and for "no match found";
    # only the former writes to stderr.
    if code != 0 and stderr.strip():
        return f"Error: global exited with code {code}: {stderr.strip()}"
    if not stdout.strip():
        return empty_message
    return _truncate(stdout.rstrip())


@mcp.tool()
def index_project(project_root: str) -> str:
    """Build (or rebuild) the gtags index for a C/C++ project.

    Creates GTAGS/GRTAGS/GPATH files in the project root. Run this once
    before any query tool, and rerun it after large-scale changes.

    Args:
        project_root: Absolute path to the root of the C/C++ source tree.
    """
    if err := _check_global_installed():
        return err
    root, err = _resolve_root(project_root)
    if err:
        return err
    stdout, stderr, code = _run(["gtags"], cwd=root)
    if code != 0:
        return f"Error: gtags exited with code {code}: {stderr.strip() or stdout.strip()}"
    return f"Indexed {root} (GTAGS, GRTAGS, GPATH created)."


@mcp.tool()
def update_index(project_root: str) -> str:
    """Incrementally update an existing gtags index after files changed.

    Much faster than a full reindex; only modified files are rescanned.

    Args:
        project_root: Absolute path to the indexed project root.
    """
    if err := _check_global_installed():
        return err
    root, err = _resolve_root(project_root)
    if err:
        return err
    if not (root / "GTAGS").is_file():
        return f"Error: no GTAGS index found in {root}. Run index_project first."
    stdout, stderr, code = _run(["global", "-u"], cwd=root)
    if code != 0:
        return f"Error: global -u exited with code {code}: {stderr.strip()}"
    return f"Index updated for {root}."


@mcp.tool()
def find_definition(symbol: str, project_root: str) -> str:
    """Find where a symbol (function, struct, macro, typedef...) is defined.

    Each result line has the format: symbol line-number file source-line.

    Args:
        symbol: Exact symbol name, e.g. "main" or "list_head".
        project_root: Absolute path to the indexed project root.
    """
    return _query_global(
        ["-x", "--", symbol],
        project_root,
        f"No definition found for symbol '{symbol}'.",
    )


@mcp.tool()
def find_references(symbol: str, project_root: str) -> str:
    """Find all places that reference (call/use) a defined symbol.

    Each result line has the format: symbol line-number file source-line.

    Args:
        symbol: Exact symbol name whose call/usage sites you want.
        project_root: Absolute path to the indexed project root.
    """
    return _query_global(
        ["-rx", "--", symbol],
        project_root,
        f"No references found for symbol '{symbol}'.",
    )


@mcp.tool()
def find_symbol_usages(symbol: str, project_root: str) -> str:
    """Find usages of symbols that have no definition in the project.

    Useful for locating uses of external/library identifiers (e.g. printf)
    or variables that gtags did not record as definitions.

    Args:
        symbol: Exact symbol name.
        project_root: Absolute path to the indexed project root.
    """
    return _query_global(
        ["-sx", "--", symbol],
        project_root,
        f"No usages found for undefined symbol '{symbol}'.",
    )


@mcp.tool()
def grep_project(pattern: str, project_root: str) -> str:
    """Grep all indexed source files for a regex pattern.

    Slower than the symbol tools but matches arbitrary text, not just
    symbol names. Uses POSIX extended regex syntax.

    Args:
        pattern: Regex to search for, e.g. "TODO|FIXME".
        project_root: Absolute path to the indexed project root.
    """
    return _query_global(
        ["-gx", "--", pattern],
        project_root,
        f"No matches for pattern '{pattern}'.",
    )


@mcp.tool()
def list_file_symbols(file_path: str, project_root: str) -> str:
    """List all symbols defined in one source file.

    Each result line has the format: symbol line-number file source-line.

    Args:
        file_path: Path to the source file, relative to project_root or absolute.
        project_root: Absolute path to the indexed project root.
    """
    return _query_global(
        ["-fx", "--", file_path],
        project_root,
        f"No symbols found in '{file_path}' (is it inside the indexed tree?).",
    )


@mcp.tool()
def complete_symbol(prefix: str, project_root: str) -> str:
    """List defined symbols that start with the given prefix.

    Handy when you know roughly what a function is called but not its
    exact name.

    Args:
        prefix: Symbol name prefix, e.g. "xdr_" or "init".
        project_root: Absolute path to the indexed project root.
    """
    return _query_global(
        ["-c", "--", prefix],
        project_root,
        f"No symbols starting with '{prefix}'.",
    )


@mcp.tool()
def find_files(pattern: str, project_root: str) -> str:
    """Find indexed source files whose path matches a regex pattern.

    Args:
        pattern: Regex matched against file paths, e.g. "net/.*\\.c$".
        project_root: Absolute path to the indexed project root.
    """
    return _query_global(
        ["-P", "--", pattern],
        project_root,
        f"No indexed files match '{pattern}'.",
    )


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
