from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import uuid
from pathlib import Path

from .provider_fixture import canonical

REF_KEYS = {"drawer_id", "portable_identity", "content_sha256", "wing", "room"}
RECEIPT_KEYS = {
    "schema",
    "status",
    "ref",
    "context",
    "requests",
    "outlines",
    "generation_provenance",
    "replayed",
    "projection_status",
    "projection",
    "projection_error",
}
ACCEPTED_SCHEMAS = {"cairntir.outline.v1", "cairntir.outline-action.v1", "cairntir.outline-set.v1"}


def components(outline):
    return [
        outline["opening"],
        *[c for point in outline["key_points"] for c in (point["point"], point["example"])],
        *[edge["bridge"] for edge in outline["bridges"]],
        outline["close"],
        outline["cta"],
        outline["finished_length"]["basis"],
        *outline["production_notes"],
    ]


def records(store, wing):
    result = []
    for drawer in store.list_by(wing=wing, room="ideation-outlines", limit=None):
        try:
            value = json.loads(drawer.content)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append((drawer, value))
    return result


def accepted(store, wing):
    return [
        (drawer, value)
        for drawer, value in records(store, wing)
        if value.get("schema") in ACCEPTED_SCHEMAS
    ]


def leaves(value):
    if isinstance(value, dict):
        return [leaf for child in value.values() for leaf in leaves(child)]
    if isinstance(value, list):
        return [leaf for child in value for leaf in leaves(child)]
    return [value]


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


def check_ref(ref, store, wing):
    assert set(ref) == REF_KEYS
    assert type(ref["drawer_id"]) is int and ref["drawer_id"] > 0
    assert str(uuid.UUID(ref["portable_identity"])) == ref["portable_identity"]
    assert re.fullmatch(r"[0-9a-f]{64}", ref["content_sha256"])
    assert ref["wing"] == wing
    found = next(
        row
        for row in store.list_by(wing=wing, room=ref["room"], limit=None)
        if row.id == ref["drawer_id"]
    )
    assert hashlib.sha256(found.content.encode()).hexdigest() == ref["content_sha256"]
    assert store.portable_identity(found.id) == ref["portable_identity"]
    assert store.get_provenance(found.id) is not None
    return json.loads(found.content)


def check_output(outline, request, source_ids, *, enriched):
    ids = []
    for component in components(outline):
        required = {"id", "text", "source_ids", "attribution", "assumption_ids"}
        if enriched:
            required |= {"idea_id", "hook_id"}
            assert (
                component["idea_id"] == request["idea_id"]
                and component["hook_id"] == request["hook_id"]
            )
        assert set(component) == required
        assert isinstance(component["text"], str) and component["text"].strip()
        assert component["source_ids"] and set(component["source_ids"]) <= set(source_ids)
        assert component["attribution"] in {
            "generated_planning",
            "hypothetical_example",
            "quoted_historical",
        }
        ids.append(component["id"])
    assert len(ids) == len(set(ids))
    assert 3 <= len(outline["key_points"]) <= 6
    point_texts = [
        re.sub(r"\s+", " ", p["point"]["text"]).strip().casefold() for p in outline["key_points"]
    ]
    example_texts = [
        re.sub(r"\s+", " ", p["example"]["text"]).strip().casefold() for p in outline["key_points"]
    ]
    assert len(point_texts) == len(set(point_texts)) and len(example_texts) == len(
        set(example_texts)
    )
    for point in outline["key_points"]:
        assert 60 <= len(point["point"]["text"]) <= 1800
        assert 40 <= len(point["example"]["text"]) <= 900
        assert point["example"]["attribution"] in {"hypothetical_example", "quoted_historical"}
    order = [
        outline["opening"]["id"],
        *[p["point"]["id"] for p in outline["key_points"]],
        outline["close"]["id"],
    ]
    assert [(e["from_component_id"], e["to_component_id"]) for e in outline["bridges"]] == list(
        zip(order, order[1:])  # noqa: B905, RUF007
    )
    assert all(20 <= len(edge["bridge"]["text"]) <= 600 for edge in outline["bridges"])
    assert (
        40 <= len(outline["opening"]["text"]) <= 800 and 40 <= len(outline["close"]["text"]) <= 800
    )
    assert 20 <= len(outline["cta"]["text"]) <= 500
    length = outline["finished_length"]
    assert length["unit"] == request["finished_length"]["unit"] and type(length["estimate"]) is int
    assert (
        request["finished_length"]["minimum"]
        <= length["estimate"]
        <= request["finished_length"]["maximum"]
    )
    assert 40 <= len(length["basis"]["text"]) <= 500
    assert 2 <= len(outline["production_notes"]) <= 4
    assert all(40 <= len(note["text"]) <= 800 for note in outline["production_notes"])
    actions = outline["actions"]
    assert 2 <= len(actions) <= 8 and len({a["id"] for a in actions}) == len(actions)
    assert any(action["kind"] == "production" for action in actions)
    earlier = set()
    by_action = {}
    for action in actions:
        assert action["kind"] in {"production", "verification"}
        assert 30 <= len(action["text"]) <= 1200
        assert action["component_ids"] and set(action["component_ids"]) <= set(ids)
        assert action["source_ids"] and set(action["source_ids"]) <= set(source_ids)
        assert 1 <= len(action["completion_checks"]) <= 4
        assert all(20 <= len(check) <= 500 for check in action["completion_checks"])
        assert (
            len(action["depends_on"]) == len(set(action["depends_on"]))
            and set(action["depends_on"]) <= earlier
        )
        earlier.add(action["id"])
        by_action[action["id"]] = action
    assumptions = {a["id"]: a for a in outline["assumptions"]}
    for component in components(outline):
        assert set(component["assumption_ids"]) <= assumptions.keys()
        for ident in component["assumption_ids"]:
            action = by_action[assumptions[ident]["verification_action_id"]]
            assert action["kind"] == "verification" and component["id"] in action["component_ids"]


