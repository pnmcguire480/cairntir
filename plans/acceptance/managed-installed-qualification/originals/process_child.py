"""Public real-child oracle: no external marker before independently visible intent."""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--action-id", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--done", required=True)
    args = parser.parse_args()
    database = Path(args.database).resolve()
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
        records = [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT result FROM workflow_runs WHERE operation='managed.dispatch.v1' AND state='committed'"
            )
        ]
        matches = [record for record in records if record.get("action_id") == args.action_id]
        if len(matches) != 1:
            print("NO UNIQUE COMMITTED PRE-ACTION INTENT", file=sys.stderr)
            return 23
        intent = matches[0]
        prediction = conn.execute(
            "SELECT content, claim, predicted_outcome FROM drawers WHERE id=?",
            (intent["prediction_drawer_id"],),
        ).fetchone()
        request = intent["request"]
        if prediction != (request["claim"], request["claim"], request["predicted_outcome"]):
            print("PRE-ACTION PREDICTION BINDING MISMATCH", file=sys.stderr)
            return 24
    marker = {
        "action_id": args.action_id,
        "prediction_drawer_id": intent["prediction_drawer_id"],
        "claim": prediction[0],
        "predicted_outcome": prediction[2],
        "pid": os.getpid(),
    }
    with Path(args.marker).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(marker, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    deadline = time.monotonic() + 20
    try:
        while not Path(args.release).exists():
            if time.monotonic() >= deadline:
                return 25
            time.sleep(0.02)
        print("actual child café 🧭")
        return 0
    finally:
        Path(args.done).write_text("done", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
