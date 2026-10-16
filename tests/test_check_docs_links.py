"""Deterministic documentation checks: links, anchors, fences, commands (#353; shared with pycubrid)."""

from __future__ import annotations

import importlib.util
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "check_docs_links", ROOT / "scripts/check_docs_links.py"
)
assert _SPEC is not None and _SPEC.loader is not None
check = importlib.util.module_from_spec(_SPEC)
sys.modules["check_docs_links"] = check
_SPEC.loader.exec_module(check)

# check_docs_links imports the shared parser; reuse that module.
_markdown = sys.modules["_markdown"]
github_slug, make_goals, parse = _markdown.github_slug, _markdown.make_goals, _markdown.parse
# The site slugifier this repository's mkdocs.yml configures (#388).
REPO_SITE_SLUG = _markdown.default_site_slug

TARGET = """# Target

## Connection options {#options}

<a id="legacy-anchor"></a>

## 한글 제목

## Same

## Same
"""


def _tree(tmp_path: Path, page: str, extra: dict[str, str] | None = None) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/tool.py").write_text("", encoding="utf-8")
    (tmp_path / "Makefile").write_text("test:\n\tpytest\nlint:\n\truff\n", encoding="utf-8")
    (tmp_path / "docs/TARGET.md").write_text(TARGET, encoding="utf-8")
    (tmp_path / "docs/PAGE.md").write_text(page, encoding="utf-8")
    for name, text in (extra or {}).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_repository_documentation_has_no_deterministic_defects() -> None:
    assert check.run(ROOT) == []


def test_valid_relative_links_and_anchors_pass(tmp_path: Path) -> None:
    page = (
        "# Page\n\n[t](TARGET.md), [o](TARGET.md#options), [a](TARGET.md#legacy-anchor),\n"
        "[k](TARGET.md#한글-제목), [d](TARGET.md#same-1), [s](TARGET.md#same_1),\n"
        '[self](#page), [dir](../docs/), [img](TARGET.md "title") and ![i](TARGET.md).\n'
    )
    assert check.run(_tree(tmp_path, page)) == []


def test_external_links_are_not_fetched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the documentation check must not open a connection")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    page = "[x](https://unreachable.invalid/page) [m](mailto:a@b.invalid) [h](http://x.invalid)\n"
    assert check.run(_tree(tmp_path, page)) == []


def test_broken_relative_link_fails_with_location_and_suggestion(tmp_path: Path) -> None:
    root = _tree(tmp_path, "# Page\n\nSee [the target](TARGTE.md).\n")
    assert check.run(root) == [
        "docs/PAGE.md:3: link target 'TARGTE.md' does not exist; did you mean 'TARGET.md'?"
    ]


def test_deleted_reference_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, "# Page\n\nSee [the target](TARGET.md#options).\n")
    assert check.run(root) == []
    (root / "docs/TARGET.md").unlink()
    assert check.run(root) == ["docs/PAGE.md:3: link target 'TARGET.md#options' does not exist"]


def test_invalid_anchor_fails_with_suggestion(tmp_path: Path) -> None:
    root = _tree(tmp_path, "# Page\n\nSee [options](TARGET.md#option) and [x](#nowhere).\n")
    assert check.run(root) == [
        "docs/PAGE.md:3: anchor #nowhere is not a heading or anchor of docs/PAGE.md",
        (
            "docs/PAGE.md:3: anchor #option is not a heading or anchor of docs/TARGET.md; "
            + "did you mean 'options'?"
        ),
    ]


def test_absolute_and_escaping_paths_fail(tmp_path: Path) -> None:
    root = _tree(tmp_path, "[a](/docs/TARGET.md) and [b](../../outside.md)\n")
    assert check.run(root) == [
        "docs/PAGE.md:1: link target '../../outside.md' points outside the repository",
        (
            "docs/PAGE.md:1: link target '/docs/TARGET.md' is absolute; use a path relative to "
            + "the file"
        ),
    ]


def test_reference_links_and_definitions(tmp_path: Path) -> None:
    page = (
        "# Page\n\nSee [ok][t], [bad][gone] and [x][missing].\n\n"
        "[t]: TARGET.md#options\n[gone]: GONE.md\n[unused]: ALSO_GONE.md\n"
    )
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:3: link target 'GONE.md' does not exist",
        "docs/PAGE.md:3: reference [missing] has no definition",
        "docs/PAGE.md:6: link target 'GONE.md' does not exist",
        "docs/PAGE.md:7: link target 'ALSO_GONE.md' does not exist",
    ]


def test_links_in_code_are_examples(tmp_path: Path) -> None:
    page = (
        "`[a](GONE.md)` and ``[b](GONE.md) with ` inside``\n\n"
        "```md\n[c](GONE.md)\n```\n\n~~~\n[d](GONE.md)\n~~~\n\n"
        "````\n```\n[e](GONE.md)\n```\n````\n"
    )
    assert check.run(_tree(tmp_path, page)) == []


@pytest.mark.parametrize(
    ("page", "line"),
    [("# Page\n\n```bash\nmake test\n", 3), ("~~~\nx\n```\n", 1), ("````\nx\n```\n", 1)],
)
def test_unclosed_fence_fails(tmp_path: Path, page: str, line: int) -> None:
    assert check.run(_tree(tmp_path, page)) == [f"docs/PAGE.md:{line}: code fence is never closed"]


def test_closed_fences_pass(tmp_path: Path) -> None:
    page = (
        "```\nx\n```\n\n~~~~\n~~~\n~~~~\n\n> ~~~\n> quoted\n> ~~~\n\n"
        "- item\n\n  ```bash\n  make test\n  ```\n\n```\nlast\n```\n"
    )
    assert check.run(_tree(tmp_path, page)) == []


@pytest.mark.parametrize("closing", ["> ~~~", "    ~~~"])
def test_a_quoted_or_over_indented_line_does_not_close_a_fence(
    tmp_path: Path, closing: str
) -> None:
    page = f"~~~\nx\n{closing}\n"
    assert check.run(_tree(tmp_path, page)) == ["docs/PAGE.md:1: code fence is never closed"]


