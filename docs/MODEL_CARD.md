# Model card — DriveMutation compiler

## Models

| Role | Identifier |
|------|------------|
| Base | `gpt-4o-mini-2024-07-18` (pinned) |
| Fine-tuned | `OPENAI_FINE_TUNED_MODEL` (`ft:…`) after successful SFT |

Temperature for compile/eval: **0.0**. Same system prompt and user formatting as Stage 2 SFT JSONL.

## Intended use

- Demo / research prototype for compiling NL stress goals into **structured** scenario mutations.
- Side-by-side comparison of base vs fine-tuned JSON validity, physics validity, hazard/oracle metrics, and rejection handling.

## Out of scope

- Real-time vehicle control or planning
- Perception / sensor simulation
- Legal or safety certification
- Production deployment without human review

## Training data

See [DATASET.md](DATASET.md). 120 train / 30 validation / 30 held-out test examples. Canonical assistants produced by deterministic generators + validators.

## Evaluation

Measured with `scripts/run_baseline.py`, `scripts/evaluate_model.py`, `scripts/compare_models.py` on the untouched Stage 2 test split. Metrics: JSON parse, schema, physics, scenario family, hazard activation, oracle correctness, rejection accuracy, latency, token use.

**Do not invent metrics.** If artifacts are missing, the Evaluation page reports unavailable.

## Risks

Fine-tuned models can still emit invalid or unsafe-looking scenarios. All outputs must pass validators before simulation. See [LIMITATIONS.md](LIMITATIONS.md).
