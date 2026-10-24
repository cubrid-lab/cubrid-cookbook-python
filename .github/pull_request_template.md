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

## Review and Final Disposition

<!-- The same review criteria apply regardless of human/agent implementation. -->
- Required GitHub CI at final head: **pending** (add runs/links once available).
- Applicable live CUBRID test evidence: **pending** / N/A with reason.
- Optional AI review (Oracle, Copilot, agent-review): link useful findings, or N/A.
- Finding dispositions: fixed + test / rejected with reason / deferred issue.
- Open threads and blocking defects: list, or "none" after checking.
- Maintainer merge decision: **pending** (after source, security and required
  CI checks are reviewed).
<!-- AI reviews and agent-review are advisory, never a tool-dependent gate.
     Keep independent scrutiny for protected security, workflow and release paths. -->

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

## Related PRs and Execution Preconditions

<!-- Cite Supersedes #N, Depends on #N, or Parallel to #N with a reason,
     or None. Recheck current main and unresolved decisions before merge. -->
Related PRs and precedence: None
Unresolved decision or dependency: None

## Related Issues

<!-- Use Closes #N for a completed LOCAL issue (or N/A and a reason).
     Cite sibling dependencies as Refs owner/repo#N, not closing keywords.
     Each repo manages its own work and closure; the PR title check enforces
     no direct auto-closing references to a foreign repository. -->
