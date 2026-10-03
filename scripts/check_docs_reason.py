r"""Recognize a real standalone docs exception, outside Markdown examples.

>>> has_docs_not_needed_reason(None)
False
>>> has_docs_not_needed_reason('Docs: not needed - tests only')
True
>>> has_docs_not_needed_reason('Docs: not needed - <reason>')
False
>>> has_docs_not_needed_reason('> Docs: not needed - tests only')
False
>>> has_docs_not_needed_reason('````text\n```\nDocs: not needed - tests only\n````')
False
>>> has_docs_not_needed_reason('<!--\nDocs: not needed - tests only\n-->')
False
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from string import punctuation
from unicodedata import category

_PREFIX = "Docs: not needed -"
_MARKDOWN_ESCAPE = re.compile(r"\\([" + re.escape(punctuation) + r"])")
_AUTOLINK = (
    r"<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\x00-\x20\x7f<>]*"
    r"|[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)>"
)
_LITERAL_RUN = re.compile(r"`+|\\+|\[[^\[\]\n\\`<>]*\]\(<[^<>\n]*>\)|" + _AUTOLINK)
_BLOCK_PREFIX = r" {0,3}(?:(?:[-+*]|[0-9]{1,9}[.)])[ \t]+)?"
_LIST_PREFIX = r" {0,3}([-+*]|[0-9]{1,9}[.)])[ \t]+"
_LINK_DESTINATION = r"(?:[^\s()<>]+|<[^<>\r\n]*>)"
_LINK_TITLE = r"""(?:"[^"\r\n]*"|'[^'\r\n]*'|\([^()\r\n]*\))"""
_LINK_TARGET = (
    r"\([ \t]*(?:"
    + _LINK_DESTINATION
    + r"(?:[ \t]+"
    + _LINK_TITLE
    + r")?|"
    + _LINK_TITLE
    + r")?[ \t]*\)"
)
_CAPTION_ONLY = re.compile(r"!?\[([^\[\]\r\n]*)\](?:" + _LINK_TARGET + r"|\[[^\[\]\r\n]*\])?")
_ATX_HEADING = r" {0,3}#{1,6}(?=[ \t\n]|$)"
_THEMATIC_BREAK = r" {0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})"
_HTML_BLOCK_START = re.compile(
    r" {0,3}(?:<!--|<\?|(?-i:<![A-Z]|<!\[CDATA\[)|<(?:pre|script|style|textarea)(?=[ \t>]|$)"
    r"|</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup"
    r"|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset"
    r"|h1|h2|h3|h4|h5|h6|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav"
    r"|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th"
    r"|thead|title|tr|track|ul)(?=[ \t>]|/>|$))",
    re.IGNORECASE | re.ASCII,
)


def _paragraph_line(line: str) -> bool:
    marker = re.match(_BLOCK_PREFIX + r"(`{3,}|~{3,})", line)
    block = (
        re.match(_ATX_HEADING, line)
        or re.match(_BLOCK_PREFIX + ">", line)
        or re.match(_LIST_PREFIX, line)
        or re.fullmatch(_THEMATIC_BREAK, line)
        or _HTML_BLOCK_START.match(line)
        or (marker and (marker[1][0] == "~" or "`" not in line[marker.end() :]))
    )
    return bool(line.strip(" \t") and not re.match(r"(?: {4,}| {0,3}\t)", line) and not block)


def _list_boundary(line: str, base: int = 0) -> bool:
    prefix = re.match(_LIST_PREFIX, line)
    if prefix is None or not line[prefix.end() :].strip(" \t"):
        return False
    indentation = len(line) - len(line.lstrip(" "))
    marker = prefix[1]
    return bool((base and indentation < base) or marker in "-+*" or int(marker[:-1]) == 1)


def _prefixed_boundary(line: str, base: int = 0) -> bool:
    return re.match(_LIST_PREFIX, line) is None or _list_boundary(line, base)


def _reason_text(text: str) -> str:
    return "".join(
        character
        for character in text
        if category(character) not in {"Cc", "Cf"}
        and character != "\u034f"
        and character not in "\u180b\u180c\u180d\u180f"
        and not ("\ufe00" <= character <= "\ufe0f" or "\U000e0100" <= character <= "\U000e01ef")
    ).strip()


