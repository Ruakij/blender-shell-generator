"""UI components for the Shell Generator addon."""

import bpy
from bpy.types import Panel, Menu
from .utils import calculate_optimal_voxel_size, format_length


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
            col.label(text="Float solver for open or")
            col.label(text="self-intersecting meshes")
        
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
                sample_size = calculate_optimal_voxel_size(obj, detail_level=props.detail_level)
                col.label(text=f"Est. Size: {format_length(context, sample_size)}", icon='INFO')
        else:
            col.prop(props, "remesh_voxel_size")

        # Actions section at the bottom
        box = layout.box()
        box.label(text="Actions", icon='PLAY')
        row = box.row()
        row.scale_y = 2.0
        row.operator("object.create_offset_shell", icon='CUBE')
        box.operator("object.shell_reset_props", text="Reset Settings", icon='LOOP_BACK')
