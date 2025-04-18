bl_info = {
    "name": "Shell Generator",
    "author": "Ruakij",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),  # Updated for compatibility with current Blender versions
    "location": "View3D > Sidebar > ShellGen",
    "description": "Generate a shell with offset/thickness for the selected mesh, optionally open at Z=0",
    "warning": "",
    "doc_url": "https://github.com/ruakij/blender-shell-generator",
    "category": "Object",
    "support": "COMMUNITY"
}

import bpy
from bpy.props import FloatProperty, BoolProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup, Operator, Panel, AddonPreferences
import math
from mathutils import Vector

# Standalone function for calculating optimal voxel size
def calculate_optimal_voxel_size(obj, detail_level=1.0, unit_scale=1.0):
    """
    Calculate optimal voxel size based on object complexity and dimensions
    
    Args:
        obj: The blender object to analyze
        detail_level: User-configurable multiplier (higher = less detail, larger voxels)
        unit_scale: Scale to convert from Blender units to display units
        
    Returns:
        float: Optimal voxel size in current units
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
    
    # Calculate voxel size
    voxel_size = diagonal_length * base_voxel_percent * detail_level
    
    # Enforce reasonable limits (limits in Blender Units, will be scaled based on unit system)
    min_size = 0.1
    max_size = 5.0 * detail_level
    voxel_size = max(min_size, min(voxel_size, max_size))
    
    return voxel_size  # Return size in current units

class ShellGenAddonPreferences(AddonPreferences):
    bl_idname = __name__

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
        layout = self.layout
        
        box = layout.box()
        box.label(text="Default Settings:")
        col = box.column(align=True)
        col.prop(self, "default_offset")
        col.prop(self, "default_thickness")
        
        box = layout.box()
        box.label(text="Advanced Options:")
        col = box.column()
        col.prop(self, "show_debug_info")
        col.prop(self, "keep_modifiers")
        
        box = layout.box()
        box.label(text="Documentation & Support:")
        col = box.column()
        col.operator("wm.url_open", text="GitHub Repository").url = "https://github.com/ruakij/blender-shell-generator"
        col.operator("wm.url_open", text="Report Issues").url = "https://github.com/ruakij/blender-shell-generator/issues"

class ShellGenProperties(PropertyGroup):
    offset: FloatProperty(
        name="Offset",
        description="Gap between object and start of shell",
        default=10.0,
        min=0.001,
        soft_max=100.0,
        subtype='DISTANCE',  # This tells Blender to treat it as a distance
        unit='LENGTH'  # This makes Blender handle unit display
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
        description="Use faster calculations with remesh (sacrifices some precision for speed)",
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

class OBJECT_OT_create_shell(Operator):
    bl_idname = "object.create_offset_shell"
    bl_label = "Create Shell"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Only enable the operator if there's a valid mesh object selected
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'
        
    def execute(self, context):
        try:
            props = context.scene.shellgen_props
            offset = props.offset
            thickness = props.thickness
            open_bottom = props.open_bottom
            fast_mode = props.fast_mode
            auto_voxel = props.auto_voxel_size
            remesh_voxel = props.remesh_voxel_size
            
            # Get addon preferences for keep_modifiers option
            prefs = context.preferences.addons[__name__].preferences
            keep_modifiers = prefs.keep_modifiers
            
            # Handle unit conversion properly
            unit_settings = context.scene.unit_settings
            # Factor to convert from display units to Blender Units
            # If unit_scale is 0.001, then 1 BU = 1 mm (no conversion needed)
            # If unit_scale is 1.0, then 1 BU = 1 m, so we need to divide by 1000 for mm
            unit_to_bu = 1.0 if unit_settings.system == 'NONE' else (0.001 / unit_settings.scale_length)
            
            # Convert input values to Blender Units
            offset_bu = offset * unit_to_bu
            thickness_bu = thickness * unit_to_bu
            
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Active object must be a mesh.")
                return {'CANCELLED'}
            
            # Calculate automatic voxel size if enabled
            if auto_voxel:
                # Use the standalone function instead of a class method
                remesh_voxel = calculate_optimal_voxel_size(
                    obj, 
                    detail_level=props.detail_level,
                    unit_scale=1.0 if unit_settings.system == 'NONE' else unit_settings.scale_length
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
                
                self.report({'INFO'}, f"Auto voxel size: {remesh_voxel:.3f}{unit_suffix}")
                
            remesh_voxel_bu = remesh_voxel * unit_to_bu
            
            # Debug info about unit conversion
            if prefs.show_debug_info:
                self.report({'INFO'}, f"Unit scale: {unit_settings.scale_length}, System: {unit_settings.system}")
                self.report({'INFO'}, f"Conversion factor (unit to BU): {unit_to_bu}")
                self.report({'INFO'}, f"Offset: {offset} → {offset_bu} BU")
                self.report({'INFO'}, f"Thickness: {thickness} → {thickness_bu} BU")
                self.report({'INFO'}, f"Remesh voxel size: {remesh_voxel} → {remesh_voxel_bu} BU")
            
            # Calculate total steps and step percentage
            total_steps = 9  # increased due to re-added cavity boolean
            step_percent = 100 / total_steps
            current_step = 0

            obj = context.active_object
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "Active object must be a mesh.")
                return {'CANCELLED'}
                
            # Store original selection and active object to restore later
            original_selected = [o for o in context.selected_objects]
            original_active = context.active_object
            
            # Helper function for applying modifiers
            def apply_modifier_if_needed(obj, modifier):
                if keep_modifiers:
                    self.report({'INFO'}, f"Keeping modifier '{modifier.name}' visible (debug mode)")
                    return
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.modifier_apply(modifier=modifier.name)

            # Prepare proxy object if requested
            mesh_objs = [o for o in context.selected_objects if o.type == 'MESH']
            proxy_obj = None
            if props.combine_selected_for_proxy and len(mesh_objs) > 0:
                # Duplicate and join the filtered meshes
                bpy.ops.object.select_all(action='DESELECT')
                for o in mesh_objs:
                    o.select_set(True)
                bpy.ops.object.duplicate()
                bpy.ops.object.join()
                proxy = context.active_object
                proxy.name = obj.name + "_proxy"
                # Remesh proxy to fuse internal geometry
                rem = proxy.modifiers.new("Proxy_Remesh", 'REMESH')
                rem.mode = 'VOXEL'
                rem.voxel_size = remesh_voxel_bu
                apply_modifier_if_needed(proxy, rem)
                proxy_obj = proxy

            # Step 1
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Duplicating object...")
            
            # Make sure we're in object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Duplicate object to create mold with proper link to scene
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.duplicate()
            mold = context.active_object
            mold.name = obj.name + "_mold"
            # Apply scale to ensure correct thickness calculations
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            # Step 2
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Adding offset shell (Solidify)...")
            solid_mod = mold.modifiers.new("Solidify_Offset", 'SOLIDIFY')
            solid_mod.thickness = offset_bu  # Use converted value
            solid_mod.offset = 1  # Push outward
            solid_mod.use_rim = False  # Turn off rim fill for the mold
            solid_mod.use_even_offset = props.even_thickness  # User option for even thickness
            apply_modifier_if_needed(mold, solid_mod)

            # Step 3
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Cleaning up mesh with remesh...")
            remesh_mod = mold.modifiers.new("Remesh_Cleanup", 'REMESH')
            remesh_mod.mode = 'VOXEL'
            remesh_mod.voxel_size = remesh_voxel_bu
            apply_modifier_if_needed(mold, remesh_mod)  # now respects keep_modifiers

            # Step 4
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Creating outer shell and thickness...")
            
            # Duplicate the mold to create shell
            bpy.ops.object.select_all(action='DESELECT')
            mold.select_set(True)
            context.view_layer.objects.active = mold
            bpy.ops.object.duplicate()
            shell = context.active_object
            shell.name = obj.name + "_shell"

            # Step 5
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Adding thickness to outer shell...")
            shell_mod = shell.modifiers.new("Solidify_Shell", 'SOLIDIFY')
            shell_mod.thickness = thickness_bu  # Use converted value
            shell_mod.offset = 1  # Push outward
            shell_mod.use_even_offset = props.even_thickness  # User option for even thickness
            apply_modifier_if_needed(shell, shell_mod)
            
            # Step 6 - Boolean operation with ground if open_bottom is enabled
            current_step += 1
            progress = int(current_step * step_percent)
            if open_bottom:
                self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Cutting open bottom at Z=0...")
                # Create large cutter cube
                bpy.ops.mesh.primitive_cube_add(size=1500, location=(0, 0, -750 + 0.001))
                cutter = context.active_object
                cutter.name = "ground_cutter"
                cutter.display_type = 'WIRE'  # Make it wireframe for visibility
            
                # Apply boolean to shell with improved settings
                context.view_layer.objects.active = shell
                bool_mod_shell = shell.modifiers.new("Cut_Open_Bottom", 'BOOLEAN')
                bool_mod_shell.operation = 'DIFFERENCE'
                if fast_mode:
                    bool_mod_shell.solver = 'FAST'
                    bool_mod_shell.use_self = True  # Helps avoid self-intersection issues
                else:
                    bool_mod_shell.solver = 'EXACT'
                    bool_mod_shell.use_self = True
                bool_mod_shell.object = cutter
                apply_modifier_if_needed(shell, bool_mod_shell)
            
                # Also cut the mold bottom with the same ground cutter
                context.view_layer.objects.active = mold
                bool_mod_mold = mold.modifiers.new("Mold_Ground_Cut", 'BOOLEAN')
                bool_mod_mold.operation = 'DIFFERENCE'
                bool_mod_mold.solver = 'FAST' if fast_mode else 'EXACT'
                bool_mod_mold.use_self = True
                bool_mod_mold.object = cutter
                apply_modifier_if_needed(mold, bool_mod_mold)
            
                # Remove cutter if not keeping modifiers
                if not keep_modifiers:
                    cutter.hide_set(True)
                    bpy.data.objects.remove(cutter, do_unlink=True)
            else:
                self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Skipping bottom cut (closed shell)...")

            # Now add Cavity_Boolean to mold only (after shell is created)
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Creating mold cavity (boolean with original or proxy)...")
            cav_target = proxy_obj if proxy_obj else obj
            bpy.context.view_layer.objects.active = mold
            cav_mod = mold.modifiers.new("Cavity_Boolean", 'BOOLEAN')
            cav_mod.operation = 'DIFFERENCE'
            cav_mod.solver = 'FAST' if fast_mode else 'EXACT'
            cav_mod.use_self = True
            cav_mod.object = cav_target
            apply_modifier_if_needed(mold, cav_mod)
            # Remove proxy when done, unless keep_modifiers is True
            if proxy_obj and not keep_modifiers:
                bpy.data.objects.remove(proxy_obj, do_unlink=True)

            # Step 6 - Boolean operation with ground if open_bottom is enabled
            current_step += 1
            progress = int(current_step * step_percent)
            if open_bottom:
                self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Cutting open bottom at Z=0...")
                # Create large cutter cube
                bpy.ops.mesh.primitive_cube_add(size=1500, location=(0, 0, -750 + 0.001))
                cutter = context.active_object
                cutter.name = "ground_cutter"
                cutter.display_type = 'WIRE'  # Make it wireframe for visibility
                
                # Apply boolean to shell with improved settings
                context.view_layer.objects.active = shell
                bool_mod_shell = shell.modifiers.new("Cut_Open_Bottom", 'BOOLEAN')
                bool_mod_shell.operation = 'DIFFERENCE'
                if fast_mode:
                    bool_mod_shell.solver = 'FAST'
                    bool_mod_shell.use_self = True  # Helps avoid self-intersection issues
                else:
                    bool_mod_shell.solver = 'EXACT'
                    bool_mod_shell.use_self = True
                bool_mod_shell.object = cutter
                apply_modifier_if_needed(shell, bool_mod_shell)
                
                # Also cut the mold bottom with the same ground cutter
                context.view_layer.objects.active = mold
                bool_mod_mold = mold.modifiers.new("Mold_Ground_Cut", 'BOOLEAN')
                bool_mod_mold.operation = 'DIFFERENCE'
                bool_mod_mold.solver = 'FAST' if fast_mode else 'EXACT'
                bool_mod_mold.use_self = True
                bool_mod_mold.object = cutter
                apply_modifier_if_needed(mold, bool_mod_mold)
            else:
                self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Skipping bottom cut (closed shell)...")

            # Step 7 - Cleanup and finalize
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Finalizing and cleaning up...")
            
            # Remove ground cutter if it exists and we're not keeping modifiers
            # (if we're keeping modifiers we need to keep the cutter object)
            cutter = bpy.data.objects.get("ground_cutter")
            if cutter and not keep_modifiers:
                cutter.hide_set(True)  # Hide it instead of deleting if keeping modifiers
                if not keep_modifiers:
                    bpy.data.objects.remove(cutter, do_unlink=True)
                
            # Setup 3D print toolbox compatibility
            for o in [mold, shell]:
                if o.get('print3d_volume') is None:
                    o['print3d_volume'] = 0
            
            # Select both the shell and mold
            try:
                for o in context.selected_objects:
                    o.select_set(False)
                mold.select_set(True)
                shell.select_set(True)
                context.view_layer.objects.active = shell
                
                self.report({'INFO'}, f"[100%] Shell generation completed!")
                if keep_modifiers:
                    self.report({'INFO'}, "Modifiers kept visible for debugging.")
                self.report({'INFO'}, "Use the 3D Print Toolbox to calculate volume.")
            except ReferenceError:
                # In case objects were removed
                self.report({'WARNING'}, "Some objects may have been removed during processing")
                
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error during execution: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

class OBJECT_OT_shell_reset_props(Operator):
    bl_idname = "object.shell_reset_props"
    bl_label = "Reset Shell Generator Properties"
    bl_description = "Reset all shell generator properties to default values"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        props = context.scene.shellgen_props
        
        # Reset to addon preference defaults
        props.offset = prefs.default_offset
        props.thickness = prefs.default_thickness
        props.fast_mode = True
        props.remesh_voxel_size = 0.5
        props.open_bottom = True
        props.auto_voxel_size = True
        props.detail_level = 1.0
        
        self.report({'INFO'}, "Shell Generator properties reset to defaults")
        return {'FINISHED'}

# Menu integration for easier access
class VIEW3D_MT_shell_gen_menu(bpy.types.Menu):
    bl_label = "Shell Generator"
    bl_idname = "VIEW3D_MT_shell_gen_menu"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("object.create_offset_shell", icon='MOD_SOLIDIFY')
        layout.separator()
        layout.operator("object.shell_reset_props", icon='LOOP_BACK')

def draw_shell_gen_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.menu(VIEW3D_MT_shell_gen_menu.bl_idname, icon='MESH_CUBE')

class OBJECT_PT_shell_panel(Panel):
    bl_label = "Shell Generator"
    bl_idname = "OBJECT_PT_shell_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ShellGen"
    bl_context = "objectmode"  # Only show in object mode
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'  # Only display in object mode

    def draw(self, context):
        layout = self.layout
        props = context.scene.shellgen_props
        prefs = context.preferences.addons[__name__].preferences
        
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
                # Calculate sample voxel size for preview using the standalone function
                try:
                    unit_settings = context.scene.unit_settings
                    unit_scale = 1.0 if unit_settings.system == 'NONE' else unit_settings.scale_length
                    
                    # Use the standalone function instead of trying to instantiate the operator
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
                    
                    # Display only numeric voxel size without classification
                    sample_text = f"Est. Size: {sample_size:.3f}{unit_suffix}"
                    
                    sub_col.label(text=sample_text, icon='INFO')
                except Exception as e:
                    # Debug the calculation error
                    import traceback
                    error_trace = traceback.format_exc()
                    print(f"Auto voxel calculation error: {str(e)}\n{error_trace}")
                    sub_col.label(text=f"Est. Size: Using calculated value", icon='INFO')
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
            col.label(text=f"Addon Version: {'.'.join(map(str, bl_info['version']))}")
            if props.auto_voxel_size and obj and obj.type == 'MESH':
                try:
                    # Show more detailed metrics for debugging
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
                    
                    # Show the actual auto calculation formula for debugging using the standalone function
                    sample_size = calculate_optimal_voxel_size(obj, props.detail_level, unit_scale=1.0)
                    col.label(text=f"Auto voxel calc: {sample_size:.4f}")
                except:
                    pass

classes = (ShellGenAddonPreferences, ShellGenProperties, OBJECT_OT_create_shell, OBJECT_OT_shell_reset_props, VIEW3D_MT_shell_gen_menu, OBJECT_PT_shell_panel)

# Add-on keymap
addon_keymaps = []

def register():
    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)
        
    # Register properties
    bpy.types.Scene.shellgen_props = PointerProperty(type=ShellGenProperties)
    
    # Register menu
    bpy.types.VIEW3D_MT_object.append(draw_shell_gen_menu)
    
    # Handle the keymaps
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Create a keymap for object mode
        km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
        
        # Add shell generator shortcut (Ctrl+Alt+S)
        kmi = km.keymap_items.new(OBJECT_OT_create_shell.bl_idname, 'S', 'PRESS', ctrl=True, alt=True)
        addon_keymaps.append((km, kmi))

def unregister():
    # Clear keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Remove menu
    bpy.types.VIEW3D_MT_object.remove(draw_shell_gen_menu)
    
    # Unregister properties
    del bpy.types.Scene.shellgen_props
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
