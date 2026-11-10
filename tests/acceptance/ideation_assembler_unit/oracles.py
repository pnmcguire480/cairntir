from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

REF_KEYS = {"drawer_id", "portable_identity", "content_sha256", "wing", "room"}
RECEIPT_KEYS = {
    "schema",
    "status",
    "ref",
    "context",
    "requests",
    "assembly_plan",
    "master_ref",
    "outlines",
    "node_evidence",
    "replayed",
    "projection_status",
    "projection",
    "projection_error",
}
COMPONENT_KEYS = {
    "id",
    "text",
    "idea_id",
    "hook_id",
    "source_ids",
    "attribution",
    "quote_ids",
    "assumption_ids",
}
QUOTE_KEYS = {
    "id",
    "source_id",
    "anchor_id",
    "source_sha256",
    "excerpt_sha256",
    "excerpt_byte_start",
    "excerpt_byte_end",
    "source_byte_start",
    "source_byte_end",
    "text",
    "span_sha256",
    "attribution",
}
ACTION_KEYS = {
    "schema",
    "status",
    "ref",
    "request_id",
    "action_id",
    "kind",
    "text",
    "completion_checks",
    "idea_id",
    "hook_id",
    "component_ids",
    "source_ids",
    "context_ref",
    "outline_ref",
    "depends_on",
}
NODE_KEYS = {
    "request_id",
    "node_id",
    "node_index",
    "kind",
    "prepared_ref",
    "exchange_ref",
    "request_sha256",
    "schema_sha256",
    "raw_response_sha256",
    "adapter_identity",
    "model_id",
    "done",
    "done_reason",
    "counters",
}
COUNTERS = {
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
}
ACCEPTED_SCHEMAS = {"cairntir.outline.v2", "cairntir.outline-action.v2", "cairntir.outline-set.v2"}


def sha(raw):
    assert isinstance(raw, bytes)
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            assert key not in result, ("duplicate JSON key", key)
            result[key] = value
        return result

    def nonfinite(value):
        raise AssertionError(("nonfinite JSON value", value))

    assert isinstance(raw, (bytes, str))
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def _keys(value, keys):
    assert isinstance(value, dict)
    assert set(value) == set(keys), (set(value), set(keys))


def _text(value):
    assert isinstance(value, str) and value.strip() and "\x00" not in value
    value.encode("utf-8", errors="strict")


def _ref(ref):
    _keys(ref, REF_KEYS)
    assert type(ref["drawer_id"]) is int and ref["drawer_id"] > 0
    for key in REF_KEYS - {"drawer_id"}:
        _text(ref[key])
    assert re.fullmatch(r"[0-9a-f]{64}", ref["content_sha256"])


def _components(outline):
    return [
        outline["opening"],
        *(
            component
            for point in outline["key_points"]
            for component in (point["point"], point["example"])
        ),
        *(bridge["bridge"] for bridge in outline["bridges"]),
        outline["close"],
        outline["cta"],
        outline["finished_length"]["basis"],
        *outline["production_notes"],
    ]


def check_compiled_topology(entry, planned):
    outline = entry["outline"]
    observed_edges = [
        (edge["from_component_id"], edge["to_component_id"], edge["bridge"]["id"])
        for edge in outline["bridges"]
    ]
    planned_edges = [(edge["from"], edge["to"], edge["bridge_id"]) for edge in planned["edges"]]
    assert len(observed_edges) == len(planned_edges)
    assert observed_edges == planned_edges
    assert [component["id"] for component in _components(outline)] == planned["component_ids"]
    assert len(outline["key_points"]) == planned["counts"]["points"]
    assert len(outline["production_notes"]) == planned["counts"]["production_notes"]
    assert [action["action_id"] for action in entry["actions"]] == [
        action["id"] for action in planned["actions"]
    ]
    action_refs = {}
    for action, expected in zip(entry["actions"], planned["actions"], strict=True):
        assert action["kind"] == expected["kind"]
        assert action["component_ids"] == expected["component_ids"]
        assert action["depends_on"] == [action_refs[key] for key in expected["depends_on"]]
        action_refs[action["action_id"]] = action["ref"]


def _pointer(value, pointer):
    assert pointer.startswith("/")
    current = value
    for key in pointer[1:].split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if isinstance(current, list) else current[key]
    return current


def _target(value, expression):
    current = value
    for token in re.findall(r"[^.\[\]]+|\[\d+\]", expression):
        current = current[int(token[1:-1])] if token.startswith("[") else current[token]
    return current