@pytest.mark.parametrize(
    ("page", "line"),
    [
        ("> ~~~\n> text\n\nAfter the quote.\n", 1),
        ("- item\n\n  ```\n  code\n\nnot indented\n", 3),
    ],
)
def test_unclosed_fence_inside_a_container_fails(tmp_path: Path, page: str, line: int) -> None:
    assert check.run(_tree(tmp_path, page)) == [f"docs/PAGE.md:{line}: code fence is never closed"]


def test_commands_are_checked_only_in_code(tmp_path: Path) -> None:
    page = (
        "Make sure to make good use of it.\n\n"
        "Run `make test lnit` then:\n\n```bash\nmake -j2 lint && make tset\n"
        "python scripts/tool.py && python scripts/gone.py\n```\n"
    )
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:3: `make lnit` is not a Makefile target; did you mean 'lint'?",
        "docs/PAGE.md:6: `make tset` is not a Makefile target; did you mean 'test'?",
        # A command's script is looked up like other recipe files (cookbook #353).
        "docs/PAGE.md:7: `python scripts/gone.py`: scripts/gone.py does not exist next to this "
        "file, at the repository root or in a directory it cds into",
    ]


def test_release_history_keeps_old_commands(tmp_path: Path) -> None:
    history = "# Changelog\n\n- Removed `make release` and scripts/check_version.py.\n"
    root = _tree(tmp_path, "# Page\n", {"CHANGELOG.md": history})
    assert check.run(root) == []
    (root / "CHANGELOG.md").write_text(history + "\nSee [gone](GONE.md).\n", encoding="utf-8")
    assert check.run(root) == ["CHANGELOG.md:5: link target 'GONE.md' does not exist"]


def test_literal_brackets_are_not_references(tmp_path: Path) -> None:
    page = (
        "Escaped \\[text\\]\\[label\\], an index rows[0][1], a closing ][label] alone,\n"
        "`[x][y]` in code and a defined [link][t].\n\n[t]: TARGET.md\n"
    )
    assert check.run(_tree(tmp_path, page)) == []


def test_html_link_and_image_targets_are_checked(tmp_path: Path) -> None:
    page = (
        '<p align="center"><img src="demo.gif" alt="Demo"></p>\n\n'
        'Inline <a href="TARGET.md#options">options</a> and <img src="dem0.gif">.\n\n'
        '<!-- <img src="commented.gif"> -->\n\n`<img src="code.gif">`\n'
    )
    root = _tree(tmp_path, page, {"docs/demo.gif": ""})
    assert check.run(root) == [
        "docs/PAGE.md:3: link target 'dem0.gif' does not exist; did you mean 'demo.gif'?"
    ]


@pytest.mark.parametrize(
    "first",
    [
        'Inline <a\nhref="https://example.invalid">x</a>',
        '[t](TARGET.md "a\nb") then',
        '![i](TARGET.md "a\nb") then',
    ],
)
def test_lines_after_multi_line_tags_and_titles_are_exact(tmp_path: Path, first: str) -> None:
    # Both occurrences keep their own line: the first spans n + 1 lines.
    page = f"{first}\n[bad](GONE.md)\n\n{first}\n[bad2](GONE2.md)\n"
    n = first.count("\n")
    assert check.run(_tree(tmp_path, page)) == [
        f"docs/PAGE.md:{n + 2}: link target 'GONE.md' does not exist",
        f"docs/PAGE.md:{2 * n + 5}: link target 'GONE2.md' does not exist",
    ]


@pytest.mark.parametrize("use", ["[ok][r]", "![ok][r]"])
def test_reference_titles_add_no_lines_at_the_use_site(tmp_path: Path, use: str) -> None:
    page = f'{use}\n[bad](GONE.md)\n\n{use} [bad2](GONE2.md)\n\n[r]: TARGET.md "a\nb\nc"\n'
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:2: link target 'GONE.md' does not exist",
        "docs/PAGE.md:4: link target 'GONE2.md' does not exist",
    ]


def test_a_malformed_link_tail_does_not_hide_later_references(tmp_path: Path) -> None:
    page = "[example]( and [broken][missing]\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:1: reference [missing] has no definition"
    ]


def test_an_angle_bracket_destination_keeps_its_title_masked(tmp_path: Path) -> None:
    page = '[site](<https://example.invalid/> "See ) [foo][bar]")\n'
    assert check.run(_tree(tmp_path, page)) == []


@pytest.mark.parametrize(
    "block",
    [
        "echo \\\\\nmake removed",  # an escaped backslash: two commands
        "echo x\\  \nmake removed",  # a backslash before spaces does not continue
        "echo 'a\\\nb'\nmake removed",  # a backslash in single quotes is literal
    ],
)
def test_only_a_real_continuation_joins_lines(tmp_path: Path, block: str) -> None:
    page = f"```bash\n{block}\n```\n"
    findings = check.run(_tree(tmp_path, page))
    assert [p.split(": ", 1)[1] for p in findings] == ["`make removed` is not a Makefile target"]


def test_grouped_and_double_colon_make_rules_declare_every_target(tmp_path: Path) -> None:
    root = _tree(tmp_path, "Run `make check-docs`, `make alpha beta` and `make again`.\n")
    (root / "Makefile").write_text(
        "check-docs alpha: ## grouped\n\ttrue\nbeta again::\n\ttrue\n"
        "var := x\nother ?= y\nlate ::= z\n\tnot-a-rule: z\n",
        encoding="utf-8",
    )
    assert check.run(root) == []
    (root / "docs/PAGE.md").write_text(
        "Run `make var`, `make late` and `make not-a-rule`.\n", encoding="utf-8"
    )
    assert [p.split(": ", 1)[1] for p in check.run(root)] == [
        "`make late` is not a Makefile target",
        "`make not-a-rule` is not a Makefile target",
        "`make var` is not a Makefile target",
    ]


