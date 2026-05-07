# Paper

Source for the arXiv artifact paper that accompanies this implementation.

## Build

Requires a TeX distribution with `pdflatex` and `bibtex` (e.g. MacTeX,
TeX Live, MiKTeX). From this directory:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Output: `main.pdf`.

## Files

- `main.tex` — the full paper source (~9 pages plus bibliography).
- `refs.bib` — bibliography (Zhang et al. RLM paper, Hermes Agent,
  CodeAct, Ouroboros).
- `README.md` — this file.

## Submission target

Suggested arXiv categories: primary `cs.AI`, with `cs.CL` or `cs.SE` as
possible cross-lists. The paper is positioned as a runtime-lifting systems
paper: it argues that RLM's operational advantages can be exposed as an
agent-runtime primitive without claiming a new model architecture or new
RLM theory.

## Honest scope reminder

The empirical core of the paper is **one controlled truncation fixture**
that now ties after claim-aware rescoring, plus TraceGuard enforcement,
Hermes-free synthetic scorer, and contract-ablation experiments. The strongest
current result is the runtime-control story: TraceGuard rejects unsafe parent
synthesis, evidence-gated Hermes-RLM stays safe, the same RLM-shaped policy
without evidence gating fails, and the project-local `ooo rlm` wrapper now
applies TraceGuard in-process after parent synthesis. Generalisation across
live tasks, model families, and chunking regimes is explicitly named as future
work.
