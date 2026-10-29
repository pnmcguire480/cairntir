from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from types import MappingProxyType

from ideation_outlines_unit import provider_fixture as provider

HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def demo():
    matrix = json.loads((HERE / "test-plan.json").read_bytes())
    planned = matrix["actual"]
    return {
        "context": json.loads((HERE / "historical-context.json").read_bytes()),
        "requests": [copy.deepcopy(row["request"]) for row in planned],
        "assembly_plan": json.loads((HERE / "assembly-plan.json").read_bytes()),
        "planned": copy.deepcopy(planned),
    }


def prepare_inputs(source_root):
    root = Path(source_root)
    assert not root.exists()
    shutil.copytree(HERE / "sources", root / "sources")
    return {"source_root": root, **demo()}


def envelope(output, **changes):
    value = {
        "model": "i05-staged-synthetic-fixture",
        "done": True,
        "done_reason": "stop",
        "response": canonical(output).decode(),
        "eval_count": 0,
        "total_duration": 0,
    }
    value.update(changes)
    return canonical(value)


def output_schema(row, job):
    matrix = json.loads((HERE / "test-plan.json").read_bytes())
    key = (
        job["kind"]
        if job["kind"] != "production"
        else matrix["actual"][0]["request"]["request_id"] + ".production"
    )
    schema = copy.deepcopy(matrix["output_schemas"][key])
    if job["kind"] == "bridges":
        schema["properties"]["bridges"].update(
            minItems=row["counts"]["bridges"], maxItems=row["counts"]["bridges"]
        )
    if job["kind"] == "production":
        props = schema["properties"]
        for field, count in (
            ("production_notes", row["counts"]["production_notes"]),
            ("actions", row["counts"]["actions"]),
        ):
            props[field].update(minItems=count, maxItems=count)
        bounds = row["request"]["finished_length"]
        props["finished_length_estimate"].update(
            minimum=bounds["minimum"], maximum=bounds["maximum"]
        )
    return schema


def outputs_for(row):
    outline = provider.output_for(row["request"])["outline"]
    p, n, a = (row["counts"][key] for key in ("points", "production_notes", "actions"))
    points = [
        {"point": item["point"]["text"], "example": item["example"]["text"], "assumptions": []}
        for item in outline["key_points"]
    ]
    points[0]["point"] += "  \r\n"
    while len(points) < p:
        points.append(
            {
                "point": (
                    "Keep a written account of what new evidence would change this pr"
                    "ovisional interpretation, so a later correction can be evaluated"
                    " against the original question."
                ),
                "example": (
                    "Hypothetically, a dated correction changes one detail of the inv"
                    "ented example; show exactly which earlier interpretation needs r"
                    "evisiting."
                ),
                "assumptions": [],
            }
        )
    points[p - 1]["assumptions"] = [outline["assumptions"][0]["claim"]]
    bridges = [item["bridge"]["text"] for item in outline["bridges"]]
    while len(bridges) < p + 1:
        bridges.insert(
            -1,
            (
                "Once the possible correction is explicit, return to the limits o"
                "f the original comparison before closing."
            ),
        )
    notes = [item["text"] for item in outline["production_notes"]]
    while len(notes) < n:
        notes.append(
            "Keep a separate review note identifying the audience, remaining "
            "uncertainties and the evidence needed before this draft is used."
        )
    actions = [
        {"text": item["text"], "completion_checks": item["completion_checks"]}
        for item in outline["actions"][:a]
    ]
    return [
        {
            "title": outline["title"] + " — draft",
            "opening": outline["opening"]["text"],
            "assumptions": [],
        },
        *points[:p],
        {"close": outline["close"]["text"], "cta": outline["cta"]["text"], "assumptions": []},
        {"bridges": bridges[: p + 1], "assumptions": []},
        {
            "production_notes": notes[:n],
            "finished_length_estimate": outline["finished_length"]["estimate"],
            "finished_length_basis": outline["finished_length"]["basis"]["text"],
            "actions": actions,
            "assumptions": [],
        },
    ]