def test_an_apostrophe_in_a_destination_does_not_open_a_title(tmp_path: Path) -> None:
    page = "[site](https://example.invalid/it's) and [broken][missing]\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:1: reference [missing] has no definition"
    ]


def test_a_word_split_across_a_continuation_is_one_word(tmp_path: Path) -> None:
    assert check.run(_tree(tmp_path, "```bash\nmake te\\\nst\n```\n")) == []
    (tmp_path / "split").mkdir()
    assert check.run(_tree(tmp_path / "split", "```bash\nmake te\\\n st\n```\n")) == [
        "docs/PAGE.md:2: `make st` is not a Makefile target",
        "docs/PAGE.md:2: `make te` is not a Makefile target",
    ]


@pytest.mark.parametrize(
    ("command", "goals"),
    [
        ("make test;>log make lint", ["test", "lint"]),
        ("echo ok;>log make removed", ["removed"]),
        ("make a&&make b", ["a", "b"]),
        ("make test &>log", ["test"]),
        ("make test &>>build.log", ["test"]),
        # Substitutions are part of their word; their bodies are commands of their own.
        ("make test ENV_FILE=<(true)", ["test"]),
        ("make test >(tee log)", ["test"]),
        ("make VAR=$(pwd) test", ["test"]),
        ("diff <(make -n removed) b", ["removed"]),
        ("make A=\"$(printf ')')\" test", ["test"]),
        ("make $(echo unbalanced", []),
        # A case pattern's ")" does not close the substitution.
        ("make test VAR=$(case x in x) printf y;; esac)", ["test"]),
        ("make test VAR=$(case x in (x) printf y;; esac)", ["test"]),
        # Substitutions run inside double quotes too, not inside single quotes.
        ('echo "$(make removed)"', ["removed"]),
        ('echo "a $(printf "%s" "$(make nested)") b"', ["nested"]),
        ("echo '$(make literal)'", []),
        ('echo "\\$(make escaped)"', []),
        # Text that is not shell names no goal, not even from its substitutions.
        ('echo $(make removed) "unclosed', []),
        ("echo $(make removed) $(unclosed", []),
        # Arithmetic expansion runs no command, only the substitutions nested in it.
        ('make=4; removed=1; echo "$((make - removed))"', []),
        ("echo $(( $(make removed) + 1 ))", ["removed"]),
        # case and esac are keywords only at the start of a command.
        ("make removed VAR=$(printf case)", ["removed"]),
        ("make test VAR=$(case x in x) printf esac;; y) printf y;; esac)", ["test"]),
        # An unquoted newline in a substitution body separates commands.
        ('echo "$(\nmake test\nmake lint\n)"', ["test", "lint"]),
        ("echo $(\n# a comment\nmake x\n)", ["x"]),
        # case is a variable name inside arithmetic, and esac closes an empty case.
        ("case=0; make removed N=$((case + 1))", ["removed"]),
        ("make removed N=$(case x in esac)", ["removed"]),
        ("make test VAR=$(case x in (x) printf esac;; esac)", ["test"]),
        ("make a N=$(case x in case) make b;; esac)", ["a", "b"]),
        # A quoted subject is one word; esac is a pattern after ( or |.
        ('make test N=$(case "x" in x) printf y;; esac)', ["test"]),
        ("echo \"$(case 'x' in x) make removed;; esac)\"", ["removed"]),
        ("make N=$(case esac in (esac) printf y;; esac) removed", ["removed"]),
        ("make N=$(case esac in x|esac) printf y;; esac) removed", ["removed"]),
    ],
)
def test_adjacent_shell_operators_are_separate(command: str, goals: list[str]) -> None:
    assert make_goals(command) == goals


@pytest.mark.parametrize(
    "first",
    ['[t](TARGET.md "a &amp;\nb") then', '![i](TARGET.md "a \\" q\nb") then'],
)
def test_decoded_inline_titles_still_count_their_lines(tmp_path: Path, first: str) -> None:
    # Both occurrences keep their own line: the first spans n + 1 lines.
    page = f"{first}\n[bad](GONE.md)\n\n{first}\n[bad2](GONE2.md)\n"
    n = first.count("\n")
    assert check.run(_tree(tmp_path, page)) == [
        f"docs/PAGE.md:{n + 2}: link target 'GONE.md' does not exist",
        f"docs/PAGE.md:{2 * n + 5}: link target 'GONE2.md' does not exist",
    ]


def test_a_backslash_in_a_comment_does_not_continue(tmp_path: Path) -> None:
    page = "```bash\necho ok # note \\\nmake removed\necho 'a # b\\\nc'\n```\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:3: `make removed` is not a Makefile target"
    ]


def test_an_entity_newline_in_a_title_adds_no_line(tmp_path: Path) -> None:
    page = '[t](TARGET.md "a&#10;b")\n[bad](GONE.md)\n'
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:2: link target 'GONE.md' does not exist"
    ]


def test_an_inline_title_equal_to_a_definition_title_still_counts(tmp_path: Path) -> None:
    page = '[t](TARGET.md "a &amp;\nb") then\n[bad](GONE.md)\n\n[r]: TARGET.md "a &\nb"\n'
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:3: link target 'GONE.md' does not exist"
    ]


def test_a_link_like_fragment_in_a_comment_does_not_hide_references(tmp_path: Path) -> None:
    page = "Inline <!-- [x](https://example.invalid/-->[broken][missing])\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:1: reference [missing] has no definition"
    ]


def test_a_make_line_inside_a_multi_line_quote_is_not_a_command(tmp_path: Path) -> None:
    page = "```bash\necho 'a\\\nmake removed\nb'\nmake gone\n```\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:5: `make gone` is not a Makefile target"
    ]


def test_a_quote_never_closed_in_a_block_is_not_shell(tmp_path: Path) -> None:
    page = "```text\nDon't run\nmake removed\n```\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:3: `make removed` is not a Makefile target"
    ]


