# ooo rlm Live In-Process TraceGuard Run

This artifact records a live project-local `ooo rlm` invocation after adding
the in-process TraceGuard wrapper.

## Command

```bash
uv run --extra dev ooo rlm experiments/paper-ooo-rlm-key-sections-target.txt --cwd /Users/jaegyu.lee/Project/ouroboros-rlm-hermes --debug
```

## Result

| Check | Result |
| --- | --- |
| In-process TraceGuard gate | accepted |
| Unsupported rate | 0.0000 |
| Accepted parent claims | 4 |
| Hermes atomic execution sub-calls | 5 |
| RLM tree depth | 1 |
| `run` / `evolve` paths invoked | false |

## Key Output

```text
TraceGuard accepted parent synthesis (unsupported_rate=0.0000, claims=4).
RLM command path completed with 5 Hermes atomic execution sub-call(s); run/evolve command paths were not invoked.
benchmark: rlm-mvp-src-dogfood-v1; cited_source_files=1; rlm_tree_depth=1
```

## Interpretation

This is the live counterpart to the deterministic in-process gate replay. The
project-local `ooo` entrypoint installed the TraceGuard adapter, delegated to
the dependency Ouroboros RLM command, ran four child Hermes calls plus one
parent synthesis call, and accepted the parent synthesis before reporting
success.
