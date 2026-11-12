# Channel hooks and formats

Available in the **2.0.0 preview line**. Take one stored [content angle](ideation-angles.md)
and ask a local model for a hook and format for each of three declared channels:

| Channel | Format | Fields (byte limit) |
| --- | --- | --- |
| community-discussion | question-post | hook 240, title 120, body 1600, closing_question 240 |
| newsletter | short-note | hook 240, subject 120, preview 200, body 2000, call_to_action 240 |
| short-video | thirty-second-concept | hook 180, spoken_opening 240, screen_text 120, visual_concept 600, call_to_action 180 |

The draft is model output and always provisional; nothing is marked as confirmed by a
person, and nothing is posted anywhere.

## Generate

```sh
cairntir channels generate --wing my-project --vault /path/to/vault --model mistral
```

The idea is your latest `cairntir angles choose` pick. Use `--angle a07` to name one, or
`--revision` for an older set. If you have not picked, the model's top-ranked angle is
used and labelled that way. The model address must be numeric loopback.

A reply is kept only if every channel has exactly its declared fields inside their limits,
the three hooks differ, no field contains "available now", "guaranteed" or
"human-confirmed", and every source id is real. Otherwise the command exits 1, the raw
reply is stored as a failure record, and the same request is not sent again (use `--key` to
make a new attempt). An identical request after a success returns the stored draft and does
not call the model.

## Link back to the idea

The angle is written to a source file under `cairntir-sync/<wing>/channel-sources/` and
quoted in the stored selection (`idea_id` is `s<set revision>-<angle id>`). The vault note
for each channel links to a selection note that quotes the angle.

## Read it back

```sh
cairntir channels show --wing my-project --vault /path/to/vault
```

prints the newest draft, the angle it came from, and the note paths, without calling a model.
