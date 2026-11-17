---
description: Run the agent team on a task and summarise the path, the decisions and the cost
argument-hint: <task>
allowed-tools: Bash(orchestrate:*), Bash(make run:*), Read
---

Run `orchestrate "$ARGUMENTS"` from the repository root.

Summarise:

- the status and the number of revisions
- the final answer
- the node path in order, and how many research subtasks ran
- LLM calls, tokens and cost

If the status is not `completed`, say which limit was reached (`budget_exhausted` or `revision_limit`) and what the findings show.
