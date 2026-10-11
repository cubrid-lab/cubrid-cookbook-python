<!--
Title: `type: description` or `type(scope): description`; add `!` before the colon
for a breaking change. Types: feat, fix, docs, test, perf, refactor, ci, build,
chore, style, revert. English, lowercase start unless the first word is an API
name, acronym, or proper noun. No trailing period, no issue numbers (put
"Closes #123" in Related Issues). The title becomes the squash commit title.
See CONTRIBUTING.md#pull-request-and-commit-titles.
-->
## High level description of this Pull-request
Include motivations, reasons, and background to add context to your contribution.
Include a description of changes associated with your commit(s)

## Example Details
- **Python/Framework**: (e.g., Python/FastAPI, Flask, SQLAlchemy)
- **Tested against CUBRID version**: (e.g., 11.2)

## Validation
- Commands actually executed and their results:
- Checks not executed, reason, and remaining gaps:
- Optional additional AI/tool review (separate from tests and not a replacement for the required review route):

## Review Route and Final Disposition

<!-- Record the route actually used; human contributors do not need a specific AI tool. -->
- Development route: OpenCode + Oracle pre/post / trivial OpenCode with recorded Oracle skip / standalone Claude Code / standalone Codex / standalone ChatGPT or other agent (name it) / human (select one).
- Trivial OpenCode exception, if used: skipped Oracle phases and reason, or not applicable.
- Review evidence: actual Oracle or submitted GitHub review link, reviewer and reviewed head SHA, or **pending**.
- Finding disposition: fixed commit + test / rejected with reason / deferred issue.
- Unresolved review threads and reason, or "none" after verification.
- Maintainer merge decision: **pending**; complete only after checking the applicable review, final code, required CI, applicable live validation and thread dispositions.
<!-- A requested review, green CI or automated "approval recommended" text alone does not complete the review route. -->

## Reviewers
- Request reviewers through GitHub review requests; avoid repeated bot @mentions and review requests.

# CHECKLIST:
Mark applicable checks and explain anything not run/not applicable. Maintainers
coordinate remaining required validation; a reason does not waive merge gates.

- [ ] Example has been tested against a live CUBRID instance
- [ ] All table names are prefixed with `cookbook_`
- [ ] README with setup and run instructions is included
- [ ] Python code passes `ruff check` and `ruff format --check`
- [ ] No hardcoded credentials — environment variables used
- [ ] Tests updated — new/changed examples ship an `expected/` golden file or a `tests/` suite (or an allowlist entry with a reason)
- [ ] Docs updated — README, SUPPORT_MATRIX, and CHANGELOG reflect any added, renamed, or removed example (or give a real standalone `Docs: not needed - <reason>` line / request the maintainer-managed `docs-not-needed` label; enforced by the `docs-sync` CI check)

<!-- If docs are unaffected, add a standalone nonempty Docs: not needed - reason
line outside this comment. The literal placeholder is not an exemption.
If translation help is needed, name the language and reason. This request does
not bypass checks; maintainers must approve the existing translations-deferred
label and record the follow-up. -->

## Related Issues

- `Closes #123` / `Refs #456`, or NA (issue numbers go here, not in the PR title)
