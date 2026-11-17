# Agent ticket prompt template

Copy the prompt below into a new agent conversation opened in this repository.
Replace the placeholders and remove optional sections that do not apply. Paste
the ticket description if the agent cannot access its URL. Keep the reusable
template committed; ticket-specific working notes can stay in the issue or chat.
Do not include credentials or private production data.

```text
Implement ticket <number>: <title>
Ticket URL: <URL, if available>

Project context:
- Read AGENTS.md and docs/architecture.md first.
- Inspect the current implementation and relevant tests before editing.
- Check current code rather than assuming documentation is always up to date.

Goal:
<Describe the user-visible outcome and the problem it solves.>

Current behavior / reproduction:
<Describe what happens today; include sanitized examples or errors if useful.>

Acceptance criteria:
- <Observable behavior or result>
- <Authorization, validation, or failure behavior>
- <Relevant test coverage>

Additional context and decisions:
<Related files, issues, agreed design choices, or constraints not already documented.>

Out of scope:
- <Changes that should not be included>

Implementation workflow:
- Check the working tree and preserve unrelated changes.
- Fetch origin and create a new ticket branch from the latest origin/main.
  Use an isolated worktree if needed to preserve existing work.
- Explain the intended approach briefly, then implement it.
- Ask when a missing requirement materially changes behavior; otherwise make
  reasonable implementation choices and state important assumptions.
- Reuse existing services, validation, and permission checks.
- Keep API contracts, frontend callers, and tests consistent.
- Document migration or configuration requirements where applicable.
- Update docs/architecture.md if the architecture or documented behavior changes.
- Add relevant tests and run the checks required by AGENTS.md.
  Report failures, skipped checks, and environment limitations accurately.

Delivery:
- Summarize the behavior changes and affected files.
- Map the result to the acceptance criteria.
- Report validation results and remaining risks or follow-ups.
- Provide a proposed PR title and description.
- Do not commit, push, open a PR, merge, or deploy unless explicitly requested.
- When merging is authorized, use a pull request and required checks.
  Never push directly to main or bypass branch protection.
```

For an exploratory ticket, replace the implementation workflow with:

```text
Read the ticket and relevant code. Explain the current behavior, propose an
implementation plan, and identify unanswered questions. Do not edit files yet.
```
