#!/usr/bin/env python3
"""Stage repository docs into docs/ for the MkDocs site (#154).

The repository files stay the single source of truth; this script copies them
into ``docs/`` (the copies are gitignored) and rewrites their relative links so
they still resolve after the move:

* a link to another staged source (``SUPPORT_MATRIX.md``, ``pitfalls/``,
  ``../../GETTING_STARTED.md#...``) points at that source's staged site page;
* a link to an authored file already under ``docs/`` (for example
  ``docs/README.ko.md``) points at it relative to the staged page;
* a link to any other repository path (recipe directories, ``.py`` files,
  ``LICENSE``, ``docs/internal/``) becomes a GitHub URL on ``main``;
* a relative link whose target does not exist in the repository is a broken
  link: staging reports every one and exits non-zero.

Sources are only read, never modified. Links inside fenced code blocks and
inline code spans are left untouched. Run it before ``mkdocs build --strict``
(``make docs`` and CI do this via ``scripts/stage_docs.sh``).

>>> rewrite_target("SUPPORT_MATRIX.md", "README.md", "docs/catalog.md", REPO_ROOT)
'support-matrix.md'
>>> rewrite_target("pitfalls/#top", "README.md", "docs/catalog.md", REPO_ROOT)
'pitfalls.md#top'
>>> rewrite_target("./connect/", "fundamentals/README.md", "docs/fundamentals.md", REPO_ROOT)
'https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/connect'
>>> rewrite_target("https://example.com/x", "README.md", "docs/catalog.md", REPO_ROOT)
'https://example.com/x'
>>> rewrite_target("#section", "README.md", "docs/catalog.md", REPO_ROOT)
'#section'
"""

from __future__ import annotations

import posixpath
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GITHUB_BASE = "https://github.com/cubrid-lab/cubrid-cookbook-python"
BRANCH = "main"
DOCS_DIR = "docs"
# Authored under docs/ but never published (see exclude_docs in mkdocs.yml).
UNPUBLISHED_DOCS = ("docs/internal/",)

# (repository source, staged page) — sources of truth stay at their repo paths.
STAGE = [
    ("README.md", "docs/catalog.md"),
    ("GETTING_STARTED.md", "docs/getting-started.md"),
    ("SUPPORT_MATRIX.md", "docs/support-matrix.md"),
    ("KNOWN_ISSUES.md", "docs/known-issues.md"),
    ("CHANGELOG.md", "docs/changelog.md"),
    ("fundamentals/README.md", "docs/fundamentals.md"),
    ("fundamentals/pycubrid/README.md", "docs/fundamentals-pycubrid.md"),
    ("fundamentals/sqlalchemy/README.md", "docs/fundamentals-sqlalchemy.md"),
    ("fundamentals/pandas/README.md", "docs/fundamentals-pandas.md"),
    (
        "fundamentals/parameterized-queries/README.md",
        "docs/fundamentals-parameterized-queries.md",
    ),
    ("performance/README.md", "docs/performance.md"),
    ("pitfalls/README.md", "docs/pitfalls.md"),
    ("templates/api-service-fastapi/README.md", "docs/template-api-service-fastapi.md"),
    ("templates/async-worker/README.md", "docs/template-async-worker.md"),
    ("templates/batch-etl/README.md", "docs/template-batch-etl.md"),
    ("templates/dashboard/README.md", "docs/template-dashboard.md"),
    ("templates/django/README.md", "docs/template-django.md"),
    ("templates/flask/README.md", "docs/template-flask.md"),
    ("templates/ai-agent/README.md", "docs/template-ai-agent.md"),
]

FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
# `](target` of inline links and images, including nested badge links.
INLINE_LINK_RE = re.compile(r"(\]\(\s*<?)([^)\s>]+)")
# `[label]: target` reference definitions (footnotes `[^x]:` are excluded).
REF_DEF_RE = re.compile(r"^(\s{0,3}\[(?!\^)[^\]]+\]:\s*<?)([^\s>]+)")
# Raw HTML attributes, which MkDocs neither validates nor rewrites.
HTML_ATTR_RE = re.compile(r"""(\s(?:src|href)=["'])([^"']+)""")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class BrokenLink(Exception):
    pass