class FixtureAdapter:
    def __init__(self, planned, *, changes=None, callback=None):
        self.planned = copy.deepcopy(planned)
        self.jobs = [job for row in planned for job in row["jobs"]]
        self.rows = [row for row in planned for job in row["jobs"]]
        self.outputs = [output for row in planned for output in outputs_for(row)]
        self.changes, self.callback = changes or {}, callback
        self.requests, self.raw_nodes = [], []
        self.identity = MappingProxyType(
            {
                "kind": "fixture",
                "model_id": "i05-staged-synthetic-fixture",
                "prompt_version": "i05.staged.v2",
                "schema_version": "cairntir.outline-node-output.v2",
                "transport": "injected_fixture",
                "endpoint": None,
                "timeout_seconds": None,
            }
        )

    @property
    def calls(self):
        return len(self.requests)

    @property
    def raws(self):
        return [item["raw"] for item in self.raw_nodes]

    def generate(self, request_bytes, *, cancel=None):
        index = self.calls
        job = self.jobs[index]
        wire = json.loads(request_bytes)
        assert set(wire) == {"model", "stream", "prompt", "format", "options"}
        assert wire["model"] == self.identity["model_id"] and wire["stream"] is False
        assert wire["options"] == {
            "num_ctx": 16384,
            "temperature": 0,
            "num_predict": job["num_predict"],
        }
        assert wire["format"] == output_schema(self.rows[index], job)
        assert job["node_id"] in wire["prompt"] and len(request_bytes) <= 65536
        self.requests.append(request_bytes)
        if self.callback:
            self.callback(index, request_bytes, cancel)
        change = self.changes.get(index)
        if isinstance(change, BaseException):
            raise change
        raw = change if isinstance(change, bytes) else envelope(self.outputs[index])
        try:
            output = json.loads(json.loads(raw)["response"])
        except (ValueError, KeyError, TypeError):
            output = None
        self.raw_nodes.append(
            {
                "node_id": job["node_id"],
                "request_id": job["node_id"].rsplit(".", 1)[0],
                "request_bytes": request_bytes,
                "raw": raw,
                "output": output,
            }
        )
        return raw