def check_wire(raw, request, context, model):
    value = json.loads(raw)
    assert raw == canonical(value) and set(value) == {
        "model",
        "stream",
        "prompt",
        "format",
        "options",
    }
    assert value["model"] == model and value["stream"] is False
    assert value["options"] == {"num_predict": 4096, "num_ctx": 16384, "temperature": 0}
    assert len(raw) <= 65536 and len(canonical(value["format"])) <= 24576
    prompt = value["prompt"]
    assert "cairntir.outline-input.v1" in prompt and "i05.v1" in prompt
    assert "human_confirmation" in prompt and "false" in prompt
    assert (
        context["attribution"] in prompt
        and request["idea_id"] in prompt
        and request["hook_id"] in prompt
    )
    assert hashlib.sha256(canonical(context)).hexdigest() in prompt
    assert "cairntir.outline-output.v1" in canonical(value["format"]).decode()
    for idea in context.get("ideas", []):
        if idea["id"] != request["idea_id"]:
            assert idea["id"] not in prompt
            assert all(hook["id"] not in prompt for hook in idea["hooks"])
    return value


def check_receipt(
    view,
    store,
    wing,
    context,
    requests,
    outputs,
    adapter,
    *,
    source_ids=("SYN-ANGLES", "SYN-HOOKS", "SYN-POLICY"),
):
    assert set(view) == RECEIPT_KEYS
    assert (
        view["schema"] == "cairntir.outline-set-receipt.v1" and view["status"] == "committed_draft"
    )
    assert view["context"] == context and view["requests"] == requests
    assert view["context"]["human_confirmation"] is False
    assert (
        view["projection_status"] == "not_requested"
        and view["projection"] is None
        and view["projection_error"] is None
    )
    assert len(view["outlines"]) == len(view["generation_provenance"]) == len(requests)
    check_ref(view["ref"], store, wing)
    for index, (item, request, output) in enumerate(
        zip(view["outlines"], requests, outputs, strict=False)
    ):
        assert (
            set(item) == {"request_id", "ref", "outline", "actions"}
            and item["request_id"] == request["request_id"]
        )
        check_ref(item["ref"], store, wing)
        check_output(item["outline"], request, source_ids, enriched=True)
        raw_outline = copy.deepcopy(item["outline"])
        for c in components(raw_outline):
            c.pop("idea_id")
            c.pop("hook_id")
        assert raw_outline == output["outline"]
        assert len(item["actions"]) == len(output["outline"]["actions"])
        action_refs = {}
        for action, expected in zip(item["actions"], output["outline"]["actions"], strict=False):
            assert (
                action["schema"] == "cairntir.outline-action.v1" and action["status"] == "planned"
            )
            assert (
                action["request_id"] == request["request_id"]
                and action["action_id"] == expected["id"]
            )
            assert action["outline_ref"] == item["ref"]
            assert (
                action["idea_id"] == request["idea_id"] and action["hook_id"] == request["hook_id"]
            )
            for key in ("kind", "text", "completion_checks", "component_ids", "source_ids"):
                assert action[key] == expected[key]
            assert action["depends_on"] == [action_refs[ident] for ident in expected["depends_on"]]
            saved = check_ref(action["ref"], store, wing)
            assert saved == {k: v for k, v in action.items() if k != "ref"}
            check_ref(action["context_ref"], store, wing)
            action_refs[action["action_id"]] = action["ref"]
        provenance = view["generation_provenance"][index]
        assert (
            provenance["request_id"] == request["request_id"]
            and provenance["request_index"] == index
        )
        assert dict(adapter.identity) in list(dictionaries(provenance))
        assert provenance["request_sha256"] == hashlib.sha256(adapter.requests[index]).hexdigest()
        assert provenance["raw_response_sha256"] == hashlib.sha256(adapter.raws[index]).hexdigest()
        assert provenance["model_id"] == adapter.identity["model_id"]
        assert provenance["done"] is True and provenance["done_reason"] == "stop"
        assert not provenance.get("model_digest") and not provenance.get("provider_version")
        for field in ("total_duration", "eval_count"):
            values = [value[field] for value in dictionaries(provenance) if field in value]
            assert values and all(type(value) is int and value >= 0 for value in values)
    assert all(d.get("human_confirmation") is not True for d in dictionaries(view))


