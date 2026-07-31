# Limitations, ethics, and human review

## Hard claims we do **not** make

- DriveMutation does **not** control a vehicle.
- It does **not** reconstruct real crashes exactly.
- It does **not** prove safety or certify an AV stack.
- It is **not** production-ready infrastructure.

## Technical limitations

- Planar 2D kinematics only (no elevation, weather, sensors, planners).
- Fixed 0.1 s timestep; constant-velocity segments between triggers.
- Roads: straight segments and simplified four-way intersections.
- Oracles are scripted proxies (collision, TTC, lane keep, initial overlap)  -  not full safety cases.
- LLM outputs may be malformed, schema-invalid, or physically invalid; the pipeline must reject them before simulation.
- Dataset scale is hackathon-sized (180 examples); generalization is limited.
- Fine-tuning cost/latency and model availability depend on external OpenAI access.

## Ethical risks

- Generated scenarios could be misread as evidence about real-world crash causation.
- Stress-test content may depict harm to vulnerable road users; treat as synthetic engineering fixtures only.
- Publishing fine-tuned models or datasets without review could spread incorrect “ground truth.”

## Human-review requirement

Any scenario used for engineering decisions must be reviewed by a qualified human. Prefer:

1. Inspect seed scene and NL goal.
2. Inspect compiled JSON and validation issues.
3. Replay simulation metrics (TTC, collisions, oracles).
4. Reject or edit before exporting downstream.

## Attribution

- Public software: FastAPI, Pydantic, React, Vite, OpenAI Python SDK, pytest, Vitest.
- Scenario families and metrics are original to this project (hackathon).
- Stage 2 natural-language goals: deterministic templates by default; optional Anthropic paraphrase if `ANTHROPIC_API_KEY` is set  -  **paraphrase only**, never labels or numeric targets.
- Stage 3 inference/fine-tuning uses OpenAI APIs when configured; secrets stay in local `.env.local` and are never committed.
