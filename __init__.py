# SPDX-License-Identifier: GPL-2.0-or-later

bl_info = {
    "name": "Local Space Normal Editor",
    "author": "shjh3117",
    "version": (0, 0, 2),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > Edit Tab",
    "description": "Edit custom normals in local space with spherical picker",
    "category": "Mesh",
    "doc_url": "https://github.com/shjh3117/LocalSpaceNormalEditor",
}

import math
import bpy
import bmesh
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
)


# -----------------------------------------------------------------------------
# Helpers


def snap_angle(angle_rad: float, step_degrees: float = 15.0) -> float:
    step = math.radians(step_degrees)
    return round(angle_rad / step) * step


def spherical_to_vector(yaw: float, pitch: float) -> Vector:
    """Convert yaw/pitch angles to direction vector"""
    cos_pitch = math.cos(pitch)
    x = math.sin(yaw) * cos_pitch
    y = -math.cos(yaw) * cos_pitch
    z = math.sin(pitch)
    vec = Vector((x, y, z))
    if vec.length_squared == 0:
        return Vector((0.0, 0.0, 1.0))
    return vec.normalized()


def vector_to_spherical(vec: Vector):
    """Convert direction vector to yaw/pitch angles"""
    vec = vec.normalized()
    pitch = math.asin(max(-1, min(1, vec.z)))
    yaw = math.atan2(vec.x, -vec.y)
    return yaw, pitch


def find_mirror_loops(bm, selected_loops, axis='X', threshold=0.001):
    """Find mirrored loop indices for selected loops based on face center matching"""
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    mirror_map = {}  # original_loop_idx -> mirror_loop_idx
    
    # Get selected faces
    selected_faces = [f for f in bm.faces if f.select]
    
    # Build face center to face map for non-selected faces
    other_faces = [f for f in bm.faces if not f.select]
    
    for sel_face in selected_faces:
        # Calculate mirrored face center
        face_center = sel_face.calc_center_median()
        mirror_center = face_center.copy()
        mirror_center[axis_idx] = -mirror_center[axis_idx]
        
        # Find matching face on the other side
        best_match = None
        best_dist = threshold
        for other_face in other_faces:
            other_center = other_face.calc_center_median()
            dist = (other_center - mirror_center).length
            if dist < best_dist:
                best_dist = dist
                best_match = other_face
        
        if best_match is None:
            continue
        
        # Match loops between the two faces by mirrored vertex positions
        for sel_loop in sel_face.loops:
            sel_vert_co = sel_loop.vert.co
            mirror_vert_co = sel_vert_co.copy()
            mirror_vert_co[axis_idx] = -mirror_vert_co[axis_idx]
            
            # Find closest loop in the mirror face
            best_loop = None
            best_loop_dist = threshold
            for other_loop in best_match.loops:
                dist = (other_loop.vert.co - mirror_vert_co).length
                if dist < best_loop_dist:
                    best_loop_dist = dist
                    best_loop = other_loop
            
            if best_loop is not None:
                mirror_map[sel_loop.index] = best_loop.index
    
    return mirror_map


def apply_normal_to_selection(context, normal: Vector, reporter=None):
    """Apply a normal direction to all selected faces"""
    obj = context.active_object
    if obj is None or obj.type != 'MESH' or obj.mode != 'EDIT':
        if reporter:
            reporter({'ERROR'}, "Select a mesh object in Edit Mode")
        return {'CANCELLED'}

    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)

    selected_loops = {loop.index for face in bm.faces if face.select for loop in face.loops}
    if not selected_loops:
        if reporter:
            reporter({'WARNING'}, "Please select faces")
        return {'CANCELLED'}

    # Check for mirror setting
    settings = context.scene.local_normal_editor
    mirror_axis = settings.mirror_axis
    mirror_map = {}
    
    if mirror_axis != 'NONE':
        mirror_map = find_mirror_loops(bm, selected_loops, mirror_axis)
    
    bpy.ops.object.mode_set(mode='OBJECT')
    normals = [Vector(cn.vector) for cn in mesh.corner_normals]
    
    for loop_idx in selected_loops:
        normals[loop_idx] = normal
    
    # Apply mirrored normals
    if mirror_map:
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[mirror_axis]
        mirrored_normal = normal.copy()
        mirrored_normal[axis_idx] = -mirrored_normal[axis_idx]
        
        for orig_idx, mirror_idx in mirror_map.items():
            normals[mirror_idx] = mirrored_normal
    
    mesh.normals_split_custom_set(normals)
    bpy.ops.object.mode_set(mode='EDIT')

    mirror_info = f" (mirrored {mirror_axis})" if mirror_map else ""
    if reporter:
        reporter({'INFO'}, f"Normal set to {tuple(round(n, 3) for n in normal)}{mirror_info}")
    return {'FINISHED'}


