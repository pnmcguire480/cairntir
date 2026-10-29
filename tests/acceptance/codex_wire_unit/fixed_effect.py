from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

database, marker = map(Path, sys.argv[1:])
with sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True) as connection:
    rows = connection.execute(
        "SELECT operation, result FROM workflow_runs WHERE state='committed'"
    ).fetchall()
records = [(operation, json.loads(result)) for operation, result in rows if result]
outcomes = {value["action_id"] for op, value in records if op == "managed.outcome.v1"}
intents = [
    value
    for op, value in records
    if op == "managed.dispatch.v1" and value["action_id"] not in outcomes
]
assert len(intents) == 1, "fixed_effect_requires_one_committed_intent"
intent = intents[0]
acks = [
    value for op, value in records if op == "managed.ack.v1" and value["ack_id"] == intent["ack_id"]
]
assert len(acks) == 1, "fixed_effect_requires_committed_ack"
ack = acks[0]
assert ack["task_id"] == intent["task_id"]
receipt = {key: ack[key] for key in ("ack_id", "brief_id", "brief_sha256", "task_id", "revision")}
receipt["action_id"] = intent["action_id"]
with marker.open("a", encoding="utf-8", newline="\n") as output:
    output.write(json.dumps(receipt, sort_keys=True) + "\n")
print("PUBLIC_R06_FIXED_EFFECT")
