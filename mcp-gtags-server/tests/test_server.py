"""End-to-end tests for the gtags MCP tools against a tiny C project."""

import shutil
import textwrap

import pytest

from gtags_mcp import server

requires_global = pytest.mark.skipif(
    shutil.which("global") is None or shutil.which("gtags") is None,
    reason="GNU Global not installed",
)

requires_pygments = pytest.mark.skipif(
    shutil.which("global") is None
    or shutil.which("gtags") is None
    or not server._plugin_deps_available(),
    reason="ctags + Pygments plugin parser not available",
)


def _drain_refresh_state():
    for thread in list(server._refresh_threads.values()):
        thread.join(timeout=30)
    server._last_update.clear()
    server._update_cost.clear()
    server._refresh_errors.clear()
    server._refresh_threads.clear()


@pytest.fixture(autouse=True)
def fresh_update_cache():
    """Isolate debounce/refresh state between tests."""
    _drain_refresh_state()
    yield
    _drain_refresh_state()


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
    """A new file becomes visible after the background refresh completes."""
    root = str(c_project)
    server.find_definition("add_numbers", root)  # builds index

    (c_project / "extra.c").write_text("int extra_fn(void) { return 42; }\n")
    server._last_update.clear()  # get past the debounce window

    server.find_definition("extra_fn", root)  # kicks background refresh
    server._wait_for_refresh(c_project.resolve())

    definition = server.find_definition("extra_fn", root)
    assert "extra.c" in definition


@requires_global
def test_query_never_blocks_on_refresh(c_project, monkeypatch):
    """Queries answer immediately even while a slow refresh runs behind."""
    import time as _time

    root = str(c_project)
    server.find_definition("add_numbers", root)  # builds index
    server._last_update.clear()  # force a refresh on the next query

    real_run = server._run

    def slow_update_run(args, cwd, timeout=server.QUERY_TIMEOUT_SECONDS):
        if args[:2] == ["global", "-u"]:
            _time.sleep(1.0)
        return real_run(args, cwd, timeout)

    monkeypatch.setattr(server, "_run", slow_update_run)

    t0 = _time.monotonic()
    result = server.find_definition("add_numbers", root)
    elapsed = _time.monotonic() - t0
    assert "util.c" in result
    assert elapsed < 0.5, f"query blocked on refresh ({elapsed:.2f}s)"
    server._wait_for_refresh(c_project.resolve())


@requires_global
def test_update_index_is_synchronous_barrier(c_project):
    root = str(c_project)
    server.find_definition("add_numbers", root)  # builds index

    (c_project / "fresh.c").write_text("int fresh_fn(void) { return 7; }\n")
    result = server.update_index(root)
    assert "synchronous" in result

    definition = server.find_definition("fresh_fn", root)
    assert "fresh.c" in definition


@requires_global
def test_background_refresh_error_surfaces(c_project, monkeypatch):
    root = str(c_project)
    server.find_definition("add_numbers", root)  # builds index
    server._last_update.clear()  # force a refresh on the next query

    real_run = server._run

    def failing_update_run(args, cwd, timeout=server.QUERY_TIMEOUT_SECONDS):
        if args[:2] == ["global", "-u"]:
            # Sleep so the kicking query returns before the failure is
            # recorded — the warning must surface on the NEXT query.
            __import__("time").sleep(0.3)
            return "", "simulated index corruption", 3
        return real_run(args, cwd, timeout)

    monkeypatch.setattr(server, "_run", failing_update_run)

    server.find_definition("add_numbers", root)  # kicks failing refresh
    server._wait_for_refresh(c_project.resolve())
    monkeypatch.setattr(server, "_run", real_run)
    server._last_update[c_project.resolve()] = __import__("time").monotonic()

    result = server.find_definition("add_numbers", root)
    assert "Warning: background index refresh failed" in result
    assert "simulated index corruption" in result


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


@requires_global
def test_get_symbol_body_returns_only_the_function(c_project):
    root = str(c_project)
    body = server.get_symbol_body("add_numbers", root)
    assert "=== util.c:3 ===" in body
    assert "return a + b;" in body
    # It must not leak the rest of the file or other files.
    assert "#include" not in body
    assert "printf" not in body


@requires_global
def test_get_symbol_body_multiline_macro(c_project):
    (c_project / "macros.h").write_text(
        "#define SQUARE(x) \\\n    ((x) * (x))\n\nint after_macro;\n"
    )
    body = server.get_symbol_body("SQUARE", str(c_project))
    assert "((x) * (x))" in body
    assert "after_macro" not in body


@requires_global
def test_find_callers_maps_refs_to_enclosing_function(c_project):
    root = str(c_project)
    result = server.find_callers("add_numbers", root)
    # gtags also counts the util.h prototype as a reference; the call from
    # main() must be attributed to the enclosing function `main`.
    assert "main  main.c  1 call site at line(s) 7" in result


