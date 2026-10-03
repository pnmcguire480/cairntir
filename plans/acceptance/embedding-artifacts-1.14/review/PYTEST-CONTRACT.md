# Public pytest integration

Copy the complete review packet unchanged beneath `plans/acceptance/embedding-artifacts-1.14/review` in the candidate checkout. Run `python -m pytest plans/acceptance/embedding-artifacts-1.14/review/test_e22_review.py --no-cov`. The wrapper finds that checkout through its parent directories; external packet execution can specify `CAIRNTIR_REVIEW_SOURCE_ROOT`.

Three pytest parameters run the original eight controls with the deliberate wrong control, the three frozen Hub controls, and the parent's final requested offline cache-stat permission control. All run in process, with original assertions and original freeze checks. The output is three pytest cases containing twelve synthetic review controls, not twelve pytest-collected cases. The deliberate wrong control must fail internally; its detected failure contributes to a passing wrapper result.

`PYTEST-FREEZE.json` freezes the wrapper and this integration explanation. Existing runners verify their own frozen test and adapter bytes. Every runner checks imported source locations and records runtime hashes. Fixtures remain synthetic and packet-local; no model, network, installation, credentials or real stores are used. Initial failures and repair receipts remain preserved.
