# Local Space Normal Editor

A Blender addon for editing custom normals in local space with an interactive spherical picker.

![Blender](https://img.shields.io/badge/Blender-4.1%2B-orange)
![License](https://img.shields.io/badge/License-GPL--2.0--or--later-blue)

## Screenshot

![Spherical Picker](Screenshot.png)

## Features

- **Interactive Spherical Picker**: Visual sphere widget for intuitive normal direction selection
  - Real-time preview - changes apply immediately as you drag
  - Front/Back hemisphere toggle (press `F` to flip)
  - 15° angle snapping (optional)
  - Cancel to restore original normals
- **Toon Shading Preview**: Visualize custom normals with toon shading effect
  - Toggle on/off with a button
  - Adjustable light direction (XYZ)
  - Yellow arrow shows current light direction
  - Only visible in Edit Mode
- **Normal Map Baking**: Export custom normals to object-space normal map
  - Resolutions: 512, 1024, 2048, 4096
  - Edge padding to prevent seam artifacts
- **Persistent Storage**: Custom normals are saved with the .blend file
- **Mirror Editing**: Edit normals symmetrically across X, Y, or Z axis
- **Clear Custom Normals**: Remove custom normals and restore defaults
- **Normal Display Settings**: Quick access to split normal visualization

## Installation

1. Download the latest release or clone this repository
2. In Blender, go to `Edit > Preferences > Add-ons`
3. Click `Install...` and select the downloaded zip file or the `__init__.py` file
4. Enable the addon by checking the checkbox

## Usage

1. Select a mesh object and enter **Edit Mode**
2. Select the faces you want to modify
3. Open the sidebar (press `N`) and find the **Edit** tab
4. Click **Spherical Picker** in the **Local Normal Editor** panel

### Spherical Picker Controls

| Action | Description |
|--------|-------------|
| **Drag** on sphere | Set normal direction (applies immediately) |
| **F** | Flip between front/back hemisphere |
| **Enter** | Confirm and close |
| **Esc** | Cancel and restore original normals |

### Tips

- Enable **Snap 15°** for precise angle increments
- Enable **Mirror (X/Y/Z)** to edit both sides symmetrically
- Use **Normal Display** panel to visualize split normals
- The sphere color changes: blue = front, red = back hemisphere

## Requirements

- Blender 4.1 or later

## License

This project is licensed under the GPL-2.0-or-later license. See the [LICENSE](LICENSE) file for details.

## Changelog

### v0.0.5
- Toon Shading Preview with adjustable light direction

### v0.0.4
- Removed auto mark sharp feature (buggy)
- Added Normal Map Baking with custom dictionary approach
- Added Persistent Storage (normals saved in .blend file)

### v0.0.3
- Auto mark edges as sharp when applying normals (to prevent interpolation)

### v0.0.2
- Added Mirror editing feature (X/Y/Z axis)

### v0.0.1
- Initial release
- Spherical picker with real-time preview
- 15° angle snapping
- Flip view (front/back hemisphere)

## Author

- **shjh3117** - [GitHub](https://github.com/shjh3117)
