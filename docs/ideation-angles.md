# Content angles

Available in the **2.0.0 preview line**. A local model proposes 20 or more distinct
angles for your captured audience, scores each against goals you set, and Cairntir
stores the ranked set with a written reason for every score. You then record your
own pick beside the automatic top choice.

Every score and reason is a model judgment, not a measurement. The set is always
`provisional`. Nothing here publishes anything.

## Before you start

- Capture an audience first (see [Audience lock](audience-lock.md)). Angles use the
  current provisional revision; if you capture a new one, generate again.
- Run a local [Ollama](https://ollama.com) with a model pulled, for example
  `ollama pull mistral`. The address must be numeric loopback
  (`http://127.0.0.1:11434` is the default); anything else is refused.
- You need an Obsidian-style vault folder, the same one used for the audience.

## Generate

```sh
cairntir angles generate --wing my-project --vault /path/to/vault \
  --model mistral --brief "Help a small shop owner save time on admin"
```

Add up to four `--objective id:weight:criterion` goals (two to four in all, weights
adding to 100). Without any, it ranks by `audience_fit` (60) and `practicality` (40).

The set is stored only if the model returned 20 to 40 angles whose angles and hooks
are all different (after ignoring case and punctuation), each with a hook, a reason
it fits, source IDs from your audience and a score and reason for every goal.
Anything else is refused and nothing is stored. A local 7B model can take several
minutes the first time it loads.

Running the identical command again returns the stored set without calling the model.
Pass `--key something-new` to ask for a fresh set (revision 2, 3, and so on). The
default key also changes when the audience, brief, goals or model change.

## Read it back

```sh
cairntir angles show --wing my-project --vault /path/to/vault
```

Lists angles best first with their hooks, why they fit, each goal's score and reason,
and the path of the note Cairntir wrote into the vault under `cairntir-sync/<wing>/ideation/`.
Add `--json` for the complete record, `--revision N` for an older set.

## Choose

```sh
cairntir angles choose --wing my-project --vault /path/to/vault \
  --candidate 5 --reason "Customers ask about this every week"
```

Your pick and reason are recorded next to the automatic top choice, which is kept.
Repeating the same command changes nothing; you can record more than one pick.

## What is stored

One row per set in the store table `cairntir_angle_sets` (the whole record as JSON
with a SHA-256 digest) and one row per pick in `cairntir_angle_steering`. A set holds
`candidates`, each with `id`, `rank`, `angle`, `hook`, `relevance`, `source_ids`,
`scores` (`value` and `reason` per goal) and `weighted_score`, plus `automatic_choice`,
the input audience revision and the model identity. A pick holds `set_revision`,
`candidate_id`, `reason` and `selection_id`.
