# Keep an explicit question open until you resolve it

The unpublished question lifecycle records exact text, an owner or an explicit
unassigned state, and optional supporting memories. A resolution appends a new
memory linked to evidence. It preserves the original question and its portable
identity. A saved resolution records your declaration; it does not prove that
the answer is true. An owner label does not authenticate a person or grant access.

## Record and inspect

Create a UTF-8 JSON file for an explicit request. For example, `question.json`:

```json
{
  "schema": "cairntir.question-open.v1",
  "request_id": "fbfb6c5a-9728-4bc4-b1b1-9e83b0504544",
  "wing": "example-project",
  "room": "questions",
  "content": "Which stored observation supports the proposed change?",
  "owner": null,
  "evidence": []
}
```

Use a new canonical UUID for each new request. Keep the original file and UUID
when retrying the same request; changed content under an old UUID is rejected.

```sh
cairntir question open question.json --wing example-project
cairntir question list --wing example-project
cairntir question list --wing example-project --include-resolved
```

The opening receipt supplies `question_id`, `question_drawer_id` and
`question_sha256`. Preserve all three for resolution. Successful stdout is one
JSON receipt or register; a rejected request returns a nonzero exit and diagnostic.
These commands do not run host registration or update checks. Existing restricted
session administrative restrictions still apply; a JSON file grants no authority.

## Resolve with evidence

A resolution request has exactly these fields: `schema` set to
`cairntir.question-resolve.v1`, a new `request_id`, `wing`, the three question
binding fields from the opening, exact nonblank `content`, and nonempty `evidence`.
Each evidence reference contains `drawer_id`, `source_identity` and
`content_sha256` from an accessible memory in that wing. Use the current
workspace manifest's actual identities and hashes; do not substitute an example
or a hash of rendered Markdown.

```sh
cairntir question resolve resolution.json --wing example-project
```

The receipt names the appended resolution memory. Exact retries reuse that
receipt after restart without appending again. A different resolution request
for an already resolved question is stale. Ordinary corrections, supersession
links and resolution-looking metadata do not close typed questions.

The trusted Python APIs also accept an already authorized scoped store. They
refuse caller-owned outer transactions: a committed receipt must describe data
that another connection can read immediately, not work a caller can later roll
back. A scoped register exposes a question only when its whole lifecycle and
supporting evidence are available. Missing, secret, expired or out-of-scope
evidence can withhold a lifecycle without reopening it or revealing hidden text.

## Use the optional Obsidian workspace

Refresh the [correction workspace](obsidian-corrections.md), then choose
**Open question**, **Resolve question** or **Show question register**. Forms
accept memory IDs from the refreshed workspace and recheck their exact bindings
before queuing. Opening or cancelling a form writes nothing; ordinary note edits
are not commands. Submit explicitly to create a retained request.

The generated `cairntir-sync/questions.md` links the opening, evidence and
resolution. `questions.json` retains exact machine-readable content. Human notes
outside Cairntir's generated block survive refresh. Legacy superseded questions
remain labeled as unverified history; they are not retroactively declared resolved.

A matching committed receipt confirms database storage. Failed acknowledgement
writing or workspace projection is reported separately, with the original
request retained for retry. Starting a process, queuing a file, or receiving a
different request's receipt cannot confirm a save. Handoff uses the same durable
question classification as the register.

## Adoption and evidence limits

This adds no database migration, dependency or MCP tool. The existing pinned
[embedding compatibility requirement](embedding-artifacts.md) still applies.
Use an explicitly selected disposable home and vault for rehearsal and preserve
the work/personal boundary. Installation, a real index rebuild and publication
require separate authorization.

Automated source, mocked UI, subprocess and installed-package results are reported
separately in the feature plan and PR. They do not certify a native graphical
Obsidian session, authenticated human acceptance, private evaluator custody or
token/cost savings.