def canonical_plan(request, selection, source_root):
    matrix = json.loads((HERE / "test-plan.json").read_bytes())
    row = copy.deepcopy(matrix["actual"][0])
    rid = request["request_id"]
    p, n, a = 4, 3, 2
    slots = [
        "opening",
        *[x for i in range(1, p + 1) for x in (f"point{i}", f"example{i}")],
        *[f"bridge{i}" for i in range(1, p + 2)],
        "close",
        "cta",
        "length-basis",
        *[f"note{i}" for i in range(1, n + 1)],
    ]
    sections = [
        f"{rid}.{slot}" for slot in ("opening", *[f"point{i}" for i in range(1, p + 1)], "close")
    ]
    spans, quotes = [], []
    for i, src in enumerate(selection["sources"], 1):
        anchor_id = (
            "i03-"
            + sha(canonical({key: src[key] for key in ("source_id", "anchor", "excerpt_sha256")}))[
                :16
            ]
        )
        raw = src["excerpt"].encode()
        absolute = (Path(source_root) / src["path"]).read_bytes().index(raw)
        span = {
            "key": f"selected{i}",
            "source_id": src["source_id"],
            "anchor_id": anchor_id,
            "source_sha256": src["sha256"],
            "excerpt_sha256": src["excerpt_sha256"],
            "excerpt_byte_start": 0,
            "excerpt_byte_end": len(raw),
            "span_sha256": sha(raw),
        }
        spans.append(span)
        quotes.append(
            {
                **span,
                "quote_id": f"{rid}.quote.selected{i}",
                "source_path": src["path"],
                "source_byte_start": absolute,
                "source_byte_end": absolute + len(raw),
                "attribution": "quoted_historical",
            }
        )
    plan = {
        "request_id": rid,
        "point_count": p,
        "production_note_count": n,
        "verification_action_key": "verify",
        "spans": spans,
        "component_bindings": [
            {"slot": slot, "span_keys": [s["key"] for s in spans]} for slot in slots
        ],
        "actions": [
            {
                "key": "verify",
                "kind": "verification",
                "purpose": "Review evidence before factual use",
                "component_slots": slots,
                "depends_on": [],
            },
            {
                "key": "draft",
                "kind": "production",
                "purpose": "Prepare the selected format draft",
                "component_slots": slots,
                "depends_on": ["verify"],
            },
        ],
    }
    kinds = ["opening", *[f"point{i}" for i in range(1, p + 1)], "close", "bridges", "production"]
    jobs = []
    for i, kind in enumerate(kinds):
        previous = [f"{rid}.{name}" for name in kinds[:i]]
        example = row["jobs"][
            0
            if kind == "opening"
            else 1
            if kind.startswith("point")
            else 4
            if kind == "close"
            else 5
            if kind == "bridges"
            else 6
        ]
        job = copy.deepcopy(example)
        job.update(node_id=f"{rid}.{kind}", ordinal=i, dependencies=previous)
        if kind == "opening":
            bindings = [("/title", "outline.title"), ("/opening", "outline.opening.text")]
            output_slots = ["opening"]
        elif kind.startswith("point"):
            position = int(kind[5:]) - 1
            bindings = [
                ("/point", f"outline.key_points[{position}].point.text"),
                ("/example", f"outline.key_points[{position}].example.text"),
            ]
            output_slots = [kind, f"example{position + 1}"]
        elif kind == "close":
            bindings = [("/close", "outline.close.text"), ("/cta", "outline.cta.text")]
            output_slots = ["close", "cta"]
        elif kind == "bridges":
            bindings = [
                (f"/bridges/{j}", f"outline.bridges[{j}].bridge.text") for j in range(p + 1)
            ]
            output_slots = [f"bridge{j}" for j in range(1, p + 2)]
        else:
            bindings = [
                (f"/production_notes/{j}", f"outline.production_notes[{j}].text") for j in range(n)
            ]
            bindings += [
                ("/finished_length_estimate", "outline.finished_length.estimate"),
                ("/finished_length_basis", "outline.finished_length.basis.text"),
            ]
            bindings += [(f"/actions/{j}/text", f"actions[{j}].text") for j in range(a)]
            bindings += [
                (f"/actions/{j}/completion_checks/*", f"actions[{j}].completion_checks[*]")
                for j in range(a)
            ]
            output_slots = ["length-basis", *[f"note{j}" for j in range(1, n + 1)]]
        job["kind"] = "point" if kind.startswith("point") else kind
        job["prose_bindings"] = [{"from": x, "to": y} for x, y in bindings]
        job["output_binding"] = [f"{rid}.{slot}" for slot in output_slots]
        job["assumption_binding"] = {
            "from": "/assumptions/*",
            "to": "outline.assumptions in node/list order",
            "component_ids": job["output_binding"],
            "verification_action_id": f"{rid}.verify",
        }
        jobs.append(job)
    row.update(
        request=request,
        counts={
            "points": p,
            "main_sections": p + 2,
            "components": len(slots),
            "bridges": p + 1,
            "production_notes": n,
            "actions": a,
        },
        component_ids=[f"{rid}.{slot}" for slot in slots],
        sections=sections,
        edges=[
            {"bridge_id": f"{rid}.bridge{i + 1}", "from": sections[i], "to": sections[i + 1]}
            for i in range(p + 1)
        ],
        quotes=quotes,
        assembly_plan_entry=plan,
        jobs=jobs,
    )
    row["actions"] = [
        {
            "id": f"{rid}.{slot['key']}",
            "kind": slot["kind"],
            "role": slot["purpose"],
            "component_ids": [f"{rid}.{key}" for key in slot["component_slots"]],
            "depends_on": [f"{rid}.{key}" for key in slot["depends_on"]],
        }
        for slot in plan["actions"]
    ]
    row["component_source_binding"] = {
        "default_quote_ids": [q["quote_id"] for q in quotes],
        "notes_additional_quote_ids": [],
        "idea_id": request["idea_id"],
        "hook_id": request["hook_id"],
    }
    return row
