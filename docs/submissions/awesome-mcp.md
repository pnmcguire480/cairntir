# Awesome MCP submission — draft

**Target list:** [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)

## Proposed entry

Submit via pull request adding Cairntir under the appropriate
category. Most likely candidate categories: **Knowledge & Memory**
or **Productivity**.

### The PR body

```markdown
### [Cairntir](https://github.com/pnmcguire480/cairntir) — Memory-first reasoning layer for Claude Code

Local-first MCP server that kills cross-chat AI amnesia. Verbatim
storage (nothing summarized), prediction-bound drawers (claim →
predicted → observed → delta), belief-as-distribution retrieval
(successful uses boost rank, dead retrievals penalize), and a
content-addressed signed format for gossip-sync over any substrate
(USB, git, Syncthing). Works unchanged with Claude Code, Claude
Desktop, Cursor, Windsurf, Zed, and any MCP client.

MIT. Python 3.11+. `pip install cairntir`.
```

### Listing order in the main entry

The MCP list typically wants one-line descriptions. Fallback short
form if the full body is too long:

```markdown
- [Cairntir](https://github.com/pnmcguire480/cairntir) — Verbatim persistent memory for LLM sessions. Kills cross-chat amnesia. MIT, local-first.
```

## Before submitting

- [ ] Confirm the README on GitHub is polished (final pass)
- [ ] Confirm `pip install cairntir` works in a fresh venv
- [ ] Confirm `cairntir setup --yes` completes cleanly on a
      second-machine dry run
- [ ] Confirm the v1.0.0 GitHub release notes are readable without
      scrolling indefinitely

## How to submit

1. Fork https://github.com/punkpeye/awesome-mcp-servers
2. Add Cairntir under the right category in `README.md`, keeping
   the existing formatting
3. Open a PR with a title like *"Add Cairntir — memory-first
   reasoning layer for Claude Code"*
4. Reference the upstream README section, not the description file,
   since the list indexes the README directly

## Expected response time

Awesome lists are community-maintained. Expect 2–14 days for
review. If nothing happens after 3 weeks, gently bump the PR with
a comment.

## Other MCP directories worth submitting to

- **smithery.ai** — https://smithery.ai — a registry / directory
  for MCP servers. Submission is via their UI.
- **mcp.so** — https://mcp.so — community-curated list, generally
  accepts PRs.
- **modelcontextprotocol.io clients/servers page** —
  https://modelcontextprotocol.io/examples — official directory of
  reference MCP implementations. Harder to land here; requires
  Anthropic review.

## Notes

Keep the pitch narrow and verifiable. Resist the urge to mention
the 3D-printing horizon or the round-table — those belong in the
README and the blog post, not in a one-line directory entry. The
job of this listing is to get a reader to click through, at which
point the README does the heavy lifting.
