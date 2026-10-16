"""Shared CommonMark helpers for the repository documentation checks (#353; shared with pycubrid and sqlalchemy-cubrid).

``markdown-it-py`` parses each file, so fenced code (backtick or tilde, any
length, inside lists and block quotes), inline code spans of any backtick
length and reference-style links follow CommonMark instead of hand-written
regular expressions. Only links a reader can follow are returned: a reference
definition without a use renders nothing, and links inside code are examples.
Every link, code span and undefined reference keeps its own source line, so a
diagnostic and its suppression comment refer to the same line.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.rules_inline import autolink as _autolink_rule
from markdown_it.rules_inline import html_inline as _html_inline_rule
from markdown_it.rules_inline import image as _image_rule
from markdown_it.rules_inline import link as _link_rule
from markdown_it.rules_inline.state_inline import StateInline
from markdown_it.token import Token

_InlineRule = Callable[[StateInline, bool], bool]


def _recording(rule: _InlineRule, kind: str) -> _InlineRule:
    """Wrap a markdown-it inline rule to record the source span of what it parsed.

    The first new token of type ``kind`` gets ``meta["span"]``, the span relative
    to the inline source. A link or an image also gets ``meta["tail"]``: the
    source after its text, ``(dest "title")`` of an inline link, ``[label]`` or
    nothing of a reference one. Line numbers and masking use these positions, not
    the decoded text, which can differ from the source or occur twice.
    """

    def recorded(state: StateInline, silent: bool) -> bool:
        start, count = state.pos, len(state.tokens)
        if not rule(state, silent):
            return False
        if silent:
            return True
        for token in state.tokens[count:]:
            if token.type != kind:
                continue
            token.meta["span"] = (start, state.pos)
            if rule in (_link_rule, _image_rule):
                is_link = state.src[start] == "["
                bracket = start if is_link else start + 1
                label_end = state.md.helpers.parseLinkLabel(state, bracket, is_link)
                token.meta["tail"] = (label_end + 1, state.pos)
            break
        return True

    return recorded


_PARSER = MarkdownIt("commonmark").enable("table")
for _name, _rule, _kind in (
    ("link", _link_rule, "link_open"),
    ("image", _image_rule, "image"),
    ("autolink", _autolink_rule, "link_open"),
    ("html_inline", _html_inline_rule, "html_inline"),
):
    _PARSER.inline.ruler.at(_name, _recording(_rule, _kind))
_ATTR_ID = re.compile(r"\s*\{[^}]*#([\w-]+)[^}]*\}\s*$")
# Python-Markdown reads ``#<digit>`` at the start of a block line as an ATX
# heading. Its block quotes strip ``>`` (after up to 3 spaces) and one space,
# list items start after their marker (``-``, ``*``, ``+``, ``1.``; not
# ``1)``), and list content is dedented by 4 spaces per level; any other
# indentation keeps the line text.
_QUOTE_PREFIX = re.compile(r"(?: {0,3}>[ ]?)*( *)")
_QUOTE_MARKER = re.compile(r" {0,3}>[ ]?")
_LIST_MARKER = re.compile(r"[ \t]*(?:[-*+]|\d+\.)[ \t]+")
_BACKTICKS = re.compile(r"`+")
# A full or collapsed reference link whose brackets are not escaped; an opening
# bracket after a word character (``rows[0][1]``) is an index, not a link.
_REFERENCE = re.compile(r"(?<![\\\]\w])\[((?:[^\[\]\\]|\\.)+)\]\[((?:[^\[\]\\]|\\.)*)\](?!\s*[(:])")
_MAKE_GOAL = re.compile(r"[a-z][a-z0-9_.-]*\Z")
# make options that take a separate argument (``-C dir``) or an optional one (``-j 4``).
_MAKE_ARG = {
    "-C",
    "-f",
    "-I",
    "-o",
    "-W",
    "--directory",
    "--file",
    "--makefile",
    "--include-dir",
    "--old-file",
    "--assume-old",
    "--new-file",
    "--assume-new",
    "--what-if",
}
_MAKE_OPTIONAL_NUMBER = {"-j", "-l", "--jobs", "--load-average", "--max-load"}


@dataclass(frozen=True)
class Link:
    """A followable link: 1-based source line and its raw target."""

    line: int
    target: str


@dataclass(frozen=True)
class Parsed:
    """The parts of a Markdown file the checks need."""

    links: list[Link]
    definitions: list[Link]
    undefined_references: list[Link]
    anchors: set[str]
    code: list[tuple[int, str]]
    unclosed_fences: list[int]
    # Paragraph lines starting with ``#<digit>``, in list items and block quotes
    # too: plain text for CommonMark and GitHub, but an ATX heading for
    # Python-Markdown, which builds the site (cubrid-lab/pycubrid#938).
    hash_digit_lines: list[int] = field(default_factory=list)


def github_slug(text: str) -> str:
    """Return GitHub's base anchor for a heading's rendered text.

    Lowercase; keep letters, marks, numbers, ``_``, ``-`` and spaces; turn each
    space into ``-`` (github-slugger).
    """
    kept = []
    for char in text.lower():
        category = unicodedata.category(char)
        if char in " -_" or category[0] in "LMN" or category == "Pc":
            kept.append(char)
    return "".join(kept).replace(" ", "-")


def _site_slug(text: str) -> str:
    """Return the ``pymdownx.slugs.slugify`` site anchor: GitHub's, without combining marks.

    ``pymdownx.slugs.slugify`` drops marks such as Devanagari vowel signs that
    GitHub keeps.
    """
    return "".join(c for c in github_slug(text) if unicodedata.category(c)[0] != "M")


def default_site_slug(text: str) -> str:
    """Return the anchor of Python-Markdown's default ``toc`` slugify.

    MkDocs uses it when ``mkdocs.yml`` sets no ``slugify`` (cubrid-lab/cubrid-cookbook-python#388):
    accents are dropped and every other non-ASCII character is removed, so
    ``Résumé`` becomes ``resume`` and a Korean heading becomes empty (the site
    then numbers it ``_1``).
    """
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


_CUSTOM_SLUGIFY = re.compile(r"\bpymdownx\.slugs\.\w+")


def site_slugifier(mkdocs_yml: Path) -> Callable[[str], str]:
    """Return the site anchor function that ``mkdocs_yml`` configures for ``toc``.

    A ``pymdownx.slugs`` slugifier selects the GitHub-like slug; no ``slugify``
    (or no ``mkdocs.yml``) selects Python-Markdown's default.
    """
    try:
        config = mkdocs_yml.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default_site_slug
    return _site_slug if _CUSTOM_SLUGIFY.search(config) else default_site_slug


_REPO_SITE_SLUG = site_slugifier(Path(__file__).resolve().parents[1] / "mkdocs.yml")


def _allocate(base: str, used: set[str], separator: str) -> str:
    """Return ``base`` or its first free ``<separator>N`` duplicate suffix."""
    slug, count = base, 0
    while slug in used:
        count += 1
        slug = f"{base}{separator}{count}"
    used.add(slug)
    return slug


_ID_COUNT = re.compile(r"^(.*)_([0-9]+)$")


def _site_unique(slug: str, used: set[str]) -> str:
    """Return the site's id for ``slug``, as Python-Markdown's ``toc`` ``unique()`` does.

    An empty or taken id gets ``_1``, and an id already ending in ``_N`` is
    incremented instead, so ``_1`` is followed by ``_2``, not ``_1_1``.
    """
    while slug in used or not slug:
        match = _ID_COUNT.match(slug)
        slug = f"{match.group(1)}_{int(match.group(2)) + 1}" if match else f"{slug}_1"
    used.add(slug)
    return slug


def _inline_text(token: Token) -> str:
    return "".join(
        child.content for child in token.children or [] if child.type in ("text", "code_inline")
    )


def _mask_code_spans(raw: str) -> str:
    """Replace inline code spans (any backtick run length) by spaces, keeping newlines."""
    out = list(raw)
    position = 0
    while True:
        opening = _BACKTICKS.search(raw, position)
        if opening is None:
            return "".join(out)
        run = opening.group(0)
        closing = re.compile(rf"(?<!`){run}(?!`)").search(raw, opening.end())
        if closing is None:
            position = opening.end()
            continue
        for index in range(opening.start(), closing.end()):
            if out[index] != "\n":
                out[index] = " "
        position = closing.end()


def _tail_newlines(raw: str, child: Token) -> tuple[int, int]:
    """Return the source newlines of a link's or image's tail, and the tail's end."""
    start, end = child.meta.get("tail", (0, 0))
    return raw.count("\n", start, end), end


def _inline_items(token: Token) -> list[tuple[int, Token]]:
    """Return ``(line offset, child)`` for the children of an inline token.

    Soft and hard breaks start a new line. A code span or an inline HTML tag
    that spans lines moves the following children down by its newlines (found
    in the raw source for code spans), and the newlines of a link or image tail
    (its destination and title, or its reference label) move the children after
    the link, since the tail follows the link text.
    """
    raw = token.content
    cursor, offset = 0, 0
    pending_titles: list[tuple[int, int]] = []
    items = []
    for child in token.children or []:
        items.append((offset, child))
        if child.type == "link_open":
            pending_titles.append(_tail_newlines(raw, child))
        elif child.type == "link_close" and pending_titles:
            newlines, end = pending_titles.pop()
            offset += newlines
            cursor = max(cursor, end)
        elif child.type == "image":
            alt_breaks = sum(
                1 for c in child.children or [] if c.type in ("softbreak", "hardbreak")
            )
            newlines, end = _tail_newlines(raw, child)
            offset += alt_breaks + newlines
            cursor = max(cursor, end)
        elif child.type == "html_inline":
            start = raw.find(child.content, cursor)
            if start >= 0:
                cursor = start + len(child.content)
            offset += child.content.count("\n")
        elif child.type in ("softbreak", "hardbreak"):
            newline = raw.find("\n", cursor)
            if newline >= 0:
                cursor = newline + 1
            offset += 1
        elif child.type == "code_inline" and child.markup:
            start = raw.find(child.markup, cursor)
            end = raw.find(child.markup, start + len(child.markup)) if start >= 0 else -1
            if start >= 0 and end >= 0:
                offset += raw.count("\n", start, end)
                cursor = end + len(child.markup)
    return items


def _starts_with_hash_digit(line: str, max_indents: int | None) -> bool:
    """Return whether ``line`` is ``#<digit>`` once its container prefixes are removed.

    Block quote markers, list markers and 4-space list indents are consumed one
    at a time, in any order (``- > #1``, ``> - #1``), at most ``max_indents``
    indents (``None``: any). Each step consumes a fixed prefix and never
    backtracks, so a long run of markers costs linear time.
    """
    position, indents = 0, 0
    while True:
        quote = _QUOTE_MARKER.match(line, position)
        if quote:
            position = quote.end()
            continue
        if (max_indents is None or indents < max_indents) and line.startswith("    ", position):
            position, indents = position + 4, indents + 1
            continue
        item = _LIST_MARKER.match(line, position)
        if item:
            position = item.end()
            continue
        break
    return line[position : position + 1] == "#" and line[position + 1 : position + 2].isdigit()


def _hash_digit_lines(lines: list[str], start: int, end: int) -> list[int]:
    """Return the lines of a paragraph (0-based ``start``..``end``) that Python-Markdown
    renders as a heading: ``#<digit>`` at the start of the line once block quote
    markers, list markers and the list indentation are removed.

    The first line may sit at any list depth (4 spaces each). A continuation line
    is dedented with its paragraph, so it may be indented by at most the first
    line's depth: ``- a`` then ``  #1`` is text, but ``#1`` is a heading.
    """
    if start >= len(lines):
        return []
    prefix = _QUOTE_PREFIX.match(lines[start])
    depth = len(prefix.group(1)) // 4 if prefix else 0
    return [
        number + 1
        for number in range(start, min(end, len(lines)))
        if _starts_with_hash_digit(lines[number], None if number == start else depth)
    ]


def _unclosed_fences(tokens: list[Token]) -> list[int]:
    """Return the opening lines of fences that run to the end of their container.

    markdown-it maps a closed fence to its opening line, its content lines and
    its closing line, and an unclosed one to the opening and content lines
    only. That is exact inside lists and block quotes, and for a line such as
    ``> ~~~`` or an over-indented ``~~~`` that does not close a top-level fence.
    """
    unclosed = []
    for token in tokens:
        if token.type != "fence" or token.map is None:
            continue
        start, end = token.map
        if end - start != len(token.content.splitlines()) + 2:
            unclosed.append(start + 1)
    return unclosed


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _parsed_spans(children: list[Token], source: str, base: int = 0) -> list[tuple[int, int]]:
    """Return the source spans of the inline HTML, autolinks and inline link tails.

    Only what markdown-it parsed counts: a tag, a comment or an autolink, and the
    ``(dest "title")`` tail of a link or an image that is a link. An image's alt
    text is parsed on its own, from the image's label, so the spans of its
    children are moved by the label's start (``base``) into ``source``.
    """
    spans = []
    for child in children:
        span = None
        if child.type == "html_inline" or child.markup == "autolink":
            span = child.meta.get("span")
        elif child.type in ("link_open", "image"):
            span = child.meta.get("tail")
            if span and source[base + span[0] : base + span[0] + 1] != "(":
                span = None  # a reference link: its label is checked below
        if span:
            spans.append((base + span[0], base + span[1]))
        if child.type == "image" and child.children and "span" in child.meta:
            label_start = base + child.meta["span"][0] + 2  # after "!["
            spans += _parsed_spans(child.children, source, label_start)
    return spans


def _undefined_references(token: Token, defined: set[str]) -> list[Link]:
    """Return unescaped ``[text][label]`` uses, outside code, whose label is undefined.

    Code spans, and the inline HTML (tags, comments), autolinks and inline link
    destinations and titles that markdown-it parsed, are blanked first at their
    source positions, so brackets in a URL, a title or a tag are not links. Text
    that only looks like a link tail or a tag stays, and is checked.
    """
    if token.map is None:
        return []
    raw = _mask_code_spans(token.content)
    for start, end in _parsed_spans(token.children or [], token.content):
        raw = raw[:start] + _blank(raw[start:end]) + raw[end:]
    found = []
    for match in _REFERENCE.finditer(raw):
        label = " ".join((match.group(2) or match.group(1)).split()).casefold()
        if label not in defined:
            line = token.map[0] + 1 + raw.count("\n", 0, match.start())
            found.append(Link(line, f"[{label}]"))
    return found


class _HtmlAttributes(HTMLParser):
    """Collect link targets and ``<a>`` anchors from HTML, as a browser parses it.

    The standard library parser reads quoted and unquoted attribute values,
    decodes entities and skips comments, so ``data-src`` is not ``src``.
    """

    TARGETS = {"a": "href", "img": "src", "source": "src"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[int, str]] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value for name, value in attrs if value is not None}
        wanted = self.TARGETS.get(tag)
        if wanted and values.get(wanted):
            self.targets.append((self.getpos()[0], values[wanted]))
        if tag == "a":
            self.anchors |= {values[name] for name in ("id", "name") if values.get(name)}

    handle_startendtag = handle_starttag


