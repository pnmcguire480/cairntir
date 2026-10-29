from __future__ import annotations

import copy
import json
from types import MappingProxyType


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def component(ident, text, source_ids, *, attribution="generated_planning", assumptions=()):
    return {
        "id": ident,
        "text": text,
        "source_ids": list(source_ids),
        "attribution": attribution,
        "assumption_ids": list(assumptions),
    }


def output_for(request, *, source_ids=("SYN-ANGLES", "SYN-HOOKS")):
    video = request["finished_length"]["unit"] == "seconds"

    def make(ident, text, **kw):
        return component(ident, text, source_ids, **kw)

    title = (
        "A synthetic library shelf review" if video else "Comparing invented library catalog notes"
    )
    opening = (
        "Two invented library notes describe the same shelf; which details"
        " would a careful workshop participant compare?"
    )
    points = [
        (
            "Begin with one shelf label and locate that label in both invented"
            " catalog notes. Keeping the subject fixed separates a disagreemen"
            "t about the same shelf from descriptions of different shelves."
        ),
        (
            "Compare the dated descriptions and the reasons each note gives fo"
            "r its shelf count. Matching numbers alone remain provisional when"
            " the two invented notes could repeat one earlier worksheet."
        ),
        (
            "Ask for a fresh shelf check before describing the imagined catalo"
            "g workflow as operational. This synthetic historical exercise sup"
            "plies no evidence that any current library uses the proposed arra"
            "ngement."
        ),
    ]
    examples = [
        (
            "Hypothetically, two invented catalog cards both describe shelf Am"
            "ber, while a third card clearly refers to shelf Birch."
        ),
        (
            "Hypothetically, both invented shelf counts came from one old work"
            "sheet; mark that shared dependency before comparing the totals."
        ),
        (
            "Hypothetically, a workshop participant finds a newer shelf label;"
            " revise the proposed account and keep the old note attributed."
        ),
    ]
    bridges = [
        "Start by locating the same shelf label in both invented notes.",
        "With the shelf identified, compare what each dated note actually records.",
        "Those recorded details still need a fresh check before a current claim is made.",
        "Keeping that check visible leaves a concrete question for the workshop.",
    ]
    close = (
        "The invented catalog comparison remains a provisional plan until "
        "someone checks the supporting shelf evidence."
    )
    cta = (
        "Suggest one missing catalog note or shelf observation that this s"
        "ynthetic exercise should check."
    )
    notes = [
        (
            "Use clearly labelled invented catalog cards and retain a source-c"
            "heck placeholder wherever current factual wording would appear."
        ),
        (
            "Review the opening, three points and adjacent bridges for clarity"
            ", preserving the provisional label and the closing workshop quest"
            "ion."
        ),
    ]
    if video:
        notes[1] = (
            "Read the opening, three spoken points and adjacent bridges aloud,"
            " leaving room for mock-card captions and the final workshop quest"
            "ion."
        )
    key_points = []
    for index, (point, example) in enumerate(zip(points, examples, strict=False), 1):
        key_points.append(
            {
                "point": make(
                    f"point-{index}",
                    point,
                    assumptions=("current-implementation",) if index == 3 else (),
                ),
                "example": make(f"example-{index}", example, attribution="hypothetical_example"),
            }
        )
    section_ids = ["opening", "point-1", "point-2", "point-3", "close"]
    outline = {
        "title": title,
        "opening": make("opening", opening),
        "key_points": key_points,
        "bridges": [
            {
                "from_component_id": section_ids[index],
                "to_component_id": section_ids[index + 1],
                "bridge": make(f"bridge-{index + 1}", text),
            }
            for index, text in enumerate(bridges)
        ],
        "close": make("close", close),
        "cta": make("cta", cta),
        "finished_length": {
            "unit": request["finished_length"]["unit"],
            "estimate": (
                request["finished_length"]["minimum"] + request["finished_length"]["maximum"]
            )
            // 2,
            "basis": make(
                "length-basis",
                (
                    "Estimate a future workshop piece from three developed points, inv"
                    "ented examples, adjacent bridges and a closing question; the outl"
                    "ine remains preparation."
                ),
            ),
        },
        "production_notes": [
            make(f"production-{index}", text) for index, text in enumerate(notes, 1)
        ],
        "assumptions": [
            {
                "id": "current-implementation",
                "claim": (
                    "Whether any current library implements the invented historical wo"
                    "rkflow remains unverified."
                ),
                "source_ids": list(source_ids),
                "verification_action_id": "check-claims",
            }
        ],
        "actions": [
            {
                "id": "check-claims",
                "kind": "verification",
                "text": (
                    "Check current catalog evidence before using any historical workfl"
                    "ow description as present factual wording."
                ),
                "component_ids": ["point-3"],
                "source_ids": list(source_ids),
                "completion_checks": [
                    (
                        "A saved check records supporting current evidence or removes the "
                        "unsupported operational assertion."
                    )
                ],
                "depends_on": [],
            },
            {
                "id": "make-draft",
                "kind": "production",
                "text": (
                    "Prepare the synthetic library workshop draft from the outline, re"
                    "taining invented labels and evidence-check placeholders."
                ),
                "component_ids": [*section_ids, "cta"],
                "source_ids": list(source_ids),
                "completion_checks": [
                    (
                        "A saved draft contains the three developed points, their examples"
                        ", adjacent bridges and final workshop question."
                    )
                ],
                "depends_on": ["check-claims"],
            },
            {
                "id": "review-draft",
                "kind": "production",
                "text": (
                    "Review the workshop draft for source traceability, provisional wo"
                    "rding, requested format and a concrete final question."
                ),
                "component_ids": ["production-1", "production-2", "cta"],
                "source_ids": list(source_ids),
                "completion_checks": [
                    (
                        "A saved review records each source link, hypothetical label, form"
                        "at constraint and closing workshop question."
                    )
                ],
                "depends_on": ["make-draft"],
            },
        ],
    }
    return {
        "schema": "cairntir.outline-output.v1",
        "request_id": request["request_id"],
        "outline": outline,
    }


def envelope(output, *, model="i05-synthetic-fixture", **changes):
    value = {
        "model": model,
        "done": True,
        "done_reason": "stop",
        "response": canonical(output).decode(),
        "total_duration": 0,
        "eval_count": 0,
    }
    value.update(changes)
    return canonical(value)


class FixtureAdapter:
    def __init__(self, outputs, *, changes=None, callback=None):
        self.outputs = copy.deepcopy(outputs)
        self.changes = changes or {}
        self.callback = callback
        self.requests = []
        self.raws = []
        self.identity = MappingProxyType(
            {
                "kind": "fixture",
                "model_id": "i05-synthetic-fixture",
                "prompt_version": "i05.v1",
                "schema_version": "cairntir.outline-output.v1",
                "transport": "injected_fixture",
                "endpoint": None,
                "timeout_seconds": None,
            }
        )

    @property
    def calls(self):
        return len(self.requests)

    def prepare(self, *args, **kwargs):
        raise AssertionError("The outline SDK must prepare its own I05 request.")

    def generate(self, request_bytes, *, cancel=None):
        index = len(self.requests)
        self.requests.append(request_bytes)
        if self.callback:
            self.callback(index, request_bytes, cancel)
        response = self.changes.get(index)
        if isinstance(response, BaseException):
            raise response
        raw = response if isinstance(response, bytes) else envelope(self.outputs[index])
        self.raws.append(raw)
        return raw
