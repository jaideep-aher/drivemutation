# Architecture

```mermaid
flowchart TB
  subgraph ui [React_Lab]
    preset[Preset_Select]
    scene[Scene_JSON_Editor]
    goal[NL_Testing_Goal]
    compare[Base_vs_FT_Panels]
    svg[SVG_BirdEye_Playback]
    evalPage[Evaluation_Page]
  end

  subgraph api [FastAPI]
    health["/api/health"]
    presets["/api/presets"]
    validate["/api/validate"]
    simulate["/api/simulate"]
    compileBase["/api/compile/base"]
    compileFT["/api/compile/fine-tuned"]
    status["/api/models/status"]
    evalSum["/api/evaluation/summary"]
  end

  subgraph core [Deterministic_Core]
    schemas[Pydantic_Schemas]
    validators[Validators]
    sim[Simulator_0.1s]
    mutations[Mutation_Apply]
  end

  subgraph llm [Server_Side_OpenAI]
    baseModel[Base_gpt4o_mini]
    ftModel[Fine_Tuned_Model]
  end

  subgraph data [Artifacts]
    jsonl[processed_jsonl]
    reports[eval_and_compare_json]
  end

  preset --> presets
  scene --> validate
  scene --> simulate
  goal --> compileBase
  goal --> compileFT
  compileBase --> baseModel
  compileFT --> ftModel
  baseModel --> validators
  ftModel --> validators
  validators -->|accepted| mutations
  mutations --> sim
  sim --> svg
  reports --> evalSum --> evalPage
  jsonl --> llm
```

## Components

| Package | Role |
|---------|------|
| `backend/app/schemas` | Strict Pydantic models (road, actors, triggers, mutations, oracles) |
| `backend/app/validators` | Schema/physics/placement/oracle/contradiction checks |
| `backend/app/simulator` | Fixed-timestep 2D kinematics, collisions, TTC, oracles |
| `backend/app/presets` | Eight handwritten demo seeds |
| `backend/app/dataset` | Deterministic SFT example generator |
| `backend/app/eval` | Offline metric harness |
| `backend/app/openai_ft` | Config, jobs, compile, measured evaluation (secrets stay server-side) |
| `frontend` | Dark lab UI + measured evaluation page |

## Trust boundary

- Browser talks only to FastAPI over `/api`.
- OpenAI SDK runs only in Python.
- Canonical training labels always come from deterministic code, never from an LLM.
