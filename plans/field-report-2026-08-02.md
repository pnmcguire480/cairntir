# Cairntir field report — from a real production session, 2026-08-02

I am handing you findings from a **live use of Cairntir**, not a review of its
code. On 2026-08-02 a Claude Code session used Cairntir throughout bite B08 of
the `detroit-clone` wing (the gdext bridge — Phase 0's final bite, which shipped
and pushed). These are the things that helped, the things that did not, and one
confirmed defect.

**Apply Cairntir's own evidence standard to this document.** Drawer #173
rejected code-review-graph's headline benchmarks as circular and strawman-based.
Every finding below is **n=1, from one session, on two wings**. Reproduce each
one before you build against it. Where I state a cause, I have given you the
command that shows it.

**The goal Patrick has set, and the bar to judge every change against:**
Cairntir should carry a chat across sessions **without a `HANDOFF.md` file** —
and do it *light, fast, and cheap on tokens*. Today it does not. See finding 5.

---

## Finding 1 — CONFIRMED DEFECT: anchors are accepted at write and rejected at read

**Structural recall is 0% functional in the `detroit-clone` wing.** Every bite
drawer that carries anchors is unreadable by the feature they were written for.

### Reproduce

```
cairntir_recall_for_change(wing="detroit-clone", files=["sim-core/src/tech.rs"])
→ No anchored drawers touch those 1 file(s). Scanned 5 anchored drawer(s).
  WARNING: 5 drawer(s) have malformed metadata.anchors: #207, #206, #205, #204, #199
```

`sim-core/src/tech.rs` **is** an anchor on #207. It still does not match.

### Cause — two anchor shapes exist in the live store

| Drawer | Wing | `metadata.anchors` | Result |
|---|---|---|---|
| #182, #173 | cairntir | `[{"path": "src/cairntir/memory/anchors.py"}]` | ✅ matches |
| #199, #204-#207 | detroit-clone | `["sim-core/src/tech.rs", "data/tech-tree.toml"]` | ❌ "malformed" |

`parse_anchors` at `src/cairntir/memory/anchors.py:176` requires every entry to
be a `dict`. The cairntir-wing drawers were written by the `cairntir anchor`
CLI, which produces the object form. The detroit-clone drawers were written by
an **agent** through the `cairntir_remember` MCP tool, which produces whatever
the agent guesses — and the agent guessed the intuitive thing: a list of paths.

**The reader is correct. The writer is unguarded.** Confirmed working:

```
cairntir_recall_for_change(wing="cairntir", files=["src/cairntir/memory/anchors.py"])
→ 6 anchored drawer(s), including #173 at layer=on_demand
```

That result is the feature working exactly as drawer #182 promised — it reached
an `on_demand` drawer that `session_start` structurally cannot load.

### Root cause, and why it is the interesting part

The `cairntir_remember` MCP schema declares:

```json
"metadata": {"type": "object"}
```

No properties. No description. No validation. **The anchor contract exists only
in `anchors.py`'s docstring and in drawer #173's prose — neither of which a
writing agent ever sees.** So the agent invents a shape, Cairntir stores it
happily, and the failure surfaces weeks later as a warning in a different tool.

Second failure mode, same cause: **drawer #208, written at the end of this
session, has no anchors at all.** Not malformed — absent. Nothing in the tool
surface told the agent anchors existed. A feature an agent cannot discover is a
feature that does not run.

This is the exact class of bug Cairntir exists to prevent — a silent contract
drift between two components, discovered long after the fact — occurring inside
Cairntir.

### Candidate fixes (pick deliberately; they are not all compatible)

1. **Put the anchor schema in the `cairntir_remember` tool description.**
   Cheapest, and probably the highest-leverage single change in this document.
   An agent that can see the contract will honour it.
2. **Validate at write.** Have `cairntir_remember` run `parse_anchors` on
   incoming metadata and reject loudly. Right now the error is loud in the wrong
   place — at read, in a different session, about a drawer nobody can fix from
   memory. `AnchorError` at write time is recoverable; at read time it is
   archaeology.
3. **Coerce the string form** — normalise `"path"` to `{"path": "path"}`.
   Consider carefully: silently accepting two shapes is the drift Cairntir
   opposes. My suggestion is coerce **at write** (with the normalised form
   stored) and keep the reader strict, so the store only ever holds one shape.
4. **Backfill #199, #204-#207** using the procedure drawer #182 documents — it
   is a good procedure and it verified cleanly last time.

   > **CORRECTION, 2026-08-02 — fix 4 as written does not work.** Verified in
   > a throwaway store, not reasoned from reading: `add_anchors` validates the
   > *merged* list, so on a drawer whose existing anchors are the string form
   > it raises `anchor entries must be objects, got str` and refuses before it
   > can append. Drawer #182's procedure succeeded because those drawers had
   > **no** anchors — a clean append. These five have malformed ones. The
   > repair tool was blocked by exactly the damage it needed to repair.
   >
   > Closed by `DrawerStore.repair_anchors` and `cairntir anchor --repair`,
   > which coerce the one unambiguous case (a bare string could only have
   > meant a path) and refuse anything else loudly. Recorded as drawer #210.

Do 1 and 2 regardless. 3 and 4 are judgement calls.

---

## Finding 2 — the read path costs three round trips, and the most expensive one is the least targeted

Answering a single question took: `session_start` → `recall` → `get`.

