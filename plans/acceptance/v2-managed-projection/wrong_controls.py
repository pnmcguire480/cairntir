"""Deliberately wrong projection controls; original cases remain immutable."""

import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import cairntir.managed_projection as projection
import test_managed_projection as acceptance


out = Path(__file__).resolve().parent / "candidate-1-independent"
real_project = acceptance.project_last_session
real_upsert = projection._upsert_generated
real_snapshot = projection._snapshot


def mutating_brief(*args, **kwargs):
    acceptance.ManagedRuntime.brief(None)
    return real_project(*args, **kwargs)


def lost_suffix(path, *args, **kwargs):
    real_upsert(path, *args, **kwargs)
    data = path.read_bytes()
    path.write_bytes(data.split(acceptance.END)[0] + acceptance.END)


def false_complete(*args, **kwargs):
    snapshot = real_snapshot(*args, **kwargs)
    snapshot["capture_complete"] = True
    snapshot["unknown_tail"] = False
    return snapshot


controls = [
    (
        "brief-write",
        acceptance,
        "project_last_session",
        mutating_brief,
        "test_read_only_restart_and_exact_human_bytes",
        "projection cannot write brief",
    ),
    (
        "lost-human-suffix",
        projection,
        "_upsert_generated",
        lost_suffix,
        "test_read_only_restart_and_exact_human_bytes",
        "Human trailing note",
    ),
    (
        "false-complete",
        projection,
        "_snapshot",
        false_complete,
        "test_missing_close_and_unknown_watermark_are_not_complete",
        "True is not False",
    ),
]
rows = []
for name, module, attr, mutation, test_name, witness in controls:
    stream = io.StringIO()
    with patch.object(module, attr, mutation):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.TestSuite([acceptance.ManagedProjectionAcceptance(test_name)])
        )
    output = stream.getvalue()
    log = out / (name + ".log")
    log.write_text(output, encoding="utf-8", newline="\n")
    caught = not result.wasSuccessful() and witness in output
    rows.append(
        {
            "control": name,
            "caught": caught,
            "specific_witness": witness,
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        }
    )
(out / "wrong-controls.json").write_text(
    json.dumps(rows, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps(rows))
raise SystemExit(0 if all(row["caught"] for row in rows) else 1)
