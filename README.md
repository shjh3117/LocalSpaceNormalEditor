# Local Space Normal Editor

A Blender addon for editing custom normals in local space with an intuitive spherical picker interface.

![Spherical Picker](Screenshot.png)

## Features

- **Spherical Picker**: Interactive 3D sphere widget to visually select normal directions
- **Real-time Preview**: See changes instantly as you drag on the sphere
- **15° Angle Snapping**: Optional snapping for precise angle control
- **Auto Mark Sharp**: Automatically marks edges as sharp to prevent normal interpolation (enabled by default)
- **Mirror Editing**: Symmetric editing across X, Y, or Z axis
- **Flip View**: Press F to toggle between front and back hemisphere

## Requirements

- Blender 4.1 or later

## Installation

1. Download `__init__.py` from this repository
2. In Blender, go to Edit > Preferences > Add-ons
3. Click "Install..." and select the downloaded file
4. Enable "Local Space Normal Editor"

## Usage

1. Select a mesh object and enter **Edit Mode**
2. Select faces you want to edit
3. Open the sidebar (N key) and find the **Edit** tab
4. Click **Spherical Picker** to open the interactive picker

### Controls

| Key | Action |
|-----|--------|
| Left Mouse Drag | Set normal direction |
| F | Flip between front/back hemisphere |
| Enter | Confirm and close |
| Esc | Cancel and restore original normals |

### Options

- **Snap 15°**: Snap angles to 15° increments
- **Auto Mark Sharp**: Automatically mark selected edges as sharp (prevents smooth shading interpolation)
- **Mirror**: Mirror edits to the opposite side (X/Y/Z axis)

## Panel Location

View3D > Sidebar > Edit Tab > Local Normal Editor

## Changelog

### v0.0.3
- Added Auto Mark Sharp option (enabled by default)
- Edges are automatically marked sharp when applying normals to prevent interpolation

### v0.0.2
- Added Mirror editing feature (X/Y/Z axis)
- Improved mirror algorithm using face-center based matching

### v0.0.1
- Initial release
- Spherical picker with real-time preview
- 15° angle snapping
- Flip view (front/back hemisphere)

## License

GPL-2.0-or-later

## Author

shjh3117
