# Cairntir Blender Add-on

> The first non-code Cairntir client. Proves the horizon thesis —
> **Cairntir doesn't care what is being remembered**. The same memory
> layer that records code decisions in the cairntir wing records 3D-print
> iteration outcomes in a blender wing. Same shape, same retrieval,
> same prediction-bound semantics.

---

## What This Is

A Blender add-on that captures decisions and 3D-print iteration outcomes
into Cairntir's memory layer and recalls prior print outcomes during preparation. You print something, you note what worked
and what didn't, the parameters you used, and Cairntir keeps the record
forever — searchable, prediction-bound, replayable through Decision
Replay just like any code decision.

After 30 prints, the **agent:reason** wing remembers which constraint
shifts you've reasoned about; the **blender-print/pla** room holds every
PLA iteration; Cairntir's contradiction detector flags when iteration #18
contradicts what iteration #11 taught you. The same machinery that
serves code memory serves print memory because *the memory layer
doesn't care*.

This is the first concrete demonstration of the path described in
`docs/roadmap.md` Horizon section — AI + grand-scale 3D printing +
post-scarcity tooling. Today it remembers code decisions. Tomorrow it
remembers which printed structure worked, what the temperature was,
what the grain direction was, what the next iteration should try.

---

## Architecture

The add-on writes drawer-shaped JSON envelopes to Cairntir's spool
directory (`$CAIRNTIR_HOME/spool/`). Cairntir's daemon already polls
that spool, parses each file into a Drawer, and persists it. The
add-on never imports the `cairntir` Python package — the writer is
**stdlib-only** by design, so installation in Blender's bundled Python
is zero-touch.

```
┌─────────┐         ┌──────────────────┐         ┌──────────┐
│ Blender │ ──drop→ │ ~/.cairntir/spool │ ──poll→ │  daemon  │
└─────────┘         └──────────────────┘         └──────────┘
                                                       │
                                                       ▼
                                                 ┌──────────┐
                                                 │ DrawerStore │
                                                 └──────────┘
```

Atomic writes (the add-on writes `.tmp` then `os.replace` into place)
mean the daemon never sees a half-written file. The spool format is
the same one `cairntir.daemon.spool.parse_capture` already
understands — no schema migration required.

---

Recall uses a separate, installed Cairntir Python process. The add-on sends the
selected wing, material and query; the bridge opens the existing store read-only,
authorizes a read grant, filters print outcomes, ranks them with matching cached
embeddings and returns complete drawers. Recall does not start the daemon,
acquire a model, migrate the store or update memory access counters.

## Install

1. Zip the `cairntir_blender/` directory:
   ```
   cd addons/
   zip -r cairntir-blender.zip cairntir_blender/
   ```
2. In Blender: **Edit → Preferences → Add-ons → Install**, select the
   zip, then tick the box next to "System: Cairntir" to enable.
3. Confirm the **Cairntir** tab appears in the 3D Viewport's N-panel
   (press `N` in any 3D Viewport).

