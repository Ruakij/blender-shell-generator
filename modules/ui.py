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

    def draw_header(self, context):
        """Draw the header with icon."""
        self.layout.label(text="", icon='MESH_CUBE')

    def draw(self, context):
        """Draw the panel."""
        layout = self.layout
        props = context.scene.shellgen_props
        
        # Check if there's a valid mesh object selected
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            col = layout.column()
            col.label(text="No mesh selected", icon='ERROR')
            col.label(text="Please select a mesh object")
            return

        # Basic Settings
        box = layout.box()
        box.label(text="Basic Settings", icon='PREFERENCES')
        col = box.column(align=True)
        col.prop(props, "offset")
        col.prop(props, "thickness")
        col.separator()
        col.prop(props, "open_bottom")

        # Advanced Settings
        box = layout.box()
        box.label(text="Advanced Settings", icon='SETTINGS')
        
        # Misc Settings
        box_inner = box.box()
        box_inner.label(text="Misc")
        col = box_inner.column()
        col.prop(props, "combine_selected_for_proxy")
        col.prop(props, "even_thickness")
        if props.even_thickness:
            col.label(text="Warning: May create artifacts", icon='ERROR')
        
        # Performance Settings
        box_inner = box.box()
        box_inner.label(text="Performance", icon='MOD_REMESH')
        col = box_inner.column()
        
        # Fast Mode
        col.prop(props, "fast_mode")
        if props.fast_mode:
            col.label(text="Uses faster boolean solver")
            col.label(text="and simpler remesh settings")
        
        # Mesh Resolution section
        box_inner = box.box()
        box_inner.label(text="Mesh Resolution")
        col = box_inner.column()
        
        # Auto Voxel Size
        col.prop(props, "auto_voxel_size")
        
        if props.auto_voxel_size:
            col.prop(props, "detail_level", slider=True)
            
            # Show estimated voxel size
            obj = context.active_object
            if obj and obj.type == 'MESH':
                try:
                    unit_settings = context.scene.unit_settings
                    unit_scale = 1.0 if unit_settings.system == 'NONE' else unit_settings.scale_length
                    
                    sample_size = calculate_optimal_voxel_size(
                        obj,
                        detail_level=props.detail_level,
                        unit_scale=unit_scale
                    )
                    
                    # Get appropriate unit suffix
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
                    col.label(text=sample_text, icon='INFO')
                except:
                    col.label(text="Est. Size: Using calculated value", icon='INFO')
        else:
            col.prop(props, "remesh_voxel_size")

        # Actions section at the bottom
        box = layout.box()
        box.label(text="Actions", icon='PLAY')
        row = box.row()
        row.scale_y = 2.0
        op = row.operator("object.create_offset_shell", icon='CUBE')
