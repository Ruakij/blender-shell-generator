"""Property definitions for the Shell Generator addon."""

import bpy
from bpy.props import (
    FloatProperty,
    BoolProperty,
    PointerProperty,
    StringProperty
)
from bpy.types import PropertyGroup, AddonPreferences


class ShellGenAddonPreferences(AddonPreferences):
    """Addon preferences for Shell Generator."""
    
    bl_idname = __package__.split('.')[0]  # Get root package name

    default_offset: FloatProperty(
        name="Default Offset",
        description="Default value for the offset distance",
        default=10.0,
        min=0.001
    )
    
    default_thickness: FloatProperty(
        name="Default Thickness",
        description="Default value for the shell thickness",
        default=5.0,
        min=0.001
    )
    
    show_debug_info: BoolProperty(
        name="Show Debug Info",
        description="Display additional debug information during operation",
        default=False
    )
    
    keep_modifiers: BoolProperty(
        name="Keep Modifiers Visible",
        description="Don't apply modifiers automatically, keep them visible for debugging",
        default=False
    )
    
    def draw(self, context):
        """Draw the preferences panel."""
        layout = self.layout
        
        box = layout.box()
        box.label(text="Default Settings")
        col = box.column(align=True)
        col.prop(self, "default_offset")
        col.prop(self, "default_thickness")
        
        box = layout.box()
        box.label(text="Advanced Options")
        col = box.column()
        col.prop(self, "show_debug_info")
        col.prop(self, "keep_modifiers")
        
        box = layout.box()
        box.label(text="Documentation & Support")
        col = box.column()
        col.operator("wm.url_open", text="GitHub Repository").url = "https://github.com/ruakij/blender-shell-generator"
        col.operator("wm.url_open", text="Report Issues").url = "https://github.com/ruakij/blender-shell-generator/issues"


class ShellGenProperties(PropertyGroup):
    """Properties for the Shell Generator tool."""
    
    offset: FloatProperty(
        name="Offset",
        description="Gap between object and start of shell",
        default=10.0,
        min=0.001,
        soft_max=100.0,
        subtype='DISTANCE',
        unit='LENGTH'
    )
    
    thickness: FloatProperty(
        name="Thickness",
        description="Shell thickness",
        default=5.0,
        min=0.001,
        soft_max=100.0,
        subtype='DISTANCE',
        unit='LENGTH'
    )
    
    open_bottom: BoolProperty(
        name="Open Bottom (Z<0)",
        description="Remove all geometry below Z=0 (make bottom open)",
        default=True,
    )
    
    fast_mode: BoolProperty(
        name="Fast Mode",
        description="Uses faster but less precise boolean solver and simpler remesh settings. May help with complex geometry but can affect quality.",
        default=False,
    )
    
    auto_voxel_size: BoolProperty(
        name="Auto Voxel Size",
        description="Automatically calculate optimal voxel size based on object complexity and dimensions",
        default=True,
    )
    
    detail_level: FloatProperty(
        name="Detail Level",
        description="Level of detail for auto voxel size (lower values = more detail, higher quality)",
        default=1.0,
        min=0.1,
        max=5.0,
        step=10,
        precision=1,
    )
    
    remesh_voxel_size: FloatProperty(
        name="Remesh Voxel Size",
        description="Voxel size for remesh operation (smaller = higher quality, slower)",
        default=1.0,
        min=0.01,
        subtype='DISTANCE',
        unit='LENGTH'
    )
    
    combine_selected_for_proxy: BoolProperty(
        name="Combine Selected Meshes for Proxy",
        description="Join and remesh all selected meshes to create a single Boolean source",
        default=False,
    )

    even_thickness: BoolProperty(
        name="Even Thickness (experimental)",
        description="Enable Blender's 'Even Thickness' for solidify modifiers (may create artifacts at sharp corners or complex geometry!)",
        default=False,
    )
