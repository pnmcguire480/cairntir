"""Read current Blender scene settings without changing the passed context."""

from datetime import UTC, datetime
from itertools import islice
from math import isfinite
from typing import Any

_GETTERS = (
    ("context.scene.name", str),
    ("context.view_layer.name", str),
    ("context.mode", str),
    ("bpy.data.filepath", str),
    ("bpy.data.is_saved", bool),
    ("context.scene.unit_settings.system", str),
    ("context.scene.unit_settings.system_rotation", str),
    ("context.scene.unit_settings.scale_length", float),
    ("context.scene.unit_settings.use_separate", bool),
    ("context.scene.unit_settings.length_unit", str),
    ("context.scene.unit_settings.mass_unit", str),
    ("context.scene.unit_settings.time_unit", str),
    ("context.scene.unit_settings.temperature_unit", str),
    ("context.active_object.name", str),
    ("context.active_object.type", str),
    ("context.active_object.dimensions", list),
    ("context.active_object.scale", list),
)
_PRINTER_FIELDS = ("nozzle_temp_c", "bed_temp_c", "infill_pct", "layer_height_mm")


def _observe(value: Any, parts: list[str], kind: type) -> tuple[Any, str | None]:
    for part in parts:
        if value is None:
            return None, "CONTEXT_MISSING"
        try:
            value = getattr(value, part)
        except AttributeError:
            return None, "ATTRIBUTE_UNAVAILABLE"
        except Exception as error:  # noqa: BLE001 - Report arbitrary getter errors as READ_ERROR.
            return None, "READ_ERROR:" + type(error).__name__
    if kind is list:
        try:
            value = list(islice(value, 4))
        except TypeError:
            return None, "UNSUPPORTED_VALUE"
        except Exception as error:  # noqa: BLE001 - Report arbitrary iterator errors as READ_ERROR.
            return None, "READ_ERROR:" + type(error).__name__
        valid = len(value) == 3 and all(type(item) is float and isfinite(item) for item in value)
    else:
        valid = type(value) is kind and (kind is not float or isfinite(value))
    return (value, None) if valid else (None, "UNSUPPORTED_VALUE")


def read_scene_settings(context: Any, blender: Any) -> dict[str, Any]:
    """Return current getter values and explicit reasons for unavailable fields."""
    observed_at = datetime.now(UTC).isoformat()
    host = {
        "version": blender.app.version_string,
        "build": blender.app.build_hash.decode("utf-8"),
    }
    values: dict[str, Any] = {}
    unavailable = {"printer." + name: "PROVIDER_UNVERIFIED" for name in _PRINTER_FIELDS}
    for path, kind in _GETTERS:
        root, *parts = path.split(".")
        value, reason = _observe(context if root == "context" else blender, parts, kind)
        if reason is None:
            values[path] = value
        else:
            unavailable[path] = reason
    return {
        "schema": "cairntir.blender-scene-settings.v1",
        "observed_at": observed_at,
        "host": host,
        "values": values,
        "unavailable": unavailable,
    }
