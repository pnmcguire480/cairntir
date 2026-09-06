# Scoped local sharing

The default CLI and MCP process remain the local owner. An owner can issue a
bearer grant through `cairntir.access.issue_grant(store, scopes=..., capabilities=...)`.
The returned token contains 256 random bits. Only its SHA-256 digest is stored;
keep the token file private to its intended process.

```python
from datetime import UTC, datetime, timedelta
from cairntir.access import issue_grant

token = issue_grant(
    owner_store,
    scopes=[{"wing": "juniper", "rooms": ["public"]}],
    capabilities=["read", "export"],
    expires_at=datetime.now(UTC) + timedelta(hours=1),
    principal="reviewer",
)
```

Set `CAIRNTIR_GRANT_FILE` to a file containing that token before starting the CLI
or MCP process. Startup reads the file once and strips surrounding whitespace.
A configured missing, empty, invalid, expired, or revoked token fails closed.
Changing the file cannot change an already running process's grant. The absent
environment variable selects owner mode. No tool argument can select owner mode.

Scope clauses combine with OR. Within each clause the exact wing, optional room
list, and optional drawer ID list combine with AND. An omitted list includes the
whole wing; an empty list includes nothing. ID restrictions permit changes to
authorized existing drawers but never authorize creating arbitrary new drawers.
Principals, host names, model names, evidence text, and imported approval claims
are descriptive data, never credentials.

`read`, `write`, `export`, `approve`, and `manage` are independent capabilities.
An export-only session can export permitted originals without reading through
ordinary retrieval. Approval also needs the relevant lifecycle's existing checks;
procedure promotion additionally requires the trusted operator callback. Grant
issuance and revocation remain owner-only, including for sessions with `manage`.
Store-wide administration and transcript recovery are unavailable in restricted
sessions. Grants do not authorize network sharing or expand other tool authority.

Restricted retrieval filters before limits, ranking, counts, and relationship
walks. A record requiring hidden evidence is withheld whole; ordinary prose is
never rewritten. Hidden successors suppress stale task evidence without disclosing
their identities. Reads do not reinforce or touch memories. Workflow keys are
namespaced by grant, so one grant cannot replay another's receipt.

Use `revoke_grant(owner_store, token)` to revoke a grant. Every operation checks
the authoritative grant again, including task snapshots, and transactions check
expiry before commit. Revocation prevents future access; it cannot recall evidence
already exported. Source retention and validity remain intact. No automatic
deletion, synchronization, network transfer, or remote identity service is added.

These controls protect a bound application session. A person who can directly
read the owner's database or execute arbitrary Python in the owner's process
already has owner access; operating-system file permissions remain that boundary.
