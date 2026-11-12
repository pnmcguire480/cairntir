# Outlines and next actions

Available in the **2.0.0 preview line**. After you pick a content angle
(see [Content angles](ideation-angles.md)), a local model expands it into one outline
per format you intend to make, and Cairntir stores each outline with its planned next
actions. Nothing is published and no action is carried out.

Everything stays `provisional` with `human_confirmation=false`. The source is the
stored angle set, whose angles and reasons are themselves model judgments.

## Before you start

- Capture an audience, generate angles and record your pick with
  `cairntir angles choose`. The outline uses your latest pick; pass `--angle ID` to
  use another angle from the set.
- Run a local [Ollama](https://ollama.com) with a model pulled. The address must be
  numeric loopback (`http://127.0.0.1:11434` is the default). Each format is one
  request with a limit of 360 seconds.

## Generate

```sh
cairntir outlines generate --wing my-project --vault /path/to/vault --model MODEL
```

Without `--format`, it makes two outlines: `written-post:words:600:900` and
`short-video:seconds:60:90`. Give your own as `--format id:unit:minimum:maximum`
(unit `words` or `seconds`), repeated for more than one. `--constraint "..."` adds a
production constraint to every format.

A set is stored only if every outline is complete:

- a written opening hook;
- 3 to 6 key points, each developed and each with an example, none repeated;
- a written bridge for every pair of neighbouring sections (opening, each point, close);
- a close and a call to action;
- an estimate of the finished piece's length inside your range and unit, with its basis;
- 2 to 4 production notes for that format;
- 2 to 8 planned next actions, each with completion checks and links to the outline
  parts it serves. Every unsupported claim must be listed as an assumption with a
  verification action.

Every part records the selected angle and hook it came from, and the source it
relies on. If any outline fails these checks, no outline set is stored; the model's
raw reply is kept as failed-attempt evidence.

Running the identical command again returns the stored set (or the stored failure)
without calling the model. Pass `--key something-new` for a fresh attempt. The
default key changes when the angle, angle note, formats, constraints or model change.

## Read it back

```sh
cairntir outlines show --wing my-project --vault /path/to/vault
```

Reopens the newest set (or `--set DRAWER_ID`), checks every outline, action and the
angle note it was made from, and prints each outline with its next actions. `--json`
prints the complete record.

## Where it goes

Outlines, actions, the request, and each raw model exchange are ordinary drawers in
the room `ideation-outlines` of the wing. Notes are written under
`cairntir-sync/<wing>/outlines/<set hash>/` in the vault: `set.md`, one note per
outline, and one per component and per action. Text you add outside the marked
block of an outline note is kept when the note is rewritten.
