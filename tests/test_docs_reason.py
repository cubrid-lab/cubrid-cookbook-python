"""Docs exemption proofs use real event JSON and the workflow's inline Python."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / "tests/fixtures/docs-reason-events.json").read_text())
WORKFLOW = ROOT / ".github/workflows/docs-sync.yml"


def workflow_python() -> str:
    text = WORKFLOW.read_text()
    return textwrap.dedent(text.split("python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])


class DocsReasonWorkflowTests(unittest.TestCase):
    def test_workflow_token_is_read_only(self) -> None:
        text = WORKFLOW.read_text()
        permissions = text.split("\npermissions:\n", 1)[1].split("\njobs:", 1)[0]
        self.assertEqual(permissions.strip(), "contents: read")
        self.assertNotIn("permissions:", text.split("\njobs:", 1)[1])

    def test_reported_item_quote_html_and_link_boundaries(self) -> None:
        from scripts.check_docs_reason import has_docs_not_needed_reason

        for case in FIXTURES:
            if case["id"].startswith("reported_"):
                with self.subTest(case=case["id"]):
                    self.assertEqual(
                        has_docs_not_needed_reason(case["event"]["pull_request"]["body"]),
                        case["expected_docs_exemption"],
                    )
        for reason in (
            "`[](https://example.com)`",
            "[tests only](https://example.com)",
            "only [](https://example.com) fixture changed",
        ):
            self.assertTrue(has_docs_not_needed_reason("Docs: not needed - " + reason))
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - [](<https://example.com>)"))
        for reason in ("[]()", "![]()", '[](/issue "context")', '[]( "context" )', "[](   )"):
            self.assertFalse(has_docs_not_needed_reason("Docs: not needed - " + reason))
        for reason in (r"\![](https://example.com)", "`![]()`", "![real alt](image.png)"):
            self.assertTrue(has_docs_not_needed_reason("Docs: not needed - " + reason))
        self.assertFalse(
            has_docs_not_needed_reason("Docs: not needed - ![&lt;reason&gt;](image.png)")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "<!--><script>\nDocs: not needed - hidden\n-->\nDocs: not needed - tests only"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason(
                "<!-->\nDocs: not needed - hidden\n-->\n~~~\nDocs: not needed - hidden\n~~~"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason("<!-- fake -- >\nhidden\n-->\nDocs: not needed - tests only")
        )
        self.assertFalse(has_docs_not_needed_reason("<!-- fake -- >\nDocs: not needed - hidden"))
        for source in (
            "`<!-->`\n\nDocs: not needed - tests only",
            "```\n<!-->\n```\nDocs: not needed - tests only",
            '<div title="<!-->">\nDocs: not needed - tests only',
            "<script>const value='<!-->';</script>\nDocs: not needed - tests only",
            "<pre>\n<!-->\n</pre>\nDocs: not needed - tests only",
        ):
            self.assertTrue(has_docs_not_needed_reason(source))
        self.assertFalse(
            has_docs_not_needed_reason("<pre>\n<!-- </pre> -->\nDocs: not needed - hidden")
        )
        for reason in (
            "![<reason>][img]",
            "![&lt;reason&gt;]",
            "![<reason>]",
            "![ ](image.png)",
            "[][url]",
        ):
            self.assertFalse(has_docs_not_needed_reason("Docs: not needed - " + reason))
        for reason in (
            "![real caption][img]",
            r"\![<reason>][img]",
            "only [ ](/issue) fixture changed",
        ):
            self.assertTrue(has_docs_not_needed_reason("Docs: not needed - " + reason))
        for opener, closer in (("<?x", "?>"), ("<!DOCTYPE html", ">"), ("<![CDATA[", "]]>")):
            self.assertFalse(has_docs_not_needed_reason(opener + "\nDocs: not needed - hidden"))
            self.assertTrue(
                has_docs_not_needed_reason(
                    opener
                    + "\nDocs: not needed - hidden\n"
                    + closer
                    + "\nDocs: not needed - tests only"
                )
            )
        self.assertFalse(has_docs_not_needed_reason("<?x>\nDocs: not needed - hidden\n?>"))
        self.assertFalse(
            has_docs_not_needed_reason(
                "<![CDATA[\nDocs: not needed - hidden\n]>\nDocs: not needed - hidden\n]]>"
            )
        )
        self.assertFalse(has_docs_not_needed_reason("> ===\nDocs: not needed - hidden"))
        self.assertFalse(has_docs_not_needed_reason("> Heading\n> =-=\nDocs: not needed - hidden"))
        for reason in (
            "[&lt;span&gt;&lt;/span&gt;](/issue)",
            "`[<!-- comment -->](/issue)`",
            r"\[<!-- comment -->](/issue)",
            "&#91;&#93;(/issue)",
            "[text<!-- comment -->](/issue)",
            "only [<!-- comment -->](/issue) fixture changed",
        ):
            self.assertTrue(has_docs_not_needed_reason("Docs: not needed - " + reason))
        for selector in ("\u180b", "\u180c", "\u180d", "\u180f"):
            self.assertFalse(has_docs_not_needed_reason("Docs: not needed - " + selector))
            self.assertFalse(has_docs_not_needed_reason(f"Docs: not needed - &#{ord(selector)};"))
            self.assertTrue(has_docs_not_needed_reason("Docs: not needed - \u1820" + selector))
            self.assertFalse(has_docs_not_needed_reason(f"Docs: not needed - [{selector}](/issue)"))
            self.assertFalse(
                has_docs_not_needed_reason(f"Docs: not needed - ![&#{ord(selector)};](image.png)")
            )
            self.assertFalse(
                has_docs_not_needed_reason("Docs: not needed - " + selector + "<reason>")
            )
        for reason in (
            '[<span title="["></span>](/issue)',
            "[<!--[-->](/issue)",
            "![<!-- empty -->](image.png)<span></span>",
        ):
            self.assertFalse(has_docs_not_needed_reason("Docs: not needed - " + reason))
        for reason in (
            "[ ]<span>(/url)</span>",
            "<https://github.com/org/repo/issues/1>",
            "<person@example.com>",
            "`<https://example.com>`",
            "only [<!--[-->](/issue) fixture changed",
            "[]() tests only []()",
            "[![real alt](/img)](/issue)",
            "`[]() []()`",
            r"\[]() \[]()",
            "&#91;&#93;() &#91;&#93;()",
            "****",
            "** **",
            "`**<!-- empty -->**`",
            r"\**<!-- empty -->**",
            "**&lt;span&gt;&lt;/span&gt;**",
            "**text<!-- empty -->**",
        ):
            self.assertTrue(has_docs_not_needed_reason("Docs: not needed - " + reason))
        for body in (
            '<div title="<https://example.com>\nDocs: not needed - hidden">',
            "<script>\n<https://example.com>\nDocs: not needed - hidden\n</script>",
            "<!--\n<https://example.com>\nDocs: not needed - hidden\n-->",
        ):
            self.assertFalse(has_docs_not_needed_reason(body))
        from scripts.check_docs_reason import _LITERAL_RUN

        for value in ("<a:x>", "<" + "a" * 33 + ":x>", "<ab: has-space>", "<ab:\x01>", "<span>"):
            self.assertIsNone(_LITERAL_RUN.fullmatch(value))

    def test_checkpoint_does_not_resplit_the_fed_tape(self) -> None:
        from scripts.check_docs_reason import _HTMLContext

        self.assertNotIn("fed_text.split", inspect.getsource(_HTMLContext.checkpoint))
        html = _HTMLContext("unfed future\n")
        html.feed("ab\n\n")
        html.feed("c\n")
        self.assertEqual(html.row_starts, [0, 3, 4, 6])
        self.assertEqual(html.row_starts[html.getpos()[0] - 1], len(html.fed_text))

    def test_reviewed_physical_and_rendered_contexts(self) -> None:
        from scripts.check_docs_reason import _HTMLContext, has_docs_not_needed_reason

        link = "[A &amp; B](<blockquote>)\n"
        html = _HTMLContext(link)
        html.feed_literals(link, 1, 0, 0)
        self.assertIn("A & B", html.lines[1])
        self.assertFalse(html.blocked)
        for blank in (">", ">   "):
            self.assertTrue(
                has_docs_not_needed_reason(f"> quote\n{blank}\nDocs: not needed - tests only")
            )
        self.assertTrue(
            has_docs_not_needed_reason(
                "Ordinary prose.\nDocs: not needed - tests only\nMore prose."
            )
        )
        for separator in ("\u2028", "\u0085", "\f"):
            self.assertFalse(
                has_docs_not_needed_reason("Example" + separator + "Docs: not needed - hidden")
            )
        for tag in ("script", "style", "textarea", "iframe"):
            self.assertFalse(
                has_docs_not_needed_reason(f"<{tag}>\nDocs: not needed - hidden\n</{tag}>")
            )
            self.assertTrue(
                has_docs_not_needed_reason(
                    f"<{tag}>hidden</{tag}>\n\nDocs: not needed - tests only"
                )
            )
        for reason in ("\u200b", "\ufeff", "&#8203;"):
            self.assertFalse(has_docs_not_needed_reason("Docs: not needed - " + reason))
        self.assertFalse(has_docs_not_needed_reason("-\t> quoted\nDocs: not needed - hidden"))
        self.assertTrue(
            has_docs_not_needed_reason("[example](<blockquote>)\n\nDocs: not needed - tests only")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "`unmatched\n# First\nDocs: not needed - tests only\n# Last `"
            )
        )
        for heading in ("####### invalid", "#no-space", "\\# escaped"):
            self.assertFalse(
                has_docs_not_needed_reason(
                    f"`unmatched\n{heading}\nDocs: not needed - hidden\nlast `"
                )
            )
        self.assertFalse(
            has_docs_not_needed_reason(
                "Docs: not needed - \u200b<reason> because docs are unchanged"
            )
        )
        self.assertTrue(has_docs_not_needed_reason("Docs: not needed - \u200btests only"))
        self.assertTrue(
            has_docs_not_needed_reason(
                "-\t~~~text\n\tDocs: not needed - hidden\n\t~~~\n\nDocs: not needed - tests only"
            )
        )
        for link in ("\\[example](<blockquote>)", "[example](<blockquote>"):
            self.assertFalse(
                has_docs_not_needed_reason(link + "\n\nDocs: not needed - hidden\n</blockquote>")
            )
        self.assertFalse(
            has_docs_not_needed_reason(
                '<blockquote title="[example](<blockquote>)">\nDocs: not needed - hidden\n</blockquote>'
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason("[<blockquote>](<dest>)\n\nDocs: not needed - hidden")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "<!-- [example](<blockquote>) -->\nDocs: not needed - tests only"
            )
        )

    def test_list_contained_examples_are_not_reasons(self) -> None:
        from scripts.check_docs_reason import has_docs_not_needed_reason

        for bullet in ("10.", "100."):
            indentation = " " * (len(bullet) + 1)
            self.assertTrue(
                has_docs_not_needed_reason(
                    f"{bullet} ~~~text\n{indentation}Docs: not needed - hidden\n{indentation}~~~\n\nDocs: not needed - tests only"
                )
            )
        self.assertFalse(
            has_docs_not_needed_reason("~~~text\n    ~~~\nDocs: not needed - hidden\n~~~")
        )
        for bullet in ("-", "+", "*", "1.", "2)"):
            with self.subTest(bullet=bullet):
                indentation = " " * (len(bullet) + 1)
                self.assertFalse(
                    has_docs_not_needed_reason(
                        f"{bullet} ```text\n{indentation}Docs: not needed - example\n{indentation}```"
                    )
                )
                self.assertFalse(
                    has_docs_not_needed_reason(f"{bullet} > quoted\n  Docs: not needed - example")
                )
                self.assertTrue(
                    has_docs_not_needed_reason(
                        f"{bullet} ```text\n{indentation}Docs: not needed - example\n{indentation}```\n\nDocs: not needed - tests only"
                    )
                )
                self.assertTrue(
                    has_docs_not_needed_reason(
                        f"{bullet} > quoted\n\nDocs: not needed - tests only"
                    )
                )
        self.assertFalse(
            has_docs_not_needed_reason("`literal\n- > quoted`\n  Docs: not needed - example")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "`literal\n- ~~~text\n  <blockquote>\n  ~~~\n\nDocs: not needed - tests only\n`"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason("```text\n- ```\n  Docs: not needed - example\n```")
        )
        self.assertFalse(has_docs_not_needed_reason("- Docs: not needed - example"))
        for opener in ("<!--", '<blockquote title="example">'):
            close = "-->" if opener == "<!--" else "</blockquote>"
            self.assertTrue(
                has_docs_not_needed_reason(
                    f"{opener}\n- ```text\n{close}\nDocs: not needed - tests only"
                )
            )

    def test_unexpanded_placeholder_is_not_a_reason(self) -> None:
        from scripts.check_docs_reason import _HTMLContext, _placeholder, has_docs_not_needed_reason

        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - \u034f"))
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - \ufe0f"))
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - (**<reason>**)"))
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - [~~&lt;reason&gt;~~]"))
        for prefix in ("\u034f", "\ufe0f", "\U000e0100"):
            self.assertFalse(
                has_docs_not_needed_reason("Docs: not needed - " + prefix + "<reason>")
            )
        for reason in (
            "cafe\u0301 fixture only",
            "\u2764\ufe0f fixture changed",
            "only (**<reason>**) fixture changed",
        ):
            self.assertTrue(has_docs_not_needed_reason("Docs: not needed - " + reason))
        for unsupported in ("(**<reason>**]", "[~~~<reason>~~~]", "[``<reason>`]"):
            self.assertFalse(_placeholder(unsupported))
        self.assertTrue(_placeholder("(" * 2000 + "<reason>" + ")" * 2000))
        self.assertTrue(
            has_docs_not_needed_reason(
                "`unmatched\nHeading\n===\nDocs: not needed - tests only\nlast `"
            )
        )
        for underline in ("====text", "    ===", "=-="):
            self.assertFalse(
                has_docs_not_needed_reason(
                    f"`unmatched\nHeading\n{underline}\nDocs: not needed - hidden\nlast `"
                )
            )
        self.assertFalse(
            has_docs_not_needed_reason(
                "`unmatched\n    Heading\n===\nDocs: not needed - hidden\nlast `"
            )
        )
        for prefix in ("&#", "&#x"):
            self.assertTrue(has_docs_not_needed_reason(prefix + "\nDocs: not needed - tests only"))
            self.assertFalse(
                has_docs_not_needed_reason(prefix + "\n~~~\nDocs: not needed - hidden\n~~~")
            )
        numeric = _HTMLContext("&#\nDocs: not needed - future")
        numeric.feed("&#")
        numeric.checkpoint()
        self.assertEqual(numeric.getpos(), (1, 0))
        self.assertFalse(numeric.marker_lines)
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - [<reason>]"))
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - (<reason>)"))
        for unmatched in ("[<reason>)", "(<reason>]", "[<reason>"):
            self.assertFalse(_placeholder(unmatched))
        self.assertTrue(
            has_docs_not_needed_reason("Docs: not needed - only [<reason>] fixture changed")
        )
        for heading in ("####### invalid", "#no-space", "\\# escaped", "     # indented"):
            self.assertFalse(has_docs_not_needed_reason(f"> {heading}\nDocs: not needed - hidden"))
        self.assertTrue(has_docs_not_needed_reason("> # Heading\nDocs: not needed - tests only"))
        self.assertTrue(
            has_docs_not_needed_reason("> paragraph\n> # Heading\nDocs: not needed - tests only")
        )
        self.assertTrue(
            has_docs_not_needed_reason("> prior quote\n<div>\nDocs: not needed - tests only")
        )
        for tag in ("table", "details", "h1", "ul", 'DIV class="example"', "/div"):
            self.assertTrue(
                has_docs_not_needed_reason(f"> prior quote\n<{tag}>\nDocs: not needed - tests only")
            )
        for tag in ("span", "code", "divine", "https://example.com"):
            self.assertFalse(
                has_docs_not_needed_reason(f"> prior quote\n<{tag}>\nDocs: not needed - hidden")
            )
        for item, indent in (("- item", "  "), ("1. item", "   ")):
            self.assertFalse(
                has_docs_not_needed_reason(
                    f"{item}\n{indent}`unmatched\nHeading\n===\nDocs: not needed - hidden\nlast `"
                )
            )
            self.assertFalse(
                has_docs_not_needed_reason(
                    f"{item}\n{indent}continued\n{indent}`unmatched\nHeading\n===\nDocs: not needed - hidden\nlast `"
                )
            )
            self.assertTrue(
                has_docs_not_needed_reason(
                    f"{item}\n{indent}`unmatched\n{indent}Heading\n{indent}===\nDocs: not needed - tests only\nlast `"
                )
            )
        self.assertFalse(
            has_docs_not_needed_reason(
                "10. item\n    `unmatched\nHeading\n===\nDocs: not needed - hidden\nlast `"
            )
        )
        for number in (100, 999999999):
            indent = " " * (len(str(number)) + 2)
            self.assertFalse(
                has_docs_not_needed_reason(
                    f"{number}. item\n{indent}continued\n{indent}`unmatched\nHeading\n===\nDocs: not needed - hidden\nlast `"
                )
            )
            self.assertTrue(
                has_docs_not_needed_reason(
                    f"{number}. item\n{indent}`unmatched\n{indent}Heading\n{indent}===\nDocs: not needed - tests only\nlast `"
                )
            )
        for source in (
            "    <blockquote>\nDocs: not needed - tests only",
            "10. item\n        <blockquote>\nDocs: not needed - tests only",
            "<!--\n10. fake item\n-->\n    <blockquote>\nDocs: not needed - tests only",
        ):
            self.assertTrue(has_docs_not_needed_reason(source))
        for heading in ("> ####### invalid", "> #no-space", "\\> # escaped"):
            self.assertFalse(
                has_docs_not_needed_reason(f"> paragraph\n{heading}\nDocs: not needed - hidden")
            )
        self.assertFalse(
            has_docs_not_needed_reason(
                "<!--\n> paragraph\n> # Heading\nDocs: not needed - hidden\n-->"
            )
        )
        self.assertTrue(has_docs_not_needed_reason(">    # Heading\nDocs: not needed - tests only"))
        self.assertTrue(has_docs_not_needed_reason("- ```text\nDocs: not needed - tests only"))
        for source in (
            "```text\nDocs: not needed - hidden",
            "- ```text\n\n  Docs: not needed - hidden",
            "- ```text\n```\nDocs: not needed - hidden",
        ):
            self.assertFalse(has_docs_not_needed_reason(source))
        self.assertFalse(has_docs_not_needed_reason(r"Docs: not needed - \<reason\>"))
        self.assertFalse(_placeholder(r"\\<reason\\>"))
        self.assertFalse(_placeholder(r"\x<reason\>"))
        self.assertTrue(
            has_docs_not_needed_reason(r"Docs: not needed - only \<reason\> fixture changed")
        )
        pending = _HTMLContext("<!--\nDocs: not needed - hidden\n-->\n")
        pending.feed("<!--\nDocs: not needed - hidden\n")
        pending.checkpoint()
        self.assertEqual(pending.getpos(), (1, 0))
        self.assertFalse(pending.marker_lines)
        for source in (
            '<blockquote title="\nDocs: not needed - hidden',
            "<script>\nDocs: not needed - hidden",
        ):
            self.assertFalse(has_docs_not_needed_reason(source))
        for unfinished in (
            "<!--\nDocs: not needed - hidden",
            '<blockquote title="\nDocs: not needed - hidden',
        ):
            self.assertTrue(
                has_docs_not_needed_reason(
                    "<!--\nDocs: not needed - hidden\n-->\nDocs: not needed - tests only\n"
                    + unfinished
                )
            )
        for source in (
            "Docs: not needed - use < in fixture text",
            "<blockquote>hidden</blockquote>\nDocs: not needed - tests only",
        ):
            self.assertTrue(has_docs_not_needed_reason(source))
        self.assertTrue(
            has_docs_not_needed_reason(
                "> quote\n<!--\n# Details\nDocs: not needed - hidden\n-->\nDocs: not needed - tests only"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason("> quote\n<!--\n# Details\nDocs: not needed - hidden")
        )
        self.assertFalse(
            has_docs_not_needed_reason(
                "<!--\nDocs: not needed - hidden\n-->\n```text\nDocs: not needed - hidden\n```"
            )
        )
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - ~~&lt;reason&gt;~~"))
        self.assertFalse(_placeholder("~~~<reason>~~~"))
        for thematic in ("***", "- - -", "___", "  *\t* *"):
            self.assertTrue(
                has_docs_not_needed_reason(f"> quote\n{thematic}\nDocs: not needed - tests only")
            )
            self.assertTrue(
                has_docs_not_needed_reason(
                    f"`unmatched\n{thematic}\nDocs: not needed - tests only\nlast `"
                )
            )
        for literal in ("*_*", "***text", "    ***", "\\***", "***\u2028"):
            self.assertFalse(
                has_docs_not_needed_reason(f"> quote\n{literal}\nDocs: not needed - hidden")
            )
        self.assertTrue(has_docs_not_needed_reason("> quote\n***\nDocs: not needed - tests only"))
        self.assertFalse(
            has_docs_not_needed_reason("> quote\n<!--\n# Details\nDocs: not needed - hidden\n-->")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "> quote\n<!--\n# Details\nhidden\n-->\nDocs: not needed - tests only"
            )
        )
        for literal in (
            "<code>",
            "<https://example.com>",
            "<prelude>",
            "\\<!--",
            "    <!--",
            "`<!--`",
        ):
            self.assertFalse(
                has_docs_not_needed_reason(f"> quote\n{literal}\nDocs: not needed - hidden")
            )
        for tag in ("pre", "script", "style", "textarea", "blockquote", "iframe"):
            self.assertFalse(
                has_docs_not_needed_reason(
                    f"> quote\n<{tag.upper()}>\n# Details\nDocs: not needed - hidden\n</{tag}>"
                )
            )
            self.assertTrue(
                has_docs_not_needed_reason(
                    f"> quote\n<{tag}>\nhidden\n</{tag}>\nDocs: not needed - tests only"
                )
            )
        for unmatched in ("`<reason>``", "``<reason>`", "*<reason>**"):
            self.assertFalse(_placeholder(unmatched))
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - `<reason>`"))
        for wrapper in ("``", "*", "**", "***", "_", "__", "___"):
            self.assertFalse(
                has_docs_not_needed_reason(f"Docs: not needed - {wrapper}&lt;reason&gt;{wrapper}")
            )
        for heading in ("####### invalid", "#no-space", "\\# escaped"):
            self.assertFalse(
                has_docs_not_needed_reason(f"> quote\n{heading}\nDocs: not needed - hidden")
            )
        self.assertFalse(
            has_docs_not_needed_reason("> quote\n```text\nDocs: not needed - hidden\n```")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "> quote\n```text\nhidden\n```\nDocs: not needed - tests only"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason("> quote\n# Details\nDocs: not needed - tests only")
        )
        self.assertFalse(
            has_docs_not_needed_reason("Docs: not needed - <reason> because docs are unchanged")
        )
        self.assertFalse(
            has_docs_not_needed_reason(
                "Docs: not needed - &lt;reason&gt; because docs are unchanged"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason("Docs: not needed - only `<reason>` fixture changed")
        )

    def test_inline_literal_html_does_not_change_outer_context(self) -> None:
        from scripts.check_docs_reason import has_docs_not_needed_reason

        self.assertTrue(
            has_docs_not_needed_reason(
                "Example `unmatched\n~~~html\n<blockquote>\n~~~\nDocs: not needed - tests only\n`"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason("`literal\n> quoted`\nDocs: not needed - hidden")
        )
        self.assertTrue(
            has_docs_not_needed_reason("`literal\n> quoted`\n\nDocs: not needed - tests only")
        )

        for literal in (
            "`<blockquote>`",
            "``<blockquote>`literal``",
            "\u005c<blockquote>",
            "\u005c\u005c\u005c<blockquote>",
            "`<pre>`",
            "`<code>`",
            "`Example\n\u005c<blockquote>\n`",
        ):
            with self.subTest(literal=literal):
                self.assertTrue(
                    has_docs_not_needed_reason(literal + "\n\nDocs: not needed - tests only")
                )
        for opener in ("`<blockquote>", "``<blockquote>`", "\u005c\u005c<blockquote>"):
            with self.subTest(opener=opener):
                self.assertFalse(
                    has_docs_not_needed_reason(
                        opener + "\nDocs: not needed - hidden\n</blockquote>"
                    )
                )
        # Type 6 HTML interrupts the paragraph before inline code is parsed.
        self.assertFalse(
            has_docs_not_needed_reason("`Example\n<blockquote>\n`\n\nDocs: not needed - hidden")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "`Example\n<blockquote>\n`\n</blockquote>\nDocs: not needed - tests only"
            )
        )
        self.assertFalse(has_docs_not_needed_reason("`Example\nDocs: not needed - hidden\n`"))
        self.assertTrue(
            has_docs_not_needed_reason(
                "Docs: not needed - only `<blockquote>` fixture text changed"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason(
                '<blockquote title="`literal`">\nDocs: not needed - hidden\n</blockquote>'
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "<blockquote>\n`</blockquote>`\nDocs: not needed - tests only"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "`<blockquote>\n\nExample\n</blockquote>\nDocs: not needed - tests only\n`"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "\u005c`<blockquote>\nExample</blockquote>\nDocs: not needed - tests only\n`"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason(
                "`literal`<blockquote>\nDocs: not needed - hidden\n</blockquote>"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason(
                "``<blockquote>```\nDocs: not needed - hidden\n</blockquote>"
            )
        )

    def test_html_entities_do_not_create_physical_lines(self) -> None:
        from scripts.check_docs_reason import has_docs_not_needed_reason

        for reference in ("&NewLine;", "&#10;", "&#13;&#10;"):
            with self.subTest(reference=reference):
                self.assertFalse(
                    has_docs_not_needed_reason(
                        f"text{reference}Docs: not needed - hidden example\nDocs: not needed -"
                    )
                )
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - &lt;reason&gt;"))
        self.assertFalse(has_docs_not_needed_reason("Docs: not needed - &#10;"))
        self.assertTrue(
            has_docs_not_needed_reason("Docs: not needed - only A &amp; B fixture changed")
        )

    def test_html_context_reason_indentation_and_fence_info(self) -> None:
        from scripts.check_docs_reason import has_docs_not_needed_reason

        for literal in ("    <blockquote>", "    <pre>", "\t<code>"):
            with self.subTest(literal=literal):
                self.assertTrue(
                    has_docs_not_needed_reason(literal + "\n\nDocs: not needed - tests only")
                )
        self.assertTrue(
            has_docs_not_needed_reason(
                "<blockquote>\nExample\n    </blockquote>\nDocs: not needed - tests only"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason("<!--\nExample\n    -->\nDocs: not needed - tests only")
        )

        for tag in ("blockquote", "pre", "code"):
            with self.subTest(tag=tag):
                self.assertFalse(
                    has_docs_not_needed_reason(
                        f'<{tag.upper()} title="example">\nDocs: not needed - hidden\n</{tag}>'
                    )
                )
                self.assertFalse(
                    has_docs_not_needed_reason(
                        f"<{tag}><{tag}>\n</{tag}>\nDocs: not needed - hidden\n</{tag}>"
                    )
                )
                self.assertTrue(
                    has_docs_not_needed_reason(
                        f"<{tag}>\nExample\n</{tag}>\nDocs: not needed - tests only"
                    )
                )
        for indentation in ("", " ", "  ", "   "):
            self.assertTrue(
                has_docs_not_needed_reason(indentation + "Docs: not needed - tests only")
            )
        for indentation in ("    ", "\t", " \t"):
            self.assertFalse(
                has_docs_not_needed_reason(indentation + "Docs: not needed - code example")
            )
        self.assertTrue(has_docs_not_needed_reason("```foo`bar\nDocs: not needed - tests only"))
        self.assertFalse(has_docs_not_needed_reason("~~~foo`bar\nDocs: not needed - hidden\n~~~"))
        self.assertTrue(
            has_docs_not_needed_reason("```html\n<blockquote>\n```\nDocs: not needed - tests only")
        )
        self.assertFalse(
            has_docs_not_needed_reason("Docs: not needed - <!--\nhidden\n-->tests only")
        )
        self.assertFalse(
            has_docs_not_needed_reason(
                "<!--\nDocs: not needed - hidden -->Docs: not needed - inline example"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason(
                '<blockquote title="\nDocs: not needed - hidden">quoted</blockquote>Docs: not needed - inline example'
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason("Docs: not needed - <span\n>\ntests only\n</span>")
        )
        self.assertTrue(
            has_docs_not_needed_reason("<!--\n```html\n-->\nDocs: not needed - tests only")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "```html <blockquote>\n<pre>\n```\nDocs: not needed - tests only"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "<blockquote>\n```html\n</blockquote>\nDocs: not needed - tests only"
            )
        )
        self.assertFalse(
            has_docs_not_needed_reason("<blockquote/>\nDocs: not needed - hidden\n</blockquote>")
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "<blockquote>\n> Example\n</blockquote>\nDocs: not needed - tests only"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason("<!--\n> Example\n-->\nDocs: not needed - tests only")
        )

    def test_comment_reopening_and_fence_indentation(self) -> None:
        from scripts.check_docs_reason import has_docs_not_needed_reason

        self.assertFalse(
            has_docs_not_needed_reason(
                "<!-- first\n--> <!-- second\nDocs: not needed - hidden example\n-->"
            )
        )
        self.assertTrue(
            has_docs_not_needed_reason(
                "<!-- first\n--> <!-- second -->\nDocs: not needed - tests only"
            )
        )
        for indentation in ("", " ", "  ", "   "):
            with self.subTest(indentation=indentation):
                self.assertFalse(
                    has_docs_not_needed_reason(
                        indentation + "```text\nDocs: not needed - hidden example\n```"
                    )
                )
                self.assertTrue(
                    has_docs_not_needed_reason(
                        "```text\n" + indentation + "```\nDocs: not needed - tests only"
                    )
                )
        for indentation in ("    ", "     ", "\t"):
            with self.subTest(indentation=indentation):
                self.assertTrue(
                    has_docs_not_needed_reason(indentation + "```\nDocs: not needed - tests only")
                )
                self.assertFalse(
                    has_docs_not_needed_reason(
                        "```text\n" + indentation + "```\nDocs: not needed - hidden example\n```"
                    )
                )

    def test_mixed_fences_and_visible_reason(self) -> None:
        from scripts.check_docs_reason import has_docs_not_needed_reason

        for body in (
            "````text\n```\nDocs: not needed - tests only\n````",
            "~~~text\n```\nDocs: not needed - tests only\n~~~",
            "```text\n~~~\nDocs: not needed - tests only\n```",
            "```text\n```example\nDocs: not needed - tests only\n```",
            "<!--\n```\nDocs: not needed - tests only\n-->\n```",
            "Docs: not needed - <!-- placeholder -->",
            "> Example\nDocs: not needed - tests only",
        ):
            with self.subTest(body=body):
                self.assertFalse(has_docs_not_needed_reason(body))
        self.assertTrue(
            has_docs_not_needed_reason("````text\n~~~\n`````\nDocs: not needed - tests only")
        )
        self.assertTrue(has_docs_not_needed_reason("Docs: not needed - tests only <!-- note -->"))

    def test_known_docs_reason_helper_limitations(self) -> None:
        """Preserve the four case families reviewed in pycubrid#429/#573."""
        from scripts.check_docs_reason import has_docs_not_needed_reason

        cases = (
            (True, "`unmatched\n<div>\nDocs: not needed - tests only\n</div>\nlast `"),
            (False, "Docs: not needed - [<!--[-->](/issue)"),
            (False, 'Docs: not needed - [<span title="["></span>](/issue)'),
            (False, "Docs: not needed - []() []()"),
            (False, "Docs: not needed - [![](/img)](/issue)"),
            (False, "Docs: not needed - [**<!-- empty -->**](/issue)"),
            (False, "Docs: not needed - [**![](/img)**](/issue)"),
            (True, "Docs: not needed - [**tests only**](/issue)"),
        )
        for expected, body in cases:
            with self.subTest(body=body):
                self.assertEqual(has_docs_not_needed_reason(body), expected)

    def test_event_json_exemptions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            git = temporary / "git"
            git.write_text(
                f"#!{sys.executable}\n"
                "import os, sys\n"
                "if sys.argv[1] == 'diff':\n"
                "    sys.stdout.write(os.environ['DOCS_TEST_CHANGED'])\n"
            )
            git.chmod(0o755)
            event = temporary / "event.json"
            env = {
                **os.environ,
                "PATH": str(temporary) + os.pathsep + os.environ.get("PATH", ""),
                "BASE_REF": "main",
                "EVENT_PATH": str(event),
                "IMPACT_GLOBS": "templates/**/*.py\nscripts/**",
                "DOC_GLOBS": "README*\ndocs/**\nCHANGELOG*",
                "IGNORE_GLOBS": "**/tests/**\n**/expected/**\n.github/**\n**/*.md",
                "DOCS_TEST_CHANGED": "templates/demo/app.py\n",
            }
            for case in FIXTURES:
                with self.subTest(case=case["id"]):
                    event.write_text(json.dumps(case["event"]))
                    run = subprocess.run(
                        [sys.executable, "-"],
                        input=workflow_python(),
                        cwd=ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(
                        run.returncode == 0,
                        case["expected_docs_exemption"],
                        run.stdout + run.stderr,
                    )

    def test_body_is_json_data_and_translation_requires_existing_label(self) -> None:
        text = WORKFLOW.read_text()
        self.assertIn("json.load(_f)", text)
        self.assertNotIn("${{ github.event.pull_request.body }}", text)
        translation = text.split("  translation-sync:", 1)[1]
        self.assertIn(
            "!contains(github.event.pull_request.labels.*.name, 'translations-deferred')",
            translation,
        )
        self.assertNotIn("pull_request.body", translation)
        script = (ROOT / "scripts/check_translation_sync.py").read_text()
        self.assertIn('REQUIRED_LANGS = {"ko"}', script)
        self.assertNotIn('print("  Docs: not needed - <reason>")', text)
        self.assertIn("Replace the example explanation with your actual reason", text)
        template = (ROOT / ".github/pull_request_template.md").read_text()
        self.assertNotIn("apply the `docs-not-needed` label", template)
        self.assertIn("request the maintainer-managed `docs-not-needed` label", template)


if __name__ == "__main__":
    unittest.main()
