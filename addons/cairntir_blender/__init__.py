"""Cairntir Blender add-on — proves the horizon thesis.

This add-on is the first non-code Cairntir client. It writes drawers
to Cairntir's spool from inside Blender so the same memory layer that
records code decisions in the cairntir wing records 3D-print iteration
outcomes in a blender wing — same shape, same retrieval, same
prediction-bound semantics. Cairntir doesn't care what is being
remembered.

Architecture: spool drop. The add-on writes JSON envelopes in the
shape Cairntir's daemon expects (see :mod:`cairntir.daemon.spool`)
to ``$CAIRNTIR_HOME/spool/``. The daemon picks them up on its next
poll cycle. No Cairntir Python install needed inside Blender's
bundled Python — the writer is stdlib-only.

Install: zip this directory, then in Blender go
Edit > Preferences > Add-ons > Install, select the zip, and tick the
box. The "Cairntir" tab appears in the 3D Viewport's N-panel.

Configuration: set ``CAIRNTIR_HOME`` in your shell environment, or
override per-session via the panel field. Wing and material default
to ``blender-print`` / ``PLA`` and can be edited in the panel.
"""

from __future__ import annotations

bl_info = {
    "name": "Cairntir",
    "author": "Patrick McGuire",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Cairntir",
    "description": (
        "Capture decisions and 3D-print outcomes into Cairntir's memory "
        "layer via the daemon spool drop pattern."
    ),
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
    from . import spool_writer

    class CAIRNTIR_PG_settings(bpy.types.PropertyGroup):  # type: ignore[misc]
        """Per-scene Cairntir capture settings."""

        wing: bpy.props.StringProperty(  # type: ignore[valid-type]
            name="Wing",
            description="Cairntir wing this Blender session writes into",
            default="blender-print",
        )
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
            home_override = (
                settings.cairntir_home_override.strip() or None
            )
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
            name="Nozzle temp (°C)",
            default=200,
        )
        bed_temp: bpy.props.IntProperty(  # type: ignore[valid-type]
            name="Bed temp (°C)",
            default=60,
        )
        infill_pct: bpy.props.IntProperty(  # type: ignore[valid-type]
            name="Infill (%)",
            default=20,
        )
        layer_height_mm: bpy.props.FloatProperty(  # type: ignore[valid-type]
            name="Layer height (mm)",
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
            home_override = (
                settings.cairntir_home_override.strip() or None
            )
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
            settings = context.scene.cairntir_settings
            layout.prop(settings, "wing")
            layout.prop(settings, "material")
            layout.prop(settings, "cairntir_home_override")
            layout.separator()
            layout.operator(CAIRNTIR_OT_capture_decision.bl_idname, icon="TEXT")
            layout.operator(
                CAIRNTIR_OT_capture_print_outcome.bl_idname, icon="MOD_BUILD"
            )

    _CLASSES = (
        CAIRNTIR_PG_settings,
        CAIRNTIR_OT_capture_decision,
        CAIRNTIR_OT_capture_print_outcome,
        CAIRNTIR_PT_panel,
    )

    def register() -> None:
        """Register every Blender class and bind the per-scene settings property."""
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
        bpy.types.Scene.cairntir_settings = bpy.props.PointerProperty(
            type=CAIRNTIR_PG_settings
        )

    def unregister() -> None:
        """Unregister Cairntir add-on classes in reverse order, dropping the property."""
        del bpy.types.Scene.cairntir_settings
        for cls in reversed(_CLASSES):
            bpy.utils.unregister_class(cls)

else:
    # Outside Blender — import from spool_writer must still work.
    def register() -> None:
        """No-op outside Blender."""

    def unregister() -> None:
        """No-op outside Blender."""