def test_a_docs_line_starting_with_an_issue_number_is_reported(tmp_path: Path) -> None:
    page = (
        "# Page\n\nWrapped text that ends here and\n#750 starts the next line.\n\n"
        "Escaped:\n\\#751 is text.\n\n## 12 a numbered heading\n\n"
        "```\n#752 in code\n```\n\n`#753` inline\n"
    )
    root = _tree(tmp_path, page, {"notes/README.md": "Text and\n#755 not on the site.\n"})
    assert check.run(root) == [
        "docs/PAGE.md:4: line starts with '#<digit>', which the MkDocs site renders as a "
        + "heading; escape it as '\\#'"
    ]


@pytest.mark.parametrize(
    ("page", "lines"),
    [
        ("- #655 adapters\n- \\#656 escaped\n", [1]),
        ("- a\n#657 lazy\n", [2]),
        ("- a\n  #658 indented continuation is text\n", []),
        ("- a\n\n    #659 later paragraph of the item\n", [3]),
        ("- a\n    - #660 nested item\n", [2]),
        ("1. #661 numbered\n\n1) #662 not a Python-Markdown list\n", [1]),
        ("> quoted\n> #663 line\n\n>  #664 two spaces is text\n", [2]),
        ("Text\n  #665 indented is text\n", []),
        (" > #666 one\n\n  > #667 two\n\n   > #668 three spaces before >\n", [1, 3, 5]),
        ("> a\n  > #669 indented marker on a continuation line\n", [2]),
        # The site renders this line as a heading and the comment delimiters as text.
        ("Text <!--\n#670 inside an inline comment\n--> tail\n", [2]),
        # A block quote inside a list item (cubrid-lab/sqlalchemy-cubrid#925); two spaces after ">" stay text.
        ("- > #750 issue\n\n1. > #751 numbered\n\n- >  #752 text\n", [1, 3]),
        ("- a\n\n    > #753 later paragraph\n    > #754 next\n", [3, 4]),
        ("> - > #755 nested both ways\n", [1]),
        ("- a\n\n  > #756 quote after a two-space indent\n", [3]),
    ],
)
def test_issue_number_lines_are_reported_where_the_site_makes_headings(
    tmp_path: Path, page: str, lines: list[int]
) -> None:
    message = (
        "line starts with '#<digit>', which the MkDocs site renders as a heading; "
        "escape it as '\\#'"
    )
    assert check.run(_tree(tmp_path, page)) == [f"docs/PAGE.md:{n}: {message}" for n in lines]


def test_a_quote_after_an_empty_destination_is_not_a_link(tmp_path: Path) -> None:
    # CommonMark reads `"See` as a bare destination; no `)` follows, so this is
    # not a link and `[foo][bar]` is literal text without a definition (cubrid-lab/sqlalchemy-cubrid#923).
    page = '[site]( "See [foo][bar]")\n'
    assert check.run(_tree(tmp_path, page)) == ["docs/PAGE.md:1: reference [bar] has no definition"]


def test_an_escaped_space_keeps_a_hash_inside_the_word(tmp_path: Path) -> None:
    page = "```bash\necho x\\ #note \\\nmake removed\nmake gone\n```\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:4: `make gone` is not a Makefile target"
    ]


@pytest.mark.parametrize("use", ["[r][ref]", "[ref]", "![r][ref]"])
def test_a_reference_does_not_take_an_equal_inline_title(tmp_path: Path, use: str) -> None:
    page = (
        f'{use} [bad](GONE.md)\n[t](TARGET.md "a\nb")\n[bad2](GONE2.md)\n\n'
        '[ref]: TARGET.md "a\nb"\n'
    )
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:1: link target 'GONE.md' does not exist",
        "docs/PAGE.md:4: link target 'GONE2.md' does not exist",
    ]


def test_a_reference_label_across_lines_counts_its_line(tmp_path: Path) -> None:
    page = "[t][multi\nline] [bad](GONE.md)\n\n[multi line]: TARGET.md\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:2: link target 'GONE.md' does not exist"
    ]


@pytest.mark.parametrize("first", ['[t](TARGET.md "a `x`\nb")', '![i](TARGET.md "a `x`\nb")'])
def test_backticks_in_a_title_keep_its_lines(tmp_path: Path, first: str) -> None:
    # Both occurrences keep their own line: the first spans n + 1 lines.
    page = f"{first}\n[bad](GONE.md)\n\n{first}\n[bad2](GONE2.md)\n"
    n = first.count("\n")
    assert check.run(_tree(tmp_path, page)) == [
        f"docs/PAGE.md:{n + 2}: link target 'GONE.md' does not exist",
        f"docs/PAGE.md:{2 * n + 5}: link target 'GONE2.md' does not exist",
    ]


def test_a_link_like_fragment_in_an_html_attribute_does_not_hide_references(
    tmp_path: Path,
) -> None:
    page = 'Inline <span title="[x](https://example.invalid/">[broken][missing])</span>\n'
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:1: reference [missing] has no definition"
    ]


@pytest.mark.parametrize(
    ("page", "found"),
    [
        # The destination is the local file "span": only that is reported.
        (
            '[site](<span> "See [foo][bar]") <span>text</span>\n',
            ["docs/PAGE.md:1: link target 'span' does not exist"],
        ),
        ("[t](https://example.invalid/<span>/[foo][bar]) <span>visible</span>\n", []),
        ("[x](<b> [broken][missing])\n", ["docs/PAGE.md:1: reference [missing] has no definition"]),
        (
            "Text <!-- x\n[y](z -->\nb [c][gone]\n",
            ["docs/PAGE.md:3: reference [gone] has no definition"],
        ),
        ("See <https://example.invalid/[a][b]> ok\n", []),
        # An image's alt text is parsed on its own: its spans are moved into the source.
        ("![<https://example.invalid/[a][b]>](TARGET.md)\n", []),
        ('![alt [site](https://example.invalid/ "See [foo][bar]")](TARGET.md)\n', []),
        (
            "![a <span title='[x](y'> b](TARGET.md) [c][gone]\n",
            ["docs/PAGE.md:1: reference [gone] has no definition"],
        ),
        ("![a ![b](https://example.invalid/[c][d])](TARGET.md)\n", []),
    ],
)
def test_only_parsed_html_and_link_tails_are_masked(
    tmp_path: Path, page: str, found: list[str]
) -> None:
    assert check.run(_tree(tmp_path, page)) == found


