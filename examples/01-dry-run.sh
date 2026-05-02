#!/usr/bin/env bash
# 01 — Dry-run RLM path validation. No Hermes calls, no side effects.
# Confirms the command is wired and source-evidence emission works.
set -euo pipefail
exec ouroboros rlm --dry-run "$@"
