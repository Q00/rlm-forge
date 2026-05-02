# Hermes setup for reviewers

This page is for judges and reviewers who do not already have Hermes Agent
configured. It walks through the simplest path to a working Hermes that the
RLM scaffold can call. Total time: 5–10 minutes plus an API key.

## What you need

- macOS, Linux, or WSL2 (native Windows is not supported by Hermes).
- A working Python 3.12 or newer.
- An API key for one supported LLM provider. **OpenRouter** is the easiest
  because a single key works across 200+ models.

## Step 1 — Install Hermes

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.bashrc       # or ~/.zshrc
hermes --version       # confirm v0.11+
```

The installer drops the `hermes` binary in `~/.local/bin` and a config
directory at `~/.hermes/`.

## Step 2 — Configure a provider

### Option A — OpenRouter (recommended for judges)

1. Get an API key at https://openrouter.ai/keys.
2. Run the wizard:
   ```bash
   hermes setup
   ```
   When prompted, choose `OpenRouter` and paste your key.
3. Pick any model you have credits for. We tested with `openai/gpt-5` and
   `anthropic/claude-opus-4.7`; both work fine for the truncation fixture.

### Option B — Direct provider configuration

If you prefer to skip the wizard, write `~/.hermes/config.yaml` directly:

```yaml
model:
  default: openai/gpt-5
  provider: openrouter
providers:
  openrouter:
    api_key: ${OPENROUTER_API_KEY}
toolsets:
  - hermes-cli
agent:
  max_turns: 150
  gateway_timeout: 1800
```

Then export the key once per shell:

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
```

### Option C — Custom OpenAI-compatible endpoint

If your organization runs an internal OpenAI-compatible proxy (the
authoring environment used `[redacted-endpoint]`), set:

```yaml
model:
  default: <your-model-name>
  provider: custom
  base_url: https://your.endpoint/v1
```

Hermes then sends OpenAI Chat Completions traffic to that base URL. No
additional auth header is required if your proxy injects credentials
upstream; otherwise add `api_key:` under the `providers.custom` block.

## Step 3 — Smoke-test Hermes alone

Before invoking the RLM scaffold, confirm Hermes itself works:

```bash
echo 'Reply with the single word OK.' | hermes --quiet
```

You should see `OK` printed within a few seconds. If you see an
authentication error, re-check the provider config; if the call hangs,
verify `~/.hermes/config.yaml`'s `model.provider` matches the key you
exported.

## Step 4 — Run the RLM truncation benchmark

```bash
git clone https://github.com/Q00/rlm-forge.git
cd rlm-forge
pip install -e .
ooo rlm --truncation-benchmark
```

Expected last lines (real Hermes, ~1 minute):

```
Shared truncation benchmark completed; vanilla Hermes and recursive RLM
outputs were recorded.
hermes_subcalls: vanilla=1, rlm=5
chunks: selected=4, omitted=2
quality: vanilla=1.00, rlm=1.00, delta=+0.00, rlm_outperforms_vanilla=False
```

Absolute scores depend on the inner model. The current committed artifact is
a traceable integration check, not evidence that recursive RLM beats vanilla
on this fixture.

## Step 5 — If you cannot install Hermes

The committed JSON artifact in `benchmarks/` was produced by a real run.
You can replay it without any Hermes call:

```bash
python3 -m rlm_forge.replay benchmarks/rlm-long-context-truncation-v1.json
```

This prints the same headline metrics from the persisted file. It is the
safety net for evaluation environments without API access.

## Common issues

| Symptom | Cause | Fix |
| --- | --- | --- |
| `hermes: command not found` | install script did not update PATH | `source ~/.bashrc` or open a new shell |
| `401 Unauthorized` | wrong provider/key combo | re-run `hermes setup` and pick the matching provider |
| `model not found` | provider does not have your selected model | `hermes model` to list and pick another |
| `ouroboros: command not found` | RLM repo not installed | `pip install -e .` from the repo root |
| `ouroboros rlm` hangs >5 min | `max_turns=150` exhausted on a slow model | switch to a faster model with `hermes model` |

## What the scaffold does NOT do

Out of respect for your account quota:

- The RLM benchmark issues at most six Hermes calls per invocation
  (one vanilla + five recursive).
- No background polling, no scheduled runs.
- Each invocation is bounded by `--max-depth` (default 5) and chunk count
  in the fixture (six total chunks).
