# SPDX-License-Identifier: GPL-2.0-or-later

bl_info = {
    "name": "Local Space Normal Editor",
    "author": "shjh3117",
    "version": (0, 0, 11),
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
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


# -----------------------------------------------------------------------------
# Custom Normal Storage (saved in object custom properties)
# This stores the normals set by Spherical Picker

import json

CUSTOM_NORMAL_PROP = "local_normal_editor_data"  # Property name for storage


def save_normals_to_object(obj, normals_dict):
    """Save normals dict to object's custom property (persists in .blend)"""
    # Convert to JSON-serializable format
    data = {str(k): list(v) for k, v in normals_dict.items()}
    obj[CUSTOM_NORMAL_PROP] = json.dumps(data)


def load_normals_from_object(obj):
    """Load normals dict from object's custom property"""
    json_str = obj.get(CUSTOM_NORMAL_PROP, "{}")
    try:
        data = json.loads(json_str)
        return {int(k): tuple(v) for k, v in data.items()}
    except:
        return {}


# -----------------------------------------------------------------------------
# Toon Preview State
_toon_preview_state = {
    "handler": None,
    "batch": None,
    "shader": None,
    "object_name": None
}

def update_toon_preview_batch(context):
    """Update the GPU batch for toon preview"""
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return
    
    mesh = obj.data
    mesh.calc_loop_triangles()
    
    # Load custom normals
    stored_normals = load_normals_from_object(obj)
    
    vertices = []
    colors = []
    
    # Light direction from settings
    settings = context.scene.local_normal_editor
    light_dir = settings.toon_light_dir.normalized()
    
    # Iterate over loop triangles to get geometry
    # Note: This might be slow for very heavy meshes, but okay for low/mid poly
    for tri in mesh.loop_triangles:
        tri_verts = []
        tri_colors = []
        
        # Determine normal for this triangle
        # If poly index has custom normal, use it. Otherwise use loop normal or poly normal.
        # Since we store by poly index, we check that.
        if tri.polygon_index in stored_normals:
            nx, ny, nz = stored_normals[tri.polygon_index]
            normal = Vector((nx, ny, nz))
        else:
            normal = tri.normal # Fallback to geometry normal
            
        # Calculate Toon Color: step(0.0, dot(N, L))
        # dot > 0 -> Lit (White), dot <= 0 -> Shadow (Black/Grey)
        dot = normal.dot(light_dir)
        intensity = 1.0 if dot > 0.0 else 0.1
        color = (intensity, intensity, intensity, 1.0)
        
        for v_idx in tri.vertices:
            vertices.append(mesh.vertices[v_idx].co)
            colors.append(color)
            
    if not vertices:
        return

    shader = gpu.shader.from_builtin('UNIFORM_COLOR') if not colors else gpu.shader.from_builtin('FLAT_COLOR')
    if colors:
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices, "color": colors})
    else:
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices})
        
    _toon_preview_state["batch"] = batch
    _toon_preview_state["shader"] = shader
    _toon_preview_state["object_name"] = obj.name

def update_preview_callback(self, context):
    """Callback for property updates to refresh preview"""
    if _toon_preview_state["handler"]:
        update_toon_preview_batch(context)
        if context.area:
            context.area.tag_redraw()

def draw_toon_preview():
    """Draw handler for toon preview"""
    if not _toon_preview_state["batch"]:
        return
        
    obj = bpy.context.active_object
    if not obj or obj.name != _toon_preview_state["object_name"]:
        return
        
    # Only draw in Edit Mode
    if obj.mode != 'EDIT':
        return

    shader = _toon_preview_state["shader"]
    batch = _toon_preview_state["batch"]
    
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.face_culling_set('BACK')
    
    matrix = obj.matrix_world
    shader.bind()
    
    gpu.matrix.push()
    gpu.matrix.multiply_matrix(matrix)
    batch.draw(shader)
    
    # Draw Light Direction Arrow
    settings = bpy.context.scene.local_normal_editor
    light_dir = settings.toon_light_dir.normalized()
    scale = 2.0  # Length of the arrow
    
    p0 = (0, 0, 0)
    p1 = (light_dir.x * scale, light_dir.y * scale, light_dir.z * scale)
    
    # Simple line for arrow shaft
    shader_line = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch_line = batch_for_shader(shader_line, 'LINES', {"pos": [p0, p1]})
    
    shader_line.bind()
    shader_line.uniform_float("color", (1.0, 1.0, 0.0, 1.0)) # Yellow
    gpu.state.line_width_set(3.0)
    batch_line.draw(shader_line)
    gpu.state.line_width_set(1.0)
    
    gpu.matrix.pop()
    
    gpu.state.face_culling_set('NONE')
    gpu.state.depth_test_set('NONE')


