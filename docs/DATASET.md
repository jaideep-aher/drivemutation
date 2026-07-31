# Stage 2 Dataset

DriveMutation Stage 2 builds a **reproducible supervised fine-tuning (SFT) dataset** and an **offline evaluation harness** that map a seed driving scene + natural-language testing goal to a canonical executable counterfactual mutation (or a structured rejection).

## Design principles

- **Canonical targets are deterministic code only** — never LLM-authored labels, numbers, mutations, or expected answers.
- Optional Claude paraphrase is used **only** to rephrase the user-facing testing goal when `ANTHROPIC_API_KEY` is present in `.env.local`. If absent, deterministic templates are used.
- Splits are by **scenario composition** `(road_layout, actor, trigger, hazard)`, not by paraphrase. The test set contains compositions unseen in train/validation.

## Counts

| Split | Examples |
|-------|----------|
| train | 120 |
| validation | 30 |
| test | 30 |
| **total** | **180** |

Includes **150 accepted mutations** and **30 structured rejections**.

## Scenario families (8)

1. Occluded pedestrian  
2. Occluded cyclist  
3. Aggressive cut-in  
4. Merge  
5. Unprotected left  
6. Construction zone  
7. Emergency vehicle  
8. Wrong-way vehicle  

## Example fields

Each JSONL record contains:

- Structured `seed_scene`
- Natural-language `testing_goal`
- `canonical_target` (accepted mutation JSON or rejection JSON)
- `expected_scenario_family`, `expected_activated_hazard`
- `expected_validation_result`, `expected_safety_oracle_results`
- `assumptions`, `unknowns`
- OpenAI-style `messages`: `[system, user, assistant]` where the assistant content is **only** canonical JSON

## Regenerate

```bash
source .venv/bin/activate
export PYTHONPATH=.
python scripts/generate_dataset.py --seed 20260730
```

Outputs:

- `data/processed/train.jsonl`
- `data/processed/validation.jsonl`
- `data/processed/test.jsonl`
- `data/outputs/dataset_report.json`
- `data/outputs/leakage_report.json`

Re-running with the same seed yields **byte-identical** JSONL files.

## Offline evaluation

```bash
python scripts/evaluate_offline.py --split test
```

Metrics:

- JSON parse rate  
- Schema-valid rate  
- Physical-validity rate  
- Scenario-family accuracy  
- Hazard-activation rate  
- Oracle correctness  
- Impossible-request rejection accuracy  

Gold assistant messages score 1.0 on all metrics (sanity check). Pass a predictions JSON map (`example_id -> assistant text`) via `--predictions` to score a model.

## Quality gates (enforced in generator + tests)

- Schema validation of every target  
- Physics validation + simulation for every accepted target  
- Rejection reasons present for rejected examples  
- Duplicate seed+goal detection  
- Train/test composition leakage detection  
- Family / split statistics  
- Reproducibility (fixed seed)  
- JSONL SFT format validation  

## Package layout

```
backend/app/dataset/   generator, compositions, scenes, targets, paraphrase, validation
backend/app/eval/      offline metrics + harness
scripts/generate_dataset.py
scripts/evaluate_offline.py
tests/test_stage2_dataset.py
```

## Dataset card (summary)

| Field | Value |
|-------|--------|
| Name | DriveMutation SFT compiler dataset |
| Language | English NL goals + JSON scenes/targets |
| License / distribution | Local hackathon artifact; regenerate via seed |
| Intended use | Supervised fine-tuning of a schema-constrained mutation compiler |
| Out of scope | Real crash reconstruction; safety certification labels |
| Creation | Deterministic Python generators; optional Anthropic paraphrase of goals only |
| Attribution | Original compositions; SI unit conventions; OpenAI SFT JSONL message format |
| Human review | Required before any downstream engineering use |
