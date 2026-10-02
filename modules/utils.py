"""Utility functions for the Shell Generator addon."""

import bpy
from mathutils import Vector

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

class ErrorHandler:
    """Handle and manage errors during shell generation."""
    
    def __init__(self):
        """Initialize the error handler."""
        self.errors = []
    
    def add_error(self, message, level='ERROR'):
        """
        Add an error message with specified level.
        
        Args:
            message: Error message
            level: Error level ('ERROR', 'WARNING', or 'INFO')
        """
        self.errors.append({'message': message, 'level': level})
    
    def has_errors(self):
        """Check if there are any errors."""
        return any(error['level'] == 'ERROR' for error in self.errors)
    
    def get_messages(self):
        """Get all error messages."""
        return self.errors
    
    def clear(self):
        """Clear all errors."""
        self.errors = []
