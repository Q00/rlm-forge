# Architecture

The RLM MVP has two layers and one orchestration owner. **Ouroboros** is the
recursion controller; **Hermes** is a subordinate model runtime called
through the existing adapter for bounded inference. Hermes never recursively
calls Ouroboros or invokes `ooo` commands as part of the RLM loop.

```text
User
  |
  v
ooo rlm
  |
  v
Ouroboros outer scaffold
  - validates ambiguity <= 0.2
  - owns ACTree recursion, max depth 5
  - owns RLM tree state, scheduling, termination, trace persistence
  - calls Hermes through HermesCliRuntime
  |
  v
Hermes inner LM layer
  - receives one bounded recursive sub-call at a time
  - proposes decomposition, atomic execution, summary, or synthesis
  - returns one structured JSON envelope to Ouroboros
```

## Responsibility split

| Concern | Ouroboros outer scaffold | Hermes inner LM |
| --- | --- | --- |
| Command entrypoint | Owns the isolated `ooo rlm` path; keeps `ooo run` and `ooo evolve` unchanged | Invoked only from the RLM path; exposes no separate RLM entrypoint |
| Recursion | Owns RLM node scheduling, AC decomposition, atomic execution, retries, stop decisions | Proposes local decomposition, execution, summary, or synthesis for one bounded node |
| Guardrails | Enforces ambiguity ≤ 0.2, AC tree max depth 5, cancellation, retry exhaustion, completion | Echoes guardrails in responses, cannot relax or finalise them |
| State mutation | Mutates AC nodes, RLM nodes, artifacts, EventStore trace records | Returns structured output only; no direct mutation |
| Context selection | Selects source chunks, summaries, child results, ancestry, token budgets within Hermes RPC limits | Uses only the supplied context and cites only supplied evidence IDs |
| Runtime boundary | Calls `HermesCliRuntime.execute_task_to_result()` through the existing `AgentRuntime` adapter | Runs behind the adapter's RPC/tool mechanism; no new REPL or transport |

## Sub-call lifecycle (six steps)

1. Ouroboros validates RLM guardrails and selects exactly one sub-call mode:
   `decompose_ac`, `execute_atomic`, `summarize_chunk`, or `synthesize_parent`.
2. Ouroboros binds bounded context and writes the call-start trace metadata.
3. Ouroboros invokes Hermes through `HermesCliRuntime` with no direct
   recursive call back into Ouroboros.
4. Ouroboros parses and validates the Hermes JSON envelope: schema version,
   echoed IDs, verdict, confidence, and evidence references.
5. Ouroboros commits accepted results into the AC tree, RLM tree, artifacts,
   and EventStore trace. Invalid responses become recorded failures and do
   not mutate recursive state.
6. Ouroboros schedules any follow-up decomposition, atomic execution,
   summary, synthesis, retry, or termination decision.

Hermes may *recommend* that a node is atomic, decomposed, retryable, or ready
for synthesis. Only Ouroboros turns that recommendation into recursive
control flow.

## Two integration paths exposed today

| Path | Entry point | Where Hermes is called |
| --- | --- | --- |
| Recursive scaffold | `ooo rlm --benchmark` | `ouroboros.rlm.loop.RLMOuterScaffoldLoop` drives 1 root + N chunk sub-calls through `HermesCliRuntime` |
| AC decomposition pipeline | `decompose_ac(hermes_runtime=...)` | `ouroboros.execution.decomposition.decompose_ac` accepts an `AgentRuntime` and delegates child-AC generation to Hermes |

The default `ooo run` and `ooo evolve` flow keep their original LLM-only
behaviour. Passing `hermes_runtime=None` (the default) bypasses every
RLM-specific branch in `decompose_ac`.

## Source map

| Concern | Upstream module | Lines (approx.) |
| --- | --- | --- |
| Outer scaffold loop | `ouroboros.rlm.loop` | 3,200 |
| Trace store / replay | `ouroboros.rlm.trace` | 1,060 |
| Vanilla baseline | `ouroboros.rlm.baseline` | 860 |
| Hermes adapter wrapper | `ouroboros.rlm.hermes_adapter` | 730 |
| Sub-call contracts | `ouroboros.rlm.contracts` | 460 |
| Fixtures | `ouroboros.rlm.fixtures` | 450 |
| Truncation benchmark | `ouroboros.rlm.truncation_benchmark` | 360 |
| Quality comparison | `ouroboros.rlm.quality` | 310 |
| Dogfood benchmark | `ouroboros.rlm.benchmark` | 250 |
| Public API | `ouroboros.rlm.__init__` | 270 |
| AC decomposition Hermes path | `ouroboros.execution.decomposition` (gated by `hermes_runtime`) | 1,322 |
| CLI command | `ouroboros.cli.commands.rlm` | ~400 |

The full concept design lives upstream at
`docs/guides/recursive-language-model.md` (1,580 lines) in the Ouroboros
repository.
