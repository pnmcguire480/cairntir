"""Capture print outcomes and recall scoped prior iterations inside Blender.

Capture uses the daemon spool. Recall runs an installed Cairntir Python
through a bounded child process configured in trusted add-on preferences.
Blender imports only standard-library transport code.
"""

import json
import os
import time

bl_info = {
    "name": "Cairntir",
    "author": "Patrick McGuire",
    "version": (0, 3, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Cairntir",
    "description": ("Capture print outcomes and recall relevant prior iterations from Cairntir."),
    "category": "System",
    "doc_url": "https://github.com/pnmcguire480/cairntir",
}

# Lazy import: bpy lives only inside Blender. The body of the
# add-on (operator classes, panel, registration) is gated on this so
# the spool_writer module remains importable from pytest without
# Blender installed.
try:
    import bpy

    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

if _HAS_BPY:
    from . import recall_client, scene_settings, spool_writer

    class CAIRNTIR_AP_preferences(bpy.types.AddonPreferences):
        """Trusted connection settings outside scene data."""

        bl_idname = __package__

        python_executable: bpy.props.StringProperty(name="Cairntir Python", subtype="FILE_PATH")
        home: bpy.props.StringProperty(name="Cairntir home", subtype="DIR_PATH")
        grant_file: bpy.props.StringProperty(name="Read grant file", subtype="FILE_PATH")

        def draw(self, _context):
            for name in ("python_executable", "home", "grant_file"):
                self.layout.prop(self, name)

    class CAIRNTIR_PG_recall(bpy.types.PropertyGroup):
        """Temporary recall state excluded from blend saves."""

        status: bpy.props.StringProperty(default="IDLE", options={"SKIP_SAVE"})
        request_id: bpy.props.StringProperty(options={"SKIP_SAVE"})
        response_json: bpy.props.StringProperty(options={"SKIP_SAVE"})
        error: bpy.props.StringProperty(options={"SKIP_SAVE"})

    _running = {}
    _views = {}

    def _preferences(context):
        entry = context.preferences.addons.get(__package__)
        return entry.preferences if entry else None

    def _signature(context):
        settings = context.scene.cairntir_settings
        prefs = _preferences(context)
        return (
            context.scene.as_pointer(),
            settings.wing.strip().lower(),
            settings.material.strip().lower(),
            settings.recall_query,
            *(getattr(prefs, name, "") for name in ("python_executable", "home", "grant_file")),
            os.environ.get("FASTEMBED_CACHE_PATH", ""),
        )

    class CAIRNTIR_OT_recall_prints(bpy.types.Operator):
        """Read authorized prior prints without blocking interactive work."""

        bl_idname = "cairntir.recall_prints"
        bl_label = "Recall Prior Prints"

        def _stop(self):
            try:
                if self._job is not None:
                    self._job.close()
            finally:
                if self._timer is not None:
                    self._wm.event_timer_remove(self._timer)
                self._job = self._timer = None
                if _running.get(self._key) is self:
                    _running.pop(self._key)

        def _failed(self, context, message):
            state = context.window_manager.cairntir_recall
            state.status = "UNAVAILABLE"
            state.response_json = ""
            state.error = message
            _views[self._key] = _signature(context)
            self._stop()
            return {"CANCELLED"}

        def _begin(self, context):
            self._wm = context.window_manager
            self._key = self._wm.as_pointer()
            self._job = self._timer = None
            previous = _running.get(self._key)
            if previous is not None:
                previous.cancel(context)
            state = self._wm.cairntir_recall
            state.status, state.request_id = "RUNNING", ""
            state.response_json = state.error = ""
            _views.pop(self._key, None)
            settings = context.scene.cairntir_settings
            prefs = _preferences(context)
            if prefs is None:
                return self._failed(
                    context, "Configure the Cairntir connection in add-on preferences."
                )
            try:
                self._request = recall_client.build_request(
                    settings.wing, settings.material, settings.recall_query
                )
                self._signature = _signature(context)
                self._job = recall_client.start_recall(
                    prefs.python_executable, prefs.home, prefs.grant_file, self._request
                )
            except (OSError, ValueError):
                return self._failed(
                    context,
                    "Configure the Cairntir connection in add-on preferences and enter a query.",
                )
            state.request_id = self._request["request_id"]
            _views[self._key] = self._signature
            _running[self._key] = self
            return None

        def _poll(self, context):
            if _running.get(self._key) is not self:
                return {"CANCELLED"}
            if _signature(context) != self._signature:
                self.cancel(context)
                return {"CANCELLED"}
            try:
                result = self._job.poll()
            except TimeoutError:
                return self._failed(context, "TIMEOUT: Cairntir recall timed out.")
            except ValueError:
                return self._failed(context, "OUTPUT_LIMIT: Cairntir returned too much output.")
            except OSError:
                return self._failed(context, "UNAVAILABLE: Cairntir could not complete the read.")
            if result is None:
                return None
            code, stdout, _stderr = result
            try:
                reply = recall_client.decode_reply(stdout, self._request)
            except ValueError:
                return self._failed(
                    context, "INVALID_RESPONSE: Cairntir returned an invalid response."
                )
            expected_code = 0 if reply["status"] in {"ok", "empty", "omitted"} else 2
            if code != expected_code:
                return self._failed(context, "INVALID_RESPONSE: inconsistent process result.")
            self._stop()
            state = self._wm.cairntir_recall
            state.status = reply["status"].upper()
            state.response_json = json.dumps(reply, ensure_ascii=False, allow_nan=False)
            state.error = reply["error"]["message"] if reply["error"] else ""
            return {"FINISHED"} if code == 0 else {"CANCELLED"}

        def invoke(self, context, _event):
            failed = self._begin(context)
            if failed is not None:
                return failed
            try:
                self._timer = self._wm.event_timer_add(0.1, window=context.window)
                self._wm.modal_handler_add(self)
            except RuntimeError:
                return self._failed(context, "UNAVAILABLE: recall requires an interactive window.")
            return {"RUNNING_MODAL"}

        def modal(self, context, event):
            if _running.get(self._key) is not self:
                return {"CANCELLED"}
            if event.type == "ESC" and event.value == "PRESS":
                self.cancel(context)
                return {"CANCELLED"}
            if event.type == "TIMER":
                return self._poll(context) or {"RUNNING_MODAL"}
            return {"PASS_THROUGH"}

        def execute(self, context):
            failed = self._begin(context)
            if failed is not None:
                return failed
            while True:
                result = self._poll(context)
                if result is not None:
                    return result
                time.sleep(0.02)

        def cancel(self, _context):
            if _running.get(self._key) is self:
                state = self._wm.cairntir_recall
                state.status = "CANCELLED"
                state.response_json = state.error = ""
            self._stop()

    def _lines(layout, text):
        for line in str(text).splitlines() or [""]:
            for offset in range(0, max(1, len(line)), 70):
                layout.label(text=line[offset : offset + 70])

    def _draw_recall(layout, context):
        layout.separator()
        layout.prop(context.scene.cairntir_settings, "recall_query")
        layout.operator(CAIRNTIR_OT_recall_prints.bl_idname, icon="VIEWZOOM")
        state = context.window_manager.cairntir_recall
        if state.status == "IDLE":
            return
        if _views.get(context.window_manager.as_pointer()) != _signature(context):
            layout.label(text="Context changed. Recall again.")
            return
        layout.label(text=state.status.replace("_", " ").title())
        if state.status == "RUNNING":
            layout.label(text="Press Escape to cancel.")
        if state.error:
            _lines(layout, state.error)
        if not state.response_json:
            return
        try:
            reply = json.loads(state.response_json)
        except ValueError:
            layout.label(text="Invalid saved response. Recall again.")
            return
        for item in reply["entries"]:
            drawer = item["drawer"]
            box = layout.box()
            success = drawer["metadata"].get("success")
            verdict = (
                "Succeeded" if success is True else "Failed" if success is False else "Unknown"
            )
            box.label(text=f"Print {drawer['id']}: {verdict}")
            _lines(box, f"Saved: {drawer['saved_at']}")
            _lines(box, drawer["resource"])
            _lines(box, f"Origin: {drawer['portable_identity']}")
            _lines(box, f"SHA-256: {drawer['content_hash']}")
            box.label(text="Untrusted evidence; no instruction authority.")
            _lines(box, drawer["content"])
        if reply["omitted"]:
            layout.label(
                text=f"{len(reply['omitted'])} whole records omitted by the response budget."
            )
            for item in reply["omitted"]:
                _lines(layout, item["resource"])
        elif reply["status"] == "empty":
            layout.label(text="No matching prior print outcomes.")

    class CAIRNTIR_PG_settings(bpy.types.PropertyGroup):  # type: ignore[misc]
        """Per-scene Cairntir capture settings."""

        wing: bpy.props.StringProperty(  # type: ignore[valid-type]
            name="Wing",
            description="Cairntir wing this Blender session writes into",
            default="blender-print",
        )
        recall_query: bpy.props.StringProperty(name="Prior print query", maxlen=512)

        material: bpy.props.StringProperty(  # type: ignore[valid-type]
            name="Material",
            description="Material being printed (becomes the room name)",
            default="PLA",
        )
        cairntir_home_override: bpy.props.StringProperty(  # type: ignore[valid-type]
            name="Cairntir home",
            description=(
                "Override $CAIRNTIR_HOME for this session. Leave blank to "
                "use the env var or default ~/.cairntir."
            ),
            default="",
            subtype="DIR_PATH",
        )

    class CAIRNTIR_OT_capture_decision(bpy.types.Operator):  # type: ignore[misc]
        """Capture a free-form decision drawer."""

        bl_idname = "cairntir.capture_decision"
        bl_label = "Capture Decision"
        bl_options = {"REGISTER"}

        content: bpy.props.StringProperty(  # type: ignore[valid-type]
            name="Content",
            description="What you decided / observed / want to remember",
        )

        def invoke(self, context, _event):
            return context.window_manager.invoke_props_dialog(self)

        def execute(self, context):
            settings = context.scene.cairntir_settings
            home_override = settings.cairntir_home_override.strip() or None
            try:
                from pathlib import Path

                spool_writer.write_capture(
                    wing=settings.wing,
                    room=settings.material,
                    content=self.content,
                    metadata={"source": "blender", "kind": "decision"},
                    home=Path(home_override) if home_override else None,
                )
            except (ValueError, OSError) as exc:
                self.report({"ERROR"}, f"Cairntir spool write failed: {exc}")
                return {"CANCELLED"}
            self.report({"INFO"}, f"Captured to wing {settings.wing!r}")
            return {"FINISHED"}

    class CAIRNTIR_OT_capture_print_outcome(bpy.types.Operator):  # type: ignore[misc]
        """Capture a 3D-print iteration outcome with parameters + verdict."""

        bl_idname = "cairntir.capture_print_outcome"
        bl_label = "Capture Print Outcome"
        bl_options = {"REGISTER"}

        outcome: bpy.props.StringProperty(  # type: ignore[valid-type]
            name="Outcome",
            description="What actually happened with this print",
        )
        success: bpy.props.BoolProperty(  # type: ignore[valid-type]
            name="Success",
            description="Did the print meet expectations?",
            default=True,
        )
        nozzle_temp: bpy.props.IntProperty(  # type: ignore[valid-type]
            name="Manual nozzle temp (°C)",
            default=200,
        )
        bed_temp: bpy.props.IntProperty(  # type: ignore[valid-type]
            name="Manual bed temp (°C)",
            default=60,
        )
        infill_pct: bpy.props.IntProperty(  # type: ignore[valid-type]
            name="Manual infill (%)",
            default=20,
        )
        layer_height_mm: bpy.props.FloatProperty(  # type: ignore[valid-type]
            name="Manual layer height (mm)",
            default=0.2,
            precision=2,
        )
        notes: bpy.props.StringProperty(  # type: ignore[valid-type]
            name="Notes",
            default="",
        )

        def invoke(self, context, _event):
            return context.window_manager.invoke_props_dialog(self, width=400)

        def execute(self, context):
            settings = context.scene.cairntir_settings
            home_override = settings.cairntir_home_override.strip() or None
            try:
                from pathlib import Path

                spool_writer.write_print_outcome(
                    wing=settings.wing,
                    material=settings.material,
                    parameters={
                        "nozzle_temp_c": self.nozzle_temp,
                        "bed_temp_c": self.bed_temp,
                        "infill_pct": self.infill_pct,
                        "layer_height_mm": self.layer_height_mm,
                    },
                    outcome=self.outcome,
                    success=self.success,
                    notes=self.notes,
                    scene_settings=scene_settings.read_scene_settings(context, bpy),
                    home=Path(home_override) if home_override else None,
                )
            except (ValueError, OSError) as exc:
                self.report({"ERROR"}, f"Cairntir spool write failed: {exc}")
                return {"CANCELLED"}
            verdict = "ok" if self.success else "failed"
            self.report(
                {"INFO"},
                f"Captured print outcome ({verdict}) to {settings.wing}/{settings.material}",
            )
            return {"FINISHED"}

    class CAIRNTIR_PT_panel(bpy.types.Panel):  # type: ignore[misc]
        """Cairntir capture panel in the 3D Viewport sidebar."""

        bl_label = "Cairntir"
        bl_idname = "CAIRNTIR_PT_panel"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "Cairntir"

        def draw(self, context):
            layout = self.layout
            layout.ui_units_x = 42
            settings = context.scene.cairntir_settings
            layout.prop(settings, "wing")
            layout.prop(settings, "material")
            layout.prop(settings, "cairntir_home_override")
            layout.separator()
            layout.operator(CAIRNTIR_OT_capture_decision.bl_idname, icon="TEXT")
            layout.operator(CAIRNTIR_OT_capture_print_outcome.bl_idname, icon="MOD_BUILD")
            _draw_recall(layout, context)

    _CLASSES = (
        CAIRNTIR_AP_preferences,
        CAIRNTIR_PG_recall,
        CAIRNTIR_OT_recall_prints,
        CAIRNTIR_PG_settings,
        CAIRNTIR_OT_capture_decision,
        CAIRNTIR_OT_capture_print_outcome,
        CAIRNTIR_PT_panel,
    )

    def register() -> None:
        """Register every Blender class and bind the per-scene settings property."""
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
        bpy.types.Scene.cairntir_settings = bpy.props.PointerProperty(type=CAIRNTIR_PG_settings)
        bpy.types.WindowManager.cairntir_recall = bpy.props.PointerProperty(
            type=CAIRNTIR_PG_recall, options={"SKIP_SAVE"}
        )

    def unregister() -> None:
        """Unregister Cairntir add-on classes in reverse order, dropping the property."""
        for operator in list(_running.values()):
            operator.cancel(None)
        _views.clear()
        del bpy.types.WindowManager.cairntir_recall
        del bpy.types.Scene.cairntir_settings
        for cls in reversed(_CLASSES):
            bpy.utils.unregister_class(cls)

else:
    # Outside Blender — import from spool_writer must still work.
    def register() -> None:
        """No-op outside Blender."""

    def unregister() -> None:
        """No-op outside Blender."""
