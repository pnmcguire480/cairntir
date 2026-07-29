# CodeGlass

CodeGlass teaches code to vibecoders and measures whether the explanation
actually stuck. It is a Cairntir recipe, not a fourth skill.

## Protocol

1. Inspect deterministic evidence: files, exact lines, symbols, calls, diffs,
   tests, configuration, and relevant drawers.
2. Run the `codeglass` recipe's Quality step over that evidence.
3. Build WHAT, HOW, WHERE, WHEN, and WHY. Every non-`unknown` section must
   include at least one `[source:absolute/path:line]` or
   `[source:cairntir://drawer/ID]` citation. Label inferred WHY claims.
4. Call `cairntir_codeglass_record`. Exact retries are idempotent.
5. Ask two or three questions that require explanation, behavior prediction,
   or a safe-change decision. Review each answer with a score from 0 to 1 and
   call `cairntir_codeglass_teachback` with `phase=immediate`.
6. At a later session, ask different questions and record `phase=delayed`.
7. Call `cairntir_codeglass_retention`. The delayed result enters the Human
   Learning Log as a reviewable candidate; it is never silently promoted.

## Quality gates

- all five sections are present or explicitly `unknown`;
- factual sections cite evidence;
- glossary and danger zones are non-empty;
- reader level is explicit;
- two or three teach-back answers are recorded or intentionally deferred;
- exact regeneration cannot duplicate a walkthrough;
- delayed retention distinguishes recognition today from learning over time.

SQLite remains authoritative. Anthropicer receives a one-way generated
projection with user notes preserved outside Cairntir's generated block.
