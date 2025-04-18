"""Shell Generator addon - Generate shells with customizable offset and thickness."""

bl_info = {
    "name": "Shell Generator",
    "author": "Ruakij",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > ShellGen",
    "description": "Generate a shell with offset/thickness for the selected mesh, optionally open at Z=0",
    "warning": "",
    "doc_url": "https://github.com/ruakij/blender-shell-generator",
    "category": "Object",
    "support": "COMMUNITY"
}

import bpy
from bpy.props import PointerProperty
from bpy.types import Menu
from bpy.utils import register_class, unregister_class

from . import (
    core,
    operators,
    properties,
    ui,
    utils,
)

# All classes that need to be registered/unregistered
classes = (
    # Properties
    properties.ShellGenAddonPreferences,
    properties.ShellGenProperties,
    
    # Operators
    operators.OBJECT_OT_create_shell,
    operators.OBJECT_OT_shell_reset_props,
    
    # UI
    ui.VIEW3D_MT_shell_gen_menu,
    ui.OBJECT_PT_shell_panel,
)

# Add-on keymap
addon_keymaps = []

def register():
    """Register the addon and its classes."""
    # Register classes
    for cls in classes:
        register_class(cls)
        
    # Register properties
    bpy.types.Scene.shellgen_props = PointerProperty(type=properties.ShellGenProperties)
    
    # Register menu
    bpy.types.VIEW3D_MT_object.append(ui.draw_shell_gen_menu)
    
    # Handle the keymaps
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Create a keymap for object mode
        km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
        
        # Add shell generator shortcut (Ctrl+Alt+S)
        kmi = km.keymap_items.new(
            operators.OBJECT_OT_create_shell.bl_idname,
            'S',
            'PRESS',
            ctrl=True,
            alt=True
        )
        addon_keymaps.append((km, kmi))

def unregister():
    """Unregister the addon and its classes."""
    # Clear keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Remove menu
    bpy.types.VIEW3D_MT_object.remove(ui.draw_shell_gen_menu)
    
    # Unregister properties
    del bpy.types.Scene.shellgen_props
    
    # Unregister classes
    for cls in reversed(classes):
        unregister_class(cls)

if __name__ == "__main__":
    register()
