"""
Shell Generator - A Blender addon to generate shells with customizable offset and thickness.
This is the wrapper module that imports from the modular package.
"""

from modules import bl_info

# Import registration functions
from modules import register, unregister

# These are kept here for backward compatibility
if __name__ == "__main__":
    register()
