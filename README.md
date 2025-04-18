# Blender Shell Generator

![Blender Version](https://img.shields.io/badge/Blender-4.0%2B-orange)
![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Version](https://img.shields.io/badge/Version-1.1.1-green)

A Blender add-on to generate shells with customizable offset and thickness for selected mesh objects, perfect for creating cases, enclosures, or molds.

## Features

- Create precise offset shells around any mesh object
- Control shell thickness and offset distance
- Option to create open-bottom shells (cut at Z=0)
- Fast mode with remesh for quicker processing
- Ability to combine multiple selected objects to create a single shell
- Compatible with the 3D Print Toolbox
- User-friendly sidebar panel with intuitive controls
- Advanced options for customization
- Asynchronous processing with visual feedback
- Proper handling of Blender's unit settings

## Usage

1. Select a mesh object in Object Mode
2. Access the Shell Generator through:
   - Sidebar panel: View3D > Sidebar > ShellGen
   - Object menu: Object > Shell Generator
   - Shortcut: Ctrl+Alt+S
3. Adjust parameters as needed
4. Click "Create Shell" to generate the shell

## Parameters

### Basic Settings
- **Offset**: Gap between original object and shell
- **Thickness**: Shell wall thickness
- **Open Bottom**: Remove geometry below Z=0

### Advanced Settings
#### Misc Options
- **Combine Selected Meshes**: Join multiple selected objects for shell creation
- **Even Thickness (experimental)**: Help maintain thickness at sharp corners (may create artifacts)

#### Performance Options
- **Fast Mode**: Use faster calculations with simplified settings
- **Mesh Resolution**:
  - **Auto Voxel Size**: Automatically calculate optimal resolution
    - **Detail Level**: Control the resolution when using auto mode
  - **Manual Voxel Size**: Direct control over remesh resolution

## Known Issues

- Very complex meshes may require more processing time or even run Blender out of memory
   - Consider using lower resolution meshes or simplifying geometry to improve performance
   - You can also try using the "Fast Mode" and coarser "Mesh Resolution" setting
- Boolean operations may occasionally fail with non-manifold geometry
    - For best results, ensure input meshes are clean and manifold
    - Alternatively you can try to use the "Combine Selected Meshes" to use a clean mesh internally (also works for single meshes)
- At sharp corners, the shell offset and/or thickness may be smaller than requested.
    - Enabling "Even Thickness" can help maintain minimum thickness, but may introduce artifacts, especially in complex geometry.

## Development

The addon uses a modular structure for better maintainability:
- `__init__.py`: Addon registration and metadata
- `modules/core.py`: Core shell generation functionality
- `modules/operators.py`: Modal operator for shell creation
- `modules/properties.py`: Property definitions and preferences
- `modules/ui.py`: User interface with section organization
- `modules/utils.py`: Utility functions and error handling

## License

This project is licensed under the GPLv3 License - see the LICENSE file for details.