@pytest.mark.parametrize(
    "line", ["-  " * 28 + "ordinary text", "1234567890.  " * 28 + "text", "> " * 200 + "text"]
)
def test_long_container_prefixes_are_scanned_in_linear_time(tmp_path: Path, line: str) -> None:
    # A backtracking pattern took seconds on these lines (cubrid-lab/sqlalchemy-cubrid#930 review).
    started = time.perf_counter()
    assert check.run(_tree(tmp_path, f"{line}\n{line}\n")) == []
    assert time.perf_counter() - started < 1.0


def test_a_quote_never_closed_before_a_final_backslash_is_not_shell(tmp_path: Path) -> None:
    page = '```text\nA literal double quote: "\nmake removed \\\n```\n'
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:3: `make removed` is not a Makefile target"
    ]


@pytest.mark.parametrize("first", ["echo $(printf x)#note \\", "cat <(true)#note \\"])
def test_a_hash_after_a_substitution_stays_in_the_word(tmp_path: Path, first: str) -> None:
    page = f"```bash\n{first}\nmake removed\nmake gone\n```\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:4: `make gone` is not a Makefile target"
    ]


def test_html_attributes_are_parsed_like_a_browser(tmp_path: Path) -> None:
    page = (
        '<img data-src="https://example.invalid/lazy.svg" src="GONE.svg">\n\n'
        "<img src=GONE2.svg alt=x>\n\n"
        '<img src="demo&#46;gif"> <a data-href="x" href="TARGET.md#options">o</a>\n'
    )
    root = _tree(tmp_path, page, {"docs/demo.gif": ""})
    assert check.run(root) == [
        "docs/PAGE.md:1: link target 'GONE.svg' does not exist",
        "docs/PAGE.md:3: link target 'GONE2.svg' does not exist",
    ]


def test_protocol_relative_urls_are_external(tmp_path: Path) -> None:
    page = (
        "![logo](//cdn.example.invalid/logo.svg) "
        '<img src="//cdn.example.invalid/a.svg"> [x](//example.invalid/page)\n'
    )
    assert check.run(_tree(tmp_path, page)) == []


def test_continued_shell_lines_are_one_command(tmp_path: Path) -> None:
    page = "```bash\nmake removed \\\n  VAR=1\nmake \\\n  removed lint\n```\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:2: `make removed` is not a Makefile target",
        "docs/PAGE.md:4: `make removed` is not a Makefile target",
    ]


@pytest.mark.parametrize(
    "command", ["echo ';' make tset", "echo \\; make tset", 'echo "a && make" tset']
)
def test_quoted_or_escaped_separators_are_words(tmp_path: Path, command: str) -> None:
    assert make_goals(command) == []
    assert check.run(_tree(tmp_path, f"Run `{command}`.\n")) == []


def test_brackets_in_urls_titles_and_comments_are_not_references(tmp_path: Path) -> None:
    page = (
        "[search](https://example.invalid/?filter=[a][b]) and\n"
        '[site](https://example.invalid/ "See [foo][bar]") and\n'
        "[nested](TARGET.md#options (title [x][y])) <!-- [c][d] --> <https://x.invalid/[e][f]>\n"
    )
    assert check.run(_tree(tmp_path, page)) == []


def test_html_anchors_in_code_or_comments_do_not_count(tmp_path: Path) -> None:
    target = (
        '# T\n\n`<a id="inline"></a>`\n\n```html\n<a id="fenced"></a>\n```\n\n'
        '<!-- <a id="commented"></a> -->\n\n<a id="real"></a>\n'
    )
    page = "[a](T.md#inline) [b](T.md#fenced) [c](T.md#commented) [d](T.md#real)\n"
    root = _tree(tmp_path, page, {"docs/T.md": target})
    assert [p.split(": ", 1)[1].split(" is ")[0] for p in check.run(root)] == [
        "anchor #commented",
        "anchor #fenced",
        "anchor #inline",
    ]


def test_explicit_heading_ids_follow_each_renderer(tmp_path: Path) -> None:
    page = (
        "[gh](TARGET.md#connection-options-options) [site](TARGET.md#options)\n"
        "[stripped](TARGET.md#connection-options)\n"
    )
    assert check.run(_tree(tmp_path, page)) == [
        (
            "docs/PAGE.md:2: anchor #connection-options is not a heading or anchor of "
            + "docs/TARGET.md; did you mean 'connection-options-options'?"
        )
    ]


def test_findings_use_the_line_of_each_occurrence(tmp_path: Path) -> None:
    page = (
        "Intro line\n[a](TARGET.md)\nthen `a code\nspan` and\n"
        "[b](GONE.md) with [c][missing] and `make tset`.\n"
    )
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:5: `make tset` is not a Makefile target; did you mean 'test'?",
        "docs/PAGE.md:5: link target 'GONE.md' does not exist",
        "docs/PAGE.md:5: reference [missing] has no definition",
    ]


def test_missing_or_empty_makefile_fails_closed(tmp_path: Path) -> None:
    root = _tree(tmp_path, "Run `make test`.\n")
    assert check.run(root) == []
    (root / "Makefile").write_text("# no targets\n", encoding="utf-8")
    assert check.run(root) == ["docs/PAGE.md:1: `make test` is not a Makefile target"]
    (root / "Makefile").unlink()
    assert check.run(root) == ["docs/PAGE.md:1: `make test` is not a Makefile target"]


def test_inline_ignore_markers_are_not_honoured(tmp_path: Path) -> None:
    """Exceptions are maintainer-reviewed allowlist entries, not markers in a page."""
    page = "[a](GONE.md) <!-- docs-check: ignore -->\n"
    assert check.run(_tree(tmp_path, page)) == [
        "docs/PAGE.md:1: link target 'GONE.md' does not exist"
    ]


