#!/usr/bin/env bash
# Replay-mode demo script. No Hermes calls.
set -euo pipefail

say() { printf '\n\033[1;36m$ %s\033[0m\n' "$1"; sleep 1.0; }

say "# RLM-FORGE — replay demo (no API key required)"
sleep 0.5

say "ls benchmarks/"
ls benchmarks/
sleep 1.5

say "python -m rlm_forge.replay benchmarks/rlm-long-context-truncation-v1.json"
python -m rlm_forge.replay benchmarks/rlm-long-context-truncation-v1.json
sleep 2.0

say "python scripts/run-traceguard-demo.py"
python scripts/run-traceguard-demo.py
sleep 2.0

say "# Corrected live scoring shows a tie on the fixture."
say "# TraceGuard is the contribution upgrade: unsafe parent synthesis is rejected."
say "# Hermes supplies sub-call boundaries; Ouroboros enforces evidence handles."
sleep 1.5
