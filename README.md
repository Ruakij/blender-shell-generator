# Blender Shell Generator

![Blender Version](https://img.shields.io/badge/Blender-4.0%2B-orange)
![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Version](https://img.shields.io/badge/Version-1.0.0-green)

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

## Usage

1. Select a mesh object in Object Mode
2. Access the Shell Generator through:
   - Sidebar panel: View3D > Sidebar > ShellGen
   - Object menu: Object > Shell Generator
   - Shortcut: Ctrl+Alt+S
3. Adjust parameters as needed:
   - **Offset**: Distance between original object and inner shell surface
   - **Thickness**: Thickness of the shell wall
   - **Open Bottom**: Remove geometry below Z=0 to create an open bottom
   - **Combine Selected Meshes**: Join multiple selected objects to create a single shell
4. Click "Create Shell" to generate the shell

## Parameters

- **Offset**: Gap between original object and shell
- **Thickness**: Shell wall thickness
- **Open Bottom**: Remove geometry below Z=0
- **Combine Selected Meshes**: Join multiple selected objects for shell creation
- **Max Gap**: Maximum allowed gap between objects when combining meshes
- **Fast Mode**: Use faster calculations (sacrifices some precision)
- **Remesh Voxel Size**: Controls resolution for remesh operations (smaller = higher quality)
- **Even Thickness (experimental)**: Enable Blender's "Even Thickness" for solidify modifiers. This can help maintain the requested thickness at sharp corners, but may introduce artifacts in complex geometry.

## Advanced Options

Access add-on preferences for additional settings:
1. Go to Edit > Preferences > Add-ons
2. Find and expand "Shell Generator"
3. Adjust advanced settings:
   - Default values
   - Debug information visibility
   - Modifier application options

## Known Issues

- Very complex meshes may require more processing time
- Boolean operations may occasionally fail with non-manifold geometry
    - For best results, ensure input meshes are clean and manifold
    - Alternatively one can try to use the "Combine Selected Meshes" to use a clean mesh internally (also works for single meshes)
    - At sharp corners, the shell thickness may be smaller than requested. Enabling "Even Thickness" can help maintain minimum thickness, but may introduce artifacts, especially in complex geometry.

## License

This project is licensed under the GPLv3 License - see the LICENSE file for details.
