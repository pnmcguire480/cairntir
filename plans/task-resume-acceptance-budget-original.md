# Supplemental exact-budget retry acceptance

Independent owner: `/root/resume_acceptance`.

The original 66 acceptance cases and two transaction-release probes remain
frozen. A development probe found that an omitted checkpoint could advertise
`required_chars=23380`, then remain omitted when the caller supplied exactly
23380 because the serialized limit gained a digit.

`tests/unit/test_task_resume_budget.py` adds two independently authored cases
using plain text and escaped Unicode text. Each creates an oversized checkpoint,
obtains its omission receipt at a 1024-character limit, and retries with exactly
the advertised required budget. The retry must return the complete original
request, fit both the JSON text plus CLI newline and the serialized MCP result,
and leave the database unchanged.

This verifies the existing advertised-budget contract without adding slack or
altering any frozen expectations. Its separate manifest freezes this document
and executable before the official implementation verification run. No new
behavioral baseline or release claim is made for this supplement.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_task_resume_budget.py --no-cov -q
```