def check_prepared(store, wing, adapter):
    prepared = [
        value
        for _, value in records(store, wing)
        if value.get("schema") == "cairntir.outline-prepared.v1"
    ]
    assert prepared
    for wire in adapter.requests:
        strings = [leaf for p in prepared for leaf in leaves(p) if isinstance(leaf, str)]
        assert wire.decode() in strings or base64.b64encode(wire).decode() in strings
        assert hashlib.sha256(wire).hexdigest() in strings


def check_raw_retained(store, wing, raws):
    values = [value for _, value in records(store, wing)]
    strings = [leaf for value in values for leaf in leaves(value) if isinstance(leaf, str)]
    for raw in raws:
        assert base64.b64encode(raw).decode() in strings
        assert hashlib.sha256(raw).hexdigest() in strings


def check_failure(error, store, wing, *, code, unavailable=False):
    assert error.code == code
    assert error.attempt_ref is not None
    failure = check_ref(error.attempt_ref, store, wing)
    assert failure["schema"] == "cairntir.outline-failure.v1" and failure["code"] == code
    assert failure["operation_stage"] in {
        "before_dispatch",
        "delegate_generate",
        "after_return",
        "validation",
        "before_commit",
    }
    assert failure["transport_substage"] is None
    assert isinstance(failure["message"], str) and failure["message"]
    assert failure["request_index"] is None or type(failure["request_index"]) is int
    if unavailable:
        assert failure["raw_availability"] == "unavailable"
        assert failure["raw_response_base64"] is None and failure["raw_response_sha256"] is None
    assert not accepted(store, wing)
    return failure


def check_projection(projection, vault):
    assert set(projection) == {
        "set_path",
        "outline_paths",
        "source_paths",
        "component_paths",
        "action_paths",
        "paths",
    }
    assert isinstance(projection["set_path"], str) and projection["set_path"] in projection["paths"]
    for key in ("outline_paths", "source_paths", "component_paths", "action_paths"):
        assert isinstance(projection[key], list) and projection[key]
        assert set(projection[key]) <= set(projection["paths"])
    vault = Path(vault).resolve()
    for relative in projection["paths"]:
        assert isinstance(relative, str) and "\\" not in relative
        file = (vault / relative).resolve()
        assert file.is_relative_to(vault) and file.is_file()
        outside = re.sub(
            r"(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$", "", file.read_text(encoding="utf-8")
        )
        for raw in re.findall(r"\[\[([^\]]+)\]\]", outside):
            path, _, fragment = raw.split("|", 1)[0].partition("#")
            target = (vault / (path if path.endswith(".md") else path + ".md")).resolve()
            assert target.is_relative_to(vault) and target.is_file(), (relative, raw)
            if fragment:
                assert fragment in re.findall(
                    r"(?m)^#{1,6} (.+)$", target.read_text(encoding="utf-8")
                ), (relative, raw)


def check_human_bytes(path, expected):
    assert Path(path).read_bytes() == expected
