"""Utility functions for the Shell Generator addon."""

import math
import textwrap
import bpy
from mathutils import Vector
from .. import ADDON_ID

def calculate_optimal_voxel_size(obj, detail_level=1.0):
    """
    Calculate optimal voxel size based on object complexity and dimensions.
    
    Args:
        obj: The blender object to analyze
        detail_level: User-configurable multiplier (higher = less detail, larger voxels)
        
    Returns:
        float: Optimal voxel size in Blender Units
    """
    # Get object dimensions from bounding box
    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_x = min(corner.x for corner in bbox_corners)
    max_x = max(corner.x for corner in bbox_corners)
    min_y = min(corner.y for corner in bbox_corners)
    max_y = max(corner.y for corner in bbox_corners)
    min_z = min(corner.z for corner in bbox_corners)
    max_z = max(corner.z for corner in bbox_corners)
    
    # Calculate diagonal length
    diagonal_length = ((max_x - min_x)**2 + (max_y - min_y)**2 + (max_z - min_z)**2)**0.5
    
    # Get mesh complexity metrics
    vertex_count = len(obj.data.vertices)
    face_count = len(obj.data.polygons)
    
    # Convert complexity to a scale factor (more complex = smaller voxels)
    # Use logarithmic scale to handle wide range of mesh complexities
    complexity_factor = 1.0 / (1.0 + 0.1 * (vertex_count ** 0.3))
    
    # Base voxel size as percentage of diagonal (smaller for complex objects)
    base_voxel_percent = 0.005 * complexity_factor  # 0.5% for average complexity
    
    return diagonal_length * base_voxel_percent * detail_level


def min_voxel_size(objects, margin, max_voxels_per_axis):
    """
    Smallest voxel size keeping the remesh grid of the objects plus margin
    within max_voxels_per_axis along the longest axis, in Blender Units.
    """
    corners = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    extent = max(max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3))
    return (extent + 2 * margin) / max_voxels_per_axis


def source_objects(context):
    """The meshes the operator builds the shell from."""
    selected = [o for o in context.selected_objects if o.type == 'MESH']
    if context.scene.shellgen_props.combine_selected_for_proxy and selected:
        return selected
    return [context.active_object]


def source_problem(context):
    """Why no shell can be built from the current selection, or None."""
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return "Select a mesh object"
    # The active object stays set after deselecting everything
    if not all(o.select_get() for o in source_objects(context)):
        return "Select a mesh object"
    if not any(o.data.polygons for o in source_objects(context)):
        return "The mesh has no faces"
    return None


def remesh_voxel_size(context):
    """
    Voxel size the operator remeshes with.

    Returns:
        tuple: (voxel size, voxels along the longest axis, offset bound,
            whether the max voxels per axis raised the size)
    """
    props = context.scene.shellgen_props
    max_voxels = context.preferences.addons[ADDON_ID].preferences.max_voxels_per_axis
    # The remesh only rebuilds the offset layer: the cavity is cut with the original
    # and the thickness is added afterwards. Its surface lands within about a voxel,
    # so half the offset keeps at least half the requested gap.
    bound = props.offset / 2
    if props.auto_voxel_size:
        voxel = min(calculate_optimal_voxel_size(context.active_object, detail_level=props.detail_level), bound)
    else:
        voxel = props.remesh_voxel_size
    floor = min_voxel_size(source_objects(context), props.offset + props.thickness, max_voxels)
    raised = voxel < floor
    voxel = max(voxel, floor)
    return voxel, round(max_voxels * floor / voxel), bound, raised


_UNIT_SYMBOLS = {
    'KILOMETERS': 'km', 'METERS': 'm', 'CENTIMETERS': 'cm', 'MILLIMETERS': 'mm', 'MICROMETERS': 'um',
    'MILES': 'mi', 'FEET': 'ft', 'INCHES': 'in', 'THOU': 'thou',
}


def format_length(context, value_bu):
    """Format a length in Blender Units in the scene's length unit, or adaptively when it has none."""
    unit_settings = context.scene.unit_settings
    value = value_bu * unit_settings.scale_length
    symbol = _UNIT_SYMBOLS.get(unit_settings.length_unit)
    # to_string always picks its own unit, ignoring the scene's chosen one
    if unit_settings.system == 'NONE' or symbol is None:
        return bpy.utils.units.to_string(unit_settings.system, 'LENGTH', value, precision=3).strip()
    factor = bpy.utils.units.to_value(unit_settings.system, 'LENGTH', '1' + symbol)
    value /= factor
    # three significant digits, but never round away whole units
    decimals = max(0, 2 - math.floor(math.log10(abs(value)))) if value else 0
    text = f"{value:.{decimals}f}"
    if decimals:
        text = text.rstrip('0').rstrip('.')
    return f"{text} {symbol}"


def draw_wrapped(layout, context, text, icon, width=None):
    """
    Draw text as labels wrapped to width, by default the region width. Only the
    first line carries the icon; the others start with a blank one, aligned under its text.
    """
    width = width or (context.region.width if context.region else 300)
    # Roughly 7 px per character at UI scale 1, less the panel margins and the icon;
    # the system scale includes the pixel size of HiDPI displays and is 0 without a window
    chars = max(16, int((width - 40) / (7 * (context.preferences.system.ui_scale or 1))))
    col = layout.column(align=True)
    # Tighter than separate labels, so each text reads as one paragraph
    col.scale_y = 0.75
    for i, line in enumerate(textwrap.wrap(text, chars)):
        col.label(text=line, icon=icon if i == 0 else 'BLANK1')


def validate_mesh(obj):
    """
    Validate mesh before processing.
    
    Args:
        obj: The blender object to validate
        
    Raises:
        ValueError: If the object is not a valid mesh
    """
    if obj is None:
        raise ValueError("No object provided")
    if obj.type != 'MESH':
        raise ValueError("Object must be a mesh")
    if len(obj.data.vertices) == 0:
        raise ValueError("Mesh has no vertices")
    if not obj.data.polygons:
        raise ValueError("Mesh has no faces")
