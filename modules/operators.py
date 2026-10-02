"""Operator classes for the Shell Generator addon."""

import bpy
from bpy.types import Operator
from mathutils import Matrix
from .. import ADDON_ID
from .utils import format_length, remesh_voxel_size, source_objects, validate_mesh
from .core import (
    prepare_object_for_shell,
    create_cutter_object,
    evaluated_mesh,
    setup_solidify_modifier,
    setup_remesh_modifier,
    setup_boolean_modifier,
    mesh_defects,
    cleanup_objects,
    setup_3d_print_toolbox,
)

class OBJECT_OT_create_shell(Operator):
    """Create a shell around the selected mesh object."""
    
    bl_idname = "object.create_offset_shell"
    bl_label = "Create Shell"
    bl_options = {'REGISTER', 'UNDO'}

    # Class-level, so poll can block a second run while one is active
    _running = False
    
    @classmethod
    def poll(cls, context):
        """Only enable the operator if there's a valid mesh object selected and no run is active."""
        if cls._running:
            cls.poll_message_set("A shell is being generated")
            return False
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def initialize_steps(self, context):
        """Capture the settings and source objects of this run and initialize its steps."""
        props = context.scene.shellgen_props
        prefs = context.preferences.addons[ADDON_ID].preferences
        
        # Length properties are stored in Blender Units
        remesh_voxel_bu, _, bound, raised = remesh_voxel_size(context)
        if raised and remesh_voxel_bu > bound:
            self.report({'WARNING'}, f"Voxel size raised to {format_length(context, remesh_voxel_bu)} "
                                     "by Max Voxels per Axis, above half the offset")

        sources = source_objects(context)
        self._timer = None
        self._step = 0
        self._errors = []
        # Every object this run adds, removed again if it fails
        self._created = []
        self._temp_data = {
            'offset_bu': props.offset,
            'thickness_bu': props.thickness,
            'remesh_voxel_bu': remesh_voxel_bu,
            'keep_modifiers': prefs.keep_modifiers,
            'fast_mode': props.fast_mode,
            'open_bottom': props.open_bottom,
            'even_thickness': props.even_thickness,
            'combine_selected': props.combine_selected_for_proxy and any(o.type == 'MESH' for o in context.selected_objects),
            'sources': sources,
            'original': context.active_object,
        }
        
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

    def add_object(self, obj):
        """Link obj next to the original and record it as created by this run."""
        for coll in self._temp_data['original'].users_collection:
            coll.objects.link(obj)
        self._created.append(obj)
        return obj
    
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
                        self.report({'ERROR'}, self._errors[-1] if self._errors else "Operation failed")
                        self.cleanup_and_finish(context, success=False)
                        return {'CANCELLED'}
                    
                    # Move to next step
                    self._step += 1
                    return {'RUNNING_MODAL'}
                    
                except Exception as e:
                    self.report({'ERROR'}, f"Error during {step_id}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    self.cleanup_and_finish(context, success=False)
                    return {'CANCELLED'}
            else:
                # All steps complete
                self.cleanup_and_finish(context, success=True)
                self.report({'INFO'}, "Shell generation completed!")
                return {'FINISHED'}
                
        return {'PASS_THROUGH'}
    
    def invoke(self, context, event):
        """Start the modal execution."""
        try:
            validate_mesh(context.active_object)
            self.initialize_steps(context)
            
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.1, window=context.window)
            wm.modal_handler_add(self)
            wm.progress_begin(0, 100)
            OBJECT_OT_create_shell._running = True
            return {'RUNNING_MODAL'}
            
        except Exception as e:
            if getattr(self, '_timer', None):
                context.window_manager.event_timer_remove(self._timer)
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def cancel(self, context):
        """Called when Blender ends the modal run, e.g. on loading a file."""
        self.cleanup_and_finish(context, success=False)
    
    def step_prepare(self, context):
        """Step 1: Prepare the object for shell generation."""
        return prepare_object_for_shell(self._temp_data['original'])
    
    def step_duplicate(self, context):
        """Step 2: Build the mold from the source meshes as the viewport shows them."""
        try:
            d = self._temp_data
            original = d['original']
            # Scale goes into the mesh; location and rotation stay on the object
            matrix = original.matrix_world.copy()
            if matrix.is_negative:
                # Unmirror the axis the object scale mirrors, else decompose() turns it into a rotation
                axis = next((i for i in range(3) if original.scale[i] < 0), 0)
                matrix.col[axis] = -matrix.col[axis]
            loc, rot, _ = matrix.decompose()
            frame = Matrix.LocRotScale(loc, rot, None)
            mesh = evaluated_mesh(d['sources'], context.evaluated_depsgraph_get(), frame, original.name)

            if d['combine_selected']:
                base = self.add_object(bpy.data.objects.new(original.name + "_proxy", mesh))
                base.matrix_world = frame
                # Remesh proxy to fuse internal geometry
                rem = base.modifiers.new("Proxy_Remesh", 'REMESH')
                rem.mode = 'VOXEL'
                rem.voxel_size = d['remesh_voxel_bu']
                if not d['keep_modifiers']:
                    context.view_layer.objects.active = base
                    bpy.ops.object.modifier_apply(modifier=rem.name)
                d['proxy'] = base
                mesh = evaluated_mesh([base], context.evaluated_depsgraph_get(), frame, original.name)
            else:
                # Cavity cutter: unlike the original its matrix never mirrors,
                # which the Manifold solver ignores and so flips the cavity
                base = self.add_object(bpy.data.objects.new(original.name + "_source", mesh))
                base.matrix_world = frame
                d['source'] = base
                mesh = mesh.copy()

            for mat in original.data.materials:
                mesh.materials.append(mat)
            mold = self.add_object(bpy.data.objects.new(original.name + "_mold", mesh))
            mold.matrix_world = frame
            d['mold'] = mold
            return True
        except Exception as e:
            self._errors.append(f"Duplication failed: {str(e)}")
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
            self._errors.append(f"Solidify modifier failed: {str(e)}")
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
            self._errors.append(f"Remesh failed: {str(e)}")
            return False
    
    def step_create_shell(self, context):
        """Step 5: Create the outer shell object."""
        try:
            mold = self._temp_data['mold']
            
            # A copy keeps the modifiers of the mold when they are not applied
            shell = mold.copy()
            shell.data = mold.data.copy()
            shell.name = self._temp_data['original'].name + "_shell"
            self.add_object(shell)
            
            # Store for later use
            self._temp_data['shell'] = shell
            
            return True
        except Exception as e:
            self._errors.append(f"Shell creation failed: {str(e)}")
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
            self._errors.append(f"Shell thickness failed: {str(e)}")
            return False
    
    def step_process_bottom(self, context):
        """Step 7: Process open bottom if enabled."""
        if not self._temp_data['open_bottom']:
            return True
            
        try:
            shell = self._temp_data['shell']
            mold = self._temp_data['mold']
            
            depsgraph = context.evaluated_depsgraph_get()
            cutter = self.add_object(create_cutter_object([o.evaluated_get(depsgraph) for o in (shell, mold)]))
            self._temp_data['cutter'] = cutter
            
            # Cut shell bottom
            bool_mod_shell = setup_boolean_modifier(
                shell,
                operation='DIFFERENCE',
                solver='MANIFOLD',  # both operands are closed by construction
                target=cutter
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = shell
                bpy.ops.object.modifier_apply(modifier=bool_mod_shell.name)
            
            # Cut mold bottom
            bool_mod_mold = setup_boolean_modifier(
                mold,
                operation='DIFFERENCE',
                solver='MANIFOLD',  # both operands are closed by construction
                target=cutter
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = mold
                bpy.ops.object.modifier_apply(modifier=bool_mod_mold.name)
            
            return True
        except Exception as e:
            self._errors.append(f"Bottom processing failed: {str(e)}")
            return False
    
    def step_create_cavity(self, context):
        """Step 8: Create the mold cavity."""
        try:
            mold = self._temp_data['mold']
            
            cavity_target = self._temp_data.get('proxy') or self._temp_data['source']
            
            # A remeshed proxy is always closed and free of self-intersections
            solver, use_self = 'MANIFOLD', False
            if 'proxy' not in self._temp_data:
                closed, self_intersecting = mesh_defects(cavity_target, context.evaluated_depsgraph_get())
                if not closed or self_intersecting:
                    solver = 'FLOAT' if self._temp_data['fast_mode'] else 'EXACT'
                    use_self = self_intersecting  # makes Exact many times slower, so only when needed

            cav_mod = setup_boolean_modifier(
                mold,
                operation='DIFFERENCE',
                solver=solver,
                target=cavity_target,
                use_self=use_self
            )
            
            if not self._temp_data['keep_modifiers']:
                context.view_layer.objects.active = mold
                bpy.ops.object.modifier_apply(modifier=cav_mod.name)
            
            return True
        except Exception as e:
            self._errors.append(f"Cavity creation failed: {str(e)}")
            return False
    
    def step_cleanup(self, context):
        """Step 9: Final cleanup and object setup."""
        try:
            # Kept modifiers still reference the helper objects, so hide them instead
            if self._temp_data['keep_modifiers']:
                for helper in self.helpers():
                    if helper:
                        helper.hide_set(True)
                        helper.hide_render = True
            
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
            self._errors.append(f"Cleanup failed: {str(e)}")
            return False
    
    def helpers(self):
        """Objects the run needs only while it builds mold and shell."""
        return [self._temp_data.get(key) for key in ('cutter', 'proxy', 'source')]

    def cleanup_and_finish(self, context, success):
        """End the run; a failed run removes every object it added."""
        OBJECT_OT_create_shell._running = False
        context.window_manager.progress_end()
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        if not success:
            cleanup_objects(self._created)
        elif not self._temp_data['keep_modifiers']:
            # Kept modifiers reference the helper objects, so they stay then
            cleanup_objects(self.helpers())


class OBJECT_OT_shell_reset_props(Operator):
    """Reset all shell generator properties to default values."""
    
    bl_idname = "object.shell_reset_props"
    bl_label = "Reset Shell Generator Properties"
    bl_description = "Reset all shell generator properties to default values"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the property reset operation."""
        prefs = context.preferences.addons[ADDON_ID].preferences
        props = context.scene.shellgen_props
        
        for name in props.bl_rna.properties.keys():
            if name not in ('rna_type', 'name'):
                props.property_unset(name)
        props.offset = prefs.default_offset
        props.thickness = prefs.default_thickness
        
        self.report({'INFO'}, "Shell Generator properties reset to defaults")
        return {'FINISHED'}
