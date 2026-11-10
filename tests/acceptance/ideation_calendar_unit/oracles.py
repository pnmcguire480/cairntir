from __future__ import annotations

import copy
import re
from pathlib import Path

DATES = tuple(f"2026-11-{day:02}" for day in range(1, 31))
SCHEDULED = tuple(f"2026-11-{day:02}" for day in (2, 4, 6, 9, 11, 13, 16, 18, 20, 23, 25, 27, 30))
FLEX = {f"2026-11-{day:02}" for day in (1, 8, 15, 22, 29)}
WEDNESDAYS = ("2026-11-04", "2026-11-11", "2026-11-18", "2026-11-25")
RECEIPT_KEYS = {
    "schema",
    "status",
    "ref",
    "revision",
    "previous_ref",
    "context",
    "policy",
    "days",
    "collisions",
    "replayed",
    "projection_status",
    "projection",
    "projection_error",
}
ENTRY_KEYS = {
    "entry_id",
    "title",
    "idea_id",
    "hook_id",
    "channel",
    "format",
    "cta",
    "notes",
    "repurpose_of",
}
REF_KEYS = {"drawer_id", "portable_identity", "content_sha256", "wing", "room"}


def entries(view):
    return [(day["date"], item) for day in view["days"] for item in day["entries"]]


def hooks(context):
    return {hook["id"]: (idea, hook) for idea in context["ideas"] for hook in idea["hooks"]}


def check_view(view, context, policy, *, scheduled=SCHEDULED):
    assert set(view) == RECEIPT_KEYS
    assert view["schema"] == "cairntir.calendar-receipt.v1"
    assert view["status"] == "committed_draft"
    assert set(view["ref"]) == REF_KEYS
    assert view["ref"]["room"] == "ideation-calendars"
    assert view["policy"] == policy
    assert view["context"] == context
    assert context["attribution"] == "historical_record_unverified"
    assert context["human_confirmation"] is False
    assert policy["timezone"] == "UTC"
    assert [day["date"] for day in view["days"]] == list(DATES)
    assert all(set(day) == {"date", "kind", "entries"} for day in view["days"])
    assert {day["date"] for day in view["days"] if day["kind"] == "flex"} == FLEX
    assert next(day for day in view["days"] if day["date"] == "2026-11-26")["kind"] == "blackout"
    items = entries(view)
    assert len(items) == 13
    assert tuple(sorted(date for date, _ in items)) == tuple(sorted(scheduled))
    assert len({item["entry_id"] for _, item in items}) == len(items)
    known = hooks(context)
    by_id = {item["entry_id"]: (date, item) for date, item in items}
    for date, item in items:
        assert set(item) == ENTRY_KEYS
        assert isinstance(item["entry_id"], str) and item["entry_id"]
        assert isinstance(item["title"], str) and len(item["title"].strip()) >= 12
        assert isinstance(item["cta"], str) and len(item["cta"].strip()) >= 12
        assert isinstance(item["notes"], str)
        idea, hook = known[item["hook_id"]]
        assert item["idea_id"] == idea["id"]
        assert item["channel"] == hook["channel"]
        assert item["format"] == hook["format"]
        if item["repurpose_of"] is not None:
            parent_date, parent = by_id[item["repurpose_of"]]
            assert parent_date < date
            assert parent["idea_id"] == item["idea_id"]
            assert parent["channel"] != item["channel"]
    repurposes = [(date, item) for date, item in items if item["repurpose_of"] is not None]
    assert tuple(date for date, _ in repurposes) == WEDNESDAYS
    assert len(repurposes) == 4


def check_base_collision(view):
    items = [item for date, item in entries(view) if date == "2026-11-04"]
    assert len(items) == 1
    diagnostics = [
        c for c in view["collisions"] if c["kind"] == "capacity" and c["date"] == "2026-11-04"
    ]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert set(diagnostic) == {"kind", "date", "entry_ids", "commitment_ids", "capacity", "load"}
    assert diagnostic["entry_ids"] == [items[0]["entry_id"]]
    assert diagnostic["commitment_ids"] == ["existing-nov04-review"]
    assert diagnostic["capacity"] == 1 and diagnostic["load"] == 2


def check_lineage(old, new):
    assert new["revision"] == old["revision"] + 1
    assert new["previous_ref"] == old["ref"]
    assert new["ref"] != old["ref"]
    assert new["ref"]["wing"] == old["ref"]["wing"]


def check_projection(projection, vault):
    assert set(projection) == {"calendar_path", "version_path", "source_paths", "paths"}
    assert projection["calendar_path"] in projection["paths"]
    assert projection["version_path"] in projection["paths"]
    assert projection["source_paths"]
    assert set(projection["source_paths"]) <= set(projection["paths"])
    vault = Path(vault).resolve()
    for relative in projection["paths"]:
        assert isinstance(relative, str) and "\\" not in relative
        path = (vault / relative).resolve()
        assert path.is_relative_to(vault) and path.is_file()
        text = path.read_text(encoding="utf-8")
        outside_evidence = re.sub(r"(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$", "", text)
        for raw in re.findall(r"\[\[([^\]]+)\]\]", outside_evidence):
            target = raw.split("|", 1)[0].split("#", 1)[0]
            assert target
            link = vault / (target if target.endswith(".md") else target + ".md")
            assert link.resolve().is_relative_to(vault) and link.is_file(), (relative, raw)


def check_human_bytes(path, expected):
    assert Path(path).read_bytes() == expected


def broken_views(view):
    wrong = copy.deepcopy(view)
    wrong["days"].pop()
    yield "missing final date", wrong
    wrong = copy.deepcopy(view)
    wrong["days"][-1]["date"] = "2026-11-29"
    yield "duplicate date", wrong
    wrong = copy.deepcopy(view)
    next(item for _, item in entries(wrong))["cta"] = " "
    yield "blank CTA", wrong
    wrong = copy.deepcopy(view)
    wrong["collisions"] = [c for c in wrong["collisions"] if c["date"] != "2026-11-04"]
    yield "missing capacity collision", wrong
    wrong = copy.deepcopy(view)
    next(item for _, item in entries(wrong) if item["repurpose_of"])["repurpose_of"] = (
        "missing-parent"
    )
    yield "dangling repurpose", wrong
    wrong = copy.deepcopy(view)
    wrong["context"]["human_confirmation"] = True
    yield "invented confirmation", wrong
