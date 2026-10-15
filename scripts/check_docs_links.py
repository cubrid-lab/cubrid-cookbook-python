#!/usr/bin/env python3
"""Fail on deterministic defects in the repository's Markdown files (#353; shared with pycubrid and sqlalchemy-cubrid).

Checks every tracked ``*.md`` file, offline and without network access:

* a relative link or image target that does not exist, or that leaves the
  repository;
* an ``#anchor`` that is not a heading (GitHub slug, ``{#id}``) or an
  ``<a id>``/``<a name>`` of the target Markdown file;
* a full reference link ``[text][label]`` without a definition;
* a fenced code block that is never closed;
* a paragraph line of a page the MkDocs site renders (``docs/`` outside
  ``docs/internal/``, and the sources ``scripts/stage_docs.py`` stages) that
  starts with ``#<digit>`` (an issue number): the site renders it as a
  heading; escape it as ``\\#``;
* a ``make`` goal, written as a command in inline code or a fenced block, that
  the Makefile does not define, and a ``scripts/...`` path that does not exist;
* a recipe command whose file does not exist: the requirements file of
  ``pip install -r FILE``, the script of ``python FILE.py`` and the module of
  ``uvicorn MODULE:APP``, looked up next to the Markdown file, at the
  repository root and in every directory the file ``cd``s into.
  Release history (``CHANGELOG.md``, ``RELEASE_CHANGELOG.md``) records commands
  and scripts as they were, so only its links are checked.

A link from ``docs/`` to a staged page (``support-matrix.md``) resolves to its
repository source (``SUPPORT_MATRIX.md``), as the site build does.

External links (any URI scheme) are never fetched: the shared doc-lint
workflow checks them, advisory. Style is not checked here either.

A reviewed exception is an entry of ``scripts/docs-check-allowlist.txt``
(``PATH TEXT  # reason``; maintainers own ``scripts/`` in CODEOWNERS): it
suppresses the findings of ``PATH`` whose message contains ``TEXT``. An entry
without a reason, or one that suppresses nothing, is itself a finding. Inline
``<!-- docs-check: ignore -->`` markers are not honoured in this repository.
Each finding prints ``file:line: problem`` and, when one is close, a suggested
replacement.

Usage: ``python scripts/check_docs_links.py [--root DIR] [FILE ...]``
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _markdown import Parsed, _shell_tokens, is_external, make_goals, parse  # noqa: E402
from stage_docs import STAGE, UNPUBLISHED_DOCS  # noqa: E402

ALLOWLIST = "scripts/docs-check-allowlist.txt"
# Pages that MkDocs (Python-Markdown) renders.
SITE_DIR = "docs/"
_PLACEHOLDER = re.compile(r"[<>{}$*~]")
# Dated release notes describe commands and scripts of their time; never rewrite them.
HISTORY = frozenset({"CHANGELOG.md", "RELEASE_CHANGELOG.md"})
_SCRIPT = re.compile(r"(?<![\w/.-])scripts/[A-Za-z0-9_./-]+\.(?:py|cjs|sh)\b")
# A rule line: one or more targets, then ``:`` or ``::``, but not an assignment
# (``:=``, ``::=``): after the colons comes neither ``=`` nor another ``:``.
# Recipe lines start with a tab and are not rules.
_MAKE_RULE = re.compile(r"^([^\t#=:][^#=:]*?)\s*::?(?![=:])")


def make_targets(text: str) -> set[str]:
    """Return every target a Makefile declares, including grouped ``a b:`` rules."""
    targets: set[str] = set()
    for line in text.splitlines():
        match = _MAKE_RULE.match(line)
        if match:
            targets.update(match.group(1).split())
    return targets


def markdown_files(root: Path) -> list[Path]:
    """Return the tracked Markdown files, or every ``*.md`` outside git."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.md"],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return sorted(p for p in root.rglob("*.md") if ".venv" not in p.parts)
    return sorted(root / name for name in out.decode().split("\0") if name)


def load_allowlist(path: Path) -> tuple[list[tuple[str, str, int]], list[str]]:
    """Return ``(entries, problems)`` of the allowlist: ``(PATH, TEXT, line)`` each."""
    entries: list[tuple[str, str, int]] = []
    problems: list[str] = []
    if not path.is_file():
        return entries, problems
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # The reason follows the documented "  #" (two spaces), so TEXT may hold "#".
        entry, _, reason = line.partition("  #")
        parts = entry.split(None, 1)
        if not reason.strip() or len(parts) != 2:
            problems.append(f"{ALLOWLIST}:{number}: an entry is 'PATH TEXT  # reason'")
            continue
        entries.append((parts[0], parts[1].strip(), number))
    return entries, problems


