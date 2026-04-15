# Blender MCP Plugin — reference implementation

> *Proof-of-concept. Proves the "Cairntir doesn't care what kind of
> thing is being remembered" thesis by making it remember print
> parameters and outcomes instead of code decisions. If this works
> for Blender, it works for any domain.*

## What this is

A tiny MCP server that exposes Blender-specific capture tools:

- `blender_capture_print_params` — record temperature, infill,
  nozzle, material, layer height, print speed, bed adhesion, etc.
- `blender_capture_outcome` — record whether the print succeeded,
  failure mode if it didn't, dimensional accuracy, surface finish
- `blender_link_to_model` — link a print drawer to the Blender
  `.blend` file hash so reopening the model surfaces every past
  attempt

Every tool writes to a Cairntir wing (default `blender`). Drawers
land with the same prediction-bound schema code decisions use: the
`claim` field holds what you expected the print to do, the
`predicted_outcome` holds the success criteria, and after the print
finishes `observed_outcome` + `delta` complete the loop.

## Why it matters

The horizon in Cairntir's mythos is **AI + grand-scale 3D printing +
post-scarcity tooling**. The bet is that when machines print their
own thingamajigs, the bottleneck stops being atoms and becomes
*knowledge that compounds across iterations*. This plugin is the
first crack at making that bet falsifiable.

Today it remembers print parameters. Tomorrow, with a larger
printer and the same plugin, it remembers building parameters. The
memory layer does not need to know the difference.

## Status

**Scaffold only.** The directory exists so the reference impl has a
home. v1.1 ships the design document; v1.2 or v1.3 ships the
working code. Pull requests welcome.

## What a working version looks like

```python
# blender_mcp_plugin/server.py
from cairntir import Drawer, Layer
from cairntir.impl import DrawerStore, SentenceTransformerProvider
from cairntir.config import db_path

store = DrawerStore(db_path(), SentenceTransformerProvider())

def capture_print_params(
    *,
    model_name: str,
    temperature: int,
    infill: float,
    layer_height: float,
    material: str,
    prediction: str,  # "should succeed — similar to #234"
) -> int:
    drawer = Drawer(
        wing="blender",
        room=model_name,
        content=(
            f"Print attempt:\n"
            f"  temperature: {temperature}C\n"
            f"  infill: {infill:.0%}\n"
            f"  layer_height: {layer_height}mm\n"
            f"  material: {material}"
        ),
        layer=Layer.ON_DEMAND,
        claim=f"print of {model_name} with these params",
        predicted_outcome=prediction,
        metadata={"source": "blender", "type": "print_params"},
    )
    saved = store.add(drawer)
    return saved.id or 0
```

After the print finishes, a second tool writes the observation
drawer with `supersedes_id` pointing at the prediction. The belief
scorer will naturally downweight parameter combinations that
repeatedly failed and upweight the ones that worked.

Three months of prints later, `cairntir recall "PLA at 210C" --wing
blender` returns the full history ranked by what worked.

## Dependencies

- `cairntir >= 1.0.0` — the memory layer
- Blender's Python API (`bpy`) — for reading scene metadata
- `mcp >= 1.0.0` — the MCP SDK for the server surface

## Install *(when shipped)*

```
pip install cairntir-blender  # future package — not yet published
```

The plugin registers its own MCP server stanza via `cairntir init
--blender`, adding the capture tools to Claude Code or Claude
Desktop alongside the base Cairntir tools.

## See also

- [docs/conception.md](../../docs/conception.md) — why this exists
  in the first place
- [docs/roadmap.md](../../docs/roadmap.md) — v1.1 milestone this is
  part of
- [docs/integration-guide.md](../../docs/integration-guide.md) —
  how to embed Cairntir in your own tool, the pattern this plugin
  follows