def _raw_node(raw_node):
    wire = strict_json(raw_node["request_bytes"])
    envelope = strict_json(raw_node["raw"])
    _keys(wire, {"model", "stream", "prompt", "format", "options"})
    assert wire["stream"] is False
    assert wire["options"]["num_ctx"] == 16384
    assert wire["options"]["temperature"] == 0
    assert len(raw_node["request_bytes"]) <= 65536
    assert len(canonical(wire["format"])) <= 24576
    assert len(raw_node["raw"]) <= 131072
    assert envelope["model"] == wire["model"]
    assert envelope["done"] is True and envelope["done_reason"] == "stop"
    assert isinstance(envelope["response"], str)
    assert len(envelope["response"].encode("utf-8")) <= 98304
    output = strict_json(envelope["response"])
    assert output == raw_node["output"]
    for key in COUNTERS & set(envelope):
        value = envelope[key]
        assert type(value) is int and 0 <= value <= 2**63 - 1
    return wire, envelope, output


def check_raw_prose(entry, planned, raw_nodes):
    selected = [
        node for node in raw_nodes if node["request_id"] == planned["request"]["request_id"]
    ]
    assert [node["node_id"] for node in selected] == [job["node_id"] for job in planned["jobs"]]
    assumptions = []
    for job, raw_node in zip(planned["jobs"], selected, strict=True):
        wire, _, output = _raw_node(raw_node)
        assert wire["options"]["num_predict"] == job["num_predict"]
        for binding in job["prose_bindings"]:
            origin, target = binding["from"], binding["to"]
            if origin.endswith("/*"):
                original = _pointer(output, origin[:-2])
                compiled = _target(entry, target.replace("[*]", ""))
                assert isinstance(original, list) and isinstance(compiled, list)
                assert [text.encode("utf-8") for text in original] == [
                    text.encode("utf-8") for text in compiled
                ]
            else:
                original = _pointer(output, origin)
                compiled = _target(entry, target)
                if isinstance(original, str):
                    assert isinstance(compiled, str)
                    assert original.encode("utf-8") == compiled.encode("utf-8")
                else:
                    assert type(original) is int and type(compiled) is int and original == compiled
        for claim in output["assumptions"]:
            assumptions.append((claim, job["assumption_binding"]))
    assert len(assumptions) <= 8
    actual = entry["outline"]["assumptions"]
    assert len(actual) == len(assumptions)
    for index, (assumption, (claim, binding)) in enumerate(
        zip(actual, assumptions, strict=True), 1
    ):
        _keys(assumption, {"id", "claim", "component_ids", "source_ids", "verification_action_id"})
        assert assumption["id"] == f"{planned['request']['request_id']}.assumption{index}"
        assert assumption["claim"].encode("utf-8") == claim.encode("utf-8")
        assert assumption["component_ids"] == binding["component_ids"]
        assert assumption["verification_action_id"] == binding["verification_action_id"]
        components = {component["id"]: component for component in _components(entry["outline"])}
        sources = list(
            dict.fromkeys(
                source
                for ident in assumption["component_ids"]
                for source in components[ident]["source_ids"]
            )
        )
        assert assumption["source_ids"] == sources


