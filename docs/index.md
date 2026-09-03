# Cairntir

> *A stack of stones that sees across time.*

**Cairntir** is a local-first persistent memory MCP server for AI coding
agents. Claude Code, Codex, Cursor, Qwen Code, and other
[Model Context Protocol](https://modelcontextprotocol.io/) clients share one
cross-session memory store.

## Install

```bash
pip install cairntir
cairntir setup
```

Live on [PyPI](https://pypi.org/project/cairntir/). Source on [GitHub](https://github.com/pnmcguire480/cairntir).

## Start Here

- **[Why I built this (blog post)](blog/amnesia-problem.md)** — The story behind the tool
- **[Cairntir for dummies](cairntir-for-dummies.md)** — Zero-prior-knowledge getting-started guide
- **[Manifesto](manifesto.md)** — Why Cairntir exists and what problem it solves
- **[Concept](concept.md)** — The three ingredients: verbatim memory, minimal skills, one loop
- **[Conception](conception.md)** — Origin story, the round table, the horizon
- **[Roadmap](roadmap.md)** — Where we are, where we're going, and the long horizon
- **[Integration guide](integration-guide.md)** — Embedding Cairntir in your own tool
- **[Deprecation policy](deprecation-policy.md)** — What "stable" means at v1.0
- **[Lineage: BrainStormer](lineage/brainstormer.md)** — What we kept, what we dropped
- **[Lineage: MemPalace](lineage/mempalace.md)** — Concepts borrowed, code reimplemented

## Status

**v1.9.0** is the current published release. It adds the bounded hotfix ledger
and hardens the prediction/experiment/outcome learning boundary. The protected
merge, trusted publication, provenance, cross-channel artifact hashes, and
fresh public install are recorded in its
[verified release record](release/v1.9.0.md). Install it from
[PyPI](https://pypi.org/project/cairntir/1.9.0/) or inspect the immutable
[GitHub Release](https://github.com/pnmcguire480/cairntir/releases/tag/v1.9.0).

## License

[MIT](https://github.com/pnmcguire480/cairntir/blob/main/LICENSE). Free forever. Local-first forever. No SaaS.
