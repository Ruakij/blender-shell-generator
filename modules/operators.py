"""Operator classes for the Shell Generator addon."""

import bpy
from bpy.types import Operator
from mathutils import Vector
from .utils import calculate_optimal_voxel_size, validate_mesh, ErrorHandler


class OBJECT_OT_create_shell(Operator):
    """Create a shell around the selected mesh object."""
    
    bl_idname = "object.create_offset_shell"
    bl_label = "Create Shell"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        """Only enable the operator if there's a valid mesh object selected."""
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'
        
    def execute(self, context):
        """Execute the shell creation operation."""
        try:
            # Initialize error handler
            error_handler = ErrorHandler()
            
            props = context.scene.shellgen_props
            offset = props.offset
            thickness = props.thickness
            open_bottom = props.open_bottom
            fast_mode = props.fast_mode
            auto_voxel = props.auto_voxel_size
            remesh_voxel = props.remesh_voxel_size
            
            # Get addon preferences for keep_modifiers option
            prefs = context.preferences.addons[__package__.split('.')[0]].preferences
            keep_modifiers = prefs.keep_modifiers
            
            # Handle unit conversion properly
            unit_settings = context.scene.unit_settings
            unit_to_bu = 1.0 if unit_settings.system == 'NONE' else (0.001 / unit_settings.scale_length)
            
            # Convert input values to Blender Units
            offset_bu = offset * unit_to_bu
            thickness_bu = thickness * unit_to_bu
            
            obj = context.active_object
            try:
                validate_mesh(obj)
            except ValueError as e:
                self.report({'ERROR'}, str(e))
                return {'CANCELLED'}
            
            # Calculate automatic voxel size if enabled
            if auto_voxel:
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
                
            # Store original selection and active object to restore later
            original_selected = [o for o in context.selected_objects]
            original_active = context.active_object
            
            # Helper function for applying modifiers
            def apply_modifier_if_needed(obj, modifier):
                if keep_modifiers:
                    self.report({'INFO'}, f"Keeping modifier '{modifier.name}' visible (debug mode)")
                    return
                context.view_layer.objects.active = obj
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
            solid_mod.thickness = offset_bu
            solid_mod.offset = 1  # Push outward
            solid_mod.use_rim = False  # Turn off rim fill for the mold
            solid_mod.use_even_offset = props.even_thickness
            apply_modifier_if_needed(mold, solid_mod)

            # Step 3
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Cleaning up mesh with remesh...")
            remesh_mod = mold.modifiers.new("Remesh_Cleanup", 'REMESH')
            remesh_mod.mode = 'VOXEL'
            remesh_mod.voxel_size = remesh_voxel_bu
            apply_modifier_if_needed(mold, remesh_mod)

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
            shell_mod.thickness = thickness_bu
            shell_mod.offset = 1  # Push outward
            shell_mod.use_even_offset = props.even_thickness
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
                    bool_mod_shell.use_self = True
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

            # Now add Cavity_Boolean to mold only (after shell is created)
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Creating mold cavity (boolean with original or proxy)...")
            cav_target = proxy_obj if proxy_obj else obj
            context.view_layer.objects.active = mold
            cav_mod = mold.modifiers.new("Cavity_Boolean", 'BOOLEAN')
            cav_mod.operation = 'DIFFERENCE'
            cav_mod.solver = 'FAST' if fast_mode else 'EXACT'
            cav_mod.use_self = True
            cav_mod.object = cav_target
            apply_modifier_if_needed(mold, cav_mod)
            # Remove proxy when done, unless keep_modifiers is True
            if proxy_obj and not keep_modifiers:
                bpy.data.objects.remove(proxy_obj, do_unlink=True)

            # Step 8 - Cleanup and finalize
            current_step += 1
            progress = int(current_step * step_percent)
            self.report({'INFO'}, f"[{progress}%] Step {current_step}/{total_steps}: Finalizing and cleaning up...")
            
            # Remove ground cutter if it exists and we're not keeping modifiers
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
    """Reset all shell generator properties to default values."""
    
    bl_idname = "object.shell_reset_props"
    bl_label = "Reset Shell Generator Properties"
    bl_description = "Reset all shell generator properties to default values"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the property reset operation."""
        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
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
