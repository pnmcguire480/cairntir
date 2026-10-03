# Surface fixture amendment v2

Before first execution, root identified that the frozen surface fixture omitted the existing required .obsidian vault directory. Add only `(self.vault / ".obsidian").mkdir()` after vault creation. Preserve the original test file and freeze. No assertion, source implementation or vault-validation rule changes.
