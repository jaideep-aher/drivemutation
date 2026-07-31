# DriveMutation

Local **counterfactual autonomous-vehicle test compiler**. Stage 1 is a fully deterministic 2D scenario simulator and validator. Stage 2 adds a reproducible SFT dataset + offline evaluation harness for compiling seed scenes + natural-language goals into canonical mutations (deterministic targets only).

## What Stage 1 does

- Strict Pydantic schemas for roads, ego/actors, behaviors, triggers, mutations, and safety oracles (SI units only: m, s, m/s, m/s²)
- Fixed **0.1 s** timestep simulation: straight roads, four-way intersections, constant-velocity motion, triggered crossing / cut-in, parked occluders
- Metrics: collisions, minimum TTC, acceleration, jerk, lane-boundary violations, initial overlap
- Deterministic validators (schema, bounds, placement, reachable triggers, oracles, contradictions)
- Six handwritten presets
- FastAPI backend + React/Vite SVG bird’s-eye UI

## Layout

```
backend/app/          FastAPI app, schemas, simulator, validators, presets, dataset/, eval/
frontend/             React + TypeScript + Vite UI
tests/                pytest suite (Stage 1 + Stage 2)
scripts/              local run helpers + dataset generation / offline eval
docs/DATASET.md       Stage 2 dataset documentation
data/                 raw / processed / outputs (generated JSONL is regenerable)
models/               reserved for later stages
```

## Setup

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

Copy `.env.example` to `.env` / `.env.local` for placeholders. **No API keys are required.** If `ANTHROPIC_API_KEY` is set in `.env.local`, Stage 2 may optionally paraphrase testing goals only — never labels, numbers, mutations, or expected answers.

## Run locally

```bash
# Terminal 1 — API on :8000
export PYTHONPATH=.
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — UI on :5173 (proxies /api → :8000)
cd frontend && npm run dev
```

Or use `scripts/run_backend.sh` and `scripts/run_frontend.sh`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness |
| GET | `/api/presets` | List six presets |
| GET | `/api/presets/{id}` | Full scenario JSON |
| POST | `/api/validate` | Validate scenario |
| POST | `/api/simulate` | Validate + simulate |

## Presets

1. Occluded pedestrian  
2. Occluded cyclist  
3. Aggressive cut-in  
4. Unprotected left turn  
5. Construction lane closure  
6. Wrong-way vehicle  

## Tests

```bash
# Backend
export PYTHONPATH=.
pytest -q

# Frontend
cd frontend && npm test && npm run build
```

## Stage 2 — SFT dataset

See [docs/DATASET.md](docs/DATASET.md) for full details.

```bash
export PYTHONPATH=.
python scripts/generate_dataset.py --seed 20260730
python scripts/evaluate_offline.py --split test
```

Produces `data/processed/{train,validation,test}.jsonl` (120/30/30), plus `data/outputs/dataset_report.json` and `leakage_report.json`. Eight scenario families; splits by composition (road × actor × trigger × hazard) with no train/test leakage. Same seed → identical files.

## Design notes

- Same scenario input → identical frames and metrics (deterministic).
- Explicit `assumptions` and `unknowns` travel with every scenario.
- Mutation ops are structured and applied before simulation; Stage 1 does not invent scenarios via LLM.
- Stage 2 canonical targets are always produced and validated by deterministic code.
