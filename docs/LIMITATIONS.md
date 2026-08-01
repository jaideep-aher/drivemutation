# Limitations, ethics, and human review

## Hard claims we do **not** make

- SignalForge does **not** control a vehicle.
- It does **not** reconstruct real crashes exactly.
- It does **not** prove safety or certify an AV stack.
- It is **not** production-ready infrastructure.

## What is published fact vs. our judgement

This distinction matters more than anything else in this document, because the
project's whole claim is provenance.

**Published, traceable to a primary source:**

- The 36 substantive NHTSA pre-crash scenario names, transcribed from
  DOT HS 810 767 (2007). Two researchers transcribed them independently from the
  primary PDFs and all 37 names matched exactly; `tests/test_catalog.py` checks
  the code against `data/typology/nhtsa_precrash_typology.json` so the two
  cannot drift.
- Per-scenario annual crash counts and shares (DOT HS 810 767, Table 13, 2004
  GES), and the nine crash groups with their 2011-2015 shares
  (DOT HS 812 745, 2019). `crash_frequency_weight` is arithmetic on those
  published shares, not an invented ranking.
- UNECE R157 risk-perception, reaction, lateral-wander and deceleration
  thresholds.
- Euro NCAP CPNA / CPFA / CPTA protocol structure.

**Our engineering judgement, not published data:**

- Every speed, distance and time-to-collision *range*. The NHTSA reports give
  crash frequencies, not parameter distributions. Each catalog entry says so in
  its provenance notes. Replacing these with distributions fitted from real
  driving logs is the entire point of a later stage.
- Which ODD parameters each scenario varies, and over what values.
- The HAZOP-derived sensor-degradation scenarios, which are derivations rather
  than transcriptions.

## Modelling conventions that reinterpret the source

Three deliberate reinterpretations, applied consistently and documented in
`catalog.py`:

- **Single-vehicle scenarios are re-cast around the ego as the system under
  test.** The typology describes what the *subject* vehicle does, so "control
  loss" means the subject skids. Testing that the ego skids exercises vehicle
  dynamics, not an automated driving system, so where the hazard is another road
  user's loss of control, failure or evasive manoeuvre, the other vehicle
  carries that behaviour. Road-edge departure is the exception.
- **Backing is modelled as a low-speed closing conflict.** There is no gear
  model; a reversing conflict's criticality is set by closing speed and gap,
  which are the same in either gear.
- **Scenario 34, Non-Collision Incident, is catalogued but not generated.** It
  has no conflict partner, so the kinematic layer cannot represent it. It is
  flagged `simulable=False` and excluded from expansion rather than given
  meaningless metrics.

## Technical limitations

- Planar 2D kinematics only. No elevation, no vehicle dynamics, no tyre model.
- Fixed 0.1 s timestep, explicit integration. This is the source of the ~3 m
  divergence between a semantically-exported braking actor and a player that
  integrates continuously (see `docs/OPENSCENARIO.md`).
- **Road curvature is an ODD label, not geometry.** Actors move in straight
  lines whatever `road_geometry` says, and exported roads are straight.
- Criticality metrics (TTC, PET, required deceleration) use longitudinal
  approximations and an axis-aligned overlap test, not true oriented bounding
  boxes.
- R157 preventability is computed against a simplified competent-driver model,
  not the full regulatory procedure.
- Lidar is a geometric raycaster, not calibrated to any real sensor. Radar is an
  RCS/Doppler approximation. There is no camera model.
- Pairwise (t=2) ODD coverage is guaranteed; higher-order interactions are not,
  and a t=2 guarantee says nothing about three-way faults.
- Coverage is over the *discrete* ODD. Continuous parameters are sampled, not
  covered.
- Scenarios are not tuned for criticality — most generated variants are benign
  by construction. Criticality search is later work.
- SGO incident classification is keyword matching over narratives, which will
  both miss and mislabel.

## Ethical risks

- Generated scenarios could be misread as evidence about real-world crash
  causation. They are engineering fixtures traced to crash *statistics*, not
  reconstructions of specific crashes.
- Crash-frequency weights come from 2004 and 2011-2015 US light-vehicle data.
  They do not describe other countries, other vehicle classes, or today.
- Stress-test content depicts harm to vulnerable road users; treat as synthetic
  fixtures only.
- Publishing a catalog that *looks* authoritative is itself a risk. The
  distinction above between published figures and our own ranges is the mitigation,
  and it should survive any summary of this work.

## Human-review requirement

Any scenario used for engineering decisions must be reviewed by a qualified
human. Prefer:

1. Inspect the logical scenario and its provenance citation.
2. Check whether the parameter ranges are judgement or published.
3. Replay the simulation metrics (TTC, PET, collisions, preventability).
4. Run the OpenSCENARIO export in your own simulator and confirm it behaves as
   you expect before trusting it.

## Attribution

- Public software: FastAPI, Pydantic, React, Vite, Three.js, NumPy, pytest.
- Validation uses [esmini](https://github.com/esmini/esmini) (Mozilla Public
  License 2.0), which is downloaded in CI and not vendored here.
- Scenario definitions derive from public NHTSA, UNECE and Euro NCAP documents;
  see `data/typology/nhtsa_precrash_typology.json` for the primary sources.
