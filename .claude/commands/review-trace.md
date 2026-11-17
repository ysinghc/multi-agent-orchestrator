---
description: Run a task with JSON output and check its trace for control-flow and cost anomalies
argument-hint: <task>
allowed-tools: Bash(make trace:*), Bash(orchestrate:*), Read, Grep
---

Write the run to `.demo/trace.json` with `make trace TASK="$ARGUMENTS"`, then read the file.

Check and report on:

1. **Budget.** `llm_calls` against the default limit of 20. Any `*.skipped` node in the path.
2. **Revisions.** The number of `write` events minus one. Whether the critic's `score` rose between drafts.
3. **Recovery.** `react.think` events with `action` set to `invalid`, and whether the next step recovered.
4. **Loops.** Any node repeated more often than the configured bounds allow.
5. **Cost.** Total USD, and the most expensive step.

Report findings only. Do not change code.
