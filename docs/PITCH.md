# Five-minute pitch outline

1. **Problem (45s)**  
   AV teams need counterfactual stress tests, but turning a natural-language testing goal into an executable scene mutation is brittle. Base LLMs often emit invalid JSON, physically impossible placements, or fail to reject contradictory asks.

2. **Why fine-tuning (30s)**  
   We need a compiler that speaks our strict schema and respects deterministic physics/oracle contracts  -  not free-form storytelling.

3. **Training strategy (45s)**  
   Build a reproducible 180-example SFT set with composition-based splits (no paraphrase leakage). Canonical answers are generated and validated by code. Optional paraphrase models never write labels.

4. **Base vs fine-tuned (45s)**  
   Same test prompts, temperature 0, identical validators. Show measured deltas: parse/schema/physics rates, hazard/oracle correctness, impossible-request rejection, latency.

5. **Live demo (90s)**  
   Lab: pick a seed → edit scene → enter goal → Compare both → inspect JSON diff → play only valid mutations on the SVG map. Show the impossible preset rejecting safely.

6. **Evaluation results (30s)**  
   Evaluation page: only measured artifacts. Call out test-set size and methodology.

7. **Risks and limitations (30s)**  
   Not a vehicle controller. Not a crash reconstructor. Not a safety proof. Requires human review. 2D kinematics only.

8. **Closing takeaway (15s)**  
   Fine-tuning helps when the target language is a validated domain DSL  -  and deterministic oracles keep the demo honest.
