"""UI components for the Shell Generator addon."""

import time
import traceback
import bpy
from bpy.types import Panel, Menu
from mathutils import Vector
from .. import ADDON_ID
from .core import AUTO_ANALYZE_FACE_COUNT, DEFERRED_ANALYZE_FACE_COUNT, cached_mesh_defects
from .utils import draw_wrapped, format_length, remesh_voxel_size, source_objects, source_problem

# A 1M-face sphere took 12 s and 7.6 GB with the Manifold solver
DENSE_FACE_COUNT = 1_000_000
# Deferred checks wait this long after the last request for another mesh, so clicking
# through objects never runs one per click
ANALYZE_DELAY = 0.3


class VIEW3D_MT_shell_gen_menu(Menu):
    """Menu for Shell Generator operations."""
    
    bl_label = "Shell Generator"
    bl_idname = "VIEW3D_MT_shell_gen_menu"
    
    def draw(self, context):
        """Draw the menu."""
        layout = self.layout
        layout.operator("object.create_offset_shell", icon='MOD_SOLIDIFY')


def draw_shell_gen_menu(self, context):
    """Draw function for menu integration."""
    layout = self.layout
    layout.separator()
    layout.menu(VIEW3D_MT_shell_gen_menu.bl_idname, icon='MESH_CUBE')


def is_combined(context):
    """Whether Combine Selected builds a remeshed proxy from the selection."""
    return (context.scene.shellgen_props.combine_selected_for_proxy
            and any(o.type == 'MESH' for o in context.selected_objects))


def analysis(obj):
    """
    When the panel checks obj: 'now' in the redraw, 'deferred' shortly after the
    changes stop, or None for a mesh only Create Shell checks.
    """
    # Array or Geometry Nodes can multiply the faces without bound, and reading the evaluated
    # count builds the subdivided mesh that GPU subdivision skips, so no count is cheap to know
    if any(m.show_viewport for m in obj.modifiers):
        return None
    faces = len(obj.data.polygons)
    if faces <= AUTO_ANALYZE_FACE_COUNT:
        return 'now'
    return 'deferred' if faces <= DEFERRED_ANALYZE_FACE_COUNT else None


_analyze_after = 0.0
_analyze_for = None


def request_analysis(obj):
    """Check the active mesh ANALYZE_DELAY after the first request for it."""
    global _analyze_after, _analyze_for
    # Every mouse move over the sidebar redraws the panel, which would postpone the check forever
    if _analyze_for == obj.name and bpy.app.timers.is_registered(run_analysis):
        return
    _analyze_for = obj.name
    _analyze_after = time.monotonic() + ANALYZE_DELAY
    if not bpy.app.timers.is_registered(run_analysis):
        bpy.app.timers.register(run_analysis, first_interval=ANALYZE_DELAY)


def run_analysis():
    """Timer behind request_analysis."""
    wait = _analyze_after - time.monotonic()
    if wait > 0:
        return wait
    context = bpy.context
    obj = context.view_layer.objects.active
    try:
        # The selection may have changed since the request
        if (obj and obj.type == 'MESH' and obj.mode == 'OBJECT' and not is_combined(context)
                and analysis(obj) == 'deferred'):
            cached_mesh_defects(obj, context.evaluated_depsgraph_get(), compute=True)
    except Exception:
        # Without the redraw no new request comes until the next change, so a failure is not retried in a loop
        traceback.print_exc()
        return None
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return None


def cavity(context):
    """
    The boolean solver the cavity cut will use. Reads only metadata; the mesh
    checks run in the redraw for small meshes and shortly after it for larger ones.

    Returns:
        tuple: (solver name, or None until the mesh is analyzed,
            (closed, self_intersecting, inverted) or None)
    """
    if is_combined(context):
        return "Manifold", None
    obj = context.active_object
    try:
        mode = analysis(obj)
        defects = cached_mesh_defects(obj, context.evaluated_depsgraph_get() if mode == 'now' else None, mode == 'now')
        if defects is None and mode == 'deferred':
            request_analysis(obj)
    except Exception:
        traceback.print_exc()
        defects = None
    if defects is None:
        return None, None
    closed, self_intersecting, _ = defects
    if closed and not self_intersecting:
        return "Manifold", defects
    return ("Float" if context.scene.shellgen_props.fast_mode else "Exact"), defects