def _simple_commands(command: str) -> list[list[str]]:
    """Split a shell command into the words of its simple commands."""
    commands: list[list[str]] = [[]]
    tokens = _shell_tokens(command)
    index = 0
    while index < len(tokens):
        text, operator = tokens[index]
        index += 1
        if operator:
            if "<" in text or ">" in text:
                index += 1  # the redirection's operand
            else:
                commands.append([])
            continue
        commands[-1].append(text)
    return [words for words in commands if words]


def recipe_files(command: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Return ``(cd targets, [(what, candidate paths)])`` of a recipe command.

    ``what`` is the command as a reader would quote it. A path with a
    placeholder (``<file>``, ``$VAR``, ``*``, ``~``) or an absolute path is skipped.
    """
    cds: list[str] = []
    files: list[tuple[str, list[str]]] = []

    def usable(path: str) -> bool:
        return bool(path) and not _PLACEHOLDER.search(path) and not path.startswith("/")

    for words in _simple_commands(command):
        while words and "=" in words[0] and not words[0].startswith("-"):
            words = words[1:]  # VAR=value prefixes
        if words[:2] == ["uv", "run"]:
            words = words[2:]
        if not words:
            continue
        name, args = words[0], words[1:]
        if re.fullmatch(r"python(?:3(?:\.\d+)?)?", name):
            if args[:2] == ["-m", "pip"]:
                name, args = "pip", args[2:]
            else:
                for arg in args:
                    if arg in ("-m", "-c"):
                        break
                    if not arg.startswith("-"):
                        if arg.endswith(".py") and usable(arg):
                            files.append((f"{name} {arg}", [arg]))
                        break
                continue
        if name in ("pip", "pip3") and "install" in args:
            for index, arg in enumerate(args):
                path = ""
                if arg in ("-r", "--requirement") and index + 1 < len(args):
                    path = args[index + 1]
                elif arg.startswith("--requirement="):
                    path = arg.split("=", 1)[1]
                elif arg.startswith("-r") and len(arg) > 2:
                    path = arg[2:]
                if usable(path):
                    files.append((f"pip install -r {path}", [path]))
        elif name == "uvicorn":
            target = next((a for a in args if ":" in a and not a.startswith("-")), "")
            module = target.split(":", 1)[0]
            if usable(module) and re.fullmatch(r"[A-Za-z_][\w.]*", module):
                base = module.replace(".", "/")
                files.append((f"uvicorn {target}", [f"{base}.py", f"{base}/__init__.py"]))
        elif name == "cd" and args and usable(args[0]):
            cds.append(args[0])
    return cds, files


def _suggest(choice: str, options: list[str], cutoff: float = 0.75) -> str:
    close = difflib.get_close_matches(choice, options, n=1, cutoff=cutoff)
    return f"; did you mean {close[0]!r}?" if close else ""


class Checker:
    """Check Markdown files of one repository, caching parses."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._parsed: dict[Path, Parsed] = {}
        makefile = self.root / "Makefile"
        self.make_targets = (
            make_targets(makefile.read_text(encoding="utf-8")) if makefile.is_file() else set()
        )
        # Staged page -> its repository source (scripts/stage_docs.py).
        self.staged = {(self.root / page).resolve(): self.root / source for source, page in STAGE}
        self.site_sources = {source for source, _ in STAGE}
        self.allowlist, self.allowlist_problems = load_allowlist(self.root / ALLOWLIST)
        self.allowlist_used: set[int] = set()

    def is_site_page(self, rel: str) -> bool:
        """Return whether the MkDocs site renders this file."""
        if rel in self.site_sources:
            return True
        return rel.startswith(SITE_DIR) and not rel.startswith(UNPUBLISHED_DOCS)

    def allowed(self, rel: str, problem: str) -> bool:
        """Return whether an allowlist entry covers this finding (and mark it used)."""
        for path, text, number in self.allowlist:
            if path == rel and text in problem:
                self.allowlist_used.add(number)
                return True
        return False

    def parsed(self, path: Path) -> Parsed:
        path = path.resolve()
        if path not in self._parsed:
            self._parsed[path] = parse(path)
        return self._parsed[path]

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def check_target(self, path: Path, target: str) -> str | None:
        """Return the problem with one link target, or ``None``."""
        if not target or is_external(target):
            return None
        file_part, _, anchor = target.partition("#")
        file_part = unquote(file_part.split("?", 1)[0])
        if file_part.startswith("/"):
            return f"link target {target!r} is absolute; use a path relative to the file"
        dest = path.resolve() if not file_part else (path.parent / file_part).resolve()
        if not dest.is_relative_to(self.root):
            return f"link target {target!r} points outside the repository"
        if dest in self.staged:
            if not self.is_site_page(self.rel(path)) or not self.rel(path).startswith(SITE_DIR):
                return (
                    f"link target {target!r} is a generated staged page; link "
                    f"{self.rel(self.staged[dest])} instead"
                )
            # A published docs/ page links the site page: check its source, even
            # when `make docs` has left a (possibly stale) generated copy.
            dest = self.staged[dest]
        if not dest.exists():
            siblings = [p.name for p in dest.parent.iterdir()] if dest.parent.is_dir() else []
            # File names share suffixes (".md"), so ask for a closer match.
            return f"link target {target!r} does not exist" + _suggest(
                dest.name, siblings, cutoff=0.8
            )
        if anchor and dest.suffix == ".md":
            anchors = self.parsed(dest).anchors
            if unquote(anchor) not in anchors:
                return (
                    f"anchor #{anchor} is not a heading or anchor of {self.rel(dest)}"
                    + _suggest(unquote(anchor), sorted(anchors))
                )
        return None

    def check_file(self, path: Path) -> list[str]:
        """Return every problem of one Markdown file as ``file:line: problem``."""
        lines = path.read_text(encoding="utf-8").splitlines()
        parsed = self.parsed(path)
        found: list[tuple[int, str]] = []
        for link in parsed.links + parsed.definitions:
            problem = self.check_target(path, link.target)
            if problem:
                found.append((link.line, problem))
        for ref in parsed.undefined_references:
            found.append((ref.line, f"reference {ref.target} has no definition"))
        for line in parsed.unclosed_fences:
            found.append((line, "code fence is never closed"))
        if self.is_site_page(self.rel(path)):
            for line in parsed.hash_digit_lines:
                found.append(
                    (
                        line,
                        "line starts with '#<digit>', which the MkDocs site renders as a "
                        "heading; escape it as '\\#'",
                    )
                )
        historical = self.rel(path) in HISTORY
        for line, command in [] if historical else parsed.code:
            for goal in make_goals(command):
                # A missing or emptied Makefile fails closed: no goal exists.
                if goal not in self.make_targets:
                    found.append(
                        (
                            line,
                            f"`make {goal}` is not a Makefile target"
                            + _suggest(goal, sorted(self.make_targets)),
                        )
                    )
        recipe_found, command_paths = (
            ([], set()) if historical else self.recipe_problems(path, parsed)
        )
        found += recipe_found
        for number, line in enumerate([] if historical else lines, 1):
            for script in _SCRIPT.findall(line):
                if script in command_paths:
                    continue  # a recipe command: checked above, with its own lookup
                if not (self.root / script).is_file():
                    names = [p.name for p in (self.root / "scripts").glob("*")]
                    found.append(
                        (
                            number,
                            f"{script} does not exist"
                            + _suggest(Path(script).name, names, cutoff=0.8),
                        )
                    )
        rel = self.rel(path)
        return [
            f"{rel}:{line}: {problem}"
            for line, problem in sorted(set(found))
            if not self.allowed(rel, problem)
        ]

    def recipe_problems(self, path: Path, parsed: Parsed) -> tuple[list[tuple[int, str]], set[str]]:
        """Return recipe commands whose file is missing, and every path a command names.

        The paths are looked up next to the file, at the root and in ``cd``
        targets, so a recipe-local ``scripts/seed.py`` resolves; the raw
        ``scripts/`` scan skips them to report each command once.
        """
        here = path.resolve().parent
        commands = [(line, recipe_files(command)) for line, command in parsed.code]
        # Successive `cd`s resolve against each other (`cd templates && cd flask`),
        # in document order; every directory reached stays a lookup base.
        bases = [here, self.root]
        current = {here, self.root}
        for _line, (cds, _files) in commands:
            for cd in cds:
                current = {(c / cd).resolve() for c in current} | {
                    (here / cd).resolve(),
                    (self.root / cd).resolve(),
                }
                bases += sorted(current)
        found = []
        named: set[str] = set()
        for line, (_cds, files) in commands:
            for what, candidates in files:
                named.update(candidates)
                if not any((base / c).is_file() for c in candidates for base in bases):
                    found.append(
                        (
                            line,
                            f"`{what}`: {candidates[0]} does not exist next to this file, "
                            "at the repository root or in a directory it cds into",
                        )
                    )
        return found, named


def run(root: Path, files: list[Path] | None = None) -> list[str]:
    """Return every problem in ``files`` (default: all Markdown files)."""
    checker = Checker(root)
    problems: list[str] = list(checker.allowlist_problems)
    for path in files if files is not None else markdown_files(checker.root):
        problems += checker.check_file(path)
    if files is None:  # a partial run cannot tell whether an entry is stale
        problems += [
            f"{ALLOWLIST}:{number}: entry suppresses nothing; remove it"
            for _path, _text, number in checker.allowlist
            if number not in checker.allowlist_used
        ]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    files = [path.resolve() for path in args.files] or None
    problems = run(root, files)
    if problems:
        print(f"Documentation defects ({len(problems)}):")
        for problem in problems:
            print(f"  {problem}")
        print(f"Fix the target, or record a reviewed exception, with its reason, in {ALLOWLIST}.")
        return 1
    count = len(files) if files else len(markdown_files(root))
    print(f"OK: {count} Markdown files; local links, anchors, fences and commands resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
