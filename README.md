# SignalForge

Grounded AV test scenarios with full **provenance**, **OpenSCENARIO export**, synthetic **lidar** and **radar**, and a Three.js viewer.

**Live:** [https://web-production-58352.up.railway.app](https://web-production-58352.up.railway.app) · Scenario viewer: [/app](https://web-production-58352.up.railway.app/app)

## Pitch

5,000+ auditable driving scenarios traced to:

- **NHTSA** pre-crash typology — all **36 substantive scenarios**, with published crash frequencies
- **UNECE R157** cut-in / cut-out / deceleration (exact regulatory parameters)
- **Euro NCAP** VRU protocols (CPNA / CPFA / CPTA)
- **HAZOP** sensor-degradation derivations
- **NHTSA SGO** real ADS incident narratives (classified into families + gap list)

No scenario is free-invented by an LLM. Click any scenario to see the regulation clause or incident report behind it.

Every scenario exports to **ASAM OpenSCENARIO**, so you can run the catalog against your own stack without installing SignalForge.

## Quick start

```bash
# Backend deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Generate catalog + 5,000 concrete scenarios + SGO ingest
python scripts/generate_signalforge.py --target 5000

# Export scenarios as runnable OpenSCENARIO bundles
python scripts/export_xosc.py --limit 50 --out data/openscenario

# API
uvicorn backend.app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 — homepage at `/`, scenario viewer at `/app`.

## Running the scenarios

Exported bundles are self-contained: a `.xosc` plus the `.xodr` road it
references, with entity geometry inline. No catalog files, no 3D models, no
dependency on your simulator's asset directory.

```bash
esmini --window 60 60 1000 600 --osc data/openscenario/<scenario>.xosc
```

Validate that exports still mean what the catalog claims:

```bash
export ESMINI=/path/to/esmini          # binary or install directory
python scripts/validate_xosc.py --check all --trajectory-mode
```

See [docs/OPENSCENARIO.md](docs/OPENSCENARIO.md) for how behaviours map onto
OpenSCENARIO constructs and what the fidelity guarantee does and does not cover.

## Coverage

The discrete ODD backbone comes from a constraint-aware **t-way covering
array**, so the coverage claim is a guarantee rather than a hope: every pair of
ODD values that is physically reachable appears in at least one scenario.
Combinations ruled out by physics — an icy surface under clear skies — are
reported as unreachable instead of quietly counted as covered.

```
Pairwise ODD coverage: 100.0% of 1769 reachable combinations (4 ruled out by constraints)
```

Coverage is measured on the scenarios that were actually generated, by code that
rebuilds the target set independently of the generator. `GET /api/coverage/odd`
serves the report.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Service status + counts |
| `GET /api/catalog` | Logical scenarios |
| `GET /api/scenarios` | Filterable concrete list |
| `GET /api/scenarios/{id}` | Full scenario + metrics + provenance |
| `POST /api/render` | On-demand lidar/radar point clouds |
| `GET /api/coverage` | Family / weather / difficulty coverage |
| `GET /api/coverage/odd` | Measured t-way ODD coverage |
| `GET /api/gaps` | SGO incidents with no catalog match |
| `GET /api/export/{id}` | nuScenes-style bundle with sensor frames |

## Architecture

```
logical catalog (46: 36 NHTSA + 3 R157 + 3 Euro NCAP + 4 HAZOP)
   → constraint-aware t-way covering array over the ODD
   → kinematic sim (TTC, PET, required decel, R157 preventability)
   → OpenSCENARIO .xosc + OpenDRIVE .xodr export, validated against esmini
   → NumPy lidar raycaster + radar RCS/Doppler + degradation layer
   → Three.js viewer with provenance panel
```

Point clouds are generated **on demand** (and optionally cached for a showcase
subset). Scenario definitions are tiny JSON, and an exported `.xosc` is about
7 KiB — no terabyte sensor dump required to run the demo.

## Production / Railway

Multi-stage `Dockerfile` builds the Vite frontend into `frontend/dist` and serves it from FastAPI (`backend.app.main:app`). Health check: `GET /api/health`.

```bash
railway up
```

## What this is not

A publishable sensor-accurate benchmark. Lidar is geometrically plausible, not
calibrated to a real Velodyne. There is no photorealistic camera. Parameter
ranges come from regulations and engineering judgement, not fitted real-world
log distributions — the published crash *frequencies* are real, the speed and
distance *ranges* are not. Road curvature is an ODD label, not simulated
geometry. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).
