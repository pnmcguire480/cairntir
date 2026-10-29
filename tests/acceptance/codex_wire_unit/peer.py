from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path.cwd()
THREAD = "PUBLIC-nonmodel-thread"
STATE = ROOT / "peer-state.json"
LOG = ROOT / "peer-wire.jsonl"
SCENARIO = json.loads((ROOT / "scenario.json").read_text(encoding="utf-8"))


def log(value):
    with LOG.open("a", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(value, sort_keys=True) + "\n")


def send(value):
    log({"kind": "sent", "server": SERVER, "frame": value})
    print(json.dumps(value, separators=(",", ":")), flush=True)


def reply(request, value):
    send({"id": request["id"], "result": value})


def item(ack, number):
    return {
        "type": "agentMessage",
        "id": f"PUBLIC-ack-{number}",
        "phase": "final_answer",
        "text": json.dumps(ack),
    }


def usage(turn):
    counts = {
        "cachedInputTokens": 0,
        "cacheWriteInputTokens": 0,
        "inputTokens": 1,
        "outputTokens": 1,
        "reasoningOutputTokens": 0,
        "totalTokens": 2,
    }
    return {
        "method": "thread/tokenUsage/updated",
        "params": {
            "threadId": THREAD,
            "turnId": turn,
            "tokenUsage": {"last": counts, "total": counts, "modelContextWindow": None},
        },
    }


def turn(request):
    number = SERVER
    turn_id = f"PUBLIC-turn-{number}"
    brief = json.loads(request["params"]["input"][0]["text"].splitlines()[-1])
    ack = {
        "schema": "cairntir.codex-managed-ack.v1",
        **{key: brief[key] for key in ("brief_id", "brief_sha256", "task_id", "revision")},
    }
    if number == 2 and SCENARIO != "current-metadata-is-not-ack":
        event = usage(state["turn_id"])
        if SCENARIO == "prior-lifecycle":
            event = {
                "method": "item/completed",
                "params": {
                    "threadId": THREAD,
                    "turnId": state["turn_id"],
                    "item": item(dict(state["ack"]), 1),
                },
            }
        elif SCENARIO == "unverified-turn":
            event["params"]["turnId"] = "PUBLIC-unverified-turn"
        elif SCENARIO == "wrong-thread":
            event["params"]["threadId"] = "PUBLIC-unrelated-thread"
        elif SCENARIO == "hidden-tool":
            event["params"]["item"] = {"type": "commandExecution", "id": "PUBLIC-forbidden-tool"}
        elif SCENARIO == "null-turn-id":
            event["params"]["turnId"] = None
        elif SCENARIO == "missing-turn-id":
            del event["params"]["turnId"]
        send(event)
    reply(request, {"turn": {"id": turn_id}})
    send(usage(turn_id))
    items = [] if number == 2 and SCENARIO == "current-metadata-is-not-ack" else [item(ack, number)]
    for message in items:
        send(
            {
                "method": "item/completed",
                "params": {"threadId": THREAD, "turnId": turn_id, "item": message},
            }
        )
    state.update(turn_id=turn_id, ack=ack)
    STATE.write_text(json.dumps(state), encoding="utf-8")
    send(
        {
            "method": "turn/completed",
            "params": {
                "threadId": THREAD,
                "turn": {"id": turn_id, "status": "completed", "items": items},
            },
        }
    )


state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"servers": 0}
state["servers"] += 1
SERVER = state["servers"]
assert SERVER in (1, 2), "unexpected third peer"
STATE.write_text(json.dumps(state), encoding="utf-8")
log({"kind": "started", "server": SERVER, "pid": os.getpid(), "peer": "PYTHON_NONMODEL"})
eof = False
try:
    for line in sys.stdin:
        request = json.loads(line)
        method = request["method"]
        log({"kind": "request", "server": SERVER, "method": method})
        if method == "initialize":
            reply(
                request,
                {
                    "userAgent": "PUBLIC_NONMODEL_PEER",
                    "platformFamily": "windows",
                    "platformOs": "windows",
                },
            )
        elif method == "initialized":
            continue
        elif method in {"thread/start", "thread/resume"}:
            if method == "thread/resume":
                assert request["params"]["threadId"] == THREAD
            reply(
                request,
                {"thread": {"id": THREAD, "ephemeral": False}, "model": request["params"]["model"]},
            )
        elif method == "thread/turns/list":
            ack = dict(state["ack"])
            if SCENARIO == "mutated-prior-history-ack":
                ack["brief_sha256"] = "0" * 64
            reply(
                request,
                {
                    "data": [
                        {
                            "id": state["turn_id"],
                            "status": "completed",
                            "itemsView": "full",
                            "items": [item(ack, 1)],
                        }
                    ]
                },
            )
        elif method == "turn/start":
            turn(request)
        else:
            raise AssertionError("unexpected protocol request")
    eof = True
finally:
    log({"kind": "closed", "server": SERVER, "pid": os.getpid(), "stdin_eof": eof})
