# Paper ooo rlm Full Demo

This artifact records an actual dependency `ouroboros rlm` run over `paper/main.tex`. In the installed CLI this is the terminal counterpart to `ooo rlm`, not the generic `ouroboros run` workflow engine.

## Command

```bash
uv run --extra dev ouroboros rlm paper/main.tex --cwd /Users/jaegyu.lee/Project/ouroboros-rlm-hermes --debug
```

Reported result: `7` Hermes atomic execution sub-calls and RLM tree depth `1`.

## Flow

```text
paper/main.tex
  |
  | ooo rlm / ouroboros rlm selects bounded chunks
  v
6 child Hermes calls
  |
  | child_result:000..005 with chunk summaries and evidence
  v
1 parent Hermes synthesis call
  |
  | consumes all child_result ids
  v
parent AC verdict: satisfied
  |
  +-- accepted claims: runtime-lifted RLM, role split, TraceGuard framing, portability
  +-- residual gaps: unsupplied later lines, no live quality/cost/token/latency proof
```

## Child Calls

| Order | Session | Chunk | Verdict | Hermes memory injected |
| ---: | --- | --- | --- | --- |
| 0 | `20260507_183455_5faa47` | `paper/main.tex:1-80` | `completed` | `true` |
| 1 | `20260507_183516_a0b0b4` | `paper/main.tex:81-160` | `completed` | `true` |
| 2 | `20260507_183540_28aa87` | `paper/main.tex:161-240` | `completed` | `true` |
| 3 | `20260507_183602_b8da5f` | `paper/main.tex:241-320` | `success` | `true` |
| 4 | `20260507_183620_9faf64` | `paper/main.tex:321-400` | `accepted` | `true` |
| 5 | `20260507_183641_ca0a99` | `paper/main.tex:401-480` | `pass` | `true` |

## Parent Thesis

The supplied target context covers paper/main.tex lines 1-480 of a LaTeX article titled "RLM-FORGE: Runtime-Lifted Recursive Language Models for Agent Infrastructure" by JQ Lee, dated May 4, 2026. Across the six completed child chunks, the paper frames RLM-FORGE as a systems/runtime implementation of Recursive Language Model behavior rather than a new recursive model checkpoint. The abstract and introduction state that RLM can be runtime-lifted into an existing agent runtime: Hermes supplies bounded provider-swappable inner calls, Ouroboros owns recursive state, scheduling, trace replay, acceptance-criteria decomposition, and state mutation, and TraceGuard validates parent synthesis against accepted child evidence before claims can be committed. The background section defines RLM as an inference strategy in which an outer LLM call invokes itself or another LLM over transformed bounded input slices, describes Hermes as a provider-agnostic agent runtime with RPC tools and isolated subagents, and identifies Ouroboros components reused unchanged, including a typed acceptance-criteria tree with depth cap five and a HermesCliRuntime adapter. The system-design sections define runtime lifting as converting the RLM inference pattern into a stable runtime contract with bounded context selection, inner-LM invocation, evidence recording, and outer decisions to recurse, summarize, synthesize, retry, or terminate. They distinguish runtime-lifted RLM from ordinary map-reduce by requiring a traceable call graph, typed modes, evidence handles, and accepted or rejected child results. They also specify the ownership split: Hermes performs bounded local inference and must not recursively invoke Ouroboros or ooo commands, while Ouroboros remains the sole recursive controller and TraceGuard ...

## Accepted Claims

