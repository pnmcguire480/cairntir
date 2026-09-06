# Independent publication verification

**PASS: Cairntir 1.10.0.**

The workflow artifact, GitHub Release and PyPI distributions have identical SHA-256 hashes. Both published distributions passed cryptographic attestation verification, pinned to the release workflow, tag ref and exact source commit.

Source commit: `be9fdc408a040674d012dad60e2d0c4bd988ce05`. All five jobs in [Release run 34010797495](https://github.com/pnmcguire480/cairntir/actions/runs/34010797495) succeeded.

| Distribution | SHA-256 |
| --- | --- |
| cairntir-1.10.0-py3-none-any.whl | `321a6275c52e09d3c7af44c0d4be878b4e176e0f3247621fb7bf653aa1f7b7e5` |
| cairntir-1.10.0.tar.gz | `cc915da3afff5405cd9d4be23516327ed565a194bc6094223017663e6d41f2d5` |

[Complete sanitized evidence](continuity-publication-independent.json). JSON SHA-256: `e4c96cabb5369e3eda7d2ec05f45d9443eaf9844554f24658b8119dd9740f95d`.

The coordinator separately verifies fresh installed CLI/MCP behavior. This check made no publication, tag, source or production-store changes.
