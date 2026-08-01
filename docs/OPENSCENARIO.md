# OpenSCENARIO export

Every concrete scenario exports to ASAM OpenSCENARIO. The goal is that someone
who has never installed SignalForge can run the catalog against their own stack
and get the same challenger behaviour we did.

## What a bundle contains

```
<scenario-id>.xosc     the scenario
<scenario-id>.xodr     the road it references
```

That is the whole dependency list. Entities carry their own bounding boxes and
performance inline, there are no `CatalogReference` elements, and no
`SceneGraphFile`. A binary-only esmini install with no `resources` directory
runs them, which is the property CI checks on every push.

```bash
esmini --window 60 60 1000 600 --osc <scenario-id>.xosc
```

## Three design decisions

### The ego is a slot, not a driver

The ego is teleported in, given its initial speed, and left alone. No scripted
braking, no controller. Whatever system is under test supplies the ego
behaviour — that is the point of the benchmark.

The reference driver's outcome rides along as metadata instead
(`sf_reference_min_ttc_s`, `sf_reference_preventable`, and so on), so you can
compare your stack against the R157 competent-driver baseline without that
baseline being baked into the scenario.

Exporting with `--reference-driver` scripts the R157 response explicitly. That
exists so we can check our own numbers reproduce, not for benchmarking.

### Challenger actors are reproducible, not reactive

Actors never react to the ego. Every system under test faces identical
challenger motion, which is what makes results comparable at all.

| Behaviour | OpenSCENARIO construct | Why |
|---|---|---|
| `constant_velocity` | init `SpeedAction` | fully described by the initial state |
| `static` | `TeleportAction` only | nothing moves |
| `brake` | `SpeedAction`, linear, `rate` | a brake really is a speed action; readable and re-parameterisable |
| `accelerate`, `cut_in`, `cut_out`, `swerve`, `cross`, `left_turn`, `encroach` | `FollowTrajectoryAction` over the simulated polyline | free-form motion the player would otherwise re-derive its own way |

`--trajectory-mode` exports *everything* as a trajectory, including braking.
That trades readability for exactness — see the fidelity table below.

### The frame is mirrored

SignalForge's kinematic layer puts oncoming traffic at negative y, which is a
left-hand-traffic convention. OpenDRIVE right-hand traffic puts opposing lanes
on the positive-`t` side, so the export mirrors y and heading. Mirroring is a
rigid transform: every distance, time-to-collision and criticality metric is
preserved exactly.

## Roads

The `.xodr` is synthesised per scenario. The reference line runs along +x and is
offset laterally so the ego's lane centre lands on y = 0, with enough lanes each
side to contain every actor for the whole run. Lane width is 3.5 m.

Actors that *cross* the carriageway — pedestrians, cyclists, animals — do not
widen the road. Sizing lanes to a pedestrian's walk would turn a two-lane road
into a fourteen-lane one.

**Road curvature is not exported.** The kinematic simulator moves actors in
straight lines regardless of what `road_geometry` says, so emitting a curved
road would put actors through a bend they never drove. Every export uses a
straight reference line and carries the declared geometry as metadata. Curvature
belongs with a map-aware simulator, not here.

## Validation

"It loaded" is a weak claim. esmini exits non-zero on structural errors —
malformed XML, a missing road file, a reference to an entity that does not
exist — but it accepts an invalid enumeration value and runs anyway. A file can
load and still describe the wrong scenario.

So validation has three gates:

1. **Loads** — esmini exits cleanly and prints nothing that looks like an error.
2. **Schema** — validates against the OpenSCENARIO XSD, when one is available
   locally (`--check schema --xsd <path>`). This is what catches the silently
   accepted bad enum.
3. **Fidelity** — esmini runs with CSV logging and the actor trajectories it
   produces are compared against SignalForge's own simulation.

Only the third can tell you the export means what it says.

```bash
export ESMINI=/path/to/esmini
python scripts/validate_xosc.py --check all --trajectory-mode
```

### Measured fidelity

Across all 45 simulable scenarios, comparing every actor at every 0.1 s step:

| Export mode | Worst position deviation |
|---|---|
| `--trajectory-mode` | **0.07 mm** |
| default (semantic) | **2.8 m**, and only on braking actors |

The semantic-mode gap is confined to `brake`. The kinematic simulator steps
deceleration at a fixed 0.1 s while the player integrates it continuously, and
over a full stop from motorway speed that difference reaches about three metres.
Everything else is trajectory-driven and exact.

Use trajectory mode when you need the published criticality metrics to
reproduce. Use the default when you want to read or re-parameterise the
scenario.

## Provenance

Provenance survives the export as `ParameterDeclarations` — the one place
OpenSCENARIO lets arbitrary key/value metadata ride inside a schema-valid
document:

```xml
<ParameterDeclaration name="sf_provenance_citation" parameterType="string"
  value="NHTSA DOT HS 810 767 (2007) pre-crash scenario 25 (Lead Vehicle Decelerating); ..."/>
```

The citation also appears in the `FileHeader` description, where a human reading
the file sees it first.

One consequence worth knowing: esmini echoes every parameter to its log, so a
scenario legitimately named "Vehicle Failure" prints the word "failure". The log
scanner skips parameter echoes for exactly this reason.