- **`session_start`** returned all 53 identity + essential drawer stubs, every
  one truncated, plus a full security-boundary evidence block repeating all 53.
  It is the largest single response in the session. **I used three of the 53.**
- **`recall`** returned 8 more truncated stubs. Truncated content cannot answer
  anything, so this call is pure routing.
- **`get`** is the only call that returns usable content, and it also returns
  the full provenance block whether or not the caller wants it.

**Measure this before acting** — I did not instrument token counts and will not
guess at them. But the shape is clear: the fixed cost is paid up front, scales
with wing size, and is mostly unused.

Worth considering:
- A char/token budget on `session_start`, or identity-only by default with
  essential fetched on demand.
- `recall` returning **full content for the top 1–2 hits** rather than stubs for
  ten. One good drawer beats ten headlines, and it removes a round trip.
- A `fields` argument on `get` so provenance is opt-in.

---

## Finding 3 — semantic recall ranked the right answer 7th

Real query from the session, run against the wing that had the answer:

```
cairntir_recall(wing="detroit-clone", query="gdext bridge Godot GDScript sim-core")
```

| Rank | Drawer | What it is | Distance |
|---|---|---|---|
| 1 | #204 | B04 — state hash | 1.0275 |
| 2 | #78 | hard rules | 1.0616 |
| … | | | |
| **7** | **#197** | **ADR-0013: drop C#, shell is GDScript** ← the answer | **1.1260** |

Every hit landed between 1.03 and 1.15. That is not ranking, it is noise.

**Likely cause, and it is a writing problem more than a retrieval one.** The
bite drawers run 3,000–8,000 characters and each covers eight to ten unrelated
topics (what shipped, which ADR, which traps, which tests, what is next). One
embedding per drawer makes the vector an *average* of ten things — it matches
everything weakly and nothing strongly.

**Cheap test:** split one bite drawer into six single-topic drawers, re-run the
identical query, compare the rank of the correct answer. If rank improves
sharply, the fix is guidance in the tool description ("one drawer, one idea"),
not a change to the embedding model.

---

## Finding 4 — the prediction and calibration machinery has never run

```
cairntir_calibration(wing="detroit-clone")
→ prediction drawers: 0 · resolved observations: 0 · confirmed/failed: 0/0
```

Zero, across eight completed bites. Same root cause as the anchors: nothing in
the write path asks for a prediction, so no agent produces one.

This is a shame, because the project generates perfect material for it. Open
question 8 in the detroit-clone roadmap is *"is `cordic`'s `exp`, at 3 parts per
billion, precise enough for the demand model?"* — a falsifiable claim with a
known resolution point (the B11 balance pass). That is exactly a prediction
drawer, and nobody wrote one because nobody was prompted to.

Consider whether `cairntir_remember` should accept an optional
`predicted_outcome` with a resolution trigger, and whether the tool description
should say when to use it.

---

## Finding 5 — the real target: replacing the handoff file

**Honest assessment of tonight.** `session_start` gave me the operating
protocol, Patrick's communication preference, and the GDScript-not-C# decision —
genuinely valuable, and the reason I needed to ask nothing before starting. But
the *working* knowledge came from `HANDOFF.md` and `research/32-grand-roadmap.md`.
Had Cairntir been empty I would have lost the frame; had the files been missing
I could not have worked at all.

**What the handoff file does that Cairntir currently does not:**

| Handoff file | Cairntir today |
|---|---|
| One entry point | Three calls, composed by the agent |
| Everything needed, nothing else | 53 stubs, 3 relevant |
| Deterministic — same content every time | Ranked, and the ranking is weak (finding 3) |
| Full text, in reading order | Truncated, unordered |
| Known, bounded cost | Scales with wing size |

**Suggested shape — `cairntir_handoff(wing)`.** One call returning one composed
brief, bounded in size, with no ranking involved:

- the active work item and its full definition
- the last N session deltas, **full text, newest first**
- open questions with owners
- anchors for the files that work touches
- the operating protocol

Every one of those already exists in the store. This is a **composition
problem, not a retrieval problem** — which is why I think it is achievable
cheaply and why ranking quality is not on its critical path.

**The use case to design against.** Patrick wants to reuse the R-00 → GATE G0
arc as a repeatable template for every later phase gate. That template is
exactly what should live in Cairntir instead of being re-copied into a markdown
file per phase: a phase opens with a research bite, produces a written brief,
turns a plan into five-field bites, and closes on a gate with machine-checked
evidence. If `cairntir_handoff` can instantiate that template for a named phase,
the handoff file stops being necessary — which is the actual goal.

---

## Suggested order

1. **Finding 1, fixes 1 and 2.** A defect, cheap, and it unblocks a shipped
   feature that is currently dead in every wing but one.
2. **Finding 5.** The stated goal. Composition of things that already exist.
3. **Finding 2.** Token cost. Measure first.
4. **Finding 3.** Test the drawer-size hypothesis before touching retrieval.
5. **Finding 4.** Lowest urgency, but nearly free if the tool description is
   being edited for finding 1 anyway.

Findings 1, 3 and 4 share one root cause worth stating plainly: **the tool
descriptions are the only documentation an agent ever reads, and they currently
omit the contracts that matter.** Three separate features are unused or misused
for that single reason. Fixing the descriptions may be the cheapest correctness
work available.
