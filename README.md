# DriveMutation

Local **counterfactual autonomous-vehicle test compiler**. Given a structured seed scene and a natural-language stress-testing goal, DriveMutation compiles an executable mutation (or a structured rejection), validates it with deterministic physics/schema checks, and plays the result in a 2D SVG simulator.

**This does not control a vehicle, reconstruct real crashes, prove safety, or constitute a production AV stack.** Human review is required before any engineering use of generated scenarios.

## What you get

| Layer | Capability |
|-------|------------|
| Stage 1 | Deterministic schemas, validators, 0.1 s simulator, 8 demo presets, FastAPI + React SVG lab |
| Stage 2 | Reproducible SFT dataset (180 examples), leakage checks, offline gold eval |
| Stage 3 | OpenAI baseline + supervised fine-tuning + measured base vs FT evaluation (server-side only) |
| Product UI | Dark AV-engineering lab: scene edit, NL goal, base/FT compare, JSON diff, evaluation page |

## Layout

```
backend/app/     schemas, simulator, validators, presets, dataset, eval, openai_ft
frontend/        React + TypeScript + Vite UI (Lab + Evaluation)
tests/           pytest (Stages 1–3)
scripts/         run helpers, dataset, FT, eval CLIs
docs/            architecture, dataset card, model card, pitch, limitations
data/            raw / processed / outputs (generated; regenerable)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..

cp .env.example .env.local
# Edit .env.local — never commit secrets
```

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | For compile / FT / live eval | Server-side only; prefer `.env.local` |
| `OPENAI_BASE_MODEL` | Default pinned | `gpt-4o-mini-2024-07-18` |
| `OPENAI_FINE_TUNING_JOB_ID` | Optional | Resume existing FT job |
| `OPENAI_FINE_TUNED_MODEL` | For FT compile | `ft:…` model id after success |
| `ANTHROPIC_API_KEY` | Optional | Stage 2 paraphrase only — never labels |
| `DATASET_SEED` | Optional | Default `20260730` |
| `VITE_API_BASE` | Unused in UI | Relative `/api` via Vite proxy |

Stage 1–2 work offline without any API keys.

## Run locally

```bash
# Terminal 1 — API :8000
source .venv/bin/activate
export PYTHONPATH=.
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — UI :5173
cd frontend && npm run dev
```

Or `scripts/run_backend.sh` / `scripts/run_frontend.sh`.

Open http://127.0.0.1:5173 — Lab (`#/lab`) and Evaluation (`#/eval`).

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness |
| GET | `/api/presets` | Eight demo presets |
| GET | `/api/presets/{id}` | Full scenario JSON |
| POST | `/api/validate` | Schema/physics validation |
| POST | `/api/simulate` | Validate + simulate |
| POST | `/api/compile/base` | Compile via base model |
| POST | `/api/compile/fine-tuned` | Compile via FT model |
| GET | `/api/models/status` | Non-secret model/job status |
| GET | `/api/evaluation/summary` | Measured eval artifacts only |

## Demo presets

1. Occluded pedestrian  
2. Occluded cyclist  
3. Aggressive cut-in  
4. Unprotected left turn  
5. Construction lane closure  
6. Wrong-way vehicle  
7. Emergency vehicle  
8. Impossible request (structured rejection expected)

## Dataset & training

```bash
export PYTHONPATH=.
python scripts/generate_dataset.py --seed 20260730
python scripts/evaluate_offline.py --split test

# Stage 3 (requires OPENAI_API_KEY in .env.local)
python scripts/run_baseline.py
python scripts/upload_training_data.py
python scripts/create_finetuning_job.py   # idempotent
python scripts/check_finetuning_job.py --poll
python scripts/evaluate_model.py --mode fine-tuned
python scripts/compare_models.py
```

Job/file IDs live in gitignored `data/outputs/.openai_ft_state.json`. Fine-tuning submission never duplicates an existing active/succeeded job for the same training file.

## Tests

```bash
export PYTHONPATH=.
pytest -q

cd frontend && npm test && npm run build
```

OpenAI is **mocked** in unit tests. Real baseline/FT evaluation runs only when credentials and models are available.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Dataset card](docs/DATASET.md)
- [Model card](docs/MODEL_CARD.md)
- [Pitch outline](docs/PITCH.md)
- [Limitations & ethics](docs/LIMITATIONS.md)

## Design notes

- SI units only (m, s, m/s, m/s²).
- Same scenario → identical simulation frames/metrics.
- Invalid model output never reaches the simulator.
- Evaluation UI shows only measured files — missing ≠ zero.
- API keys never ship to the browser.