def _empty_caption(raw: str, visible: str | None = None) -> bool:
    original = _CAPTION_ONLY.fullmatch(_reason_text(raw))
    if original is None:
        return False
    caption = original if visible is None else _CAPTION_ONLY.fullmatch(_reason_text(visible))
    return caption is not None and not _reason_text(unescape(caption[1]))


def _empty_emphasis(raw_segment: str, text_segment: str) -> bool:
    """True when a whole-segment emphasis wrapper (``**...**``, ``_..._``, ...)
    surrounds otherwise-empty content, e.g. a caption reading only
    ``**<!-- empty -->**`` (#429): the delimiters alone are not visible
    explanatory text.
    """
    wrapper = re.fullmatch(r"(\*{1,3}|_{1,3})(.+)\1", raw_segment.strip())
    if wrapper is None:
        return False
    inner = wrapper[2]
    if (
        inner[0].isspace()
        or inner[-1].isspace()
        or inner[0] == wrapper[1][0]
        or inner[-1] == wrapper[1][0]
    ):
        return False
    closing_escape = re.search(r"\\+$", inner)
    if closing_escape and len(closing_escape[0]) % 2:
        return False
    leading = len(raw_segment) - len(raw_segment.lstrip())
    return not _reason_text(
        unescape(text_segment[leading + wrapper.start(2) : leading + wrapper.end(2)])
    )


def _empty_composition(text: str, raw: str, origin: int, spans: list[tuple[int, int]]) -> bool:
    while True:
        reduced = list(text)
        changed = False
        for token in _CAPTION_ONLY.finditer(text):
            start, end = origin + token.start(), origin + token.end()
            escaped = re.search(r"\\+$", text[: token.start()])
            populated = _reason_text(unescape(token[1])) and not _empty_emphasis(
                raw[token.start(1) : token.end(1)], token[1]
            )
            if (
                populated
                or (escaped and len(escaped[0]) % 2)
                or any(left < end and start < right for left, right in spans)
            ):
                continue
            reduced[token.start() : token.end()] = " " * len(token[0])
            changed = True
        if not changed:
            if not _reason_text(unescape(text)):
                return True
            if any(left < origin + len(raw) and origin < right for left, right in spans):
                return False
            return _empty_emphasis(raw, text)
        text = "".join(reduced)


def _placeholder(text: str) -> bool:
    raw = _reason_text(text)
    if raw.startswith("!["):
        text = raw[1:]
    reason = _reason_text(unescape(_MARKDOWN_ESCAPE.sub(r"\1", text)))
    index = 0
    closers: list[str] = []
    while True:
        while index < len(reason) and reason[index] in " \t":
            index += 1
        if reason.startswith("<reason>", index):
            index += len("<reason>")
            break
        if index == len(reason):
            return False
        character = reason[index]
        if character in "[(":
            closers.append("]" if character == "[" else ")")
            index += 1
        elif character in "`*_~":
            end = index + 1
            while end < len(reason) and reason[end] == character:
                end += 1
            width = end - index
            if (character in "*_" and width > 3) or (character == "~" and width > 2):
                return False
            closers.append(reason[index:end])
            index = end
        else:
            return False
    for closer in reversed(closers):
        while index < len(reason) and reason[index] in " \t":
            index += 1
        if not reason.startswith(closer, index):
            return False
        index += len(closer)
        if closer[0] in "`*_~" and index < len(reason) and reason[index] == closer[0]:
            return False
    return True


