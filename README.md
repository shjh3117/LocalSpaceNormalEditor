# Local Space Normal Editor

A Blender addon for editing custom normals in local space with an interactive spherical picker.

![Blender](https://img.shields.io/badge/Blender-4.1%2B-orange)
![License](https://img.shields.io/badge/License-GPL--2.0--or--later-blue)

## Features

- **Interactive Spherical Picker**: Visual sphere widget for intuitive normal direction selection
  - Real-time preview - changes apply immediately as you drag
  - Front/Back hemisphere toggle (press `F` to flip)
  - 15° angle snapping (optional)
  - Cancel to restore original normals
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
- Use **Normal Display** panel to visualize split normals
- The sphere color changes: blue = front, red = back hemisphere

## Requirements

- Blender 4.1 or later

## License

This project is licensed under the GPL-2.0-or-later license. See the [LICENSE](LICENSE) file for details.

## Author

- **shjh3117** - [GitHub](https://github.com/shjh3117)
