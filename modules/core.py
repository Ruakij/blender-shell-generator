"""Core functionality for shell generation."""

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from .utils import validate_mesh


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


def create_cutter_object(objects):
    """
    Create a box ending at Z=0.001 that covers the world bounding box of objects
    with a margin, for open bottom shells.

    Returns:
        bpy.types.Object: The cutter, not linked to any collection
    """
    corners = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    margin = 0.1 * max(hi - lo)
    lo -= Vector((margin,) * 3)
    hi += Vector((margin,) * 3)
    lo.z = min(lo.z, 0.001 - margin)
    hi.z = 0.001
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bm.transform(Matrix.LocRotScale((lo + hi) / 2, None, hi - lo))
    mesh = bpy.data.meshes.new("ground_cutter")
    bm.to_mesh(mesh)
    bm.free()
    cutter = bpy.data.objects.new("ground_cutter", mesh)
    cutter.display_type = 'WIRE'  # Make it wireframe for visibility
    return cutter


def evaluated_mesh(objects, depsgraph, frame, name):
    """
    Join the meshes of objects as the viewport shows them, with modifiers and
    shape keys applied, into a new mesh in the space of the matrix frame.
    Faces of objects with a negative scale are flipped, so the result keeps
    the normals the viewport shows without needing the mirroring matrix.
    """
    bm = bmesh.new()
    for obj in objects:
        faces_start = len(bm.faces)
        verts_start = len(bm.verts)
        bm.from_object(obj, depsgraph)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bmesh.ops.transform(bm, matrix=frame.inverted() @ obj.matrix_world, verts=bm.verts[verts_start:])
        if obj.matrix_world.is_negative:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[faces_start:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


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
        tuple: (closed, self_intersecting, inverted), inverted meaning the
            normals of a closed mesh point inward
    """
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    closed = all(e.is_manifold for e in bm.edges)
    inverted = closed and bm.calc_volume(signed=True) < 0
    bm.verts.index_update()
    tris = [[l.vert.index for l in tri] for tri in bm.calc_loop_triangles()]
    tree = BVHTree.FromPolygons([v.co for v in bm.verts], tris)
    bm.free()
    # overlap() also reports neighbouring triangles, which only touch
    self_intersecting = any(not set(tris[a]) & set(tris[b]) for a, b in tree.overlap(tree))
    return closed, self_intersecting, inverted


# mesh_defects takes about 2 us per face (UV spheres: 50k faces 106 ms, 100k 188 ms, 200k 451 ms);
# this keeps a panel redraw under about 20 ms
AUTO_ANALYZE_FACE_COUNT = 10_000
# Larger meshes are checked shortly after changes stop, which pauses Blender for up to about 200 ms
DEFERRED_ANALYZE_FACE_COUNT = 100_000

_defects_cache = {}


def cached_mesh_defects(obj, depsgraph, compute):
    """
    mesh_defects cached per object for the panel.

    Returns:
        tuple: see mesh_defects, or None when not cached and compute is False
    """
    fingerprint = (
        obj.data.as_pointer(),
        len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons),
        tuple(map(tuple, obj.matrix_world)),
        tuple((m.name, m.type, m.show_viewport) for m in obj.modifiers),
    )
    cached = _defects_cache.get(obj.name)
    if cached and cached[0] == fingerprint:
        return cached[1]
    if not compute:
        return None
    defects = mesh_defects(obj, depsgraph)
    _defects_cache[obj.name] = (fingerprint, defects)
    return defects


@bpy.app.handlers.persistent
def clear_defects_cache(scene, depsgraph):
    """depsgraph_update_post handler dropping the analysis of changed mesh objects."""
    for update in depsgraph.updates:
        if (isinstance(update.id, bpy.types.Object) and update.id.type == 'MESH'
                and (update.is_updated_geometry or update.is_updated_transform)):
            _defects_cache.pop(update.id.name, None)


def cleanup_objects(objects_to_remove):
    """
    Remove temporary objects created during shell generation, with their
    meshes once nothing else uses them.

    Args:
        objects_to_remove: List of objects to remove
    """
    for obj in objects_to_remove:
        if obj is None:
            continue
        try:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
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