class _HTMLContext(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.blocked: list[str] = []
        self.lines: dict[int, str] = {}
        self.syntax_lines: dict[int, list[str]] = {}
        self.marker_lines: set[int] = set()
        self.literal_positions: set[tuple[int, int]] = set()
        self.source = source
        self.paragraph_base = 0
        self.fed_text = ""
        self.parser_text = ""
        self.row_starts: list[int] = [0]
        self.comment_start: int | None = None
        self.comment_end: int | None = None
        self.comment_scan = 0
        self.comment_marker = "-->"
        self.comment_width = 4
        self.inline_end = -1
        self.inline_spans: list[tuple[int, int]] = []

    def feed(self, data: str) -> None:
        cursor = 0
        while cursor < len(data):
            end = data.find(">", cursor)
            end = len(data) if end == -1 else end + 1
            fragment = data[cursor:end]
            close = self.strict_close()
            original = fragment
            if self.blocked and self.blocked[-1] == "pre":
                fragment = fragment.replace("<!-->", " !-->")
            if self.comment_start is not None and (close is None or len(self.fed_text) < close):
                fragment = fragment.replace("<", " ").replace("&", " ")
            base = len(self.fed_text)
            self.row_starts.extend(base + match.end() for match in re.finditer("\n", original))
            self.fed_text += original
            self.parser_text += fragment
            super().feed(fragment)
            cursor = end

    def position(self) -> int:
        line, column = self.getpos()
        return self.row_starts[line - 1] + column

    def strict_close(self) -> int | None:
        if self.comment_start is not None and self.comment_end is None:
            close = self.fed_text.find(self.comment_marker, self.comment_scan)
            if close == -1:
                self.comment_scan = max(
                    self.comment_start + self.comment_width,
                    len(self.fed_text) - len(self.comment_marker) + 1,
                )
            else:
                self.comment_end = close + len(self.comment_marker)
        return self.comment_end

    def inside_comment(self) -> bool:
        if self.comment_start is None:
            return False
        close = self.strict_close()
        if close is None or self.position() < close:
            return True
        self.comment_start = None
        self.comment_end = None
        return False

    def confirm_comment(self) -> None:
        if self.blocked or self.inside_comment():
            return
        line, column = self.getpos()
        start = self.position()
        prefix = self.fed_text[self.row_starts[line - 1] : start]
        opener = None
        for token, end_marker in (("<!--", "-->"), ("<?", "?>"), ("<![CDATA[", "]]>")):
            if self.fed_text.startswith(token, start):
                opener = token, end_marker
                break
        if opener is None and re.match(r"<![A-Z]", self.fed_text[start:]):
            opener = "<!", ">"
        if column <= 3 and not prefix.strip(" ") and opener:
            self.comment_start = start
            self.comment_end = None
            self.comment_width = len(opener[0])
            self.comment_marker = opener[1]
            self.comment_scan = start + self.comment_width

    def handle_comment(self, data: str) -> None:
        self.confirm_comment()

    def handle_pi(self, data: str) -> None:
        self.confirm_comment()

    def handle_decl(self, data: str) -> None:
        self.confirm_comment()

    def unknown_decl(self, data: str) -> None:
        self.confirm_comment()

    def checkpoint(self) -> None:
        line, column = self.getpos()
        start = self.row_starts[line - 1] + column
        pending = self.parser_text[start:]
        safe = "<" not in pending and "&" not in pending
        if pending.startswith("<!--"):
            closer = pending.rfind("-->")
            tail = pending[closer + 3 :]
            safe = closer > pending.rfind("<!--") and "<" not in tail and "&" not in tail
        elif (
            pending.startswith("<?")
            or pending.startswith("<![CDATA[")
            or re.match(r"<![A-Z]", pending)
        ):
            if pending.startswith("<?"):
                marker, width = "?>", 2
            elif pending.startswith("<![CDATA["):
                marker, width = "]]>", 9
            else:
                marker, width = ">", 2
            closer = pending.find(marker, width)
            tail = pending[closer + len(marker) :]
            safe = closer != -1 and "<" not in tail and "&" not in tail
        elif pending.startswith("&#"):
            numeric = re.match(r"&#(?:[xX][0-9a-fA-F]*|[0-9]*)\n", pending)
            if numeric:
                tail = pending[numeric.end() :]
                safe = "<" not in tail and "&" not in tail
        if pending and safe:
            self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.inside_comment():
            return
        if tag in {"blockquote", "pre", "code", "script", "style", "textarea", "iframe"}:
            self.blocked.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # These non-void containers still need an explicit closing tag in HTML.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self.inside_comment():
            return
        if self.blocked and self.blocked[-1] == tag:
            self.blocked.pop()

    def handle_data(self, data: str) -> None:
        self.collect_data(data)

    def project_data(self, data: str, line: int, column: int) -> None:
        for offset, text in enumerate(data.split("\n")):
            row = self.syntax_lines.setdefault(line + offset, [])
            origin = column if offset == 0 else 0
            if len(row) < origin + len(text):
                row.extend(" " * (origin + len(text) - len(row)))
            row[origin : origin + len(text)] = text

    def collect_data(self, data: str, project: bool = True) -> None:
        if not self.blocked:
            if data.startswith("<"):
                self.confirm_comment()
            line, column = self.getpos()
            if self.comment_start is not None:
                close = self.strict_close()
                if close is None:
                    return
                ignored = close - self.position()
                if ignored >= len(data):
                    return
                if ignored > 0:
                    removed = data[:ignored]
                    line += removed.count("\n")
                    column = (
                        len(removed) - removed.rfind("\n") - 1
                        if "\n" in removed
                        else column + ignored
                    )
                    data = data[ignored:]
                self.comment_start = None
                self.comment_end = None
            if project:
                self.project_data(data, line, column)
            for offset, text in enumerate(data.split("\n")):
                number = line + offset
                self.lines[number] = self.lines.get(number, "") + text
                indentation = len(text) - len(text.lstrip(" "))
                origin = column if offset == 0 else 0
                if origin + indentation <= 3 and text.lstrip(" ").startswith(_PREFIX):
                    self.marker_lines.add(number)
                for index, character in enumerate(text):
                    if character in "`\\[":
                        self.literal_positions.add((number, origin + index))

    def handle_entityref(self, name: str) -> None:
        if self.inside_comment():
            return
        self.project_reference(name, 1)
        self.collect_data(unescape(f"&{name};").replace("\r", " ").replace("\n", " "), False)

    def handle_charref(self, name: str) -> None:
        if self.inside_comment():
            return
        self.project_reference(name, 2)
        self.collect_data(unescape(f"&#{name};").replace("\r", " ").replace("\n", " "), False)

    def project_reference(self, name: str, width: int) -> None:
        if self.blocked:
            return
        line, column = self.getpos()
        start = self.position()
        end = start + width + len(name)
        if self.fed_text[end : end + 1] == ";":
            end += 1
        self.project_data(self.fed_text[start:end], line, column)

    def outside_prefix(self, number: int, prefix: str) -> bool:
        self.feed(prefix)
        self.checkpoint()
        return not self.blocked and self.lines.get(number) == prefix

    def feed_literals(self, text: str, number: int, column: int, offset: int) -> None:
        cursor = 0
        while cursor < len(text):
            if offset + cursor < self.inline_end:
                end = min(len(text), self.inline_end - offset)
                self.feed(text[cursor:end].replace("<", " ").replace("&", " "))
                cursor = end
                continue
            run = _LITERAL_RUN.search(text, cursor)
            if run is None:
                self.feed(text[cursor:])
                break
            if run[0][0] == "<":
                self.feed(text[cursor : run.start()])
                self.checkpoint()
                outside = (
                    not self.blocked
                    and not self.inside_comment()
                    and self.getpos() == (number, column + run.start())
                )
                self.feed(run[0].replace("<", " ").replace("&", " ") if outside else run[0])
                cursor = run.end()
                continue
            if run[0][0] == "[":
                self.feed(text[cursor : run.start() + 1])
                self.checkpoint()
                escaped = re.search(r"\\+$", self.source[: offset + run.start()])
                outside = (
                    not self.blocked and (number, column + run.start()) in self.literal_positions
                )
                literal = outside and (escaped is None or len(escaped[0]) % 2 == 0)
                destination = run[0].index("](<") + 2
                self.feed(run[0][1:destination])
                tail = run[0][destination:]
                self.feed(tail.replace("<", " ").replace("&", " ") if literal else tail)
                cursor = run.end()
                continue
            self.feed(text[cursor : run.end()])
            self.checkpoint()
            outside = not self.blocked and (number, column + run.start()) in self.literal_positions
            cursor = run.end()
            if not outside:
                continue
            if run[0][0] == "\\":
                if len(run[0]) % 2 and cursor < len(text) and text[cursor] in "<`":
                    self.feed(" " if text[cursor] == "<" else "`")
                    cursor += 1
                continue
            start = offset + cursor
            paragraph = re.search(r"\n[ \t]*\n", self.source[start:])
            limit = start + paragraph.start() if paragraph else len(self.source)
            for quote_boundary in re.finditer(
                r"\n" + _BLOCK_PREFIX + r">[^\n]*", self.source[start:limit]
            ):
                if _prefixed_boundary(quote_boundary[0][1:], self.paragraph_base):
                    limit = start + quote_boundary.start() + 1
                    break
            heading = re.search(r"\n" + _ATX_HEADING, self.source[start:limit])
            if heading:
                limit = start + heading.start() + 1
            thematic = re.search(r"\n" + _THEMATIC_BREAK + r"(?=\n|$)", self.source[start:limit])
            if thematic:
                limit = start + thematic.start() + 1
            html_boundary = re.search(
                r"\n" + _HTML_BLOCK_START.pattern,
                self.source[start:limit],
                _HTML_BLOCK_START.flags,
            )
            if html_boundary:
                limit = start + html_boundary.start() + 1
            for item in re.finditer(r"\n" + _LIST_PREFIX + r"[^\n]*", self.source[start:limit]):
                if _list_boundary(item[0][1:], self.paragraph_base):
                    limit = start + item.start() + 1
                    break
            base = self.paragraph_base
            for setext in re.finditer(
                r"\n([ \t]*)(?:=+|-+)[ \t]*(?=\n|$)", self.source[start:limit]
            ):
                if not base <= len(setext[1].expandtabs(4)) <= base + 3:
                    continue
                underline_offset = start + setext.start()
                previous = self.source[
                    self.source.rfind("\n", 0, underline_offset) + 1 : underline_offset
                ].expandtabs(4)
                if base and len(previous) - len(previous.lstrip(" ")) >= base:
                    previous = previous[base:]
                if _paragraph_line(previous):
                    limit = underline_offset + 1
                    break
            for boundary in re.finditer(
                r"\n" + _BLOCK_PREFIX + r"(`{3,}|~{3,})([^\n]*)", self.source[start:limit]
            ):
                if _prefixed_boundary(boundary[0][1:], self.paragraph_base) and (
                    boundary[1][0] == "~" or "`" not in boundary[2]
                ):
                    limit = start + boundary.start() + 1
                    break
            closing = next(
                (
                    match
                    for match in re.finditer(r"`+", self.source[start:limit])
                    if len(match[0]) == len(run[0])
                ),
                None,
            )
            if closing is not None:
                self.inline_end = start + closing.end()
                self.inline_spans.append((offset + run.start(), self.inline_end))


def has_docs_not_needed_reason(body: str | None) -> bool:
    prefix = _PREFIX
    raw_lines = re.split(r"\r\n|\r|\n", body or "")
    html = _HTMLContext("\n".join(raw_lines))
    candidates = []
    fence = None
    quoted = False
    quote_fence: tuple[str, int] | None = None
    offset = 0
    for number, raw in enumerate(raw_lines, 1):
        origin = offset
        offset += len(raw) + 1
        line = raw.rstrip()
        stripped = line.lstrip()
        opener = re.match(_BLOCK_PREFIX + r"(`{3,}|~{3,})", line)
        quote = re.match(_BLOCK_PREFIX + ">", line)
        if quote_fence and not quote:
            quote_fence = None
            quoted = False
        if origin < html.inline_end:
            html.feed_literals(line + "\n", number, 0, origin)
            continue
        if html.paragraph_base:
            expanded = line.expandtabs(4)
            leading_width = len(expanded) - len(expanded.lstrip(" "))
            content = (
                expanded[html.paragraph_base :]
                if leading_width >= html.paragraph_base
                else expanded
            )
            if not _paragraph_line(content):
                html.paragraph_base = 0
        if fence and fence[2] > 0 and raw.strip(" \t"):
            leading = raw[: len(raw) - len(raw.lstrip(" \t"))]
            if len(leading.expandtabs(4)) < fence[2]:
                fence = None
        if fence:
            html.paragraph_base = 0
            marker = re.match(r"[ \t]*(`{3,}|~{3,})", line)
            fence_indent = len(line[: marker.start(1)].expandtabs(4)) if marker else -1
            if (
                marker
                and fence[2] <= fence_indent <= fence[2] + 3
                and marker[1][0] == fence[0]
                and len(marker[1]) >= fence[1]
            ):
                if not line[marker.end() :].strip():
                    fence = None
            html.feed("\n")
            continue
        if not stripped:
            quoted = False
        if quoted and re.fullmatch(r" {0,3}>[ \t]*", line):
            quoted = False
            html.feed("\n")
            continue
        if quoted and (
            re.match(_ATX_HEADING, line)
            or re.fullmatch(_THEMATIC_BREAK, raw)
            or _HTML_BLOCK_START.match(line)
            or _list_boundary(line)
            or (
                opener
                and _prefixed_boundary(line)
                and (opener[1][0] == "~" or "`" not in line[opener.end() :])
            )
        ):
            quoted = False
        if quoted and not _prefixed_boundary(line):
            quote = None
        if quoted and not quote:
            html.paragraph_base = 0
            html.feed("\n")
            continue
        indentation = re.match(r"(?: {4,}| {0,3}\t)", line)
        if indentation:
            leading = line[: len(line) - len(line.lstrip(" \t"))]
            relative = len(leading.expandtabs(4)) - html.paragraph_base
            if html.paragraph_base and 0 <= relative <= 3:
                html.feed_literals(line + "\n", number, 0, origin)
            elif html.outside_prefix(number, line[: indentation.end()]):
                html.feed("\n")
                continue
            else:
                html.feed_literals(
                    line[indentation.end() :] + "\n",
                    number,
                    indentation.end(),
                    origin + indentation.end(),
                )
        elif quote:
            html.paragraph_base = 0
            if html.outside_prefix(number, line[: quote.end()]):
                content = line[quote.end() :]
                raw_content = raw[quote.end() :]
                if content.startswith(" "):
                    content = content[1:]
                if raw_content.startswith(" "):
                    raw_content = raw_content[1:]
                marker = re.match(r" {0,3}(`{3,}|~{3,})", content)
                if quote_fence:
                    if (
                        marker
                        and marker[1][0] == quote_fence[0]
                        and len(marker[1]) >= quote_fence[1]
                        and not content[marker.end() :].strip(" \t")
                    ):
                        quote_fence = None
                    quoted = False
                elif marker and (marker[1][0] == "~" or "`" not in content[marker.end() :]):
                    quote_fence = (marker[1][0], len(marker[1]))
                    quoted = False
                else:
                    quoted = (
                        re.match(_ATX_HEADING, content) is None
                        and re.fullmatch(_THEMATIC_BREAK, raw_content) is None
                        and not (quoted and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", raw_content))
                    )
                html.feed("\n")
                continue
            html.feed_literals(
                line[quote.end() :] + "\n", number, quote.end(), origin + quote.end()
            )
        elif opener and (opener[1][0] == "~" or "`" not in line[opener.end() :]):
            html.paragraph_base = 0
            if html.outside_prefix(number, line[: opener.end()]):
                list_item = re.match(_LIST_PREFIX, line)
                base = len(line[: opener.start(1)].expandtabs(4)) if list_item else 0
                fence = (opener[1][0], len(opener[1]), base)
                html.feed("\n")
                continue
            html.feed_literals(
                line[opener.end() :] + "\n", number, opener.end(), origin + opener.end()
            )
        else:
            list_item = re.match(_LIST_PREFIX, line)
            if list_item:
                visible = html.outside_prefix(number, line[: list_item.end()])
                html.paragraph_base = (
                    len(line[: list_item.end()].expandtabs(4))
                    if visible and _paragraph_line(line[list_item.end() :])
                    else 0
                )
                html.feed_literals(
                    line[list_item.end() :] + "\n",
                    number,
                    list_item.end(),
                    origin + list_item.end(),
                )
            else:
                html.feed_literals(line + "\n", number, 0, origin)
        if re.match(r" {0,3}" + re.escape(prefix), line):
            html.checkpoint()
            position = origin + len(line) - len(line.lstrip(" "))
            raw_reason = line.lstrip(" ")[len(prefix) :]
            if not _placeholder(raw_reason) and not _empty_caption(raw_reason):
                candidates.append((number, position))
    html.checkpoint()
    for number, position in candidates:
        line = html.lines.get(number, "").lstrip(" ")
        projected = "".join(html.syntax_lines.get(number, [])).lstrip(" ")
        inside = any(start <= position < end for start, end in html.inline_spans)
        if not inside and number in html.marker_lines and line.startswith(prefix):
            reason = _reason_text(line[len(prefix) :])
            syntax_reason = projected[len(prefix) :]
            raw_reason = raw_lines[number - 1].lstrip(" ")[len(prefix) :]
            if (
                reason
                and not _placeholder(reason)
                and not _empty_composition(
                    syntax_reason, raw_reason, position + len(prefix), html.inline_spans
                )
            ):
                return True
    return False
