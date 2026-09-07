# Supplemental transaction-release evidence

Independent owner: `/root/resume_acceptance`.

The original 66-case acceptance and its hashes remain unchanged. A reviewer
observed after that freeze that equality of database snapshots from a separate
connection proves absence of committed partial writes, but does not by itself
prove the failed writer released an uncommitted transaction.

`tests/unit/test_task_resume_supporting.py` independently adds two probes:
failure during initial creation and failure during an existing task update.
Both inject a typed failure immediately after the real drawer append, verify
the originating connection has no open transaction and the committed database
is unchanged, and then successfully write the same operation through a fresh
independent store connection while the original connection remains open.

These supporting probes extend evidence for the existing atomic rollback and
recoverability contract. They do not replace original acceptance, weaken any
assertion, or change the public contract. Their separate manifest freezes this
file and the supplemental executable before final verification.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_task_resume_supporting.py --no-cov -q
```

No behavioral pre-implementation baseline is claimed for this supplement: the
original runtime implementation had already begun. An early collection attempt
encountered its temporary missing `cairntir.tasks` import and was not an
acceptance verdict. Ruff and formatting passed before this supplemental freeze.
