<!--
Title: `type: description` or `type(scope): description`; add `!` before the colon
for a breaking change. Types: feat, fix, docs, test, perf, refactor, ci, build,
chore, style, revert. English, lowercase start, no trailing period, no issue
numbers (put "Closes #123" in Related Issues). The title becomes the squash
commit title. See CONTRIBUTING.md#pull-request-and-commit-titles.
-->
## High level description of this Pull-request
Include motivations, reasons, and background to add context to your contribution.
Include a description of changes associated with your commit(s)

## Related Issues
- `Closes #123` / `Refs #456`, or NA (issue numbers go here, not in the PR title)

## Example Details
- **Python/Framework**: (e.g., Python/FastAPI, Flask, SQLAlchemy)
- **Tested against CUBRID version**: (e.g., 11.2)

## Validation
- Commands actually executed and their results:
- Checks not executed, reason, and remaining gaps:
- Optional AI/tool review and findings (separate from executed tests):

## Reviewers
- Use @Mentions to specify the reviewers for your PR.

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