# -----------------------------------------------------------------------------
# Helpers





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
    toon_light_dir: FloatVectorProperty(
        name="Light Direction",
        description="Direction of the light for toon preview",
        subtype='XYZ',
        default=(0.5, 0.5, 1.0),
        min=-1.0,
        max=1.0,
        update=update_preview_callback,
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
    smooth_factor: FloatProperty(
        name="Smooth Factor",
        description="Strength of the smoothing effect",
        default=0.5,
        min=0.0,
        max=1.0,
    )
    smooth_iterations: IntProperty(
        name="Iterations",
        description="Number of smoothing passes",
        default=3,
        min=1,
        max=20,
    )


# -----------------------------------------------------------------------------
# Spherical Popup Picker

class MESH_OT_spherical_popup(bpy.types.Operator):
    """Open a popup to visually select normal direction using angle picker"""
    bl_idname = "mesh.spherical_normal_popup"
    bl_label = "Normal Angle Picker"
    bl_options = {'REGISTER', 'UNDO'}

    _handle = None
    _yaw = 0.0
    _pitch = 0.0
    _dragging = False
    _popup_x = 0
    _popup_y = 0
    _width = 240   # Rectangle width (Yaw: -180 to +180)
    _height = 120  # Rectangle height (Pitch: -90 to +90)
    _original_normals = None
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

        settings = context.scene.local_normal_editor
        self._yaw = settings.yaw
        self._pitch = settings.pitch

        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        self._selected_loops = {loop.index for face in bm.faces if face.select for loop in face.loops}
        
        if not self._selected_loops:
            self.report({'WARNING'}, "Please select faces first")
            return {'CANCELLED'}
        
        if settings.mirror_axis != 'NONE':
            self._mirror_map = find_mirror_loops(bm, self._selected_loops, settings.mirror_axis)
        else:
            self._mirror_map = {}
        
        bpy.ops.object.mode_set(mode='OBJECT')
        self._original_normals = [Vector(cn.vector) for cn in mesh.corner_normals]
        bpy.ops.object.mode_set(mode='EDIT')

        region = context.region
        self._popup_x = region.width // 2
        self._popup_y = region.height // 2

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
        )

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()

        self.report({'INFO'}, "Drag to set angle. Enter=Apply, Esc=Cancel")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        context.area.tag_redraw()

        dx = event.mouse_region_x - self._popup_x
        dy = event.mouse_region_y - self._popup_y
        half_w = self._width // 2
        half_h = self._height // 2
        in_rect = abs(dx) <= half_w and abs(dy) <= half_h

        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and in_rect:
                self._dragging = True
                self.update_angles_from_mouse(dx, dy, context)
                self.apply_current_normal(context)
                return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE':
                self._dragging = False
                return {'RUNNING_MODAL'}

        elif event.type == 'MOUSEMOVE':
            if self._dragging:
                self.update_angles_from_mouse(dx, dy, context)
                self.apply_current_normal(context)
            return {'RUNNING_MODAL'}

        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            settings = context.scene.local_normal_editor
            settings.yaw = self._yaw
            settings.pitch = self._pitch
            
            self.report({'INFO'}, "Normal confirmed")
            self.cleanup(context)
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self.restore_original_normals(context)
            self.cleanup(context)
            self.report({'INFO'}, "Cancelled - normals restored")
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def update_angles_from_mouse(self, dx, dy, context):
        """Convert 2D mouse position directly to Yaw/Pitch angles"""
        settings = context.scene.local_normal_editor
        half_w = self._width // 2
        half_h = self._height // 2

        # Clamp to rectangle bounds
        dx = max(-half_w, min(half_w, dx))
        dy = max(-half_h, min(half_h, dy))

        # Direct mapping: X -> Yaw (-180 to +180), Y -> Pitch (-90 to +90)
        yaw = (dx / half_w) * math.pi      # -π to +π
        pitch = (dy / half_h) * (math.pi / 2)  # -π/2 to +π/2

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
        
        stored_normals = load_normals_from_object(obj)
        
        for poly in mesh.polygons:
            poly_loops = set(poly.loop_indices)
            if poly_loops & self._selected_loops:
                stored_normals[poly.index] = (normal.x, normal.y, normal.z)
        
        for loop_idx in self._selected_loops:
            normals[loop_idx] = normal
        
        if self._mirror_map:
            axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[settings.mirror_axis]
            mirrored_normal = normal.copy()
            mirrored_normal[axis_idx] = -mirrored_normal[axis_idx]
            
            for orig_idx, mirror_idx in self._mirror_map.items():
                normals[mirror_idx] = mirrored_normal
            
            for poly in mesh.polygons:
                poly_loops = set(poly.loop_indices)
                mirror_loops = set(self._mirror_map.values())
                if poly_loops & mirror_loops:
                    stored_normals[poly.index] = (mirrored_normal.x, mirrored_normal.y, mirrored_normal.z)
        
        save_normals_to_object(obj, stored_normals)
        mesh.normals_split_custom_set(normals)
        
        if _toon_preview_state["handler"]:
            update_toon_preview_batch(context)
            context.area.tag_redraw()
            
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
        """Draw the angle picker rectangle"""
        cx = self._popup_x
        cy = self._popup_y
        w = self._width
        h = self._height
        half_w = w // 2
        half_h = h // 2

        gpu.state.blend_set('ALPHA')

        # Background panel
        self.draw_rect(cx - half_w - 20, cy - half_h - 60, w + 40, h + 100, (0.1, 0.1, 0.1, 0.9))

        # Main rectangle area
        self.draw_rect(cx - half_w, cy - half_h, w, h, (0.2, 0.2, 0.25, 1.0))

        # Grid lines (every 15 degrees if snap enabled, else 30 degrees)
        settings = context.scene.local_normal_editor
        grid_step = 15 if settings.use_snap else 30
        
        # Vertical grid (Yaw)
        for deg in range(-180, 181, grid_step):
            x = cx + (deg / 180) * half_w
            alpha = 0.6 if deg % 90 == 0 else 0.3
            self.draw_line(x, cy - half_h, x, cy + half_h, (0.5, 0.5, 0.5, alpha), 1.0)
        
        # Horizontal grid (Pitch)
        for deg in range(-90, 91, grid_step):
            y = cy + (deg / 90) * half_h
            alpha = 0.6 if deg % 45 == 0 else 0.3
            self.draw_line(cx - half_w, y, cx + half_w, y, (0.5, 0.5, 0.5, alpha), 1.0)

        # Center crosshair (0,0)
        self.draw_line(cx - half_w, cy, cx + half_w, cy, (0.6, 0.6, 0.6, 0.8), 2.0)
        self.draw_line(cx, cy - half_h, cx, cy + half_h, (0.6, 0.6, 0.6, 0.8), 2.0)

        # Rectangle outline
        self.draw_rect_outline(cx - half_w, cy - half_h, w, h, (0.7, 0.7, 0.7, 1.0))

        # Current position indicator
        yaw_deg = math.degrees(self._yaw)
        pitch_deg = math.degrees(self._pitch)
        px = cx + (yaw_deg / 180) * half_w
        py = cy + (pitch_deg / 90) * half_h
        
        # Draw crosshair at current position
        self.draw_line(px - 8, py, px + 8, py, (1.0, 0.4, 0.1, 1.0), 2.0)
        self.draw_line(px, py - 8, px, py + 8, (1.0, 0.4, 0.1, 1.0), 2.0)
        self.draw_filled_circle(px, py, 6, (1.0, 0.5, 0.1, 1.0))
        self.draw_circle_outline(px, py, 6, (1.0, 1.0, 1.0, 1.0), 16)

        # Title
        blf.size(0, 16)
        blf.color(0, 1.0, 1.0, 1.0, 1.0)
        blf.position(0, cx - 55, cy + half_h + 25, 0)
        blf.draw(0, "Normal Angle Picker")

        # Angle display
        blf.size(0, 14)
        blf.position(0, cx - 70, cy - half_h - 25, 0)
        blf.draw(0, f"Yaw: {yaw_deg:.0f}°  Pitch: {pitch_deg:.0f}°")

        # Instructions
        blf.size(0, 12)
        blf.color(0, 0.6, 0.6, 0.6, 1.0)
        blf.position(0, cx - 70, cy - half_h - 45, 0)
        blf.draw(0, "Enter=Confirm  Esc=Cancel")

        # Axis labels
        blf.color(0, 0.5, 0.8, 1.0, 1.0)
        blf.size(0, 11)
        blf.position(0, cx - half_w - 15, cy - 5, 0)
        blf.draw(0, "-180°")
        blf.position(0, cx + half_w + 3, cy - 5, 0)
        blf.draw(0, "+180°")
        blf.position(0, cx - 12, cy + half_h + 5, 0)
        blf.draw(0, "+90°")
        blf.position(0, cx - 12, cy - half_h - 15, 0)
        blf.draw(0, "-90°")
        
        # Axis names
        blf.color(0, 0.7, 0.7, 0.7, 1.0)
        blf.position(0, cx + half_w + 3, cy + half_h - 10, 0)
        blf.draw(0, "Yaw")
        blf.position(0, cx - half_w - 5, cy + half_h + 5, 0)
        blf.draw(0, "Pitch")

        gpu.state.blend_set('NONE')

    def draw_rect(self, x, y, w, h, color):
        """Draw filled rectangle"""
        verts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        indices = [(0, 1, 2), (0, 2, 3)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    def draw_rect_outline(self, x, y, w, h, color):
        """Draw rectangle outline"""
        verts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        indices = [(0, 1), (1, 2), (2, 3), (3, 0)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": verts}, indices=indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    def draw_filled_circle(self, cx, cy, radius, color):
        """Draw filled circle"""
        segments = 16
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


class MESH_OT_mark_all_sharp(bpy.types.Operator):
    """Mark all edges as sharp to prevent normal interpolation"""
    bl_idname = "mesh.mark_all_edges_sharp"
    bl_label = "Mark All Edges Sharp"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        mode = obj.mode
        
        if mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Mark all edges as sharp
        count = 0
        for edge in mesh.edges:
            if not edge.use_edge_sharp:
                edge.use_edge_sharp = True
                count += 1
        
        if mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        self.report({'INFO'}, f"Marked {count} edges as sharp (Total: {len(mesh.edges)})")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Smooth Custom Normals

class MESH_OT_smooth_custom_normals(bpy.types.Operator):
    """Smooth custom normals using Gaussian-like filter"""
    bl_idname = "mesh.smooth_custom_normals"
    bl_label = "Smooth Custom Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        settings = context.scene.local_normal_editor
        
        # Load stored normals
        stored_normals = load_normals_from_object(obj) # {poly_index: (x, y, z)}
        if not stored_normals:
            self.report({'WARNING'}, "No custom normals found to smooth")
            return {'CANCELLED'}

        # Build connectivity map: face_idx -> list of connected face_indices
        # Two faces are connected if they share at least one vertex
        vert_to_faces = {} # vert_idx -> [face_idx, ...]
        for poly in mesh.polygons:
            for v_idx in poly.vertices:
                if v_idx not in vert_to_faces:
                    vert_to_faces[v_idx] = []
                vert_to_faces[v_idx].append(poly.index)
        
        face_neighbors = {} # face_idx -> set(neighbor_face_indices)
        for poly in mesh.polygons:
            neighbors = set()
            for v_idx in poly.vertices:
                for neighbor_idx in vert_to_faces[v_idx]:
                    if neighbor_idx != poly.index:
                        neighbors.add(neighbor_idx)
            face_neighbors[poly.index] = neighbors
            
        # Smoothing iterations
        current_normals = stored_normals.copy()
        factor = settings.smooth_factor
        
        self.report({'INFO'}, f"Smoothing normals... (Factor: {factor}, Iterations: {settings.smooth_iterations})")
        
        for i in range(settings.smooth_iterations):
            next_normals = {}
            for poly_idx, current_normal_tuple in current_normals.items():
                current_normal = Vector(current_normal_tuple)
                
                # Gather neighbor normals
                neighbor_sum = Vector((0, 0, 0))
                count = 0
                
                # Check if neighbors have custom normals
                neighbors = face_neighbors.get(poly_idx, set())
                for n_idx in neighbors:
                    if n_idx in current_normals:
                        neighbor_sum += Vector(current_normals[n_idx])
                        count += 1
                
                if count > 0:
                    avg_normal = neighbor_sum / count
                    avg_normal.normalize()
                    
                    # Lerp: original -> average
                    smoothed = current_normal.lerp(avg_normal, factor)
                    smoothed.normalize()
                    next_normals[poly_idx] = (smoothed.x, smoothed.y, smoothed.z)
                else:
                    next_normals[poly_idx] = current_normal_tuple
            
            current_normals = next_normals
            
        # Save back
        save_normals_to_object(obj, current_normals)
        
        # Apply to mesh
        # We need to apply these new normals to the loop normals of the mesh
        # If a face has a custom normal, all its loops get that normal (flat shading style for custom normals per face)
        
        # 1. Get current loop normals (to keep non-custom ones intact if any mixed state exists, though we usually overwrite)
        mesh.calc_normals_split()
        loop_normals = [Vector(l.normal) for l in mesh.loops] # Fallback to auto
        
        # 2. But we want to apply OUR stored normals
        # Create a list of normals for all loops
        # If a poly has a stored normal, use it. Else use... what? 
        # Usually we apply to ALL loops if we are using this system.
        
        # However, MESH_OT_apply_current_normal updates specific loops.
        # Let's reconstruct the fill list.
        
        new_loop_normals = []
        for poly in mesh.polygons:
            if poly.index in current_normals:
                nx, ny, nz = current_normals[poly.index]
                n = Vector((nx, ny, nz))
            else:
                n = Vector((0, 0, 1)) # Fallback, shouldn't happen if we loaded them
                # Or better, use the existing loop normal?
                # For safety, let's look at the first loop of the poly
                # But calculating split normals might be slow.
                # Let's just assume we rely on stored normals for everything relevant.
                
            for _ in poly.loop_indices:
                new_loop_normals.append(n)

        # Apply
        try:
            mesh.normals_split_custom_set(new_loop_normals)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to set normals: {e}")

        # Update preview
        if _toon_preview_state["handler"]:
            update_toon_preview_batch(context)
            context.area.tag_redraw()

        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Toon Preview Operator


class MESH_OT_toggle_toon_preview(bpy.types.Operator):
    """Toggle Toon Shading Preview for Custom Normals"""
    bl_idname = "mesh.toggle_toon_preview"
    bl_label = "Toggle Toon Preview"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        global _toon_preview_state
        
        if _toon_preview_state["handler"]:
            # Turn OFF
            bpy.types.SpaceView3D.draw_handler_remove(_toon_preview_state["handler"], 'WINDOW')
            _toon_preview_state["handler"] = None
            _toon_preview_state["batch"] = None
            self.report({'INFO'}, "Toon Preview: OFF")
        else:
            # Turn ON
            update_toon_preview_batch(context)
            if _toon_preview_state["batch"]:
                _toon_preview_state["handler"] = bpy.types.SpaceView3D.draw_handler_add(
                    draw_toon_preview, (), 'WINDOW', 'POST_VIEW'
                )
                self.report({'INFO'}, "Toon Preview: ON")
            else:
                self.report({'WARNING'}, "Could not create preview batch")
                
        context.area.tag_redraw()
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Bake Normal Map


class MESH_OT_bake_normal_map(bpy.types.Operator):
    """Bake custom normals to a normal map texture (Object/Local Space)"""
    bl_idname = "mesh.bake_custom_normal_map"
    bl_label = "Bake Normal Map"
    bl_options = {'REGISTER', 'UNDO'}
    
    resolution: EnumProperty(
        name="Resolution",
        items=[
            ('512', "512x512", ""),
            ('1024', "1024x1024", ""),
            ('2048', "2048x2048", ""),
            ('4096', "4096x4096", ""),
        ],
        default='2048',
    )
    
    padding: IntProperty(
        name="Padding",
        description="Edge padding in pixels to prevent seam artifacts",
        default=16,
        min=0,
        max=64,
    )
    
    filepath: StringProperty(
        name="File Path",
        subtype='FILE_PATH',
        default="//normal_map.png",
    )
    
    flip_red: BoolProperty(
        name="Flip X (Unreal Engine)",
        description="Flip X/Red channel",
        default=False,
    )
    
    flip_green: BoolProperty(
        name="Flip Y",
        description="Flip Y/Green channel",
        default=False,
    )
    
    flip_blue: BoolProperty(
        name="Flip Z (Unreal Engine)",
        description="Flip Z/Blue channel",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            return False
        return len(obj.data.uv_layers) > 0

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        
        original_mode = obj.mode
        selected_poly_indices = set()
        
        # Get selected polygons in Edit Mode
        if original_mode == 'EDIT':
            bm = bmesh.from_edit_mesh(mesh)
            selected_poly_indices = {f.index for f in bm.faces if f.select}
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # If no selection, use all polygons
        if not selected_poly_indices:
            selected_poly_indices = {p.index for p in mesh.polygons}
        
        res = int(self.resolution)
        
        # Create image array
        pixels = np.zeros((res, res, 4), dtype=np.float32)
        pixels[:, :, 0] = 0.5  # R - neutral
        pixels[:, :, 1] = 0.5  # G - neutral
        pixels[:, :, 2] = 1.0  # B - neutral (+Z)
        pixels[:, :, 3] = 1.0  # A
        
        mask = np.zeros((res, res), dtype=np.bool_)
        
        uv_layer = mesh.uv_layers.active
        if uv_layer is None:
            self.report({'ERROR'}, "No active UV layer")
            return {'CANCELLED'}
        
        # Load stored custom normals from object (saved in .blend file)
        stored_normals = load_normals_from_object(obj)
        
        if not stored_normals:
            self.report({'WARNING'}, "No custom normals set. Use Spherical Picker first!")
        
        # Rasterize only selected polygons using stored custom normals
        for poly in mesh.polygons:
            if poly.index not in selected_poly_indices:
                continue
            loop_indices = list(poly.loop_indices)
            uvs = [Vector((uv_layer.data[li].uv[0], uv_layer.data[li].uv[1])) for li in loop_indices]
            
            # Get stored normal for this polygon, or use default (0, 0, 1) = blue
            if poly.index in stored_normals:
                nx, ny, nz = stored_normals[poly.index]
                normal = Vector((nx, ny, nz))
            else:
                normal = Vector((0, 0, 1))  # Default: +Z (blue in normal map)
            
            # Fan triangulation
            for i in range(1, len(loop_indices) - 1):
                self._rasterize_solid(
                    pixels, mask, res,
                    [uvs[0], uvs[i], uvs[i + 1]],
                    normal,
                    flip_x=self.flip_red,
                    flip_y=self.flip_green,
                    flip_z=self.flip_blue
                )
        
        # Apply padding
        if self.padding > 0:
            self._apply_padding(pixels, mask, self.padding)
        
        # Save image
        img = bpy.data.images.new("NormalMapBake", width=res, height=res, alpha=False)
        img.pixels = pixels.flatten().tolist()
        img.filepath_raw = bpy.path.abspath(self.filepath)
        img.file_format = 'PNG'
        img.save()
        
        if original_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        self.report({'INFO'}, f"Normal map saved to {self.filepath}")
        return {'FINISHED'}
    
    def _rasterize_solid(self, pixels, mask, res, uvs, normal, flip_x=False, flip_y=False, flip_z=False):
        """Fill triangle with a single solid color"""
        p0 = (uvs[0].x * res, uvs[0].y * res)
        p1 = (uvs[1].x * res, uvs[1].y * res)
        p2 = (uvs[2].x * res, uvs[2].y * res)
        
        # Pre-compute color (flip RGB channels independently)
        r = (-normal.x * 0.5 + 0.5) if flip_x else (normal.x * 0.5 + 0.5)
        g = (-normal.y * 0.5 + 0.5) if flip_y else (normal.y * 0.5 + 0.5)
        b = (-normal.z * 0.5 + 0.5) if flip_z else (normal.z * 0.5 + 0.5)
        
        min_x = max(0, int(min(p0[0], p1[0], p2[0])))
        max_x = min(res - 1, int(max(p0[0], p1[0], p2[0])) + 1)
        min_y = max(0, int(min(p0[1], p1[1], p2[1])))
        max_y = min(res - 1, int(max(p0[1], p1[1], p2[1])) + 1)
        
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                bc = self._barycentric(p0, p1, p2, (x + 0.5, y + 0.5))
                if bc and bc[0] >= 0 and bc[1] >= 0 and bc[2] >= 0:
                    pixels[y, x, 0] = r
                    pixels[y, x, 1] = g
                    pixels[y, x, 2] = b
                    pixels[y, x, 3] = 1.0
                    mask[y, x] = True
    

    
    def _barycentric(self, p0, p1, p2, p):
        """Calculate barycentric coordinates for point p in triangle p0,p1,p2.
        Returns weights (w0, w1, w2) such that P = w0*p0 + w1*p1 + w2*p2"""
        v0 = (p1[0] - p0[0], p1[1] - p0[1])  # p1 - p0
        v1 = (p2[0] - p0[0], p2[1] - p0[1])  # p2 - p0
        v2 = (p[0] - p0[0], p[1] - p0[1])    # p - p0
        
        d00 = v0[0] * v0[0] + v0[1] * v0[1]
        d01 = v0[0] * v1[0] + v0[1] * v1[1]
        d02 = v0[0] * v2[0] + v0[1] * v2[1]
        d11 = v1[0] * v1[0] + v1[1] * v1[1]
        d12 = v1[0] * v2[0] + v1[1] * v2[1]
        
        denom = d00 * d11 - d01 * d01
        if abs(denom) < 1e-10:
            return None
        
        inv = 1.0 / denom
        u = (d11 * d02 - d01 * d12) * inv  # weight for p1
        v = (d00 * d12 - d01 * d02) * inv  # weight for p2
        w = 1.0 - u - v                     # weight for p0
        
        return (w, u, v)  # (p0_weight, p1_weight, p2_weight)
    
    def _apply_padding(self, pixels, mask, padding_size):
        padded = pixels.copy()
        current_mask = mask.copy()
        res = pixels.shape[0]
        
        for _ in range(padding_size):
            new_mask = current_mask.copy()
            for y in range(res):
                for x in range(res):
                    if current_mask[y, x]:
                        continue
                    neighbors = []
                    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < res and 0 <= nx < res and current_mask[ny, nx]:
                            neighbors.append((ny, nx))
                    if neighbors:
                        r, g, b = 0.0, 0.0, 0.0
                        for ny, nx in neighbors:
                            r += padded[ny, nx, 0]
                            g += padded[ny, nx, 1]
                            b += padded[ny, nx, 2]
                        n = len(neighbors)
                        padded[y, x] = [r/n, g/n, b/n, 1.0]
                        new_mask[y, x] = True
            current_mask = new_mask
        pixels[:] = padded


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

        # Angle Picker (Main Feature)
        col = layout.column(align=True)
        col.scale_y = 1.5
        col.operator("mesh.spherical_normal_popup", text="Angle Picker", icon='ORIENTATION_GIMBAL')
        
        col = layout.column(align=True)
        col.prop(settings, "use_snap")
        col.prop(settings, "mirror_axis")

        layout.separator()

        # Preview
        icon = 'HIDE_OFF' if _toon_preview_state["handler"] else 'HIDE_ON'
        text = "Disable Preview" if _toon_preview_state["handler"] else "Enable Toon Preview"
        layout.operator("mesh.toggle_toon_preview", text=text, icon=icon)
        
        if _toon_preview_state["handler"]:
            layout.prop(settings, "toon_light_dir")
        
        layout.separator()

        # Clear / Setup
        col = layout.column(align=True)
        col.operator("mesh.mark_all_edges_sharp", text="Mark All Sharp", icon='EDGESEL')
        col.operator("mesh.clear_custom_normals", text="Clear Custom Normals", icon='X')
        
        layout.separator()
        
        # Smooth
        layout.label(text="Processing")
        col = layout.column(align=True)
        col.operator("mesh.smooth_custom_normals", text="Smooth Normals", icon='MOD_SMOOTH')
        col.prop(settings, "smooth_factor", text="Factor")
        col.prop(settings, "smooth_iterations", text="Iterations")
        
        layout.separator()
        
        # Bake
        layout.operator("mesh.bake_custom_normal_map", text="Bake Normal Map", icon='IMAGE_DATA')


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
        
        layout.separator()
        col = layout.column(align=True)
        col.prop(overlay, "show_edge_sharp", text="Show Sharp Edges (Blue)")


# -----------------------------------------------------------------------------
# Registration


classes = (
    LocalNormalSettings,
    MESH_OT_spherical_popup,
    MESH_OT_clear_custom_normals,
    MESH_OT_mark_all_sharp,
    MESH_OT_smooth_custom_normals,
    MESH_OT_toggle_toon_preview,
    MESH_OT_bake_normal_map,
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
