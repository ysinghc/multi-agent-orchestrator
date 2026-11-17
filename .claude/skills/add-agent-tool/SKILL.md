---
name: add-agent-tool
description: Adds a new tool that ReAct workers can call, with its limits, offline behaviour, tests and documentation. Use when an agent needs a new capability, such as a lookup, a calculation or a database query.
---

# Add an agent tool

## Steps

1. Write a function `(input: str) -> tuple[str, list[str]]` in `src/orchestrator/tools.py`. It returns an observation the agent can read, and a list of source IDs. Return an `error:` observation for expected failures. `react.py` catches unexpected exceptions, but do not rely on that.
2. Enforce limits inside the tool: input length, a timeout, and access only to what the tool is for. A network tool needs an explicit allowlist and a timeout, and its tests use a stub, never a live call.
3. Wrap the function in a `Tool(name, description, run)` factory, the same way `calculator_tool` and `knowledge_tool` are built. The name is what the model writes in `action`, so keep it short, lowercase, with underscores.
4. Register the tool where `cli.py` assembles its tool list. Tests that build the graph pass tools explicitly.
5. Teach the offline model when to use it. Add a branch to `OfflineModel._react` in `offline.py`, and keep the existing branches working.
6. Add tests. Put unit tests for the happy path, the error observation and the limits in `tests/test_tools_and_parsing.py`. Add one ReAct test with `ScriptedModel` in `tests/test_react.py`.
7. If you add a module, update the Layout section of `AGENTS.md`.

## Done when

- `make check` passes.
- `make trace TASK="..."` shows the new tool being called, with its observation in the trace.
- The tool cannot run without bound: a timeout or size cap exists, and a test covers it.
