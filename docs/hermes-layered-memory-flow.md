# Hermes Layered Memory Flow

This note records the observed memory behavior in the RLM-FORGE + Hermes
runtime path. It is meant as a presentation and investigation aid, not as a
new benchmark claim.

## Short Claim

Hermes built-in memory is actually injected into RLM-FORGE Hermes calls when
`HermesCliRuntime` invokes `hermes chat` without `--ignore-rules`.

That memory can shape the model's behavior, but RLM-FORGE still admits only
fresh child evidence into TraceGuard. In the real-world replay below, the parent
synthesis correctly refused to treat the locally observed Hermes built-in memory
layer as document evidence because the supplied child records did not support
that claim.

## Layer Map

```text
                                user / evaluator
                                      |
                                      v
                         +-------------------------+
                         | Ouroboros / RLM-FORGE   |
                         | control plane           |
                         +-------------------------+
                         | - selects chunks        |
                         | - schedules child calls |
                         | - records child outputs |
                         | - runs TraceGuard       |
                         +------------+------------+
                                      |
                                      | HermesCliRuntime
                                      | hermes chat -Q --source tool -q <prompt>
                                      | no --ignore-rules
                                      v
           +-------------------------------------------------------+
           | Hermes Agent process                                 |
           +-------------------------------------------------------+
           | auto-injected context before RLM-FORGE prompt          |
           |                                                       |
           |   AGENTS.md / SOUL.md / .cursorrules / skills          |
           |   ~/.hermes/memories/MEMORY.md                         |
           |       RLM-FORGE operational prior entries              |
           |                                                       |
           | explicit RLM-FORGE prompt                              |
           |   task: extract_child_evidence                         |
           |   task: synthesize_parent_answer_from_child_evidence   |
           |   optional memory_priors from RLM-FORGE JSONL memory    |
           +--------------------------+----------------------------+
                                      |
                                      v
                         +-------------------------+
                         | Hermes JSON output      |
                         +-------------------------+
                                      |
                                      v
                         +-------------------------+
                         | TraceGuard              |
                         +-------------------------+
                         | validates parent claims |
                         | only against fresh      |
                         | child evidence manifest |
                         +-------------------------+
```

## Three Memory-Like Surfaces

```text
+----------------------+---------------------------+---------------------------+
| Surface              | Where it lives            | What it may influence     |
+----------------------+---------------------------+---------------------------+
| Hermes built-in      | ~/.hermes/memories/       | Prompt prior, formatting, |
| memory               | MEMORY.md                 | habits, schema discipline |
+----------------------+---------------------------+---------------------------+
| RLM-FORGE guarded    | JSONL memory store        | Structured memory_priors  |
| operational memory   | e.g. experiments/*.jsonl  | for schema/retry policy   |
+----------------------+---------------------------+---------------------------+
| Fresh child evidence | current run child_records | Only admissible basis for |
| manifest             | built per run             | accepted parent claims    |
+----------------------+---------------------------+---------------------------+
```

Important distinction:

```text
memory prior      -> may guide how Hermes behaves
fresh evidence    -> may support a parent claim
TraceGuard        -> decides whether a claim can be accepted
```

## Confirmed Local Evidence

Hermes memory file:

```text
~/.hermes/memories/MEMORY.md
mtime: 2026-05-03 19:22:23
size: 1939 bytes
contains: RLM-FORGE operational prior entries
```

Representative entry shape:

```text
RLM-FORGE operational prior (not answer evidence): Completed
fixture=simple-truncation-01,
family=hermes_glm,
status=live_contract_pass,
traceguard_accepted=true,
child_call_count=4,
...
Memory is not evidence; it is a prior over how to ask for fresh evidence...
```

Hermes sessions created after that memory was written include the memory block
in `system_prompt`:

```text
~/.hermes/sessions/session_20260504_124943_1690c5.json
  system_prompt contains "MEMORY (your personal notes)"
  system_prompt contains "RLM-FORGE operational prior"

~/.hermes/sessions/session_20260507_155921_c20dde.json
  system_prompt contains "MEMORY (your personal notes)"
  system_prompt contains "RLM-FORGE operational prior"

~/.hermes/sessions/session_20260507_155955_c29c7d.json
  system_prompt contains "MEMORY (your personal notes)"
  system_prompt contains "RLM-FORGE operational prior"
```

RLM-FORGE runtime invocation:

