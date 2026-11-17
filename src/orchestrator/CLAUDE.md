# Rules for `src/orchestrator`

These rules apply on top of `AGENTS.md` when working in this package.

- The graph is built by `build_graph` in `graph.py`. Nodes are closures over `llm`, `tools` and `cfg`. Do not add module-level mutable state.
- Before a node writes a new state key, declare it in `state.py`. If the key accumulates, give it a reducer.
- Use `step_event` for every node. When a model is called, pass the response `usage`. Use `detail` keyword arguments for anything else worth seeing in the trace.
- `route_supervisor` and `route_after_critique` are the only places that choose the next node. Keep them pure: read state, return a label, and make sure every label is in the edge map.
- The ReAct subgraph is invoked from `research`. Pass `max_steps` clipped to the remaining model-call budget, and merge its events into the parent state.
- A new prompt role needs a `ROLE:` tag, a branch in `OfflineModel.complete`, and a test that exercises it.
- `GraphConfig` is the single source of limits. Tests override it. Production defaults stay in `config.py`.
