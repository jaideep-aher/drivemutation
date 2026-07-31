# DriveMutation

Small local app that turns a driving scene plus an English stress-test goal into a structured mutation, then plays it in a 2D SVG view.

It fine-tunes OpenAI `gpt-4o-mini` so the model learns our mutation JSON schema. The demo compares stock GPT vs the fine-tuned model side by side.

This is a research / class prototype. It does not control a car and it is not a safety proof.

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env.local
# put OPENAI_API_KEY and OPENAI_FINE_TUNED_MODEL in .env.local

export PYTHONPATH=.
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# other terminal
cd frontend && npm run dev
```

Open http://127.0.0.1:5173

Or build the frontend and let FastAPI serve it:

```bash
cd frontend && npm run build && cd ..
export PYTHONPATH=.
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## Env vars

| Name | Notes |
|------|--------|
| OPENAI_API_KEY | required for compile / fine-tune scripts |
| OPENAI_BASE_MODEL | default gpt-4o-mini-2024-07-18 |
| OPENAI_FINE_TUNED_MODEL | your ft:... model id |
| OPENAI_FINE_TUNING_JOB_ID | optional, for resume |
| DATASET_SEED | default 20260730 |

Secrets stay in `.env.local`. Do not commit them.

## Fine-tune / eval scripts

```bash
export PYTHONPATH=.
python scripts/generate_dataset.py --seed 20260730
python scripts/run_baseline.py
python scripts/upload_training_data.py
python scripts/create_finetuning_job.py
python scripts/check_finetuning_job.py --poll
python scripts/evaluate_model.py --which fine-tuned
python scripts/compare_models.py
```

Model id pointer: `models/MODEL_CARD.txt`

## Deploy

Dockerfile builds the UI and runs one uvicorn process.

Railway: connect this repo, set the env vars above, deploy.

Hugging Face Spaces: create a Docker space from this repo, set the same secrets, port 7860. See `README_SPACE.md`.

## Tests

```bash
export PYTHONPATH=.
pytest -q
cd frontend && npm test && npm run build
```

## Docs

- docs/ARCHITECTURE.md
- docs/DATASET.md
- docs/MODEL_CARD.md
- docs/PITCH.md
- docs/LIMITATIONS.md