```text
HermesCliRuntime:

args = [self._cli_path, "chat"]
args.extend(["-Q", "--source", "tool"])
args.extend(["-q", full_prompt])

No --ignore-rules is passed.
```

So Hermes built-in memory injection is not hypothetical in this environment.
It is present in the actual session prompts.

## RLM-FORGE Guarded Memory

RLM-FORGE also has its own memory mechanism.

```text
src/rlm_forge/memory.py
  - allowlisted prior kinds
  - allowlisted tasks
  - allowlisted recommendations
  - forbidden patterns for FACT:, LP/LC fact IDs, chunk IDs, injection text

src/rlm_forge/live_portability.py
  - recalls memory only when memory_context.can_read
  - attaches structured memory_priors to child/parent prompt payloads
  - writes operational observations only when memory_context.can_write
```

Prompt-level rule attached by RLM-FORGE:

```json
{
  "memory_priors": {
    "scope": "operational_policy_only",
    "rules": [
      "Memory is not evidence.",
      "Do not use memory to support factual claims.",
      "Use memory only for schema, routing, or retry policy."
    ],
    "priors": []
  }
}
```

## TraceGuard Boundary

TraceGuard does not inspect either memory layer directly.

```text
current run child_records
        |
        v
build_fresh_child_evidence_manifest(...)
        |
        v
TraceGuardEvidence(fact_id, chunk_id, text, child_call_id)
        |
        v
validate_parent_synthesis(evidence_manifest, parent_synthesis)
        |
        +--> accept only fact_id + evidence_chunk_id pairs in manifest
        +--> reject unsupported fact IDs
        +--> reject missing evidence handles
        +--> reject chunk-only references
```

This is the evidence firewall:

```text
Hermes MEMORY.md
  can bias behavior
  cannot become evidence

RLM-FORGE memory_priors
  can bias schema/retry policy
  cannot become evidence

fresh child manifest
  can support parent claims
```

## Real-World Replay

To avoid relying only on synthetic fixture text, a mini real-world replay was
run over actual repository documents.

### Inputs

Child 1 received the README memory section:

```text
README.md:364-424
```

Child 2 received the paper memory experiment section:

```text
paper/main.tex:466-508
```

Both calls were made through Hermes:

```text
hermes chat -Q --source tool -q <json prompt>
```

Both calls also had Hermes built-in memory in their `system_prompt`. The prompt
explicitly instructed the model:

```text
Do not call tools.
Do not write or update memory.
Use only the provided chunk/child_records as evidence.
Do not infer from Hermes built-in MEMORY.md; it is a prior, not evidence.
```

### Child Prompt Shape

```json
{
  "task": "extract_child_evidence",
  "real_world_case": "rlm_forge_memory_claim_from_repo_docs",
  "rules": [
    "Use only the provided repository document chunk.",
    "Extract concise facts about memory, evidence, TraceGuard, and what can be claimed.",
    "Every observed_fact must include fact_id, text, and evidence_chunk_id.",
    "Do not infer from Hermes built-in MEMORY.md; it is a prior, not evidence."
  ],
  "required_schema": {
    "observed_facts": [
      {
        "fact_id": "string",
        "text": "string",
        "evidence_chunk_id": "string"
      }
    ],
    "residual_gaps": ["string"]
  },
  "chunk": {
    "chunk_id": "README.md:364-424",
    "text": "..."
  }
}
```

### Child Outputs

Child 1 extracted README-supported facts:

```text
RW-001  RLM-FORGE includes experimental memory mode for live portability.
RW-002  Memory is not evidence; it is a prior over how to ask for evidence.
RW-003  TraceGuard manifest is built from current child outputs, not memory.
RW-004  Parent claims still need fresh child evidence and TraceGuard acceptance.
```

Child 2 extracted paper-supported facts:

```text
RW-005  Memory backend is JSONL with allowlisted operational records.
RW-006  memory_priors may enter prompts but are not accepted evidence.
RW-007  TraceGuard manifest is rebuilt from current child outputs.
RW-008  24 memory-enabled cells passed, supporting runtime feedback only.
```

### Parent Prompt Shape

