# Security Policy

## Supported Versions

Cairntir is published. Only the latest release on PyPI is supported
for security fixes. Development snapshots on `main` may include fixes
that have not been tagged yet.

| Version   | Supported |
| --------- | --------- |
| `1.7.x`   | ✅        |
| `main`    | ✅ (unreleased) |
| < 1.7.0   | ❌        |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, use GitHub's private vulnerability reporting:

1. Go to https://github.com/pnmcguire480/cairntir/security/advisories/new
2. Describe the issue with enough detail for reproduction
3. Include impact assessment if you have one

You will receive an acknowledgment within 72 hours. A fix timeline will be proposed within 7 days of triage.

## What Counts

Cairntir's threat model is local-first:

- **In scope:** code execution from untrusted drawer content, path traversal in wing/room names, SQL injection in sqlite-vec queries, deserialization attacks on stored embeddings, MCP tool argument validation bypass
- **Out of scope:** physical access to the machine running Cairntir (we assume the user owns their box), vulnerabilities in upstream dependencies (report those upstream; we'll track via Dependabot)

## Disclosure

We practice coordinated disclosure. Once a fix is merged and released, we will publish a GHSA advisory crediting the reporter unless anonymity is requested.

## Dependencies

Cairntir uses Dependabot for weekly automated dependency updates. CodeQL runs on every push for static security analysis.
