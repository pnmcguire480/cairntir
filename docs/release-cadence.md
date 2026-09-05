# Release policy

## Commit, merge, publish

A commit records source changes. A protected pull request brings a coherent,
verified change to `main`. Neither publishes a package.

Publication normally starts with a pushed `vX.Y.Z` tag. The Release workflow
also supports manual recovery of an existing tag; it verifies that the tag,
checkout, and package version agree. Never move a published tag.

Code completion does not authorize publication. The maintainer explicitly
approves the release gate. See the [publishing checklist](publish-checklist.md)
for verification, trusted publishing, attestations, and fresh-install checks.

## When to release

Accumulate a coherent capability or a useful set of smaller improvements.
Install failures, first-run failures, and fixes a current user is blocked on
warrant an immediate patch proposal.

Before closing a session, inspect `CHANGELOG.md` under `[Unreleased]`. Do not
leave a user-facing fix silently waiting merely because its changelog is short.
A release is complete only after package publication and verification, not
after writing a changelog header.

## Version numbers

- Patch: fixes without a new capability.
- Minor: additive capability or a deprecated surface removed after its warning
  window.
- Major 2: reserved for a revolutionary change in what Cairntir is.

This deliberately differs from strict Semantic Versioning. The
[deprecation policy](deprecation-policy.md) supplies the compatibility window.
Use three numeric segments; minor versions are not bounded.

## Gates

All changes reach `main` through a pull request. Required status checks enforce
the build and evaluation gates; the CI matrix covers the supported operating
systems and Python versions. Local review also includes strict types, lint,
format, tests, documentation, and executable commitments.

`scripts/check_release_tags.py` checks released changelog entries against tags
and public PyPI versions, with explicit exceptions for documented historical
publication misses. It requires network access and fails closed when PyPI
cannot be checked.
