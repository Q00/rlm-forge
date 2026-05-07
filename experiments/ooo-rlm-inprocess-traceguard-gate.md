# ooo rlm In-Process TraceGuard Gate

This artifact exercises the same adapter installed by the project-local
`uv run ooo rlm` and `uv run ouroboros rlm` entrypoints. It uses the
persisted paper run so the experiment is deterministic and does not
rerun Hermes.

## Source

- Demo artifact: `experiments/paper-key-sections-ooo-rlm-demo.json`
- Source command: `uv run --extra dev ouroboros rlm experiments/paper-ooo-rlm-key-sections-target.txt --cwd /Users/jaegyu.lee/Project/ouroboros-rlm-hermes --debug`
- Process-local patch installed in experiment: `true`

## Cases

| Case | Accepted | Unsupported rate | Rejection reasons |
| --- | ---: | ---: | --- |
| raw_persisted_parent | false | 0.0435 | unsupported_fact_id |
| handle_repaired_parent | true | 0.0000 | none |
| handle_repaired_parent_plus_memory_answer | false | 0.0500 | unsupported_fact_id |

## Interpretation

The in-process gate is stricter than the earlier normalized post-run
artifact. It rejects the raw persisted parent because that parent cites
`rlm_node_root:child_result:004`, while the actual run produced child
results `000..003`. After repairing that handle to the actual fresh
child manifest, the same evidence boundary accepts. When a memory-answer
fact is injected into the repaired parent, the gate rejects it because
the fact is not present in the current run's child evidence manifest.
