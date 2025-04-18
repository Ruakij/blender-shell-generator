"""UI components for the Shell Generator addon."""

import bpy
from bpy.types import Panel, Menu
from .utils import calculate_optimal_voxel_size


class VIEW3D_MT_shell_gen_menu(Menu):
    """Menu for Shell Generator operations."""
    
    bl_label = "Shell Generator"
    bl_idname = "VIEW3D_MT_shell_gen_menu"
    
    def draw(self, context):
        """Draw the menu."""
        layout = self.layout
        layout.operator("object.create_offset_shell", icon='MOD_SOLIDIFY')
        layout.separator()
        layout.operator("object.shell_reset_props", icon='LOOP_BACK')


def draw_shell_gen_menu(self, context):
    """Draw function for menu integration."""
    layout = self.layout
    layout.separator()
    layout.menu(VIEW3D_MT_shell_gen_menu.bl_idname, icon='MESH_CUBE')


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

    def draw(self, context):
        """Draw the panel."""
        layout = self.layout
        props = context.scene.shellgen_props
        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
        
        # Check if there's a valid mesh object selected
        obj = context.active_object
        has_valid_object = obj is not None and obj.type == 'MESH'
        
        # Help and info box
        box = layout.box()
        row = box.row()
        row.label(text="Shell Generator", icon='MESH_CUBE')
        
        if not has_valid_object:
            box = layout.box()
            col = box.column()
            col.label(text="No mesh selected", icon='ERROR')
            col.label(text="Please select a mesh object")
            return
        
        # Shell Parameters
        box = layout.box()
        box.label(text="Shell Parameters:", icon='MOD_SOLIDIFY')
        col = box.column(align=True)
        col.prop(props, "offset")
        col.prop(props, "thickness")
        col.separator()
        col.prop(props, "open_bottom")
        col.prop(props, "combine_selected_for_proxy")
        col.separator()
        col.prop(props, "even_thickness")
        if props.even_thickness:
            col.label(text="May create artifacts at sharp corners!", icon='ERROR')
        
        # Performance Settings  
        box = layout.box()
        box.label(text="Performance Settings:", icon='SETTINGS')
        col = box.column()
        
        # Fast Mode row
        row = col.row()
        row.prop(props, "fast_mode")
        
        # Auto Voxel Size row
        row = col.row()
        row.prop(props, "auto_voxel_size")
        
        # Conditional controls based on auto voxel size
        sub_col = col.column(align=True)
        if props.auto_voxel_size:
            sub_col.prop(props, "detail_level", slider=True)
            
            # Show estimated voxel size if auto mode and object is selected
            if obj and obj.type == 'MESH':
                try:
                    unit_settings = context.scene.unit_settings
                    unit_scale = 1.0 if unit_settings.system == 'NONE' else unit_settings.scale_length
                    
                    sample_size = calculate_optimal_voxel_size(
                        obj,
                        detail_level=props.detail_level,
                        unit_scale=unit_scale
                    )
                    
                    # Get appropriate unit suffix based on scene settings
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
                    
                    sample_text = f"Est. Size: {sample_size:.3f}{unit_suffix}"
                    sub_col.label(text=sample_text, icon='INFO')
                except Exception as e:
                    sub_col.label(text="Est. Size: Using calculated value", icon='INFO')
        else:
            # Manual voxel size control
            sub_col.prop(props, "remesh_voxel_size")
        
        # Reset to defaults button
        box = layout.box()
        row = box.row()
        row.label(text="Utilities:")
        row = box.row()
        reset_op = row.operator("object.shell_reset_props", text="Reset to Defaults", icon='LOOP_BACK')
        
        # Create button
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.5
        op = row.operator("object.create_offset_shell", icon='CUBE')
        
        # Debug info
        if prefs.show_debug_info:
            box = layout.box()
            box.label(text="Debug Info:", icon='INFO')
            col = box.column()
            col.label(text=f"Object: {obj.name}")
            col.label(text=f"Verts: {len(obj.data.vertices)}")
            # Get addon version from bl_info
            # We can't access bl_info directly here, but the version can be accessed
            # through the addon preferences if needed
            if obj and obj.type == 'MESH':
                try:
                    vertex_count = len(obj.data.vertices)
                    face_count = len(obj.data.polygons)
                    
                    from mathutils import Vector
                    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
                    min_x = min(corner.x for corner in bbox_corners)
                    max_x = max(corner.x for corner in bbox_corners)
                    min_y = min(corner.y for corner in bbox_corners)
                    max_y = max(corner.y for corner in bbox_corners)
                    min_z = min(corner.z for corner in bbox_corners)
                    max_z = max(corner.z for corner in bbox_corners)
                    
                    diagonal = ((max_x - min_x)**2 + (max_y - min_y)**2 + (max_z - min_z)**2)**0.5
                    
                    col.label(text=f"Dimensions: {max_x-min_x:.1f} x {max_y-min_y:.1f} x {max_z-min_z:.1f}")
                    col.label(text=f"Diagonal: {diagonal:.1f}")
                    col.label(text=f"Faces: {face_count}")
                    
                    # Show the actual auto calculation formula for debugging
                    sample_size = calculate_optimal_voxel_size(obj, props.detail_level, unit_scale=1.0)
                    col.label(text=f"Auto voxel calc: {sample_size:.4f}")
                except:
                    pass
