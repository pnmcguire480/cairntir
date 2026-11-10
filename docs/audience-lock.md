# Audience lock

Available in the **2.0.0a1 preview**. An audience stays provisional until a person
confirms it. A model or script can draft one, but it cannot confirm it.

## What a revision holds

An audience revision has five dimensions: audience, channels, pain, sophistication
and desired outcome. Each one links to its sources. Publishing a new revision never
changes an earlier one, and it returns the project to provisional.

## Check and confirm

```sh
cairntir audience status --wing my-project --vault /path/to/vault
cairntir audience confirm --wing my-project --vault /path/to/vault
```

`confirm` shows every value with its sources, then asks you to type a short code
that changes on each attempt. A wrong answer, no answer or piped input records
nothing. It needs a real interactive terminal.

Confirmation shows that someone deliberately answered at a terminal on this computer.
It does not show who typed the code, and it does not stop a program that drives a
real terminal.

## Carry it into a specification

```sh
cairntir audience transfer-spec --spec SPEC.md --wing my-project --vault /path/to/vault
cairntir audience status --spec SPEC.md --wing my-project --vault /path/to/vault
```

Transfer writes all five dimensions, their sources and the current status between
the `cairntir:audience` markers, and leaves every other byte of the file unchanged.
It adds the block to the end of the file if there are no markers, and creates the
file if it does not exist. Unmatched or repeated markers and invalid UTF-8 are
refused without changing the file.

`status --spec` reports `current`, `stale` or `absent`. Transfer does not run by
itself, so a specification is `stale` after a new revision or confirmation until you
run it again.