```json
{
  "task": "synthesize_parent_answer_from_child_evidence",
  "real_world_case": "rlm_forge_memory_claim_from_repo_docs",
  "rules": [
    "Use only observed_facts returned by child calls.",
    "Summarize what can be safely presented about RLM-FORGE memory.",
    "Separate documented RLM-FORGE guarded memory from the locally observed Hermes built-in memory layer.",
    "Every retained_facts entry must include fact_id and evidence_chunk_id.",
    "Do not claim quality improvement from memory."
  ],
  "child_records": [
    {
      "call_id": "realworld-memory-docs::hermes_glm::child::1",
      "chunk_id": "README.md:364-424",
      "output": {
        "observed_facts": ["RW-001", "RW-002", "RW-003", "RW-004"]
      }
    },
    {
      "call_id": "realworld-memory-docs::hermes_glm::child::2",
      "chunk_id": "paper/main.tex:466-508",
      "output": {
        "observed_facts": ["RW-005", "RW-006", "RW-007", "RW-008"]
      }
    }
  ]
}
```

### Parent Output Behavior

The parent synthesis accepted the documented RLM-FORGE guarded memory claims,
but refused to overclaim the Hermes built-in memory layer from document evidence.

Key residual gaps:

```text
The provided evidence supports only the documented RLM-FORGE guarded memory
design and reported live portability-harness behavior; it does not establish
anything about the locally observed Hermes built-in memory layer.

The provided evidence does not support any claim that memory improves downstream
model quality.
```

This is exactly the desired separation:

```text
local observation:
  Hermes built-in memory is injected into system_prompt

document evidence:
  RLM-FORGE guarded memory exists and is not evidence

parent synthesis:
  may claim document-supported RLM-FORGE guarded memory
  may not claim document-unsupported Hermes built-in memory
```

### TraceGuard Result

The parent output was validated with the local TraceGuard implementation.

```text
accepted: true
unsupported_claim_rate: 0.0
rejected_claims: []
allowed_fact_ids:
  RW-001 RW-002 RW-003 RW-004
  RW-005 RW-006 RW-007 RW-008
allowed_chunk_ids:
  README.md:364-424
  paper/main.tex:466-508
```

## Detailed Call Timeline

```text
t0  Hermes MEMORY.md already contains RLM-FORGE operational prior entries
    |
    v
t1  RLM-FORGE / investigator calls Hermes child extraction
    |
    | hermes chat -Q --source tool -q <child prompt>
    | no --ignore-rules
    v
t2  Hermes builds system prompt
    |
    | includes MEMORY.md
    | includes RLM-FORGE operational prior text
    | then includes explicit child prompt
    v
t3  Child output extracts facts only from supplied README / paper chunk
    |
    v
t4  Parent synthesis call repeats the same Hermes memory injection behavior
    |
    | but parent prompt says:
    |   use only child_records as evidence
    |   do not infer from Hermes built-in memory
    v
t5  Parent output claims RW-001..RW-008
    |
    | parent also records residual gap:
    |   local Hermes built-in memory layer is not established by child evidence
    v
t6  TraceGuard validates parent claims against fresh child manifest
    |
    v
t7  all claims accepted, unsupported_claim_rate = 0.0
```

## Presentation Framing

Safe version:

```text
We observed an emergent layered memory effect.

Hermes built-in memory was present in actual RLM sub-call system prompts,
because the Hermes adapter calls `hermes chat` without `--ignore-rules`.
RLM-FORGE also has a separate guarded JSONL memory that enters prompts only as
structured `memory_priors`.

Both memory layers can influence model behavior, but neither is admissible
evidence. TraceGuard accepts parent claims only when fresh child evidence from
the current run supports the cited fact_id and evidence_chunk_id.
```

Avoid saying:

```text
We intentionally designed a two-layer memory architecture.
Hermes memory proves the answer.
Memory improves quality.
TraceGuard validates semantic truth.
```

Say instead:

```text
This layered memory behavior emerged from composing Hermes with RLM-FORGE.
It is useful as a behavioral prior, while TraceGuard preserves the evidence
boundary.
```

## Open Questions

```text
1. Which exact Hermes turn wrote the first RLM-FORGE operational prior into
   ~/.hermes/memories/MEMORY.md?

2. Should production RLM-FORGE pass --ignore-rules for isolated benchmark runs,
   and omit it only for memory-enabled product runs?

3. Should public artifacts explicitly record whether Hermes built-in memory was
   active, separate from RLM-FORGE memory mode?

4. Should a future benchmark compare:
      no Hermes memory + no RLM-FORGE memory
      Hermes memory only
      RLM-FORGE memory only
      both memory layers
   while keeping TraceGuard evidence rules unchanged?
```

