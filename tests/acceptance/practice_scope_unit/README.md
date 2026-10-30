# Practice scope and transaction controls

These 32 original R18 cases retain eight test functions, their parameterization,
assertions and the original inert Hash16 fixture. They cover hidden-record
completeness, lifecycle visibility, cross-wing dependencies, atomic scope-write
refusal, provisional receipts and commit-failure rollback/retry.

The original `_grant_book` deliberately injects the grant lookup. These cases
qualify scope, completeness and transaction composition; they do not qualify
persisted-grant authentication. The runner is inert, and the original autouse
fixture forbids network access and production model/embedding providers.

Only historical ZIP/seal/exec loading becomes ordinary package imports. The
selected fixture helpers and test bodies remain original behavior, with ordinary
import sorting and formatting. No private packet, machine manifest, native
observer, model installation or historical result is required or transferred.
The first local source run passed all 32 cases after independent AST/source
review. Hosted results remain separate.
