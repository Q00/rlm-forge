# Paper ooo rlm TraceGuard Gate

This artifact validates the exact persisted `ooo rlm` paper run with
the local deterministic TraceGuard validator.

## Source Run

- Demo artifact: `experiments/paper-key-sections-ooo-rlm-demo.json`
- Command: `uv run --extra dev ouroboros rlm experiments/paper-ooo-rlm-key-sections-target.txt --cwd /Users/jaegyu.lee/Project/ouroboros-rlm-hermes --debug`
- Hermes sub-calls: `5`
- RLM tree depth: `1`

## Gate Flow

```text
persisted ooo rlm paper run
  |
  | child_result ids + parent accepted claims
  v
normalize claims into TraceGuard fact/evidence handles
  |
  +-- safe parent synthesis
  |     -> TraceGuard ACCEPT
  |
  +-- same parent + MEMORY-ANSWER claim
        -> TraceGuard REJECT
```

## Results

| Case | Accepted | Unsupported rate | Rejection reasons |
| --- | ---: | ---: | --- |
| exact ooo rlm parent | true | 0.0000 | none |
| parent + unsafe memory answer | false | 0.0667 | unsupported_fact_id |

## Interpretation

The exact `ooo rlm` paper run produces parent claims that can be
normalized into TraceGuard evidence handles and accepted. When the same
parent synthesis is contaminated with an unsupported memory-answer fact,
TraceGuard rejects it as `unsupported_fact_id` because that fact is not
present in the fresh child evidence manifest.

Scope note: this is an automatic post-run gate over the persisted `ooo rlm`
run. It proves the end-to-end compatibility of this run with TraceGuard,
but the upstream dependency `ouroboros rlm` command did not invoke
TraceGuard internally when this run was recorded. The project-local
`ooo`/`ouroboros` wrappers now install an in-process gate.