- `OOO-RLM-CLAIM-001` RLM-FORGE's main claim is systems-level: it runtime-lifts RLM into existing agent infrastructure rather than introducing a new model architecture. Supports: paper/main.tex:41-75, paper/main.tex:81-96, paper/main.tex:196-211.
- `OOO-RLM-CLAIM-002` The runtime architecture separates responsibilities: Hermes performs bounded inner calls, Ouroboros owns recursive orchestration and state mutation, and TraceGuard validates parent synthesis against accepted child evidence. Supports: paper/main.tex:47-56, paper/main.tex:88-96, paper/main.tex:213-240, paper/main.tex:241-320, paper/main.tex:321-337.
- `OOO-RLM-CLAIM-003` The paper identifies preserved RLM runtime control surfaces: bounded context partitioning, explicit parent-child call graphs, replayable child evidence, inspectable intermediate claims, and rejectable parent synthesis before state mutation. Supports: paper/main.tex:51-56, paper/main.tex:98-107, paper/main.tex:204-211, paper/main.tex:241-274.
- `OOO-RLM-CLAIM-004` Hermes is constrained to local bounded inference and is explicitly prohibited from recursively invoking Ouroboros or ooo commands inside the RLM loop. Supports: paper/main.tex:281-291, paper/main.tex:334-337.
- `OOO-RLM-CLAIM-005` RLM-FORGE has two integration paths: a dedicated RLMOuterScaffoldLoop used by ooo rlm, and an optional Hermes-backed decompose_ac extension that leaves default ooo run and ooo evolve behavior unchanged when hermes_runtime is absent. Supports: paper/main.tex:124-129, paper/main.tex:341-360.
- `OOO-RLM-CLAIM-006` The experiment is framed as a runtime/control-surface validation, not a broad quality benchmark; the live truncation fixture reports a tie after scorer correction. Supports: paper/main.tex:56-62, paper/main.tex:131-143, paper/main.tex:369-377.
- `OOO-RLM-CLAIM-007` The primary portability run reports 24 mandatory contract passes across Hermes+GLM, Claude Code, and Codex under the same RLM-FORGE+TraceGuard contract. Supports: paper/main.tex:56-62, paper/main.tex:131-143, paper/main.tex:429-463.
- `OOO-RLM-CLAIM-008` Memory is treated as operational policy or schema/retry prior rather than admissible factual evidence; accepted evidence is rebuilt from fresh child outputs. Supports: paper/main.tex:62-72, paper/main.tex:145-160.
- `OOO-RLM-CLAIM-009` The repair loop is a bounded runtime-control response for missing or null evidence handles, not a benchmark win in the latest matrix because all initial parent syntheses validated before repair. Supports: paper/main.tex:131-143, paper/main.tex:463-477.

## Evidence Gate Result

- Parent AC status: `satisfied`
- All child results consumed: `true`
- All accepted claims have child support: `true`
- Memory is treated as prior, not evidence.
- Caveat: `ouroboros rlm` did not automatically call `rlm_forge.traceguard.validate_parent_synthesis`; that validator belongs to the TraceGuard/live-portability harness. This demo proves the `ooo rlm` decomposition and parent-synthesis path.

## Residual Gaps

- Only paper/main.tex lines 1-480 were supplied; later sections, bibliography, appendices, code artifacts, trace logs, and any content after the beginning of the operational memory experiment are outside the supplied context.
- Several empirical claims are reported in the supplied text, including truncation-fixture parity, deterministic ablations, memory-enabled matrix results, and a 24-cell primary portability pass, but the underlying raw traces, full benchmark data, scoring code, and artifact contents are not supplied here for independent verification.
- The 96-cell matrix is described as a plan, while the supplied text states that only the primary 24 live cells are executed in this version; no conclusion should be drawn about the full baseline sweep.
- The supplied text explicitly states that latency, token count, and monetary cost were not persisted for the live truncation artifact and that cost-profile generalization across providers is not established.
- The operational memory experiment begins at line 479 but substantive details are outside the supplied context, so parent synthesis can only report the earlier abstract/introduction-level memory claims and the transition into that section.
- Some child summaries reference line ranges beyond their chunk labels, such as a scope limitation cited as lines 162-166 inside the chunk labeled 81-160; this synthesis treats the supplied chunk contents and explicit evidence references conservatively and does not rely on unsupplied lines for new claims.