# -----------------------------------------------------------------------------
# Property Group


class LocalNormalSettings(bpy.types.PropertyGroup):
    yaw: FloatProperty(
        name="Yaw",
        description="Rotation around Z axis (0° = Front)",
        subtype='ANGLE',
        default=0.0,
    )
    pitch: FloatProperty(
        name="Pitch",
        description="Tilt up/down (positive = up)",
        subtype='ANGLE',
        default=0.0,
        min=math.radians(-89.9),
        max=math.radians(89.9),
    )
    use_snap: BoolProperty(
        name="Snap 15°",
        description="Snap angles to 15° increments",
        default=True,
    )
    mirror_axis: EnumProperty(
        name="Mirror",
        description="Mirror edit to opposite side",
        items=[
            ('NONE', "None", "No mirroring"),
            ('X', "X", "Mirror across X axis"),
            ('Y', "Y", "Mirror across Y axis"),
            ('Z', "Z", "Mirror across Z axis"),
        ],
        default='NONE',
    )


# -----------------------------------------------------------------------------
# Spherical Popup Picker


class MESH_OT_spherical_popup(bpy.types.Operator):
    """Open a popup to visually select normal direction on a sphere"""
    bl_idname = "mesh.spherical_normal_popup"
    bl_label = "Spherical Normal Picker"
    bl_options = {'REGISTER', 'UNDO'}

    _handle = None
    _yaw = 0.0
    _pitch = 0.0
    _dragging = False
    _flipped = False  # True = back hemisphere
    _popup_x = 0
    _popup_y = 0
    _sphere_radius = 100
    _original_normals = None  # Store original normals for cancel
    _selected_loops = None
    _mirror_map = None

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found")
            return {'CANCELLED'}

        # Initialize from current settings
        settings = context.scene.local_normal_editor
        self._yaw = settings.yaw
        self._pitch = settings.pitch
        self._flipped = False

        # Store original normals for cancel
        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        self._selected_loops = {loop.index for face in bm.faces if face.select for loop in face.loops}
        
        if not self._selected_loops:
            self.report({'WARNING'}, "Please select faces first")
            return {'CANCELLED'}
        
        # Setup mirror map if mirror is enabled
        if settings.mirror_axis != 'NONE':
            self._mirror_map = find_mirror_loops(bm, self._selected_loops, settings.mirror_axis)
        else:
            self._mirror_map = {}
        
        bpy.ops.object.mode_set(mode='OBJECT')
        self._original_normals = [Vector(cn.vector) for cn in mesh.corner_normals]
        bpy.ops.object.mode_set(mode='EDIT')

        # Center popup in the region
        region = context.region
        self._popup_x = region.width // 2
        self._popup_y = region.height // 2

        # Add draw handler
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
        )

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()

        self.report({'INFO'}, "Drag on sphere to set direction. Enter=Apply, Esc=Cancel")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        context.area.tag_redraw()

        dx = event.mouse_region_x - self._popup_x
        dy = event.mouse_region_y - self._popup_y
        in_sphere = (dx * dx + dy * dy) <= (self._sphere_radius * self._sphere_radius)

        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and in_sphere:
                self._dragging = True
                self.update_angles_from_mouse(dx, dy, context)
                self.apply_current_normal(context)  # Apply immediately
                return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE':
                self._dragging = False
                return {'RUNNING_MODAL'}

        elif event.type == 'MOUSEMOVE':
            if self._dragging:
                self.update_angles_from_mouse(dx, dy, context)
                self.apply_current_normal(context)  # Apply immediately
            return {'RUNNING_MODAL'}

        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            # Confirm and close (normals already applied)
            settings = context.scene.local_normal_editor
            settings.yaw = self._yaw
            settings.pitch = self._pitch
            
            self.report({'INFO'}, "Normal confirmed")
            self.cleanup(context)
            return {'FINISHED'}

        elif event.type == 'F' and event.value == 'PRESS':
            # Flip sphere (toggle front/back hemisphere)
            self._flipped = not self._flipped
            return {'RUNNING_MODAL'}

        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            # Cancel - restore original normals
            self.restore_original_normals(context)
            self.cleanup(context)
            self.report({'INFO'}, "Cancelled - normals restored")
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def update_angles_from_mouse(self, dx, dy, context):
        """Convert 2D mouse position to spherical angles"""
        settings = context.scene.local_normal_editor
        r = self._sphere_radius

        nx = max(-1, min(1, dx / r))
        ny = max(-1, min(1, dy / r))

        dist_sq = nx * nx + ny * ny
        if dist_sq > 1.0:
            dist = math.sqrt(dist_sq)
            nx /= dist
            ny /= dist
            dist_sq = 1.0

        nz = math.sqrt(max(0, 1.0 - dist_sq))
        
        # Flip direction if viewing back hemisphere
        if self._flipped:
            nz = -nz
        
        vec = Vector((nx, -nz, ny))

        yaw, pitch = vector_to_spherical(vec)

        if settings.use_snap:
            yaw = snap_angle(yaw)
            pitch = snap_angle(pitch)

        self._yaw = yaw
        self._pitch = pitch

    def apply_current_normal(self, context):
        """Apply current normal direction immediately"""
        obj = context.active_object
        mesh = obj.data
        normal = spherical_to_vector(self._yaw, self._pitch)
        settings = context.scene.local_normal_editor

        bpy.ops.object.mode_set(mode='OBJECT')
        normals = [Vector(cn.vector) for cn in mesh.corner_normals]
        
        for loop_idx in self._selected_loops:
            normals[loop_idx] = normal
        
        # Apply mirrored normals
        if self._mirror_map:
            axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[settings.mirror_axis]
            mirrored_normal = normal.copy()
            mirrored_normal[axis_idx] = -mirrored_normal[axis_idx]
            
            for orig_idx, mirror_idx in self._mirror_map.items():
                normals[mirror_idx] = mirrored_normal
        
        mesh.normals_split_custom_set(normals)
        bpy.ops.object.mode_set(mode='EDIT')

    def restore_original_normals(self, context):
        """Restore original normals (for cancel)"""
        if self._original_normals is None:
            return
        obj = context.active_object
        mesh = obj.data

        bpy.ops.object.mode_set(mode='OBJECT')
        mesh.normals_split_custom_set(self._original_normals)
        bpy.ops.object.mode_set(mode='EDIT')

    def draw_callback(self, context):
        """Draw the spherical picker"""
        cx = self._popup_x
        cy = self._popup_y
        r = self._sphere_radius

        # Enable blending for transparency
        gpu.state.blend_set('ALPHA')

        # Background panel
        self.draw_rect(cx - r - 20, cy - r - 50, (r + 20) * 2, (r + 20) * 2 + 70, (0.1, 0.1, 0.1, 0.9))

        # Sphere fill (different color for front/back)
        if self._flipped:
            self.draw_filled_circle(cx, cy, r, (0.25, 0.2, 0.2, 1.0))  # Reddish for back
        else:
            self.draw_filled_circle(cx, cy, r, (0.2, 0.2, 0.25, 1.0))  # Bluish for front

        # Grid lines
        self.draw_sphere_grid(cx, cy, r)

        # Sphere outline
        self.draw_circle_outline(cx, cy, r, (0.6, 0.6, 0.6, 1.0), 64)

        # Current direction indicator
        normal = spherical_to_vector(self._yaw, self._pitch)
        px = cx + normal.x * r
        py = cy + normal.z * r

        # Show indicator based on which hemisphere we're viewing
        show_indicator = (normal.y < 0 and not self._flipped) or (normal.y > 0 and self._flipped)
        if show_indicator:
            self.draw_line(cx, cy, px, py, (1.0, 0.5, 0.1, 1.0), 3.0)
            self.draw_filled_circle(px, py, 10, (1.0, 0.4, 0.1, 1.0))
            self.draw_circle_outline(px, py, 10, (1.0, 1.0, 1.0, 1.0), 16)

        # Center point
        self.draw_filled_circle(cx, cy, 5, (0.4, 0.4, 0.4, 1.0))

        # Text
        yaw_deg = math.degrees(self._yaw)
        pitch_deg = math.degrees(self._pitch)

        blf.size(0, 16)
        blf.color(0, 1.0, 1.0, 1.0, 1.0)
        blf.position(0, cx - 80, cy + r + 30, 0)
        side_text = "[Back]" if self._flipped else "[Front]"
        blf.draw(0, f"Spherical Picker {side_text}")

        blf.size(0, 14)
        blf.position(0, cx - 70, cy - r - 30, 0)
        blf.draw(0, f"Yaw: {yaw_deg:.0f}°  Pitch: {pitch_deg:.0f}°")

        blf.size(0, 12)
        blf.color(0, 0.6, 0.6, 0.6, 1.0)
        blf.position(0, cx - 95, cy - r - 50, 0)
        blf.draw(0, "Enter=Confirm  F=Flip  Esc=Cancel")

        # Direction labels
        blf.color(0, 0.5, 0.8, 1.0, 1.0)
        blf.position(0, cx - 8, cy + r + 8, 0)
        blf.draw(0, "Up")
        blf.position(0, cx - 14, cy - r - 18, 0)
        blf.draw(0, "Down")
        blf.position(0, cx + r + 8, cy - 5, 0)
        blf.draw(0, "R")
        blf.position(0, cx - r - 18, cy - 5, 0)
        blf.draw(0, "L")

        gpu.state.blend_set('NONE')

    def draw_sphere_grid(self, cx, cy, r):
        """Draw grid lines on sphere"""
        # Horizontal lines (latitude)
        for i in [-2, -1, 1, 2]:
            angle = math.radians(i * 30)
            y_offset = math.sin(angle) * r
            lat_r = math.cos(angle) * r
            self.draw_circle_outline(cx, cy + y_offset, lat_r, (0.35, 0.35, 0.35, 0.8), 32)

        # Vertical line (center meridian)
        self.draw_line(cx, cy - r, cx, cy + r, (0.35, 0.35, 0.35, 0.8), 1.0)
        
        # Horizontal center line
        self.draw_line(cx - r, cy, cx + r, cy, (0.35, 0.35, 0.35, 0.8), 1.0)

    def draw_rect(self, x, y, w, h, color):
        """Draw filled rectangle"""
        verts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        indices = [(0, 1, 2), (0, 2, 3)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    def draw_filled_circle(self, cx, cy, radius, color):
        """Draw filled circle"""
        segments = 32
        verts = [(cx, cy)]
        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            verts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        indices = [(0, i, i + 1) for i in range(1, segments + 1)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    def draw_circle_outline(self, cx, cy, radius, color, segments):
        """Draw circle outline"""
        verts = []
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            verts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        indices = [(i, (i + 1) % segments) for i in range(segments)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": verts}, indices=indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    def draw_line(self, x1, y1, x2, y2, color, width):
        """Draw line"""
        gpu.state.line_width_set(width)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": [(x1, y1), (x2, y2)]})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)

    def cleanup(self, context):
        if self._handle:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            self._handle = None
        context.area.tag_redraw()


# -----------------------------------------------------------------------------
# Clear Custom Normals


class MESH_OT_clear_custom_normals(bpy.types.Operator):
    """Remove custom normals and restore default"""
    bl_idname = "mesh.clear_custom_normals"
    bl_label = "Clear Custom Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mode = obj.mode
        if mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.mesh.customdata_custom_splitnormals_clear()

        if mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, "Custom normals cleared")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Panel


class VIEW3D_PT_local_normal_editor(bpy.types.Panel):
    """Local Normal Editor Panel"""
    bl_label = "Local Normal Editor"
    bl_idname = "VIEW3D_PT_local_normal_editor"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Edit'
    bl_context = "mesh_edit"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.local_normal_editor

        # Spherical Picker (Main Feature)
        col = layout.column(align=True)
        col.scale_y = 1.5
        col.operator("mesh.spherical_normal_popup", text="Spherical Picker", icon='SPHERE')
        
        col = layout.column(align=True)
        col.prop(settings, "use_snap")
        col.prop(settings, "mirror_axis")

        layout.separator()

        # Clear
        layout.operator("mesh.clear_custom_normals", text="Clear Custom Normals", icon='X')


class VIEW3D_PT_local_normal_display(bpy.types.Panel):
    """Normal Display Settings Panel"""
    bl_label = "Normal Display"
    bl_idname = "VIEW3D_PT_local_normal_display"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Edit'
    bl_context = "mesh_edit"
    bl_parent_id = "VIEW3D_PT_local_normal_editor"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        overlay = context.space_data.overlay

        col = layout.column(align=True)
        col.prop(overlay, "show_split_normals", text="Show Split Normals")
        col.prop(overlay, "normals_length", text="Length")


# -----------------------------------------------------------------------------
# Registration


classes = (
    LocalNormalSettings,
    MESH_OT_spherical_popup,
    MESH_OT_clear_custom_normals,
    VIEW3D_PT_local_normal_editor,
    VIEW3D_PT_local_normal_display,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.local_normal_editor = PointerProperty(type=LocalNormalSettings)


def unregister():
    del bpy.types.Scene.local_normal_editor
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
