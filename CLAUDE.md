# Instructions for the coding agent

@AGENTS.md

## Workflow in this repository

- For graph topology changes (a new node, a new edge or a new routing rule), plan first. Show the updated mermaid diagram from the README and wait for approval.
- Run `/check` before saying work is finished. Run `/review-trace` after any change to routing, budgets or prompts.
- Before committing a change to `graph.py`, `react.py` or `state.py`, ask the `graph-reviewer` subagent to review the diff. Fix blockers. Discuss majors with the user.
- Edited Python files are formatted and lint-fixed by the post-edit hook. If lint errors remain, the hook reports them back to you. Fix the code instead of adding `# noqa`.
- Pre-approved without asking: the `make` targets listed in `.claude/settings.json`, `pytest`, `ruff`, `orchestrate`, and read-only git commands. `git commit`, `git push`, `gcloud` and `docker` need confirmation.
- Never open `.env` files. Configuration comes from the environment variables listed in the README.
