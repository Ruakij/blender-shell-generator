"""Core functionality for shell generation."""

import bpy
from mathutils import Vector
from .utils import validate_mesh, ErrorHandler


def prepare_object_for_shell(obj):
    """
    Prepare an object for shell generation by ensuring it's in the correct state.
    
    Args:
        obj: The blender object to prepare
        
    Returns:
        bool: True if preparation was successful, False otherwise
        
    Raises:
        ValueError: If the object is invalid
    """
    validate_mesh(obj)
    
    # Ensure we're in object mode
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    # Apply scale to ensure correct thickness calculations
    original_scale = obj.scale.copy()
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    
    return True


def create_cutter_object():
    """
    Create a cutter object for open bottom shells.
    
    Returns:
        bpy.types.Object: The created cutter object
    """
    bpy.ops.mesh.primitive_cube_add(size=1500, location=(0, 0, -750 + 0.001))
    cutter = bpy.context.active_object
    cutter.name = "ground_cutter"
    cutter.display_type = 'WIRE'  # Make it wireframe for visibility
    return cutter


def setup_solidify_modifier(obj, thickness, offset=1.0, use_rim=True, use_even_offset=False):
    """
    Add and configure a solidify modifier on an object.
    
    Args:
        obj: The object to add the modifier to
        thickness: Thickness value for the solidify modifier
        offset: Offset value for the solidify modifier
        use_rim: Whether to fill the rim
        use_even_offset: Whether to use even thickness
        
    Returns:
        bpy.types.SolidifyModifier: The created modifier
    """
    mod = obj.modifiers.new("Solidify", 'SOLIDIFY')
    mod.thickness = thickness
    mod.offset = offset
    mod.use_rim = use_rim
    mod.use_even_offset = use_even_offset
    return mod


def setup_remesh_modifier(obj, voxel_size):
    """
    Add and configure a remesh modifier on an object.
    
    Args:
        obj: The object to add the modifier to
        voxel_size: Voxel size for the remesh operation
        
    Returns:
        bpy.types.RemeshModifier: The created modifier
    """
    mod = obj.modifiers.new("Remesh", 'REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = voxel_size
    return mod


def setup_boolean_modifier(obj, operation='DIFFERENCE', solver='EXACT', target=None):
    """
    Add and configure a boolean modifier on an object.
    
    Args:
        obj: The object to add the modifier to
        operation: Boolean operation type ('DIFFERENCE', 'UNION', or 'INTERSECT')
        solver: Solver type ('EXACT' or 'FAST')
        target: Target object for the boolean operation
        
    Returns:
        bpy.types.BooleanModifier: The created modifier
    """
    mod = obj.modifiers.new("Boolean", 'BOOLEAN')
    mod.operation = operation
    mod.solver = solver
    mod.use_self = True
    if target:
        mod.object = target
    return mod


def cleanup_objects(objects_to_remove):
    """
    Remove temporary objects created during shell generation.
    
    Args:
        objects_to_remove: List of objects to remove
    """
    for obj in objects_to_remove:
        if obj is None:
            continue
        # First hide the object
        obj.hide_set(True)
        # Then remove it
        bpy.data.objects.remove(obj, do_unlink=True)


def setup_3d_print_toolbox(obj):
    """
    Setup 3D Print Toolbox compatibility for an object.
    
    Args:
        obj: The object to setup
    """
    if obj.get('print3d_volume') is None:
        obj['print3d_volume'] = 0


def get_unit_settings(context):
    """
    Get unit conversion settings from the scene.
    
    Args:
        context: Blender context
        
    Returns:
        tuple: (unit_to_bu, unit_suffix)
            unit_to_bu: Factor to convert from display units to Blender Units
            unit_suffix: String suffix for the current unit system
    """
    unit_settings = context.scene.unit_settings
    unit_to_bu = 1.0 if unit_settings.system == 'NONE' else (0.001 / unit_settings.scale_length)
    
    # Determine unit suffix
    unit_suffix = ""
    if unit_settings.system == 'METRIC':
        if unit_settings.length_unit == 'KILOMETERS':
            unit_suffix = "km"
        elif unit_settings.length_unit == 'METERS':
            unit_suffix = "m"
        elif unit_settings.length_unit == 'CENTIMETERS':
            unit_suffix = "cm"
        elif unit_settings.length_unit == 'MILLIMETERS':
            unit_suffix = "mm"
        elif unit_settings.length_unit == 'MICROMETERS':
            unit_suffix = "μm"
    elif unit_settings.system == 'IMPERIAL':
        if unit_settings.length_unit == 'MILES':
            unit_suffix = "mi"
        elif unit_settings.length_unit == 'FEET':
            unit_suffix = "'"
        elif unit_settings.length_unit == 'INCHES':
            unit_suffix = "\""
        elif unit_settings.length_unit == 'THOU':
            unit_suffix = "thou"
            
    return unit_to_bu, unit_suffix
