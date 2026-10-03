# Exact original fixture compatibility amendment

The original PR124 embedding-adapter tests predate E22 complete local provenance.
Their synthetic FastEmbed loader classes omit registry dimension and complete
required assets. The original store identity-distinction test computes offline
FastEmbed identity with no asset fixture. Their outcome assertions remain useful;
these fixture omissions must not create a broad runtime exception or obsolete
test exclusion.

The separate plugin guards the exact SHA256 of both original files before use and
refuses every other test file/store case. It is used only by the exact-case runner.
Seven parameterized FastEmbed fake-loader cases receive registry dimension 2 and
four required JSON files plus synthetic model bytes. For readonly existing-assets
cases, the original model bytes/path remain unchanged and the new JSON files are
written before the original snapshot assertion. For the other fake-loader cases,
the plugin annotates the synthetic loader at the exact original
monkeypatch.setitem(sys.modules, "fastembed", ...) seam. All constructors, inference
functions, output capture, exception/cause/advice assertions and resulting vectors
stay original. SentenceTransformer counterparts and missing-dependency cases get
no registry/asset adapter. All other cases execute unchanged.

The one store identity case receives a registry-only loader whose constructor
fails if used, plus synthetic complete local assets. It preserves the original
three-distinct-identities assertion without loading an actual model.

The plugin wraps only the identified item's monkeypatch instance and restores it
through pytest's normal cleanup. It does not globally rewrite fixtures, runtime,
source tests, assertions, markers or preservation gates. No missing-dimension,
stdio corruption, wrong-count, failure diagnostic or readonly mutability assertion
is removed. The existing missing-dimension FastEmbed case still requires rejecting
empty dimension probe vectors, even with valid registry dimension 2.

All test stores/caches lie beneath the fresh packet/runs pytest basetemp. Socket
network calls are blocked. No dependency installation, real model, private cache,
live store, API spend or heavyweight suite is allowed. Original evidence and
assertion files remain unchanged. A dedicated hash freeze records adapter custody;
this fixture-only amendment does not alter the primary E22 semantic freeze or
consume independent review reserve/product repair rounds.

Command: existing development Python, `run_exact_adapters.py --source-root <candidate>
--report <packet>/exact-adapters-candidate.json`. Use a distinct report for the
reviewed PR124 baseline. Requested routing gpt-6.1-sol/high; actual serving model
and effort not exposed; cost unavailable.
