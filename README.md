# SignalForge

Grounded AV test scenarios with synthetic **lidar** and **radar**, full **provenance**, and a Three.js viewer.

**Live:** [https://web-production-58352.up.railway.app](https://web-production-58352.up.railway.app) · Scenario viewer: [/app](https://web-production-58352.up.railway.app/app)

## Pitch

2,000+ auditable driving scenarios traced to:

- **NHTSA** pre-crash typology (9 groups + crash-frequency weights)
- **UNECE R157** cut-in / cut-out / deceleration (exact regulatory parameters)
- **Euro NCAP** VRU protocols (CPNA / CPFA / CPTA)
- **HAZOP** sensor-degradation derivations
- **NHTSA SGO** real ADS incident narratives (classified into families + gap list)

No scenario is free-invented by an LLM. Click any scenario to see the regulation clause or incident report behind it.

## Quick start

```bash
# Backend deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Generate catalog + ~2200 concrete scenarios + SGO ingest
python scripts/generate_signalforge.py --target 2200

# Optional: precompute lidar for showcase subset
python scripts/precompute_showcase.py --count 40

# API
uvicorn backend.app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 — homepage at `/`, scenario viewer at `/app`.

## Production / Railway

Multi-stage `Dockerfile` builds the Vite frontend into `frontend/dist` and serves it from FastAPI (`backend.app.main:app`). Health check: `GET /api/health`.

```bash
railway up
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Service status + counts |
| `GET /api/catalog` | Logical scenarios |
| `GET /api/scenarios` | Filterable concrete list |
| `GET /api/scenarios/{id}` | Full scenario + metrics + provenance |
| `POST /api/render` | On-demand lidar/radar point clouds |
| `GET /api/coverage` | Family / weather / difficulty coverage |
| `GET /api/gaps` | SGO incidents with no catalog match |

## Architecture

```
logical catalog (19)
   → constraint-checked combinatorial ODD expansion
   → kinematic sim (TTC, PET, required decel, R157 preventability)
   → NumPy lidar raycaster + radar RCS/Doppler + degradation layer
   → Three.js viewer with provenance panel
```

Point clouds are generated **on demand** (and optionally cached for a showcase subset). Scenario definitions are tiny JSON — no terabyte sensor dump required to run the demo.

## What this is not

A publishable sensor-accurate benchmark. Lidar is geometrically plausible, not calibrated to a real Velodyne. There is no photorealistic camera. Parameter ranges come from regulations, not fitted real-world log distributions. It demonstrates the provenance-first approach end-to-end.