def _is_external(target: str) -> bool:
    return bool(SCHEME_RE.match(target)) or target.startswith(("#", "/"))


def _split(target: str) -> tuple[str, str]:
    for sep in ("#", "?"):
        if sep in target:
            path, rest = target.split(sep, 1)
            return path, sep + rest
    return target, ""


def _page_for(resolved: str, root: Path) -> str | None:
    staged = dict(STAGE)
    if resolved in staged:
        return staged[resolved]
    if (root / resolved).is_dir():
        return staged.get(posixpath.join(resolved, "README.md"))
    return None


def _github_url(resolved: str, root: Path) -> str:
    kind = "tree" if (root / resolved).is_dir() else "blob"
    return f"{GITHUB_BASE}/{kind}/{BRANCH}/{resolved}"


def rewrite_target(target: str, src: str, dst: str, root: Path, html: bool = False) -> str:
    """Return ``target`` (a link in repo file ``src``) as seen from staged ``dst``."""
    if _is_external(target):
        return target
    path, suffix = _split(target)
    if not path:
        return target
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(src), path))
    if resolved.startswith("../") or resolved == "..":
        raise BrokenLink(f"{src}: link '{target}' leaves the repository")
    if resolved == ".":
        resolved = ""
    if resolved and not (root / resolved).exists():
        raise BrokenLink(f"{src}: link '{target}' points to missing '{resolved}'")

    dst_dir = posixpath.dirname(dst)
    page = _page_for(resolved, root) if resolved else None
    in_docs = resolved.startswith(DOCS_DIR + "/") and not resolved.startswith(UNPUBLISHED_DOCS)
    if not html:
        if page:
            return posixpath.relpath(page, dst_dir) + suffix
        if in_docs and (root / resolved).is_file():
            return posixpath.relpath(resolved, dst_dir) + suffix
    elif in_docs and not resolved.endswith(".md") and (root / resolved).is_file():
        # Raw HTML is emitted verbatim; with use_directory_urls a page is served
        # one directory deeper than its .md file (index.md excepted).
        rel = posixpath.relpath(resolved, dst_dir)
        return (rel if posixpath.basename(dst) == "index.md" else "../" + rel) + suffix
    if not resolved:
        return f"{GITHUB_BASE}/tree/{BRANCH}" + suffix
    return _github_url(resolved, root) + suffix


def rewrite_text(text: str, src: str, dst: str, root: Path) -> tuple[str, list[str]]:
    """Rewrite every relative link in ``text``; return (new text, broken links)."""
    errors: list[str] = []

    def sub(match: re.Match[str], html: bool = False) -> str:
        try:
            return match.group(1) + rewrite_target(match.group(2), src, dst, root, html)
        except BrokenLink as exc:
            errors.append(str(exc))
            return match.group(0)

    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        opener = FENCE_RE.match(line)
        if fence is not None:
            if opener and opener.group(1)[0] == fence[0] and len(opener.group(1)) >= len(fence):
                fence = None
            out.append(line)
            continue
        if opener:
            fence = opener.group(1)
            out.append(line)
            continue
        # Protect inline code spans, rewrite, then restore them.
        spans: list[str] = []

        def hide(m: re.Match[str]) -> str:
            spans.append(m.group(0))
            return f"\x00{len(spans) - 1}\x00"

        masked = CODE_SPAN_RE.sub(hide, line)
        masked = REF_DEF_RE.sub(sub, masked)
        masked = INLINE_LINK_RE.sub(sub, masked)
        masked = HTML_ATTR_RE.sub(lambda m: sub(m, html=True), masked)
        out.append(re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], masked))
    return "".join(out), errors


def stage(root: Path = REPO_ROOT) -> list[str]:
    """Stage every source into docs/; return the broken-link errors found."""
    errors: list[str] = []
    for src, dst in STAGE:
        source = root / src
        if not source.is_file():
            print(f"stage-docs: missing {src} — skipping", file=sys.stderr)
            continue
        text, broken = rewrite_text(source.read_text(encoding="utf-8"), src, dst, root)
        errors.extend(broken)
        target = root / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return errors


def main() -> int:
    errors = stage()
    for error in errors:
        print(f"stage-docs: broken link: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
