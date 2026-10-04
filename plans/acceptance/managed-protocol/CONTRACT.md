# Managed foreground JSONL protocol controls

This finite additive acceptance preserves the already specified foreground managed
session behavior, original frozen tests, coverage thresholds and source. It adds
no production feature or external authority.

Thirty-three cases:

- Six allowed envelopes route exactly one public operation and preserve supplied
  payload. Capture/acknowledge/dispatch request schemas remain validated by their
  existing runtime APIs, with historical controls retained.
- Twelve invalid envelope shapes, extra fields, wrong schemas, unsupported/private
  operations, malformed request objects and extra/missing brief/status/close fields
  produce a typed error without invoking runtime state or process dispatch.
- Thirteen actual Typer CLI loop cases use an inert explicitly supplied runtime.
  They verify explicit close stops input, EOF supplies no producer watermark,
  malformed and duplicate-key JSON rejects, an oversized line is fully drained,
  input/operation/start/EOF-close failures remain structured and exit nonzero,
  subsequent valid commands survive input errors, config replacement refuses
  dispatch, and the owned store context closes on every path.
- Two actual CLI loop cases use an isolated HashEmbeddingProvider store. An exact
  captured request remains verbatim and resumable after worker close. Only an
  explicit complete producer watermark can report capture_complete=true; EOF
  cannot. No configured action is launched.

The one inert wrong-control plugin deliberately routes unsupported start to
dispatch inside its disposable pytest process. The original rejection assertion
must fail, demonstrating the controls detect expanded execution authority.

Tests are portable and require only the installed development dependencies. The
external runner supplies candidate/src through PYTHONPATH and isolated homes/cache.
No production models, downloads, installs, credentials, live stores, APIs, full
local suites or coverage runs are used. Public normal-pytest routing must expose
all thirty-three cases with the exact frozen hashes. Historical two production-model
CLI cases and hosted installed qualification remain separate unchanged controls.

Source expectation: qualified ManagedRuntime/stream_command and CLI protocols in
plans/v2-managed-runtime.md and plans/acceptance/v2-managed-runtime/CONTRACT.md.
Freeze precedes execution and any candidate repair. Preserve failures, corrections,
source bindings and wrong-control receipts without changing frozen assertions.