def _allowlist(root: Path, text: str) -> Path:
    (root / check.ALLOWLIST).write_text(text, encoding="utf-8")
    return root


def test_an_allowlist_entry_suppresses_the_matching_findings_of_its_path(tmp_path: Path) -> None:
    page = "[a](GONE.md) and [b](OTHER.md)\n\n[c](GONE.md)\n"
    root = _allowlist(
        _tree(tmp_path, page, {"README.md": "[d](GONE.md)\n"}),
        "# comment\n\ndocs/PAGE.md 'GONE.md'  # reviewed: the page is published elsewhere\n",
    )
    assert check.run(root) == [
        "README.md:1: link target 'GONE.md' does not exist",
        "docs/PAGE.md:1: link target 'OTHER.md' does not exist",
    ]


@pytest.mark.parametrize(
    "entry", ["docs/PAGE.md 'GONE.md'\n", "docs/PAGE.md  # reason without text\n"]
)
def test_an_allowlist_entry_needs_a_path_text_and_reason(tmp_path: Path, entry: str) -> None:
    root = _allowlist(_tree(tmp_path, "[a](GONE.md)\n"), entry)
    assert check.run(root) == [
        f"{check.ALLOWLIST}:1: an entry is 'PATH TEXT  # reason'",
        "docs/PAGE.md:1: link target 'GONE.md' does not exist",
    ]


def test_a_stale_allowlist_entry_is_reported_on_a_full_run_only(tmp_path: Path) -> None:
    root = _allowlist(_tree(tmp_path, "# Page\n"), "docs/PAGE.md 'GONE.md'  # was broken\n")
    assert check.run(root) == [f"{check.ALLOWLIST}:1: entry suppresses nothing; remove it"]
    assert check.run(root, [root / "docs/PAGE.md"]) == []


def test_only_tracked_files_are_checked_in_git(tmp_path: Path) -> None:
    root = _tree(tmp_path, "# Page\n", {"untracked/NOTES.md": "[x](GONE.md)\n"})
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "docs", "Makefile", "scripts"], check=True)
    assert check.run(root) == []
    assert [p.name for p in check.markdown_files(root)] == ["PAGE.md", "TARGET.md"]


def test_github_slug_matches_github_rendering() -> None:
    assert github_slug("Development Workflow (cubrid-lab org standard)") == (
        "development-workflow-cubrid-lab-org-standard"
    )
    assert github_slug("`ping(reconnect=True)` and #485") == "pingreconnecttrue-and-485"
    assert github_slug("한글 제목 (Korean)") == "한글-제목-korean"


@pytest.mark.parametrize(
    ("command", "goals"),
    [
        ("make test", ["test"]),
        ("make -j2 -C sub lint VAR=1 test # comment", ["lint", "test"]),
        ("cd x && make integration CUBRID_TEST_PORT=1 | tee log", ["integration"]),
        ("make -j 2 tset", ["tset"]),
        ("make --directory . tset", ["tset"]),
        ("make --directory docs tset", ["tset"]),
        ("make --directory=docs --jobs=4 tset", ["tset"]),
        ("make tset;make lint", ["tset", "lint"]),
        ("(make a)&&make b||make c", ["a", "b", "c"]),
        ("make sure", ["sure"]),
        ("cmake build", []),
        ("make 'unbalanced", []),
        ("make test VAR='value; make removed; tail'", ["test"]),
        ("make test > test.log", ["test"]),
        ("make test >> log 2>&1 | tee x", ["test"]),
        ("make test < in.txt", ["test"]),
        ("make test 2> err.txt", ["test"]),
        ("echo make test", []),
        ("VAR=1 make lint", ["lint"]),
    ],
)
def test_make_goals(command: str, goals: list[str]) -> None:
    assert make_goals(command) == goals


def test_parse_reports_heading_anchors(tmp_path: Path) -> None:
    path = tmp_path / "t.md"
    path.write_text(TARGET, encoding="utf-8")
    assert parse(path).anchors == {
        "target",
        "options",  # the site uses the explicit id
        "connection-options-options",  # GitHub keeps the literal {#options} text
        "legacy-anchor",
        "한글-제목",
        "_1",  # this site's default slugifier drops Korean (#388)
        "same",
        "same-1",
        "same_1",
    }


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _tree(tmp_path, "# Page\n\n[x](GONE.md)\n")
    assert check.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "docs/PAGE.md:3: link target 'GONE.md' does not exist" in out
    assert check.ALLOWLIST in out
    (root / "docs/PAGE.md").write_text("# Page\n", encoding="utf-8")
    assert check.main(["--root", str(root), str(root / "docs/PAGE.md")]) == 0
    assert "OK: 1 Markdown files" in capsys.readouterr().out


# ----- site slugifier (cubrid-lab/cubrid-cookbook-python#388) -----

SLUG_HEADINGS = ["Résumé", "한글 제목", "Connection options", "C++ & Python!", "naïve  café"]


@pytest.mark.parametrize(
    ("heading", "default", "pymdownx"),
    [
        ("Résumé", "resume", "résumé"),
        ("한글 제목", "", "한글-제목"),
        ("Connection options", "connection-options", "connection-options"),
    ],
)
def test_site_slugifiers(heading: str, default: str, pymdownx: str) -> None:
    assert _markdown.default_site_slug(heading) == default
    assert _markdown._site_slug(heading) == pymdownx


def test_default_site_slug_matches_python_markdown() -> None:
    toc = pytest.importorskip("markdown.extensions.toc")
    for heading in SLUG_HEADINGS:
        assert _markdown.default_site_slug(heading) == toc.slugify(heading, "-"), heading


