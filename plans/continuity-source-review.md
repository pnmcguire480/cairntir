# Continuity release source review

PASS for the bounded integration/release diff from `ad3ccee`; no newly introduced
blocking issue reproduced. Reviewer: `/root/foundation_review`. Runtime areas
already covered by their independent milestone gates were not audited again.

| Check | Evidence |
| --- | --- |
| Provisioning isolation | `.github/workflows/ci.yml:98` and `.github/workflows/release.yml:22` bind dedicated evaluation homes and FastEmbed caches. `scripts/provision_eval.py:21` rejects an existing database before model construction; an isolated existing-file probe returned 2 and preserved its bytes. The script explicitly labels its one synthetic corpus (`scripts/provision_eval.py:36`). This hosted gate makes no claim about the production corpus. |
| Offline evaluation | Provisioning precedes offline model tests (`.github/workflows/ci.yml:111`, `.github/workflows/release.yml:51`). Both production FastEmbed and legacy SentenceTransformer models are provisioned (`scripts/provision_eval.py:25`). |
| Versions and dependencies | `pyproject.toml:7`, `uv.lock:85`, `src/cairntir/__init__.py:60`, `.claude-plugin/plugin.json:4` all declare 1.10.0. Parsed project and lock contents equal `ad3ccee` after normalizing only Cairntir's version: no dependency selection change. `CHANGELOG.md:16` is dated and Unreleased is empty. |
| Workflow integrity | All four workflow YAML documents parse; all 28 external action references are pinned to 40-hex commit IDs. Release verification precedes build (`.github/workflows/release.yml:71`); OIDC publishing and post-publication checks precede the GitHub release (`.github/workflows/release.yml:102`, `:141`). |
| In-flight tag handling | `scripts/check_release_tags.py:162` exempts only the untagged current candidate; tagged releases still require PyPI artifacts (`:198`). The current 1.10.0 tag is absent. All 13 offline release-tag behavior tests pass; the network publication test was deliberately excluded from this source audit. |
| Distribution inventory | Candidate wheel: 77 files, SHA-256 `0501b5018f6155b7cdf15f12061a3f901711ec3c24baf2771f20376d67e720a6`. Candidate sdist: 276 files, SHA-256 `f0751e5cf50b9dbd9d9371a7e8cfefcd095c1044509dc86981391dc3cb129036`. Both include access/procedures. Every wheel Python file matches held source. No runtime database, environment, bytecode or compiler-cache paths were found; the deliberate schema-v6 acceptance fixture remains included. The sdist predates the final documentation/changelog edits and must be rebuilt for publication. |
| Credential inventory | Strong private-key/GitHub-token/API-key patterns returned no hits across 143 changed/new tracked-or-unignored files. Neither archive contains private-key markers. This is a bounded pattern scan, not a universal secret-detection claim. |

An existing checklist discrepancy remains explicit: `docs/publish-checklist.md:88`
mentions plugin metadata in release artifacts, but both the previous 1.9.0 wheel
and this candidate omit `plugin.json`. Packaging boundaries (`pyproject.toml:80`,
`:82`) are unchanged; the aligned plugin manifest is distributed through the
repository. This review does not attest that manifest inside the wheel/sdist.

No production configuration, installation, database, source, or tests changed in
this audit. The real Claude client health result remains unverified; isolated
wheel CLI/stdio evidence does not substitute for it. Published artifact inventory,
remote CI, protected merge, attestations and fresh PyPI installation remain
separate release gates.