def checks(context):
    """
    What may give a poor or slow result with the current settings.

    Returns:
        list: (text, icon) tuples, icon 'ERROR' for a broken, lost or very costly result,
            'INFO' for what only looks unintended or may lower the quality
    """
    props = context.scene.shellgen_props
    obj = context.active_object
    fmt = lambda value: format_length(context, value)
    sources = source_objects(context)
    selected = [o for o in context.selected_objects if o.type == 'MESH']
    proxy = is_combined(context)
    warnings = []

    if not proxy and len(selected) > 1:
        warnings.append((f"{len(selected)} meshes selected, only {obj.name} is used. "
                         "Advanced > Combine Selected joins them", 'INFO'))
    if props.combine_selected_for_proxy:
        others = len(context.selected_objects) - len(selected)
        if others:
            warnings.append((f"{others} non-mesh objects ignored", 'INFO'))
        if proxy and obj not in selected:
            warnings.append((f"{obj.name} is active but not selected, so it is not combined", 'INFO'))

    def extent(objects):
        corners = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
        return max(max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3))

    size = extent(sources)
    if len(sources) > 1 and size > 3 * max(extent([o]) for o in sources):
        warnings.append(("Combined meshes lie far apart: the remesh grid spans all of them, "
                         "so the voxel gets coarse", 'INFO'))
    if props.offset + props.thickness > size:
        warnings.append((f"Offset plus thickness ({fmt(props.offset + props.thickness)}) exceed the object size "
                         f"({fmt(size)}): the sizes look wrong for this scene", 'INFO'))
    prefs = context.preferences.addons[ADDON_ID].preferences
    unit_scale = context.scene.unit_settings.scale_length
    if unit_scale != 1 and (props.offset, props.thickness) == (prefs.default_offset, prefs.default_thickness):
        warnings.append((f"Default offset and thickness with a unit scale of {unit_scale:g}: "
                         "check that the sizes fit this scene", 'INFO'))

    voxel, _, bound, raised = remesh_voxel_size(context)
    if voxel > bound:
        if raised:
            warnings.append((f"The Max Voxels per Axis preference forces a voxel above half the offset ({fmt(bound)}), "
                             "so the gap may come out uneven. Raise the limit or the offset", 'INFO'))
        else:
            warnings.append((f"Voxel size is above half the offset ({fmt(bound)}), "
                             "so the gap may come out uneven", 'INFO'))

    solver, defects = cavity(context)
    if defects:
        closed, self_intersecting, inverted = defects
        if not closed:
            effect = "will be less reliable" if props.fast_mode else "will be slow"
            warnings.append((f"Open mesh: the {solver} solver {effect}. "
                             "Advanced > Combine Selected avoids it", 'ERROR'))
        if self_intersecting:
            effect = "may cut it wrong" if props.fast_mode else "will be much slower"
            warnings.append((f"Self-intersecting mesh: the {solver} solver {effect}. "
                             "Advanced > Combine Selected avoids it", 'ERROR'))
        # Solidify then offsets inward and the cavity cut removes the mold
        if inverted:
            warnings.append(("Normals point inward - recalculate normals first", 'ERROR'))
    elif not proxy and analysis(obj) is None:
        kind = "Mesh with modifiers" if any(m.show_viewport for m in obj.modifiers) else "Large mesh"
        warnings.append((f"{kind}, not fully checked: more warnings may appear on Create Shell", 'INFO'))

    if props.open_bottom:
        zs = [(o.matrix_world @ Vector(c)).z for o in sources for c in o.bound_box]
        # The cutter ends at Z=0.001, see create_cutter_object
        if max(zs) <= 0.001:
            warnings.append(("Object lies below Z=0: the cut removes the cavity and leaves "
                             "little or nothing of mold and shell", 'ERROR'))
        elif min(zs) > 0.001:
            warnings.append((f"Object starts {fmt(min(zs))} above Z=0: the cut does not reach "
                             "the cavity, which stays closed at the bottom", 'INFO'))

    faces = sum(len(o.data.polygons) for o in sources)
    if faces > DENSE_FACE_COUNT:
        warnings.append((f"Dense mesh ({faces:,} faces): the run takes long and needs a lot of memory", 'ERROR'))

    return warnings


def hint(layout, context, text):
    """Draw text greyed out, for values the add-on chooses on its own."""
    col = layout.column(align=True)
    col.active = False
    draw_wrapped(col, context, text, 'INFO')


class OBJECT_PT_shell_panel(Panel):
    """Main panel for Shell Generator."""
    
    bl_label = "Shell Generator"
    bl_idname = "OBJECT_PT_shell_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ShellGen"
    bl_context = "objectmode"
    
    @classmethod
    def poll(cls, context):
        """Only display in object mode."""
        return context.mode == 'OBJECT'

    def draw_header(self, context):
        """Draw the header with icon."""
        self.layout.label(text="", icon='MESH_CUBE')

    def draw(self, context):
        """Draw the panel."""
        layout = self.layout
        props = context.scene.shellgen_props
        
        problem = source_problem(context)
        if problem:
            layout.label(text=problem, icon='ERROR')
            return

        col = layout.column(align=True)
        col.prop(props, "offset")
        col.prop(props, "thickness")
        layout.prop(props, "open_bottom")

        try:
            for text, icon in checks(context):
                draw_wrapped(layout, context, text, icon)
        except Exception:
            traceback.print_exc()
            layout.label(text="Checks unavailable", icon='ERROR')

        row = layout.row()
        row.scale_y = 2.0
        row.operator("object.create_offset_shell")


class OBJECT_PT_shell_advanced(Panel):
    """Collapsed subpanel for settings whose defaults rarely need changing."""

    bl_label = "Advanced"
    bl_idname = "OBJECT_PT_shell_advanced"
    bl_parent_id = "OBJECT_PT_shell_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ShellGen"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        """Only display when there is a mesh to build from."""
        return source_problem(context) is None

    def draw(self, context):
        """Draw the advanced settings."""
        layout = self.layout
        props = context.scene.shellgen_props

        col = layout.column()
        col.prop(props, "combine_selected_for_proxy")
        col.prop(props, "even_thickness")
        if props.even_thickness:
            col.label(text="May create artifacts", icon='ERROR')
        col.prop(props, "fast_mode")
        solver = cavity(context)[0]
        if solver:
            hint(col, context, f"Cavity solver: {solver}")

        col = layout.column()
        col.prop(props, "auto_voxel_size")
        if props.auto_voxel_size:
            col.prop(props, "detail_level", slider=True)
        else:
            col.prop(props, "remesh_voxel_size")
        voxel, per_axis, _, raised = remesh_voxel_size(context)
        if props.auto_voxel_size or raised:
            prefix = "Auto" if props.auto_voxel_size else "Raised"
            hint(col, context, f"{prefix}: {format_length(context, voxel)} ({per_axis} per axis)")

        layout.operator("object.shell_reset_props", text="Reset Settings", icon='LOOP_BACK')
