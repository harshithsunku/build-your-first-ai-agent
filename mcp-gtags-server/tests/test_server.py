"""End-to-end tests for the gtags MCP tools against a tiny C project."""

import shutil
import textwrap

import pytest

from gtags_mcp import server

requires_global = pytest.mark.skipif(
    shutil.which("global") is None or shutil.which("gtags") is None,
    reason="GNU Global not installed",
)


@pytest.fixture(autouse=True)
def fresh_update_cache():
    """Isolate the per-root update debounce between tests."""
    server._last_update.clear()
    yield
    server._last_update.clear()


@pytest.fixture
def c_project(tmp_path):
    (tmp_path / "util.h").write_text(
        textwrap.dedent(
            """\
            #ifndef UTIL_H
            #define UTIL_H
            int add_numbers(int a, int b);
            #endif
            """
        )
    )
    (tmp_path / "util.c").write_text(
        textwrap.dedent(
            """\
            #include "util.h"

            int add_numbers(int a, int b)
            {
                return a + b;
            }
            """
        )
    )
    (tmp_path / "main.c").write_text(
        textwrap.dedent(
            """\
            #include <stdio.h>
            #include "util.h"

            int main(void)
            {
                /* TODO: handle argv */
                printf("%d\\n", add_numbers(2, 3));
                return 0;
            }
            """
        )
    )
    return tmp_path


@requires_global
def test_auto_index_on_first_query(c_project):
    """Queries build the index themselves — no index_project call needed."""
    root = str(c_project)
    assert not (c_project / "GTAGS").exists()

    definition = server.find_definition("add_numbers", root)
    assert "util.c" in definition
    assert (c_project / "GTAGS").is_file()


@requires_global
def test_query_flow(c_project):
    root = str(c_project)

    references = server.find_references("add_numbers", root)
    assert "main.c" in references

    symbols = server.list_file_symbols("util.c", root)
    assert "add_numbers" in symbols

    completions = server.complete_symbol("add_", root)
    assert "add_numbers" in completions

    grep = server.grep_project("TODO", root)
    assert "main.c" in grep

    files = server.find_files(r"util\.c$", root)
    assert "util.c" in files

    usages = server.find_symbol_usages("printf", root)
    assert "main.c" in usages


@requires_global
def test_default_root_is_cwd(c_project, monkeypatch):
    monkeypatch.chdir(c_project)
    definition = server.find_definition("add_numbers")
    assert "util.c" in definition


@requires_global
def test_auto_update_picks_up_new_symbol(c_project):
    """A new file is visible on the next query without any explicit update."""
    root = str(c_project)
    server.find_definition("add_numbers", root)  # builds index

    (c_project / "extra.c").write_text("int extra_fn(void) { return 42; }\n")
    server._last_update.clear()  # get past the debounce window

    definition = server.find_definition("extra_fn", root)
    assert "extra.c" in definition


@requires_global
def test_explicit_index_and_update_tools(c_project):
    root = str(c_project)
    assert "Indexed" in server.index_project(root)

    (c_project / "extra.c").write_text("int extra_fn(void) { return 42; }\n")
    assert "updated" in server.update_index(root)
    assert "extra.c" in server.find_definition("extra_fn", root)


@requires_global
def test_pagination(c_project):
    root = str(c_project)
    # 4 symbols total across the project: UTIL_H, add_numbers (x2 via -c? no)
    # Use grep for a predictable multi-line result: every line containing 'int'.
    full = server.grep_project("int", root, limit=100)
    total = len(full.splitlines())
    assert total >= 3

    page = server.grep_project("int", root, limit=2)
    assert f"showing 1-2 of {total} matches" in page
    assert "pass offset=2 to continue" in page

    page2 = server.grep_project("int", root, limit=2, offset=2)
    assert f"showing 3-{min(4, total)} of {total} matches" in page2

    past_end = server.grep_project("int", root, offset=999)
    assert "past the last" in past_end


@requires_global
def test_case_insensitive(c_project):
    root = str(c_project)
    assert "No definition found" in server.find_definition("ADD_NUMBERS", root)
    result = server.find_definition("ADD_NUMBERS", root, case_insensitive=True)
    assert "util.c" in result


@requires_global
def test_long_lines_are_truncated(c_project):
    root = str(c_project)
    long_line = "int long_named_fn(void) { return 0; } /* " + "x" * 500 + " */\n"
    (c_project / "long.c").write_text(long_line)

    result = server.find_definition("long_named_fn", root)
    assert "long.c" in result
    assert all(len(line) <= server.MAX_LINE_CHARS + 4 for line in result.splitlines())


def test_bad_project_root():
    result = server.find_definition("main", "/nonexistent/path/xyz")
    assert result.startswith("Error")


@requires_global
def test_no_match_message(c_project):
    root = str(c_project)
    result = server.find_definition("does_not_exist_anywhere", root)
    assert "No definition found" in result
