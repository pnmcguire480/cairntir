# Managed CLI behavior

Fifteen existing authored cases invoke the public managed JSONL command through
in-process Typer CliRunner.
Thirteen use an inline recording runtime to verify routing, typed JSONL errors,
continued service after bad input, bounded-line draining, configuration changes,
explicit close and EOF. They qualify CLI protocol behavior, not real dispatch.

Two cases use the actual ManagedRuntime, TaskBook and temporary SQLite store
with Hash embeddings. They preserve the original request including Unicode and
CRLF, distinguish EOF from an explicit capture watermark, and verify task resume
remains ready with the exact original request. No process action is dispatched.

The original inert profile retains its two-second/100-byte bounds. All selected
bodies, decorators, assertions and helpers are unchanged. The original six allowed
and twelve rejected stream-command API envelope cases are excluded.

All inputs are inline or disposable. No model, private packet, host account,
observer, installation or old sealed-run qualification is required or claimed.
