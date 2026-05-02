# Why Hermes was the right inner LM

Building a Recursive Language Model needs an inner LM runtime that is
*callable like a function*. Most inference stacks force you to wrap the LM
in something stateful — sessions, conversations, tool catalogs, retrieval
indexes. Hermes already collapses those into a single quiet RPC turn.
That is the property the RLM scaffold needs.

## What we did *not* have to build

The RLM literature (Zhang et al., arXiv 2512.24601) describes a Python REPL
environment that holds long context as a variable while an outer LM
recursively calls itself. Implementing that from scratch usually means:

- a sandboxed REPL with bounded variables and message replay,
- a tool catalog the inner LM can interact with,
- a session manager to scope each recursive frame,
- transport that delivers structured I/O without leaking outer context.

Hermes already provides all four. From the Hermes README:

> *"Spawn isolated subagents for parallel workstreams. Write Python scripts
> that call tools via RPC, collapsing multi-step pipelines into zero-context
> turns."*

That sentence is the load-bearing quote for this submission. The "RPC,
zero-context turns" pattern is structurally identical to one RLM sub-call:

```
Outer caller
  -> envelope (structured JSON: mode, context, IDs, guardrails)
  -> Hermes runtime (isolated)
  -> bounded inference
  -> envelope (structured JSON: verdict, evidence, residuals)
  -> back to outer caller
```

We adopted the existing `HermesCliRuntime.execute_task_to_result()` as the
single recursive boundary. No new REPL, no new sandbox, no new transport.
The `HermesCliRuntime` adapter ships with Ouroboros and was unchanged for
the MVP.

## Concrete properties leveraged

### 1. Provider-agnostic LLM

Hermes can target Nous Portal, OpenRouter (200+ models), NIM, Xiaomi MiMo,
z.ai/GLM, Kimi, MiniMax, OpenAI, and custom endpoints. The recursion is
invariant to the chosen model — `hermes model` swaps it out without code
changes. For the hackathon judges this means an OpenRouter key is enough.

For our empirical run we routed through a custom endpoint declared in
`~/.hermes/config.yaml`:

```yaml
model:
  default: gpt-5.5
  provider: custom
  base_url: https://[redacted-endpoint]/v1
```

Replacing `base_url` with `https://openrouter.ai/api/v1` and choosing a
different `default` model yields the same RLM behaviour.

### 2. Quiet, structured I/O

Hermes accepts a JSON prompt and returns a JSON `final_message`. The
adapter strips reasoning prelude and banner output for clean parsing. This
makes the LM call **functional** — same input, same output, no incidental
state leakage between recursive frames.

### 3. Existing RPC tool reuse

Each RLM sub-call envelope carries:

- `mode` — one of `decompose_ac`, `execute_atomic`, `summarize_chunk`,
  `synthesize_parent`.
- `call_context` — `call_id`, `parent_call_id`, `rlm_node_id`, `ac_node_id`.
- `constraints` — `must_not_call_ouroboros: true`, ambiguity threshold,
  depth cap.
- `context` — only the chunks, summaries, ancestry, and child results
  selected by the outer scaffold.
- `evidence_handles` — IDs Hermes is allowed to cite.

The response carries `verdict`, `confidence`, `result`, `evidence_references`,
and `residual_gaps`. All of this is enforced by `ouroboros.rlm.contracts`
and validated before the outer scaffold mutates state.

### 4. Subagent spawn potential

Hermes' isolated subagent mechanism is not used in the MVP, but it is the
obvious vehicle for *horizontal* RLM tree expansion (multiple chunks
processed in parallel sub-calls instead of sequentially). The MVP keeps
recursion sequential to keep the trace replayable and the scoring
deterministic.

## What the inner LM is forbidden to do

Hermes operates under three explicit constraints expressed in the system
prompt and re-encoded in the structured contract:

1. **Do not call Ouroboros recursively.** No invoking `ooo` commands, no
   spawning ouroboros sessions from within an inner sub-call. Recursion
   ownership stays with the outer scaffold.
2. **Cite only supplied evidence.** The `evidence_handles` list is the
   universe of valid citations. References outside that set are recorded
   as a contract violation and the response is rejected.
3. **No guardrail relaxation.** Hermes can echo `ambiguity_threshold` and
   `max_depth` in its envelope but cannot widen them.

These constraints are what make omitted-fact safety measurable: the scaffold
can reject evidence references outside the supplied handles. They reduce the
surface for unsupported claims, but they do not by themselves prove a quality
advantage over vanilla single-call inference.

## Summary

The MVP works because Hermes was already built to be *the inner LM you want
in an RLM scaffold*. Provider-agnostic, structured, isolated, and with an
existing RPC pattern that maps onto recursive sub-calls one-to-one.
