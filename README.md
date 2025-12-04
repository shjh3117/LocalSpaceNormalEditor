# Local Space Normal Editor

A Blender addon for editing custom normals in local space with intuitive directional controls.

![Blender](https://img.shields.io/badge/Blender-4.1%2B-orange)
![License](https://img.shields.io/badge/License-GPL--2.0--or--later-blue)

## Features

- **Intuitive Direction Grid**: Set normals using a 3x3 directional grid (front view perspective)
- **Custom Direction**: Specify any custom normal direction
- **Copy from Active Face**: Copy the normal from the active face to all selected faces
- **Average Normals**: Average the normals of selected vertices
- **Clear Custom Normals**: Remove custom normals and restore defaults

## Installation

1. Download the latest release or clone this repository
2. In Blender, go to `Edit > Preferences > Add-ons`
3. Click `Install...` and select the downloaded zip file or the `__init__.py` file
4. Enable the addon by checking the checkbox

## Usage

1. Select a mesh object and enter **Edit Mode**
2. Select the faces you want to modify
3. Open the sidebar (press `N`) and find the **Edit** tab
4. Use the **Local Normal Editor** panel:

### Direction Grid
```
  ↖  ↑  ↗
  ←  ●  →
  ↙  ↓  ↘
```
- **●** (center): Front direction (facing camera)
- **Arrows**: Diagonal and cardinal directions

### Tools
- **Copy from Active Face**: Copies the active face's normal to all selected faces
- **Average Normals**: Averages normals of selected vertices
- **Clear Custom Normals**: Removes all custom normal data

## Requirements

- Blender 4.1 or later

## License

This project is licensed under the GPL-2.0-or-later license. See the [LICENSE](LICENSE) file for details.

## Author

- **shjh3117** - [GitHub](https://github.com/shjh3117)