def test_site_slugifier_follows_mkdocs_yml(tmp_path: Path) -> None:
    config = tmp_path / "mkdocs.yml"
    assert _markdown.site_slugifier(config) is _markdown.default_site_slug  # no mkdocs.yml
    config.write_text("markdown_extensions:\n  - toc:\n      permalink: true\n", encoding="utf-8")
    assert _markdown.site_slugifier(config) is _markdown.default_site_slug
    config.write_text(
        "markdown_extensions:\n  - toc:\n"
        "      slugify: !!python/object/apply:pymdownx.slugs.slugify\n",
        encoding="utf-8",
    )
    assert _markdown.site_slugifier(config) is _markdown._site_slug
    # This repository's own site.
    assert _markdown.site_slugifier(ROOT / "mkdocs.yml") is REPO_SITE_SLUG


@pytest.mark.parametrize(
    ("headings", "github", "site"),
    [
        # An empty id is numbered, and a taken ``_N`` is incremented, not suffixed.
        (["한글", "_1"], {"한글", "_1"}, {"_1", "_2"}),
        (["same", "same", "same_1"], {"same", "same-1", "same_1"}, {"same", "same_1", "same_2"}),
        (["a_1", "a_1"], {"a_1", "a_1-1"}, {"a_1", "a_2"}),
    ],
)
def test_site_anchors_are_unique_as_toc_makes_them(
    tmp_path: Path, headings: list[str], github: set[str], site: set[str]
) -> None:
    path = tmp_path / "t.md"
    path.write_text("".join(f"## {h}\n\n" for h in headings), encoding="utf-8")
    assert parse(path, _markdown.default_site_slug).anchors == github | site
    markdown = pytest.importorskip("markdown")
    html = markdown.markdown(path.read_text(encoding="utf-8"), extensions=["toc"])
    assert set(re.findall(r'id="([^"]*)"', html)) == site


@pytest.mark.parametrize(
    ("slugifier", "site"),
    [
        ("default_site_slug", {"resume", "_1", "_2"}),
        ("_site_slug", {"résumé", "한글-제목", "다른-제목"}),
    ],
)
def test_parse_uses_the_site_slugifier(tmp_path: Path, slugifier: str, site: set[str]) -> None:
    path = tmp_path / "t.md"
    path.write_text("# Résumé\n\n## 한글 제목\n\n## 다른 제목\n", encoding="utf-8")
    github = {"résumé", "한글-제목", "다른-제목"}
    assert parse(path, getattr(_markdown, slugifier)).anchors == github | site


# ----- cookbook-specific checks (#353) -----

MATRIX = "# Support Matrix\n\n## Recipe coverage\n"


def test_a_docs_link_to_a_staged_page_resolves_to_its_source(tmp_path: Path) -> None:
    page = (
        "[m](support-matrix.md#recipe-coverage) and [bad](support-matrix.md#gone)\n\n"
        "[unstaged](not-staged.md)\n"
    )
    root = _tree(tmp_path, page, {"SUPPORT_MATRIX.md": MATRIX})
    assert check.run(root) == [
        "docs/PAGE.md:1: anchor #gone is not a heading or anchor of SUPPORT_MATRIX.md",
        "docs/PAGE.md:3: link target 'not-staged.md' does not exist",
    ]


def test_issue_number_lines_are_reported_on_every_page_the_site_renders(tmp_path: Path) -> None:
    text = "Wrapped and\n#755 on the next line.\n"
    root = _tree(
        tmp_path,
        "# Page\n",
        {
            "README.md": text,  # staged as docs/catalog.md
            "docs/internal/design.md": text,  # never published
            "fundamentals/connect/README.md": text,  # not staged
        },
    )
    assert check.run(root) == [
        "README.md:2: line starts with '#<digit>', which the MkDocs site renders as a "
        + "heading; escape it as '\\#'"
    ]


RECIPE = {
    "templates/flask/requirements.txt": "",
    "templates/flask/run.py": "",
    "templates/flask/app/main.py": "",
    "templates/flask/main.py": "",
    "fundamentals/pycubrid/01_connect.py": "",
}


@pytest.mark.parametrize(
    "block",
    [
        "pip install -r requirements.txt pytest\npython run.py\nuvicorn main:app --reload",
        "uvicorn app.main:app --host 0.0.0.0 --port 8000",
        "python -m venv .venv\npython -m pytest tests/ -v\npython3 -m pip install -r requirements.txt",
        "python fundamentals/pycubrid/01_connect.py",
        'DATABASE_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python run.py',
        "python <your_script>.py\npip install -r $REQS\nuv run python run.py",
        "docker compose exec app python manage.py migrate",
    ],
)
def test_recipe_commands_that_resolve_pass(tmp_path: Path, block: str) -> None:
    extra = dict(RECIPE, **{"templates/flask/README.md": f"```bash\n{block}\n```\n"})
    assert check.run(_tree(tmp_path, "# Page\n", extra)) == []


@pytest.mark.parametrize(
    ("block", "what", "missing"),
    [
        ("pip install -r requirement.txt", "pip install -r requirement.txt", "requirement.txt"),
        ("pip install --requirement=dev.txt", "pip install -r dev.txt", "dev.txt"),
        ("python app.py", "python app.py", "app.py"),
        ("python3 -u tools/seed.py", "python3 tools/seed.py", "tools/seed.py"),
        ("uvicorn api.server:app", "uvicorn api.server:app", "api/server.py"),
    ],
)
def test_a_missing_recipe_file_is_reported(
    tmp_path: Path, block: str, what: str, missing: str
) -> None:
    extra = dict(RECIPE, **{"templates/flask/README.md": f"# Flask\n\n```bash\n{block}\n```\n"})
    assert check.run(_tree(tmp_path, "# Page\n", extra)) == [
        f"templates/flask/README.md:4: `{what}`: {missing} does not exist next to this file, "
        "at the repository root or in a directory it cds into"
    ]


def test_a_cd_in_the_file_adds_a_lookup_directory(tmp_path: Path) -> None:
    readme = (
        "```bash\ncd templates/flask\npip install -r requirements.txt\n```\nThen `python run.py`.\n"
    )
    assert check.run(_tree(tmp_path, "# Page\n", dict(RECIPE, **{"README.md": readme}))) == []


