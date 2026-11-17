# Agent guide: multi-agent-orchestrator

This file is the shared instruction set for coding agents and human contributors. Keep it accurate. When a workflow or invariant changes, change this file in the same commit.

## What this project is

A hierarchical multi-agent system on LangGraph. A supervisor plans the work. Research workers run a ReAct subgraph with tools. A writer drafts the answer, and a critic reviews it and triggers bounded revisions. State is checkpointed, so a run can pause for review and resume. Budgets are enforced inside the graph, and every step emits a trace event.

The default model is `OfflineModel`, a deterministic rules engine that is not an LLM. It lets the whole control flow run without credentials. `GeminiChat` is the production adapter.

## Commands

Run these from the repository root. `make install` creates `.venv` once.

| Task | Command |
|---|---|
| Install the dev environment | `make install` |
| Format | `make format` |
| Lint | `make lint` |
| Tests | `make test` |
| Lint and tests (run before reporting work as done) | `make check` |
| Run a task and print the step trace | `make run TASK="..."` |
| Run a task and write the JSON trace to `.demo/trace.json` | `make trace TASK="..."` |
| Remove caches and build output | `make clean` |

## Layout

- `src/orchestrator/graph.py`: the supervisor graph. Nodes are `plan`, `research`, `write`, `critique` and `finish`. Routing functions and `build_graph`.
- `react.py`: the ReAct worker subgraph: `think`, `act`, `finalize`.
- `state.py`: `OrchestratorState` and `ReActState`, with reducers for accumulating keys.
- `config.py`: `GraphConfig` (limits, approval threshold, budgets) and `Pricing`.
- `tools.py`: `calculate` (AST whitelist), `calculator_tool`, `KnowledgeBase`, `knowledge_tool`.
- `prompts.py`: role prompts. Each one starts with a `ROLE:` tag.
- `parsing.py`: tolerant JSON parsing for plans and critiques.
- `offline.py`: `OfflineModel` (rules per role) and `ScriptedModel` (replays fixed replies in tests).
- `llm.py`: the `ChatModel` protocol, `Usage`, `LLMResponse`, and `GeminiChat`.
- `telemetry.py`: `step_event` and `summarize`.
- `runner.py`: `run_task`, `RunResult`, `initial_state`.
- `cli.py`: the `orchestrate` command.
- `examples/corpus/`: the knowledge base used by the demo.

## Invariants: do not break these

1. **Budget before every model call.** A node that calls the model checks `over_budget` first and degrades without calling when the budget is spent. The planner is the only exception, because it runs first.
2. **Reducers for accumulating state.** `findings`, `events`, `llm_calls`, `cost_usd`, and the ReAct keys `scratchpad`, `sources` and `steps` are declared with reducers in `state.py`. Never overwrite them with a plain assignment.
3. **Every node emits a trace event** built with `step_event`. A step that calls the model passes the response usage, so it is counted. A graph test checks that the trace call count matches the expected control flow.
4. **Every loop is bounded.** ReAct stops at `max_react_steps`, clipped to the remaining call budget. Revisions stop at `max_revisions`. Subtasks stop at `max_subtasks`. A new loop needs a bound and a test that reaches it.
5. **Failures become observations.** Tool errors and malformed model replies are returned to the agent as text. They must not raise out of a node.
6. **Model output is data.** Never pass it to `eval` or `exec`. The calculator walks a whitelisted AST.
7. **The offline model covers every path.** It exercises the revision loop, budget exhaustion, the step limit and malformed replies. If you change a `ROLE:` tag or a prompt, update the dispatch in `offline.py` and the tests that depend on it.

## Testing rules

- Every behaviour change ships with a test. Changes to control flow need a graph-level test in `tests/test_graph.py`, not only a unit test.
- Tests make no network calls. Use `OfflineModel` or `ScriptedModel`. Test the Gemini adapter with fake clients.
- Never weaken a budget or loop assertion to make a test pass.

## Conventions

- Python 3.11+. Type hints on public functions. Dataclasses for data.
- `ruff`, line length 100. Run `make format` before committing.
- New dependencies go in `pyproject.toml`. The PR explains why each is needed.
- No secrets in code or config. Never read `.env` files.
- Commit subjects are imperative and under 72 characters.

## Working agreement for agents

1. Read the node or module and its tests before editing. For graph changes, read `graph.py` from start to finish.
2. Make the smallest change that works, and add tests alongside it.
3. Run `make check`. For changes to routing, budgets or prompts, also run `make trace TASK="..."` and check the path it prints.
4. Report what you ran and what it returned. State what you did not verify, such as live Gemini calls.
5. Do not push, deploy or change cloud resources unless the user explicitly asks.

## Known gaps

- Offline outputs come from rules, so they say nothing about answer quality. Quality needs a live model and a labelled task set.
- Checkpointing uses `MemorySaver`, which lives in one process.
- The prices in `config.py` are placeholders.
- Research workers run one after another. LangGraph `Send` fan-out is not implemented yet.
