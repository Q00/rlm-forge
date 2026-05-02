#!/usr/bin/env bash
# 02 — Vanilla single-Hermes-call baseline on the long-context truncation
# fixture. One hermes call, two chunks omitted on purpose. Reports the
# baseline quality score that recursive RLM must beat.
set -euo pipefail
exec ouroboros rlm --vanilla-baseline "$@"