def test_inline_recipe_commands_are_checked(tmp_path: Path) -> None:
    extra = dict(RECIPE, **{"templates/flask/README.md": "Run: `python serve.py`\n"})
    assert check.run(_tree(tmp_path, "# Page\n", extra)) == [
        "templates/flask/README.md:1: `python serve.py`: serve.py does not exist next to this "
        "file, at the repository root or in a directory it cds into"
    ]


def test_release_history_keeps_its_recipe_commands(tmp_path: Path) -> None:
    root = _tree(tmp_path, "# Page\n", {"CHANGELOG.md": "Run `python gone.py`.\n"})
    assert check.run(root) == []


@pytest.mark.parametrize(
    "change",
    [
        # Delete-only: the recipe's requirements file is removed, its README is not edited.
        lambda root: (root / "templates/flask/requirements.txt").unlink(),
        # Rename-only: the recipe directory moves, the README linking to it does not change.
        lambda root: (root / "templates/flask").rename(root / "templates/flask-app"),
    ],
)
def test_a_rename_or_delete_without_a_docs_change_is_caught(tmp_path: Path, change) -> None:
    readme = "See [Flask](templates/flask/README.md).\n\n```bash\ncd templates/flask\npip install -r requirements.txt\n```\n"
    extra = dict(RECIPE, **{"README.md": readme, "templates/flask/README.md": "# Flask\n"})
    root = _tree(tmp_path, "# Page\n", extra)
    assert check.run(root) == []
    change(root)
    assert check.run(root), "the stale reference must be reported"


def test_the_docs_check_job_always_runs_and_gates_the_merge() -> None:
    """A rename- or delete-only diff touches no Markdown, so the job must not be scoped."""
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    after = workflow.split("\n  docs-check:\n", 1)[1]
    job = re.split(r"\n  (?=\S)", after, maxsplit=1)[0]  # up to the next job or comment
    assert "Check links, anchors, fences and recipe commands" in job
    assert "\n    if:" not in job
    assert "python scripts/check_docs_links.py" in job
    gate = workflow.split("\n  ci-gate:\n", 1)[1]
    assert "docs-check" in gate.split("needs:", 1)[1].split("\n", 1)[0]
    assert "R_DOCS_CHECK: ${{ needs.docs-check.result }}" in gate


def test_allowlist_text_may_contain_a_hash(tmp_path: Path) -> None:
    """The reason starts at the documented "  #", so TEXT may contain "#"."""
    page = "[a](TARGET.md#legacy)\n\n[b](TARGET.md#other)\n"
    root = _allowlist(_tree(tmp_path, page), "docs/PAGE.md anchor #legacy  # reviewed exception\n")
    assert check.run(root) == [
        "docs/PAGE.md:3: anchor #other is not a heading or anchor of docs/TARGET.md"
    ]


def test_an_allowlist_entry_with_a_hash_but_no_reason_is_rejected(tmp_path: Path) -> None:
    page = "[a](TARGET.md#legacy)\n"
    root = _allowlist(_tree(tmp_path, page), "docs/PAGE.md anchor #legacy\n")
    assert check.run(root) == [
        f"{check.ALLOWLIST}:1: an entry is 'PATH TEXT  # reason'",
        "docs/PAGE.md:1: anchor #legacy is not a heading or anchor of docs/TARGET.md",
    ]


def test_only_published_docs_pages_link_staged_pages(tmp_path: Path) -> None:
    extra = {
        "SUPPORT_MATRIX.md": MATRIX,
        "quickstart/5min/README.md": "[m](../../docs/support-matrix.md)\n",
        "docs/internal/notes.md": "[m](../support-matrix.md)\n",
    }
    assert check.run(_tree(tmp_path, "# Page\n", extra)) == [
        "docs/internal/notes.md:1: link target '../support-matrix.md' is a generated staged "
        "page; link SUPPORT_MATRIX.md instead",
        "quickstart/5min/README.md:1: link target '../../docs/support-matrix.md' is a "
        "generated staged page; link SUPPORT_MATRIX.md instead",
    ]


def test_a_staged_link_is_checked_against_its_source_after_make_docs(tmp_path: Path) -> None:
    page = "[m](support-matrix.md#recipe-coverage) [s](support-matrix.md#stale-heading)\n"
    extra = {
        "SUPPORT_MATRIX.md": MATRIX,
        # A generated copy left by `make docs`, with a heading the source no longer has.
        "docs/support-matrix.md": "# Support Matrix\n\n## Stale heading\n",
    }
    assert check.run(_tree(tmp_path, page, extra)) == [
        "docs/PAGE.md:1: anchor #stale-heading is not a heading or anchor of SUPPORT_MATRIX.md"
    ]


def test_a_recipe_local_script_resolves(tmp_path: Path) -> None:
    extra = dict(
        RECIPE,
        **{
            "templates/flask/scripts/seed.py": "",
            "templates/flask/README.md": "```bash\npython scripts/seed.py\n```\n",
        },
    )
    assert check.run(_tree(tmp_path, "# Page\n", extra)) == []


def test_a_missing_uvicorn_module_under_scripts_is_reported(tmp_path: Path) -> None:
    extra = dict(
        RECIPE, **{"templates/flask/README.md": "```bash\nuvicorn scripts.missing:app\n```\n"}
    )
    assert check.run(_tree(tmp_path, "# Page\n", extra)) == [
        "templates/flask/README.md:2: `uvicorn scripts.missing:app`: scripts/missing.py does not "
        "exist next to this file, at the repository root or in a directory it cds into"
    ]


@pytest.mark.parametrize(
    "readme",
    [
        "```bash\ncd templates && cd flask && python run.py\n```\n",
        "```bash\ncd templates\ncd flask\npip install -r requirements.txt\n```\n",
    ],
)
def test_successive_cds_resolve_against_each_other(tmp_path: Path, readme: str) -> None:
    assert check.run(_tree(tmp_path, "# Page\n", dict(RECIPE, **{"README.md": readme}))) == []
