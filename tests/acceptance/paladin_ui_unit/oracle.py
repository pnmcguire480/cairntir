import hashlib
import json
import math
from pathlib import Path

PACKET = Path(__file__).resolve().parent
VIEWPORTS = {"mobile": (375, 800), "desktop": (1280, 800)}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def read_json(path, limit=2 * 1024 * 1024):
    path = Path(path)
    assert path.stat().st_size <= limit

    def unique(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, "Duplicate JSON key"
            result[key] = value
        return result

    def invalid_constant(value):
        raise AssertionError("Nonfinite JSON: " + value)

    return json.loads(path.read_bytes(), object_pairs_hook=unique, parse_constant=invalid_constant)


def artifact(root, reference):
    root = Path(root).resolve()
    path = root / reference["path"]
    assert not path.is_symlink()
    path = path.resolve()
    assert path.is_relative_to(root) and path.is_file()
    assert path.stat().st_size == reference["bytes"] <= 8 * 1024 * 1024
    assert digest(path.read_bytes()) == reference["sha256"]
    return path


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def semantic_status(check, observed, width, height):
    kind = check["kind"]
    if kind == "document-equals":
        passed = observed["value"] == check["expected"]
    elif kind == "ax-role-name":
        passed = (
            observed["selector_count"] == 1
            and type(observed["backend_node_id"]) is int
            and observed["backend_node_id"] > 0
            and bool(observed["ax_node_id"])
            and observed["ignored"] is False
            and observed["role"] == check["role"]
            and observed["name"] == check["name"]
        )
    elif kind == "keyboard-tab-order":
        steps = observed["steps"]
        passed = (
            observed["start_matches"] is True
            and len(steps) == len(check["expected_focus"])
            and all(
                step["key"] == "Tab"
                and step["expected_selector_matches"] is True
                and step["actual"]["id"] == selector.removeprefix("#")
                for step, selector in zip(steps, check["expected_focus"], strict=True)
            )
        )
    elif kind == "keyboard-key-state":
        passed = (
            observed["control_focused"] is True
            and observed["control_count"] == observed["panel_count"] == 1
            and observed["actual_focus"]["id"] == check["control"].removeprefix("#")
            and observed["expanded"] == str(check["expanded"]).lower()
            and observed["panel_visible"] is check["visible"]
        )
    elif kind == "required-visible":
        elements = observed["elements"]
        assert [row["selector"] for row in elements] == check["selectors"]
        passed = True
        for row in elements:
            rect = row["rect"]
            inside = (
                rect is not None
                and all(finite_number(rect[key]) for key in ("x", "y", "width", "height"))
                and rect["width"] > 0
                and rect["height"] > 0
                and rect["x"] >= -1
                and rect["y"] >= -1
                and rect["x"] + rect["width"] <= width + 1
                and rect["y"] + rect["height"] <= height + 1
            )
            assert row["within_viewport"] is inside
            passed = passed and row["count"] == 1 and row["visible"] is True and inside
    elif kind == "horizontal-overflow":
        assert observed["viewport_width"] == width
        assert observed["overflow_css_pixels"] == max(
            0, observed["scroll_width"] - observed["client_width"]
        )
        passed = observed["overflow_css_pixels"] <= check["maximum_css_pixels"]
    elif kind == "rgba-diff":
        assert observed["width"] == width and observed["height"] == height
        if observed["baseline"] is None:
            assert observed["diff"] is None
            assert observed["compared_pixels"] == 0
            assert all(
                observed[key] is None
                for key in (
                    "mismatched_pixels",
                    "exact_changed_pixels",
                    "allowed_diff_pixels",
                    "diff_ratio",
                )
            )
            return "UNREVIEWED"
        total = width * height
        assert observed["compared_pixels"] == total
        assert type(observed["mismatched_pixels"]) is int
        assert 0 <= observed["mismatched_pixels"] <= total
        assert observed["diff_ratio"] == observed["mismatched_pixels"] / total
        assert observed["allowed_diff_pixels"] == math.floor(total * 0.001)
        passed = observed["mismatched_pixels"] <= observed["allowed_diff_pixels"]
    else:
        raise AssertionError("Unknown frozen check kind: " + kind)
    return "PASS" if passed else "FAIL"


def verify_semantics(report, checks=None):
    checks = checks or read_json(PACKET / "CHECKS.json")
    assert [row["id"] for row in report["viewports"]] == list(VIEWPORTS)
    families = {name: [] for name in ("accessibility", "responsive", "visual")}
    derived = {}
    for viewport in report["viewports"]:
        width, height = VIEWPORTS[viewport["id"]]
        assert (viewport["width"], viewport["height"], viewport["device_scale_factor"]) == (
            width,
            height,
            1,
        )
        assert [row["check"] for row in viewport["checks"]] == checks
        results = {}
        for row in viewport["checks"]:
            status = semantic_status(row["check"], row["observation"], width, height)
            assert row["status"] == status, (
                "Declared result disagrees with raw observation: " + row["check"]["id"]
            )
            results[row["check"]["id"]] = status
            families[row["check"]["family"]].append(status)
        expected_font = read_json(PACKET / "RENDER-POLICY.json")["font"]
        assert [item["selector"] for item in viewport["font_observations"]] == expected_font[
            "text_selectors"
        ]
        for item in viewport["font_observations"]:
            assert item["document_fonts_ready"] is True and item["font_face_loaded"] is True
            assert expected_font["css_family"] in item["computed_family"]
            used = [font for font in item["fonts"] if font["glyph_count"] > 0]
            assert used and all(
                font["is_custom_font"] is True
                and font["family_name"] == expected_font["platform_family"]
                and font["postscript_name"] == expected_font["postscript_name"]
                for font in used
            )
        derived[viewport["id"]] = results
    for family, statuses in families.items():
        status = (
            "FAIL" if "FAIL" in statuses else ("UNREVIEWED" if "UNREVIEWED" in statuses else "PASS")
        )
        assert report["families"][family] == status
    return derived


def require_variant(report, variant):
    result = verify_semantics(report)
    if variant == "clean":
        assert report["families"] == {
            "accessibility": "PASS",
            "responsive": "PASS",
            "visual": "PASS",
        }
    elif variant == "name-fault":
        assert all(row["ax.email-name"] == "FAIL" for row in result.values())
        assert report["families"]["accessibility"] == "FAIL"
    elif variant == "keyboard-fault":
        assert all(row["kbd.enter-open"] == "FAIL" for row in result.values())
        assert all(row["ax.disclosure-name"] == "PASS" for row in result.values())
        assert report["families"]["accessibility"] == "FAIL"
    elif variant == "overflow-fault":
        assert result["mobile"]["layout.no-x-overflow"] == "FAIL"
        assert result["desktop"]["layout.no-x-overflow"] == "PASS"
        assert report["families"]["accessibility"] == "PASS"
    elif variant == "visual-fault":
        assert all(row["visual.rgba-diff"] == "FAIL" for row in result.values())
        assert report["families"] == {
            "accessibility": "PASS",
            "responsive": "PASS",
            "visual": "FAIL",
        }
    else:
        raise AssertionError(variant)
    return result