@requires_global
def test_summarize_references(c_project):
    root = str(c_project)
    result = server.summarize_references("add_numbers", root)
    assert "2 references across 2 files:" in result
    assert "main.c" in result and "util.h" in result


CHAIN_C = """\
#include "util.h"
int level1(void) { return add_numbers(1, 2); }
int level2(void) { return level1(); }
int level3(void) { return level2(); }
int rec_fn(int n) { return n <= 0 ? 0 : rec_fn(n - 1); }
"""


@requires_global
def test_call_hierarchy_multi_level(c_project):
    (c_project / "chain.c").write_text(CHAIN_C)
    root = str(c_project)

    deep = server.call_hierarchy("add_numbers", root, depth=3)
    assert deep.startswith("add_numbers  (definition: util.c:3)")
    assert "level1" in deep and "level2" in deep and "level3" in deep
    # level2 is one level deeper than level1 in the rendered tree
    l1 = next(l for l in deep.splitlines() if "level1" in l)
    l2 = next(l for l in deep.splitlines() if "level2" in l)
    assert len(l2) - len(l2.lstrip("│ ")) > len(l1) - len(l1.lstrip("│ "))

    shallow = server.call_hierarchy("add_numbers", root, depth=1)
    assert "level1" in shallow and "level2" not in shallow


@requires_global
def test_call_hierarchy_handles_recursion(c_project):
    (c_project / "chain.c").write_text(CHAIN_C)
    result = server.call_hierarchy("rec_fn", str(c_project), depth=3)
    assert "(recursive)" in result


@requires_global
def test_find_callees(c_project):
    root = str(c_project)
    result = server.find_callees("main", root)
    assert "add_numbers  util.c:3" in result
    assert "External/unresolved: printf" in result


@requires_global
def test_symbol_info(c_project):
    root = str(c_project)
    result = server.symbol_info("add_numbers", root)
    assert "defined at util.c:3" in result
    assert "referenced 2 time(s) across 2 file(s)" in result
    assert "next: get_symbol_body" in result


@requires_global
def test_project_overview(c_project):
    result = server.project_overview(str(c_project))
    assert "3 indexed source files" in result
    assert ".c (2)" in result and ".h (1)" in result


@requires_global
def test_find_dead_symbols(c_project):
    (c_project / "dead.c").write_text(
        '#include "util.h"\n'
        "int dead_fn(void) { return 0; }\n"
        "int live_fn(void) { return add_numbers(1, 1); }\n"
        "int caller_of_live(void) { return live_fn(); }\n"
    )
    result = server.find_dead_symbols("dead.c", str(c_project))
    assert "dead_fn" in result
    assert "live_fn  " not in result  # live_fn is referenced by caller_of_live


@requires_global
def test_find_includers(c_project):
    result = server.find_includers("util.h", str(c_project))
    assert "main.c" in result and "util.c" in result


@pytest.fixture
def mixed_project(c_project):
    (c_project / "pylib.py").write_text(
        textwrap.dedent(
            """\
            def py_util(a, b):
                total = a + b
                return total


            def unrelated():
                return 42
            """
        )
    )
    (c_project / "app.py").write_text(
        textwrap.dedent(
            """\
            from pylib import py_util


            def run_app():
                return py_util(2, 3)
            """
        )
    )
    return c_project


@requires_pygments
def test_mixed_project_python_definition(mixed_project):
    root = str(mixed_project)
    result = server.find_definition("py_util", root)
    assert "pylib.py" in result


@requires_pygments
def test_mixed_project_python_references(mixed_project):
    root = str(mixed_project)
    result = server.find_references("py_util", root)
    assert "app.py" in result


@requires_pygments
def test_mixed_project_c_still_works(mixed_project):
    root = str(mixed_project)
    result = server.find_definition("add_numbers", root)
    assert "util.c" in result


@requires_pygments
def test_python_body_extraction(mixed_project):
    root = str(mixed_project)
    body = server.get_symbol_body("py_util", root)
    assert "def py_util(a, b):" in body
    assert "return total" in body
    assert "unrelated" not in body  # indentation-delimited: next def excluded


@requires_pygments
def test_python_callees(mixed_project):
    root = str(mixed_project)
    result = server.find_callees("run_app", root)
    assert "py_util  pylib.py:1" in result


@requires_pygments
def test_index_reports_multilanguage_label(mixed_project):
    result = server.index_project(str(mixed_project))
    assert "native-pygments" in result


def test_bad_project_root():
    result = server.find_definition("main", "/nonexistent/path/xyz")
    assert result.startswith("Error")


@requires_global
def test_no_match_message(c_project):
    root = str(c_project)
    result = server.find_definition("does_not_exist_anywhere", root)
    assert "No definition found" in result
