# Cairntir Blender Add-on

> The first non-code Cairntir client. Proves the horizon thesis —
> **Cairntir doesn't care what is being remembered**. The same memory
> layer that records code decisions in the cairntir wing records 3D-print
> iteration outcomes in a blender wing. Same shape, same retrieval,
> same prediction-bound semantics.

---

## What This Is

A Blender add-on that captures decisions and 3D-print iteration outcomes
into Cairntir's memory layer. You print something, you note what worked
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

Settings persist in the .blend file (per-scene properties), not
globally — different .blend files can target different wings.

---

## Use

### Capture Decision

Free-form drawer in the configured wing/room. Use this for design
choices, mid-iteration notes, or anything that isn't strictly a
print outcome.

### Capture Print Outcome

Structured drawer with parameters and an outcome verdict. The
parameters captured by default:
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

- **Pull from Cairntir into Blender.** This is a one-way capture
  surface. Surfacing prior iteration drawers inside Blender as the
  user sets up a new print is the obvious next step.
- **Auto-detect parameters from the active scene.** Today the user
  types nozzle/bed/infill/layer-height into the dialog. A future
  version could read them from the active 3D printer settings if
  Blender exposes them.
- **Capture STL/G-code as drawer attachments.** The portable signed
  format already supports content beyond text; binary-attached
  drawers are a separate roadmap item.

These gaps are not bugs — the v0.1 add-on exists to **prove the
horizon thesis** by establishing that Cairntir's memory layer can
serve a non-code workload at all. Refinement comes after the bet is
de-risked.

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
