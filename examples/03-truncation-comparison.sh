#!/usr/bin/env bash
# 03 — Side-by-side vanilla vs recursive RLM on the same truncation fixture.
# Real Hermes is invoked for both paths. Persists JSON artifacts under
# .ouroboros/rlm/{benchmarks,baselines}/ for replay.
set -euo pipefail
exec ouroboros rlm --truncation-benchmark "$@"
