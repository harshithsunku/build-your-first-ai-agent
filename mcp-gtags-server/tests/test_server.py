"""End-to-end tests for the gtags MCP tools against a tiny C project."""

import shutil
import textwrap

import pytest

from gtags_mcp import server

requires_global = pytest.mark.skipif(
    shutil.which("global") is None or shutil.which("gtags") is None,
    reason="GNU Global not installed",
)


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
def test_index_and_query_flow(c_project):
    root = str(c_project)

    result = server.index_project(root)
    assert "Indexed" in result
    assert (c_project / "GTAGS").is_file()

    definition = server.find_definition("add_numbers", root)
    assert "util.c" in definition

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
def test_update_index_picks_up_new_symbol(c_project):
    root = str(c_project)
    server.index_project(root)

    (c_project / "extra.c").write_text("int extra_fn(void) { return 42; }\n")
    result = server.update_index(root)
    assert "updated" in result

    definition = server.find_definition("extra_fn", root)
    assert "extra.c" in definition


@requires_global
def test_query_without_index_gives_helpful_error(tmp_path):
    result = server.find_definition("main", str(tmp_path))
    assert "index_project" in result


def test_bad_project_root():
    result = server.find_definition("main", "/nonexistent/path/xyz")
    assert result.startswith("Error")


@requires_global
def test_no_match_message(c_project):
    root = str(c_project)
    server.index_project(root)
    result = server.find_definition("does_not_exist_anywhere", root)
    assert "No definition found" in result