You also need Cairntir's daemon running for drawers to actually land
in the store. From a normal terminal (not Blender's Python):
```
python -m cairntir.daemon
```
…or rely on whatever supervisor you use to keep it running.

---

## Configure

In the Cairntir panel:
- **Wing** — the Cairntir wing this Blender session writes into.
  Defaults to `blender-print`. Use one wing per project (e.g.
  `blender-clamp-2026`, `blender-truss-prototypes`).
- **Material** — becomes the room name inside the wing. Defaults to
  `PLA`. Auto-lowercased to satisfy Cairntir's identifier convention.
- **Cairntir home** — overrides `$CAIRNTIR_HOME` for this session.
  Leave blank to use the env var or the default `~/.cairntir`.

Wing, material, capture-home override and recall query persist per scene in the
.blend file. Recall connection settings belong to trusted add-on preferences:

- **Cairntir Python** — absolute path to Python with the compatible Cairntir
  installation and its dependencies. The recall bridge requires the read-only
  APIs provided by the 1.16.0 candidate.
- **Cairntir home** — absolute path to an existing store. Set the capture-home
  override to this same location when capturing into that store.
- **Read grant file** — absolute path to a token file provisioned by the store
  owner, with read access to the selected wing and material room. Owner tooling
  can issue this with `cairntir.access.issue_grant`, using a scope such as
  `{"wing": "blender-print", "rooms": ["pla"]}` and `capabilities=["read"]`.
  Keep the returned token in the grant file; do not paste it into a scene.

Recall never accepts an executable, home or grant from scene properties. It
requires the store's matching embedding index and already cached production
model artifacts. A configured FASTEMBED_CACHE_PATH is inherited from the host
environment. Missing credentials, incompatible indexes and unavailable assets
produce explicit refusals; the bridge does not fall back to owner access.

Recall results and running jobs are temporary WindowManager state. They are not
saved in .blend files. Changing the scene, selectors, query or connection hides
old results and cancels an active read.

---

## Use

### Capture Decision

Free-form drawer in the configured wing/room. Use this for design
choices, mid-iteration notes, or anything that isn't strictly a
print outcome.

### Capture Print Outcome

Structured drawer with manual print parameters, an outcome verdict, and
an automatic snapshot of the current scene. The dialog labels these
parameters as manual:
- Nozzle temp (°C)
- Bed temp (°C)
- Infill (%)
- Layer height (mm)

Plus the outcome text, success/fail flag, and free-form notes.

The drawer's content is human-readable markdown with the parameters
and outcome laid out; the metadata carries the structured fields
(`source: "blender"`, `kind: "print_outcome"`, `parameters`, `success`)
so a future Decision Replay or consolidation pass can recover the
prediction-bound semantics.

Each operator capture also reads the passed Blender context: scene and
view-layer names, mode, saved/filepath state, current units and unit scale,
and active-object name, type, dimensions and scale. Vectors are copied as
separate three-float lists without conversion or additional scaling.

`metadata.scene_settings` uses schema `cairntir.blender-scene-settings.v1`,
with a UTC observation time, host version/build, getter-path `values`, and
`unavailable` reasons. Missing context, unavailable attributes, getter errors
and unsupported values remain explicit; earlier observations are never reused.
Nozzle temperature, bed temperature, infill and layer height stay unavailable
with `PROVIDER_UNVERIFIED`. Scene units, custom properties and dialog defaults
do not supply printer settings. `metadata.parameters_source` is `manual`.

The stdlib writer accepts the optional `scene_settings` keyword. Calls without
it preserve the original metadata and content.

---

### Recall Prior Prints

Enter a **Prior print query** and click **Recall Prior Prints** in the Cairntir
panel. The interactive read runs as a modal job; press Escape to cancel. It has
a 60-second timeout and bounded output. Cancellation and timeout terminate the
owned child process tree.

The panel shows the recorded success/failure (or unknown), full outcome and
manual parameters, saved date, local memory URI, portable UUID and content hash.
Stored text remains untrusted evidence with no instruction authority. Only print
outcomes in the authorized wing/material are eligible, before ranking and the
default five-record limit. Whole records that cannot fit the response budget
receive omission receipts; their content is never clipped into a partial record.
An authorized empty result is distinct from denied access or an unavailable read.

---

## Iteration Workflow

The compounding workflow Cairntir was built for:

1. **Iteration 1**: print, capture outcome with `success=True/False`
   and the parameters you used.
2. **Iteration 2-N**: same, with revised parameters.
3. **Monthly review**: `cairntir cross-recall "warping at corners"`
   surfaces every print across every material where warping was
   noted. `cairntir recall "PETG bed temp" --wing blender-print`
   pulls the parameter history.
4. **When the rules harden**: write a prediction-bound drawer in
   `blender-print` with `claim` = "PETG warps below 75°C bed temp"
   and `predicted_outcome` = "every print at 70°C will warp at
   corners". Future Decision Replay invocations close the
   prediction window when you actually run that print.
5. **The signals wing applies here too**: structural shifts in
   filament chemistry, slicer firmware, hardware capabilities are
   "constraint moves" the same way AI inference cost is — Signal
   Reader the relevant news the same way.

---

## What This Doesn't Do (yet)

- **Read printer-specific parameters from an unverified provider.**
  Nozzle/bed/infill/layer-height remain manual dialog inputs. Automatic
  scene observations do not establish a printer's configuration.
- **Capture STL/G-code as drawer attachments.** The portable signed
  format already supports content beyond text; binary-attached
  drawers are a separate roadmap item.

The v0.3 add-on adds scoped prior-print recall to the v0.2 scene capture
workflow. It does not operate a printer or observe a physical print.

---

## Testing

The `spool_writer.py` module is stdlib-only and testable from pytest
without Blender installed. See `tests/unit/test_blender_addon.py`.
The load-bearing test is the round-trip: a file written by the
Blender writer must parse cleanly through
`cairntir.daemon.spool.parse_capture` and produce a Drawer with the
right wing/room/layer/metadata. If that test ever breaks, the
"Cairntir doesn't care what is being remembered" thesis becomes
aspiration instead of fact.

The scene reader is also stdlib-only. Native qualification additionally requires
real add-on registration and operator dispatch, exact spool bytes, daemon
persistence, and retrieval after reopening an isolated store. Unit fixtures alone
do not establish that Blender workflow.

The independent recall controls are in `tests/unit/test_blender_print_recall_c47.py`.
They cover exact outcomes and identity, scope and kind filtering, revoked access,
whole-record budgets, invalid replies and actual child-process cancellation. The
sealed packet in `plans/acceptance/v2-blender-c47-acceptance-r1` also defines the
native registered modal workflow and real rendered-panel evidence.
