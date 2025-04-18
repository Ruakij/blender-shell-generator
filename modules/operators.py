"""Operator classes for the Shell Generator addon."""

import bpy
from bpy.types import Operator
from mathutils import Vector
from .utils import calculate_optimal_voxel_size, validate_mesh, ErrorHandler
from .core import (
    prepare_object_for_shell,
    create_cutter_object,
    setup_solidify_modifier,
    setup_remesh_modifier,
    setup_boolean_modifier,
    cleanup_objects,
    setup_3d_print_toolbox,
    get_unit_settings
)

class OBJECT_OT_create_shell(Operator):
    """Create a shell around the selected mesh object."""
    
    bl_idname = "object.create_offset_shell"
    bl_label = "Create Shell"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Timer for modal execution
    _timer = None
    # Current step in the process
    _step = 0
    # Store temporary objects and data
    _temp_data = {}
    # Operation steps
    _steps = []
    # Error handler
    _error_handler = None
    
    @classmethod
    def poll(cls, context):
        """Only enable the operator if there's a valid mesh object selected."""
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def initialize_steps(self, context):
        """Initialize the operation steps."""
        props = context.scene.shellgen_props
        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
        
        # Get unit settings
        unit_to_bu, unit_suffix = get_unit_settings(context)
        
        # Convert input values to Blender Units
        offset_bu = props.offset * unit_to_bu
        thickness_bu = props.thickness * unit_to_bu
        remesh_voxel = props.remesh_voxel_size
        
        if props.auto_voxel_size:
            remesh_voxel = calculate_optimal_voxel_size(
                context.active_object,
                detail_level=props.detail_level,
                unit_scale=1.0 if context.scene.unit_settings.system == 'NONE' else context.scene.unit_settings.scale_length
            )
        remesh_voxel_bu = remesh_voxel * unit_to_bu
        
        # Store settings in temp data
        self._temp_data.update({
            'offset_bu': offset_bu,
            'thickness_bu': thickness_bu,
            'remesh_voxel_bu': remesh_voxel_bu,
            'keep_modifiers': prefs.keep_modifiers,
            'show_debug': prefs.show_debug_info,
            'fast_mode': props.fast_mode,
            'open_bottom': props.open_bottom,
            'even_thickness': props.even_thickness,
            'combine_selected': props.combine_selected_for_proxy,
            'selected_objects': [obj for obj in context.selected_objects if obj.type == 'MESH'],
            'active_object': context.active_object
        })
        
        # Define operation steps
        self._steps = [
            ('PREPARE', "Preparing object...", self.step_prepare),
            ('DUPLICATE', "Creating base geometry...", self.step_duplicate),
            ('SOLIDIFY', "Adding initial shell...", self.step_add_solidify),
            ('REMESH', "Optimizing mesh...", self.step_remesh),
            ('CREATE_SHELL', "Creating outer shell...", self.step_create_shell),
            ('SHELL_THICKNESS', "Adding shell thickness...", self.step_add_shell_thickness),
            ('OPEN_BOTTOM', "Processing bottom cut..." if props.open_bottom else None, self.step_process_bottom),
            ('CAVITY', "Creating mold cavity...", self.step_create_cavity),
            ('CLEANUP', "Finalizing...", self.step_cleanup)
        ]
        
        # Filter out None steps
        self._steps = [(id, msg, func) for id, msg, func in self._steps if msg is not None]
    
    def modal(self, context, event):
        """Handle modal execution of the shell generation process."""
        if event.type == 'TIMER':
            # Check if we have more steps to process
            if self._step < len(self._steps):
                try:
                    # Get current step info
                    step_id, message, step_func = self._steps[self._step]
                    
                    # Update progress
                    progress = int((self._step / len(self._steps)) * 100)
                    context.window_manager.progress_update(progress)
                    self.report({'INFO'}, f"[{progress}%] {message}")
                    
                    # Execute step
                    if not step_func(context):
                        self.report({'ERROR'}, "Operation failed")
                        self.cleanup_and_finish(context)
                        return {'CANCELLED'}
                    
                    # Move to next step
                    self._step += 1
                    return {'RUNNING_MODAL'}
                    
                except Exception as e:
                    self.report({'ERROR'}, f"Error during {step_id}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    self.cleanup_and_finish(context)
                    return {'CANCELLED'}
            else:
                # All steps complete
                self.cleanup_and_finish(context)
                self.report({'INFO'}, "Shell generation completed!")
                return {'FINISHED'}
                
        return {'PASS_THROUGH'}
    
    def invoke(self, context, event):
        """Start the modal execution."""
        try:
            # Initialize error handler
            self._error_handler = ErrorHandler()
            
            # Validate input object
            obj = context.active_object
            validate_mesh(obj)
            
            # Initialize operation steps
            self.initialize_steps(context)
            
            # Start progress indicator
            context.window_manager.progress_begin(0, 100)
            
            # Add timer for modal execution
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.1, window=context.window)
            wm.modal_handler_add(self)
            
            return {'RUNNING_MODAL'}
            
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
    
    def step_prepare(self, context):
        """Step 1: Prepare the object for shell generation."""
        obj = context.active_object
        return prepare_object_for_shell(obj)
    
    def step_duplicate(self, context):
        """Step 2: Duplicate the object to create mold."""
        try:
            obj = context.active_object
            proxy_obj = None
            
            # Handle proxy object if requested
            if self._temp_data['combine_selected'] and len(self._temp_data['selected_objects']) > 0:
                # Deselect all objects first
                bpy.ops.object.select_all(action='DESELECT')
                
                # Select and duplicate all mesh objects
                for o in self._temp_data['selected_objects']:
                    o.select_set(True)
                context.view_layer.objects.active = self._temp_data['active_object']
                
                # Duplicate selected objects
                bpy.ops.object.duplicate()
                
                # Join duplicated objects
                if len(context.selected_objects) > 1:
                    bpy.ops.object.join()
                
                proxy_obj = context.active_object
                proxy_obj.name = obj.name + "_proxy"
                
                # Remesh proxy to fuse internal geometry
                rem = proxy_obj.modifiers.new("Proxy_Remesh", 'REMESH')
                rem.mode = 'VOXEL'
                rem.voxel_size = self._temp_data['remesh_voxel_bu']
                
                if not self._temp_data['keep_modifiers']:
                    context.view_layer.objects.active = proxy_obj
                    bpy.ops.object.modifier_apply(modifier=rem.name)
                
                self._temp_data['proxy'] = proxy_obj
                obj = proxy_obj
            
            # Ensure we're in object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Duplicate object
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.duplicate()
            
            mold = context.active_object
            mold.name = self._temp_data['active_object'].name + "_mold"
            
            # Store for later use
            self._temp_data['mold'] = mold
            self._temp_data['original'] = self._temp_data['active_object']
            
            return True
        except Exception as e:
            self._error_handler.add_error(f"Duplication failed: {str(e)}")
            return False
    
    def step_add_solidify(self, context):
        """Step 3: Add initial solidify modifier for offset."""
        try:
            mold = self._temp_data['mold']
            
            solid_mod = setup_solidify_modifier(
                mold,
                self._temp_data['offset_bu'],
                offset=1,
                use_rim=False,
                use_even_offset=self._temp_data['even_thickness']
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = mold
                bpy.ops.object.modifier_apply(modifier=solid_mod.name)
            
            return True
        except Exception as e:
            self._error_handler.add_error(f"Solidify modifier failed: {str(e)}")
            return False
    
    def step_remesh(self, context):
        """Step 4: Add remesh modifier for cleanup."""
        try:
            mold = self._temp_data['mold']
            
            remesh_mod = setup_remesh_modifier(
                mold,
                self._temp_data['remesh_voxel_bu']
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = mold
                bpy.ops.object.modifier_apply(modifier=remesh_mod.name)
            
            return True
        except Exception as e:
            self._error_handler.add_error(f"Remesh failed: {str(e)}")
            return False
    
    def step_create_shell(self, context):
        """Step 5: Create the outer shell object."""
        try:
            mold = self._temp_data['mold']
            
            # Duplicate mold to create shell
            bpy.ops.object.select_all(action='DESELECT')
            mold.select_set(True)
            context.view_layer.objects.active = mold
            bpy.ops.object.duplicate()
            
            shell = context.active_object
            shell.name = self._temp_data['original'].name + "_shell"
            
            # Store for later use
            self._temp_data['shell'] = shell
            
            return True
        except Exception as e:
            self._error_handler.add_error(f"Shell creation failed: {str(e)}")
            return False
    
    def step_add_shell_thickness(self, context):
        """Step 6: Add thickness to the shell."""
        try:
            shell = self._temp_data['shell']
            
            shell_mod = setup_solidify_modifier(
                shell,
                self._temp_data['thickness_bu'],
                offset=1,
                use_even_offset=self._temp_data['even_thickness']
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = shell
                bpy.ops.object.modifier_apply(modifier=shell_mod.name)
            
            return True
        except Exception as e:
            self._error_handler.add_error(f"Shell thickness failed: {str(e)}")
            return False
    
    def step_process_bottom(self, context):
        """Step 7: Process open bottom if enabled."""
        if not self._temp_data['open_bottom']:
            return True
            
        try:
            shell = self._temp_data['shell']
            mold = self._temp_data['mold']
            
            # Create cutter
            cutter = create_cutter_object()
            self._temp_data['cutter'] = cutter
            
            # Cut shell bottom
            bool_mod_shell = setup_boolean_modifier(
                shell,
                operation='DIFFERENCE',
                solver='FAST' if self._temp_data['fast_mode'] else 'EXACT',
                target=cutter
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = shell
                bpy.ops.object.modifier_apply(modifier=bool_mod_shell.name)
            
            # Cut mold bottom
            bool_mod_mold = setup_boolean_modifier(
                mold,
                operation='DIFFERENCE',
                solver='FAST' if self._temp_data['fast_mode'] else 'EXACT',
                target=cutter
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = mold
                bpy.ops.object.modifier_apply(modifier=bool_mod_mold.name)
            
            return True
        except Exception as e:
            self._error_handler.add_error(f"Bottom processing failed: {str(e)}")
            return False
    
    def step_create_cavity(self, context):
        """Step 8: Create the mold cavity."""
        try:
            mold = self._temp_data['mold']
            
            # Use proxy or original object for cavity
            cavity_target = self._temp_data.get('proxy', self._temp_data['original'])
            
            cav_mod = setup_boolean_modifier(
                mold,
                operation='DIFFERENCE',
                solver='FAST' if self._temp_data['fast_mode'] else 'EXACT',
                target=cavity_target
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = mold
                bpy.ops.object.modifier_apply(modifier=cav_mod.name)
            
            return True
        except Exception as e:
            self._error_handler.add_error(f"Cavity creation failed: {str(e)}")
            return False
    
    def step_cleanup(self, context):
        """Step 9: Final cleanup and object setup."""
        try:
            # Clean up temporary objects
            if not self._temp_data['keep_modifiers']:
                cleanup_objects([
                    self._temp_data.get('cutter'),
                    self._temp_data.get('proxy')
                ])
            
            # Setup 3D print toolbox compatibility
            for obj in [self._temp_data['mold'], self._temp_data['shell']]:
                setup_3d_print_toolbox(obj)
            
            # Select shell and mold
            bpy.ops.object.select_all(action='DESELECT')
            self._temp_data['mold'].select_set(True)
            self._temp_data['shell'].select_set(True)
            context.view_layer.objects.active = self._temp_data['shell']
            
            return True
        except Exception as e:
            self._error_handler.add_error(f"Cleanup failed: {str(e)}")
            return False
    
    def cleanup_and_finish(self, context):
        """Clean up the operator state."""
        context.window_manager.progress_end()
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            
        # Clear temporary data
        self._temp_data.clear()
        self._step = 0
        self._steps.clear()


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
