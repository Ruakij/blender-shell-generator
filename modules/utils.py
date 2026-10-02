"""Utility functions for the Shell Generator addon."""

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


def format_length(context, value_bu):
    """Format a length in Blender Units using the scene unit settings."""
    unit_settings = context.scene.unit_settings
    return bpy.utils.units.to_string(
        unit_settings.system, 'LENGTH', value_bu * unit_settings.scale_length, precision=3
    )


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
