# Content angles

Available in the **2.0.0 preview line**, experimental. A local model is asked for 20 or more distinct
angles for your captured audience, scores each against goals you set, and Cairntir
stores the ranked set with a written reason for every score. You then record your
own pick beside the automatic top choice.

Every score and reason is a model judgment, not a measurement. The set is always
`provisional`. Nothing here publishes anything.

**Honest status.** With a local 7B model this often ends in a refusal ("only N distinct
angle(s) found"). On 13 November 2026, three real Mistral 7B briefs gave: 5 distinct (refused),
12 distinct (refused), and a stored set of 21 that a person reading it counted as about 18
truly different. Nothing is stored in a refused run. Larger models are untested.

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
Cairntir then compares the angles by meaning with its own embedding model and keeps
only the angles that say something different from every angle kept before them. A
repeat ("Q&A" and "FAQ", "Handbook" and "Guide", "The impact of sleep deprivation on
mood" and "... on mental health") is dropped, never stored and never renamed. If fewer
than 20 remain, Cairntir asks the model for replacements, telling it which ideas are
already taken, up to four more times (so at most five model requests, each limited by
`--timeout`). If it still has fewer than 20, it stops, says how many distinct angles
it found and stores nothing. The set that is stored holds the survivors, ranked; the
dropped ones and the extra requests are recorded beside it (`--json`). Anything else that
fails is also refused and nothing is stored.

Running the identical command again returns the stored set without calling the model.
Pass `--key something-new` to ask for a fresh set (revision 2, 3, and so on). The
default key also changes when the audience, brief, goals or model change.

### How the meaning check was set

The line is a cosine similarity of 0.85 between angle texts. One fixed line on short
titles cannot cleanly separate a reworded angle from a different idea, so it was
measured: 36 same-idea pairs and 934 different-idea pairs were labelled by hand from
six sets (the independent checker's controlled set and two real runs of its own, plus real
Mistral 7B and qwen3:8b runs), in `tests/unit/angle_meaning_labels.json`. The same-idea
pairs score 0.77 to 0.95, the different-idea pairs up to 0.95, so the ranges overlap.
At 0.93 (the first choice) only 3 of the 36 repeats were caught. At 0.85 the line catches
29 of the 36 (every plain paraphrase and every "The impact of X on Y" rotation) and wrongly
drops 103 of the 934 different pairs (11%). It errs towards false rejection on purpose: a
dropped good angle costs one more model request, a kept repeat makes the set look bigger
than it is. The 7 repeats it misses are loose topic overlaps (thank-you notes versus
recognition awards, mindfulness versus stress management). A test with the real model
keeps these rates from drifting.

Still open: the check cannot read the reasons. Real models repeat the same score
reason on most angles ("Addresses the audience's pain and desired outcome") and give many
angles the same score; the reasons are stored and labelled model judgment, but they do
not discriminate between angles. The embedding model must be available locally
(`cairntir setup` fetches it); if it is not, the command stops without storing anything.

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