def check_owned_quotes(entry, planned, source_root):
    actual = entry["outline"]["quoted_evidence"]
    assert len(actual) == len(planned["quotes"])
    expected_quotes = {quote["quote_id"]: quote for quote in planned["quotes"]}
    assert [quote["id"] for quote in actual] == [quote["quote_id"] for quote in planned["quotes"]]
    root = Path(source_root).resolve()
    for quote in actual:
        _keys(quote, QUOTE_KEYS)
        expected = expected_quotes[quote["id"]]
        for key in QUOTE_KEYS - {"id", "text"}:
            assert quote[key] == expected[key], (key, quote[key], expected[key])
        relative = PurePosixPath(expected["source_path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        path = root.joinpath(*relative.parts).resolve()
        assert path.is_relative_to(root) and path.is_file()
        raw = path.read_bytes()
        assert sha(raw) == quote["source_sha256"]
        start, end = quote["source_byte_start"], quote["source_byte_end"]
        assert type(start) is int and type(end) is int and 0 <= start < end <= len(raw)
        raw[:start].decode("utf-8", errors="strict")
        raw[end:].decode("utf-8", errors="strict")
        selected = raw[start:end]
        assert selected.decode("utf-8", errors="strict").encode("utf-8") == quote["text"].encode(
            "utf-8"
        )
        assert sha(selected) == quote["span_sha256"]
        assert end - start == quote["excerpt_byte_end"] - quote["excerpt_byte_start"]
    plan = planned["assembly_plan_entry"]
    bindings = {
        f"{plan['request_id']}.{item['slot']}": item["span_keys"]
        for item in plan["component_bindings"]
    }
    spans = {span["key"]: span for span in plan["spans"]}
    for component in _components(entry["outline"]):
        _keys(component, COMPONENT_KEYS)
        _text(component["text"])
        examples = {
            f"{plan['request_id']}.example{index}" for index in range(1, plan["point_count"] + 1)
        }
        assert component["attribution"] == (
            "hypothetical_example" if component["id"] in examples else "generated_planning"
        )
        assert component["idea_id"] == planned["request"]["idea_id"]
        assert component["hook_id"] == planned["request"]["hook_id"]
        selected_keys = bindings[component["id"]]
        assert component["quote_ids"] == [
            f"{plan['request_id']}.quote.{key}" for key in selected_keys
        ]
        assert component["source_ids"] == list(
            dict.fromkeys(spans[key]["source_id"] for key in selected_keys)
        )
        assert len(set(component["assumption_ids"])) == len(component["assumption_ids"])
        actual_assumptions = entry["outline"]["assumptions"]
        assert component["assumption_ids"] == [
            item["id"] for item in actual_assumptions if component["id"] in item["component_ids"]
        ]


def check_receipt(receipt, planned_actual_rows, raw_nodes, source_root):
    _keys(receipt, RECEIPT_KEYS)
    assert receipt["schema"] == "cairntir.outline-set-receipt.v2"
    assert receipt["status"] == "committed_draft"
    assert type(receipt["replayed"]) is bool
    _ref(receipt["ref"])
    _ref(receipt["master_ref"])
    assert receipt["requests"] == [planned["request"] for planned in planned_actual_rows]
    assert receipt["assembly_plan"] == {
        "schema": "cairntir.outline-assembly-plan.v2",
        "requests": [planned["assembly_plan_entry"] for planned in planned_actual_rows],
    }
    assert [entry["request_id"] for entry in receipt["outlines"]] == [
        planned["request"]["request_id"] for planned in planned_actual_rows
    ]
    ref_ids = [receipt["ref"]["drawer_id"], receipt["master_ref"]["drawer_id"]]
    for entry, planned in zip(receipt["outlines"], planned_actual_rows, strict=True):
        check_compiled_topology(entry, planned)
        _keys(entry, {"request_id", "ref", "outline", "actions"})
        _ref(entry["ref"])
        ref_ids.append(entry["ref"]["drawer_id"])
        _keys(
            entry["outline"],
            {
                "title",
                "opening",
                "key_points",
                "bridges",
                "close",
                "cta",
                "finished_length",
                "production_notes",
                "assumptions",
                "quoted_evidence",
            },
        )
        _text(entry["outline"]["title"])
        for point in entry["outline"]["key_points"]:
            _keys(point, {"point", "example"})
        for bridge in entry["outline"]["bridges"]:
            _keys(bridge, {"from_component_id", "to_component_id", "bridge"})
        length = entry["outline"]["finished_length"]
        _keys(length, {"unit", "estimate", "basis"})
        limits = planned["request"]["finished_length"]
        assert length["unit"] == limits["unit"]
        assert (
            type(length["estimate"]) is int
            and limits["minimum"] <= length["estimate"] <= limits["maximum"]
        )
        check_raw_prose(entry, planned, raw_nodes)
        check_owned_quotes(entry, planned, source_root)
        for action, expected in zip(entry["actions"], planned["actions"], strict=True):
            _keys(action, ACTION_KEYS)
            _ref(action["ref"])
            _ref(action["context_ref"])
            assert (
                action["schema"] == "cairntir.outline-action.v2" and action["status"] == "planned"
            )
            assert action["request_id"] == planned["request"]["request_id"]
            assert action["outline_ref"] == entry["ref"]
            assert action["idea_id"] == planned["request"]["idea_id"]
            assert action["hook_id"] == planned["request"]["hook_id"]
            assert action["component_ids"] == expected["component_ids"]
            components = {component["id"]: component for component in _components(entry["outline"])}
            sources = list(
                dict.fromkeys(
                    source
                    for ident in action["component_ids"]
                    for source in components[ident]["source_ids"]
                )
            )
            assert action["source_ids"] == sources
            _text(action["text"])
            assert isinstance(action["completion_checks"], list) and action["completion_checks"]
            for check in action["completion_checks"]:
                _text(check)
            ref_ids.append(action["ref"]["drawer_id"])
    assert len(ref_ids) == len(set(ref_ids))
    jobs = [job for planned in planned_actual_rows for job in planned["jobs"]]
    assert len(receipt["node_evidence"]) == len(jobs) == len(raw_nodes)
    for evidence, job, raw_node in zip(receipt["node_evidence"], jobs, raw_nodes, strict=True):
        _keys(evidence, NODE_KEYS)
        assert evidence["node_id"] == raw_node["node_id"] == job["node_id"]
        assert evidence["request_id"] == raw_node["request_id"]
        assert evidence["node_index"] == job["ordinal"]
        assert evidence["kind"] == job["kind"]
        _ref(evidence["prepared_ref"])
        _ref(evidence["exchange_ref"])
        wire, envelope, _ = _raw_node(raw_node)
        assert evidence["request_sha256"] == sha(raw_node["request_bytes"])
        assert evidence["schema_sha256"] == sha(canonical(wire["format"]))
        assert evidence["raw_response_sha256"] == sha(raw_node["raw"])
        assert evidence["model_id"] == envelope["model"]
        assert evidence["done"] is True and evidence["done_reason"] == "stop"
        assert evidence["counters"] == {key: envelope[key] for key in COUNTERS if key in envelope}
        assert evidence["adapter_identity"]["model_id"] == envelope["model"]
        assert evidence["adapter_identity"]["prompt_version"] == "i05.staged.v2"
        assert evidence["adapter_identity"]["schema_version"] == "cairntir.outline-node-output.v2"
    assert receipt["projection_status"] in {"not_requested", "ready", "failed"}
    if receipt["projection_status"] == "not_requested":
        assert receipt["projection"] is None and receipt["projection_error"] is None


def records(store, wing):
    result = {}
    for drawer in store.list_by(wing=wing, limit=None, include_expired=True):
        try:
            content = strict_json(drawer.content)
        except (AssertionError, ValueError, UnicodeError):
            continue
        if isinstance(content, dict):
            result[drawer.id] = content
    return result


def accepted(store, wing):
    return {
        key: value
        for key, value in records(store, wing).items()
        if value.get("schema") in ACCEPTED_SCHEMAS
    }


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def check_raw_retained(store, wing, raw_nodes):
    public_records = [set(_strings(value)) for value in records(store, wing).values()]
    for node in raw_nodes:
        raw = node["raw"]
        encoded = base64.b64encode(raw).decode("ascii")
        digest = sha(raw)
        assert any(encoded in values and digest in values for values in public_records), node[
            "node_id"
        ]


def _markdown(raw):
    result, fence = [], None
    for line in raw.decode("utf-8", errors="strict").splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)[0]
            fence = token if fence is None else (None if token == fence else fence)
            continue
        if fence is None:
            result.append(line)
    return "\n".join(result)


def check_vault(projection, vault_root, human_before=None):
    _keys(
        projection,
        {"set_path", "outline_paths", "source_paths", "component_paths", "action_paths", "paths"},
    )
    root = Path(vault_root).resolve()
    paths = projection["paths"]
    assert isinstance(paths, list) and len(paths) == len(set(paths))
    declared = [
        projection["set_path"],
        *projection["outline_paths"],
        *projection["source_paths"],
        *projection["component_paths"],
        *projection["action_paths"],
    ]
    assert len(declared) == len(set(declared)) and set(declared) == set(paths)
    human_before = human_before or {}
    notes, generated = {}, {}
    for name in paths:
        relative = PurePosixPath(name)
        assert not relative.is_absolute() and ".." not in relative.parts and "\\" not in name
        path = root.joinpath(*relative.parts).resolve()
        assert path.is_relative_to(root) and path.is_file()
        raw = path.read_bytes()
        notes[name] = _markdown(raw)
        before = human_before.get(name)
        if isinstance(before, bytes):
            assert raw == before
            generated[name] = ""
        elif before is not None:
            _keys(before, {"prefix", "suffix"})
            assert raw.startswith(before["prefix"]) and raw.endswith(before["suffix"])
            assert len(before["prefix"]) + len(before["suffix"]) <= len(raw)
            generated[name] = _markdown(
                raw[len(before["prefix"]) : len(raw) - len(before["suffix"])]
            )
        else:
            generated[name] = notes[name]
    for name, text in generated.items():
        for link in re.findall(r"\[\[([^\]\n]+)\]\]", text):
            target, _, fragment = unquote(link.split("|", 1)[0]).partition("#")
            destination = target + ("" if target.endswith(".md") else ".md") if target else name
            assert destination in notes, (name, link)
            if fragment:
                heading = " ".join(fragment.split()).casefold()
                if fragment.startswith("^"):
                    assert re.search(
                        r"(?:^|\s)" + re.escape(fragment) + r"\s*$",
                        notes[destination],
                        re.MULTILINE,
                    ), (name, link)
                else:
                    headings = [
                        " ".join(match.strip().rstrip("#").strip().split()).casefold()
                        for match in re.findall(
                            r"^#{1,6}\s+(.+)$", notes[destination], re.MULTILINE
                        )
                    ]
                    assert heading in headings, (name, link, headings)
    for name, before in human_before.items():
        path = root.joinpath(*PurePosixPath(name).parts).resolve()
        assert path.is_relative_to(root) and path.is_file()
        actual = path.read_bytes()
        if isinstance(before, bytes):
            assert actual == before
        else:
            _keys(before, {"prefix", "suffix"})
            assert actual.startswith(before["prefix"]) and actual.endswith(before["suffix"])
