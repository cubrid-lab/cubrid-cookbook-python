# Agent Playbook

## Source Of Truth
- `README.md` for example catalog, quick start, and project structure.
- `docs/internal/PRD.md` for example quality expectations and roadmap.
- `CONTRIBUTING.md` for contribution rules and language-specific checks.
- `Makefile` and `docker-compose.yml` for local database workflow.

## Repository Map
- Language example directories under the repository root.
- Shared infrastructure in Docker and Make targets.
- Root docs define example standards and contribution workflow.

## Change Workflow
1. Identify the language and layer of the example you are touching.
2. Keep example code minimal, runnable, and directly aligned with the README.
3. If you add a new example family, document it in both `README.md` and `docs/internal/PRD.md`.
4. Prefer examples that can be copied by users with minimal adaptation.

## Validation
- `make up`
- Run the relevant example commands for the changed language.
- `make status`
- `make down`
