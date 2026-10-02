"""Core functionality for shell generation."""

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
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


def setup_boolean_modifier(obj, operation='DIFFERENCE', solver='EXACT', target=None, use_self=False):
    """
    Add and configure a boolean modifier on an object.
    
    Args:
        obj: The object to add the modifier to
        operation: Boolean operation type ('DIFFERENCE', 'UNION', or 'INTERSECT')
        solver: Solver type ('EXACT', 'FLOAT' or 'MANIFOLD')
        target: Target object for the boolean operation
        use_self: Handle self-intersecting operands; makes the exact solver
            many times slower and more memory hungry on dense meshes
        
    Returns:
        bpy.types.BooleanModifier: The created modifier
    """
    mod = obj.modifiers.new("Boolean", 'BOOLEAN')
    mod.operation = operation
    mod.solver = solver
    mod.use_self = use_self
    if target:
        mod.object = target
    return mod


def mesh_defects(obj, depsgraph):
    """
    Check the evaluated mesh of obj for what the Manifold boolean solver cannot
    handle; it silently leaves the target unchanged on such an operand.

    Returns:
        tuple: (closed, self_intersecting)
    """
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    closed = all(e.is_manifold for e in bm.edges)
    bm.verts.index_update()
    tris = [[l.vert.index for l in tri] for tri in bm.calc_loop_triangles()]
    tree = BVHTree.FromPolygons([v.co for v in bm.verts], tris)
    bm.free()
    # overlap() also reports neighbouring triangles, which only touch
    self_intersecting = any(not set(tris[a]) & set(tris[b]) for a, b in tree.overlap(tree))
    return closed, self_intersecting


def cleanup_objects(objects_to_remove):
    """
    Remove temporary objects created during shell generation.
    
    Args:
        objects_to_remove: List of objects to remove
    """
    for obj in objects_to_remove:
        if obj is None:
            continue
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass  # Already removed


def setup_3d_print_toolbox(obj):
    """
    Setup 3D Print Toolbox compatibility for an object.
    
    Args:
        obj: The object to setup
    """
    if obj.get('print3d_volume') is None:
        obj['print3d_volume'] = 0