def _html_parse(source: str) -> _HtmlAttributes:
    parser = _HtmlAttributes()
    parser.feed(source)
    parser.close()
    return parser


def _html_targets(line: int, source: str) -> list[Link]:
    """Return ``href``/``src`` targets of HTML, outside comments, with their lines."""
    return [Link(line + row - 1, target) for row, target in _html_parse(source).targets]


def _html_anchors(tokens: list[Token]) -> set[str]:
    """Return ``<a id>``/``<a name>`` anchors of HTML blocks and inline HTML, not comments."""
    found: set[str] = set()
    for token in tokens:
        sources = [token.content] if token.type == "html_block" else []
        if token.type == "inline":
            sources += [c.content for c in token.children or [] if c.type == "html_inline"]
        for source in sources:
            found |= _html_parse(source).anchors
    return found


def parse(path: Path, site_slug: Callable[[str], str] | None = None) -> Parsed:
    """Parse one Markdown file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    env: dict[str, object] = {}
    tokens = _PARSER.parse(text, env)
    references = env.get("references", {})
    references = references if isinstance(references, dict) else {}
    defined = {" ".join(str(label).split()).casefold() for label in references}
    links: list[Link] = []
    code: list[tuple[int, str]] = []
    undefined: list[Link] = []
    # GitHub keeps a literal ``{#id}`` in its slug and suffixes duplicates with
    # -1, -2 ...; the MkDocs site (attr_list, toc) uses the id and _1, _2 ...
    github_used: set[str] = set()
    site_used: set[str] = set()
    anchors = _html_anchors(tokens)
    hash_digit_lines: list[int] = []
    for index, token in enumerate(tokens):
        if token.map is None:
            continue
        line = token.map[0] + 1
        if token.type == "inline" and index and tokens[index - 1].type == "paragraph_open":
            hash_digit_lines += _hash_digit_lines(lines, token.map[0], token.map[1])
        if token.type == "fence":
            code += _logical_lines(line + 1, token.content.splitlines())
            continue
        if token.type == "html_block":
            links += _html_targets(line, token.content)
            continue
        if token.type != "inline":
            continue
        for offset, child in _inline_items(token):
            if child.type == "link_open":
                links.append(Link(line + offset, str(child.attrGet("href") or "")))
            elif child.type == "image":
                links.append(Link(line + offset, str(child.attrGet("src") or "")))
            elif child.type == "code_inline":
                code.append((line + offset, child.content))
            elif child.type == "html_inline":
                links += _html_targets(line + offset, child.content)
        undefined += _undefined_references(token, defined)
        if index and tokens[index - 1].type == "heading_open":
            heading = _inline_text(token).strip()
            anchors.add(_allocate(github_slug(heading), github_used, "-"))
            explicit = _ATTR_ID.search(heading)
            if explicit:
                anchors.add(explicit.group(1))
                site_used.add(explicit.group(1))
            else:
                anchors.add(_site_unique((site_slug or _REPO_SITE_SLUG)(heading), site_used))
    definitions = []
    for label, ref in references.items():
        if isinstance(ref, dict):
            map_ = ref.get("map")
            number = map_[0] + 1 if map_ else _definition_line(lines, str(label))
            definitions.append(Link(number, str(ref.get("href", ""))))
    return Parsed(
        links=links,
        definitions=definitions,
        undefined_references=undefined,
        anchors=anchors,
        code=sorted(code),
        unclosed_fences=_unclosed_fences(tokens),
        hash_digit_lines=hash_digit_lines,
    )


def _continues(text: str) -> str:
    """Return how shell ``text`` continues on the next line.

    ``"backslash"``: an unescaped backslash is the very last character, outside
    single quotes (where a backslash is literal); ``\\\\`` at the end, or a
    backslash followed by spaces, does not continue. ``"quote"``: a quote is
    still open, so the newline is part of the quoted text. ``""``: the command
    ends here. A backslash or a quote in a comment continues nothing; ``#``
    starts a comment only at the start of a word, so not after ``x\\ `` (an
    escaped space keeps the word open), a closing quote or a balanced
    ``$(...)``, ``<(...)`` or ``>(...)`` substitution.
    """
    quote = ""
    in_word = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote == "'":
            quote = "" if char == "'" else quote
        elif char == "\\":
            if index == len(text) - 1:
                return "backslash"
            index += 1
            in_word = True
        elif quote:
            quote = "" if char == quote else quote
        elif (
            char in "$<>"
            and text.startswith("(", index + 1)
            and _substitution_end(text, index + 1) > 0
        ):
            # a balanced substitution is part of the word: ``$(x)#y`` is no comment
            index, in_word = _substitution_end(text, index + 1), True
            continue
        elif char in "'\"":
            quote, in_word = char, True
        elif char in " \t\n;&|()<>":
            in_word = False
        elif char == "#" and not in_word:
            return ""  # a comment: a backslash in it does not continue the line
        else:
            in_word = True
        index += 1
    return "quote" if quote else ""


def _logical_lines(first: int, lines: list[str]) -> list[tuple[int, str]]:
    """Join continued lines into one command, reported at its first line.

    The shell removes the backslash-newline pair and nothing else, so the
    fragments are concatenated as they are: ``check-\\`` + ``all`` is ``check-all``.
    A newline inside an open quote is quoted text, so it is kept and the quoted
    lines (``echo 'a``, ``make x``, ``b'``) stay one command. A quote that the
    block never closes is not shell (prose such as ``don't``): the command ends
    at that line, and the lines after it are read again, also when the block's
    last line ends with a backslash.
    """
    result: list[tuple[int, str]] = []
    position = 0
    while position < len(lines):
        start, joined, state, resume = position, "", "", 0
        while position < len(lines):
            joined += lines[position]
            position += 1
            state = _continues(joined)
            if state == "backslash":
                joined = joined[:-1]
            elif state == "quote":
                resume = resume or position
                joined += "\n"
            else:
                break
        if state and _continues(joined) == "quote":
            # never closed: end the command at the quote's line, rescan the rest
            joined, position = joined.split("\n", 1)[0], resume or start + 1
        result.append((first + start, joined))
    return result


def _definition_line(lines: list[str], label: str) -> int:
    pattern = re.compile(rf"^ {{0,3}}\[{re.escape(label)}\]:", re.I)
    for number, line in enumerate(lines, 1):
        if pattern.match(line):
            return number
    return 1


_OPERATOR_CHARS = frozenset(";&|()<>")
# Shell operators, longest first: adjacent ones (``;>``) are separate tokens.
_OPERATORS = (
    "<<<",
    "&>>",
    "&&",
    "||",
    ";;",
    "<<",
    ">>",
    "&>",
    ">&",
    "<&",
    ">|",
    "<>",
    ";",
    "&",
    "|",
    "(",
    ")",
    "<",
    ">",
)


def _substitution_end(command: str, index: int) -> int:
    """Return the index after the ``)`` that closes the ``(`` at ``index``, or ``-1``.

    Nested parentheses, quotes and backslash escapes inside are honoured.
    """
    depth, size = 0, len(command)
    while index < size:
        char = command[index]
        if char == "\\":
            index += 2
            continue
        if char in "'\"":
            end = index + 1
            while end < size and command[end] != char:
                end += 2 if char == '"' and command[end] == "\\" else 1
            if end >= size:
                return -1
            index = end + 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return -1


def _shell_tokens(command: str, substitutions: list[str] | None = None) -> list[tuple[str, bool]]:
    """Split a shell command into ``(text, is_operator)`` tokens.

    Quotes and backslashes make text literal, so a quoted or escaped ``;`` is
    a word, not a separator. ``#`` starts a comment at the start of a word.
    A command or process substitution (``$(...)``, ``<(...)``, ``>(...)``) is
    part of its word; its body goes to ``substitutions``, if given, as a
    command of its own. An unbalanced quote or substitution means the text is
    not a shell command: no tokens.
    """
    tokens: list[tuple[str, bool]] = []
    word: list[str] = []
    in_word = False
    index, size = 0, len(command)

    def flush() -> None:
        nonlocal in_word
        if in_word:
            tokens.append(("".join(word), False))
            word.clear()
            in_word = False

    while index < size:
        char = command[index]
        if char in " \t\n":
            flush()
            index += 1
        elif char == "#" and not in_word:
            break
        elif char == "\\":
            word.append(command[index + 1 : index + 2])
            in_word = True
            index += 2
        elif char in "'\"":
            end = index + 1
            while end < size and command[end] != char:
                end += 2 if char == '"' and command[end] == "\\" else 1
            if end >= size:
                return []
            text = command[index + 1 : end]
            word.append(re.sub(r'\\(["\\$`])', r"\1", text) if char == '"' else text)
            in_word = True
            index = end + 1
        elif char in "$<>" and command.startswith("(", index + 1):
            end = _substitution_end(command, index + 1)
            if end < 0:
                return []
            if substitutions is not None:
                substitutions.append(command[index + 2 : end - 1])
            word.append(command[index:end])
            in_word = True
            index = end
        elif char in _OPERATOR_CHARS:
            flush()
            operator = next(op for op in _OPERATORS if command.startswith(op, index))
            tokens.append((operator, True))
            index += len(operator)
        else:
            word.append(char)
            in_word = True
            index += 1
    flush()
    return tokens


def make_goals(command: str) -> list[str]:
    """Return the explicit goals of every ``make`` invocation in a command line.

    Separators (``;``, ``&&``, ``||``, ``|``, ``&``, parentheses) end an
    invocation, with or without spaces, but only outside quotes. Redirections
    (``>``, ``2>&1``, ``<``) are skipped with their operand, options with
    their arguments (``-C dir``, ``--directory=dir``, ``-j 4``), and
    ``VAR=value`` assignments; every other operand is a goal.
    """
    goals = []
    substitutions: list[str] = []
    tokens = _shell_tokens(command, substitutions)
    # ``make`` counts only as the command word of a simple command, after any
    # ``VAR=value`` prefixes: ``echo make test`` names no goal.
    index, in_make, at_start = 0, False, True
    while index < len(tokens):
        token, operator = tokens[index]
        index += 1
        if operator:
            if "<" in token or ">" in token:
                index += 1  # the redirection's operand
            else:
                in_make, at_start = False, True
            continue
        if not in_make:
            if at_start and "=" in token and not token.startswith("-"):
                continue  # an environment prefix: the command word is still ahead
            in_make, at_start = at_start and token == "make", False
            continue
        if token in _MAKE_ARG:
            index += 1
        elif token in _MAKE_OPTIONAL_NUMBER:
            if index < len(tokens) and tokens[index][0].isdigit():
                index += 1
        elif token.startswith("-") or "=" in token:
            continue
        elif _MAKE_GOAL.match(token):
            goals.append(token)
    for body in substitutions:  # a substitution runs its own commands
        goals += make_goals(body)
    return goals


def is_external(target: str) -> bool:
    """Return whether a target is a URL: a scheme (``https:``, ``mailto:``) or ``//host``."""
    return target.startswith("//") or bool(re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target))
