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
  numeric loopback (`http://127.0.0.1:11434` is the default).

## How it asks the model

By default the model writes each outline one section at a time: the opening, each
key point with its example, the close and call to action, all the bridges, then the
production notes, length estimate and next actions. That is 8 calls for a written
post (4 key points) and 7 for a short video (3). Each call is limited to 180
seconds by default; on a slow computer raise it with `--timeout`, up to 3600 seconds
(one hour) per section. There is no separate limit for the whole run: it is at most the
number of sections times that limit. Cairntir assigns every id, which sections each bridge
joins and which parts each action covers, so the model only writes the prose. Each
outline gets three planned actions: check the facts (covering every part), draft,
and finish (edit and lay out the post, or rehearse, record and edit the video).

Each section request turns the model's hidden "thinking" off (Ollama's `think: false`),
so its token budget and time go to the writing. `--thinking` leaves it on (slower; the
per-section token budgets stay the same, so a model that thinks at length can still run
out of room). Any figure, percentage, price or time
saving in the written prose that is not in your request or the angle note must also be
listed as an assumption (each assumption is linked to the check-the-facts action);
otherwise the set is refused.

`--single-call` asks for each whole outline in one call instead. Its limit is fixed at
360 seconds at most, by the original outline engine's frozen contract. Small local models tend to get its structure wrong.

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
default key changes when the angle, angle note, formats, constraints, model, time
limit or `--single-call` change. A failed section is not retried.

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
