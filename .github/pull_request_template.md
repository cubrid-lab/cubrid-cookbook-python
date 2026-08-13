## High level description of this Pull-request
Include motivations, reasons, and background to add context to your contribution.
Include a description of changes associated with your commit(s)

## Related Issues
- List all related issues or NA

## Example Details
- **Language/Framework**: (e.g., Python/FastAPI, Go/GORM, Node.js/Drizzle)
- **Tested against CUBRID version**: (e.g., 11.2)

## Reviewers
- Use @Mentions to specify the reviewers for your PR.

# CHECKLIST:
Make sure all items are marked when you submit the pull-request.

- [ ] Example has been tested against a live CUBRID instance
- [ ] All table names are prefixed with `cookbook_`
- [ ] README with setup and run instructions is included
- [ ] Python code passes `ruff check` and `ruff format --check`
- [ ] No hardcoded credentials — environment variables used
- [ ] Tests updated — new/changed examples ship an `expected/` golden file or a `tests/` suite (or an allowlist entry with a reason)
- [ ] Docs updated — README, SUPPORT_MATRIX, and CHANGELOG reflect any added, renamed, or removed example (4-phase workflow: code without doc updates is incomplete)
