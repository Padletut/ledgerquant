# Replay analysis scripts

One-off analyses behind `documents/research/2026-10-analyst-replay-findings.md`.
They read finished run directories and the tick archive; no model calls. Run from
the repository root with `PYTHONPATH=src` and the project environment. Paths
default to `data/replay_runs` and `data/archive`; override with
`LEDGERQUANT_RUNS` and `LEDGERQUANT_ARCHIVE`.

| Script | Question |
| --- | --- |
| `decompose.py` | analyst/3 vs analyst/4: exits, the same entries held under the same rules, entry geometry |
| `openended.py` | weekend close vs open-ended holding for every entry |
| `naive.py` | always long / always short at every decision hour with declared geometry |
| `momentum.py` | 23-hour momentum at every decision hour with declared geometry |
| `fx_losses.py` | per-trade diagnostics (direction, noise stops, chasing, news); writes a JSON of rows |
| `claude_vs_gpt.py` | Claude vs GPT week by week and what acting on Claude's stated view at WAIT/NO_SIGNAL would have earned |

The report's free-rule comparison itself is part of the pipeline
(`ledgerquant.replay.baselines`), not of these scripts.
