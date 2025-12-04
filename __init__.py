# SPDX-License-Identifier: GPL-2.0-or-later

bl_info = {
    "name": "Local Space Normal Editor",
    "author": "shjh3117",
    "version": (1, 0, 0),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > Edit Tab",
    "description": "Edit custom normals in local space with intuitive directional controls",
    "category": "Mesh",
    "doc_url": "https://github.com/shjh3117/LocalSpaceNormalEditor",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.props import FloatVectorProperty, EnumProperty


class MESH_OT_set_local_normal(bpy.types.Operator):
    """Set custom normals for selected faces in local space"""
    bl_idname = "mesh.set_local_normal"
    bl_label = "Set Local Normal"
    bl_options = {'REGISTER', 'UNDO'}

    normal_direction: FloatVectorProperty(
        name="Normal Direction",
        description="Normal direction in local space",
        default=(0.0, 0.0, 1.0),
        subtype='DIRECTION',
        size=3,
    )

    preset: EnumProperty(
        name="Preset",
        description="Predefined normal directions",
        items=[
            ('CUSTOM', "Custom", "Custom direction"),
            ('FRONT', "Front", "Front direction (Y-)"),
            ('BACK', "Back", "Back direction (Y+)"),
            ('LEFT', "Left", "Left direction (X-)"),
            ('RIGHT', "Right", "Right direction (X+)"),
            ('UP', "Up", "Up direction (Z+)"),
            ('DOWN', "Down", "Down direction (Z-)"),
            ('FRONT_LEFT_UP', "Front Left Up", "Front left up diagonal"),
            ('FRONT_UP', "Front Up", "Front up diagonal"),
            ('FRONT_RIGHT_UP', "Front Right Up", "Front right up diagonal"),
            ('FRONT_LEFT', "Front Left", "Front left diagonal"),
            ('FRONT_RIGHT', "Front Right", "Front right diagonal"),
            ('FRONT_LEFT_DOWN', "Front Left Down", "Front left down diagonal"),
            ('FRONT_DOWN', "Front Down", "Front down diagonal"),
            ('FRONT_RIGHT_DOWN', "Front Right Down", "Front right down diagonal"),
        ],
        default='CUSTOM',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data

        # Preset directions (Blender: X=right, Y=back, Z=up)
        # Front = looking at -Y direction
        preset_directions = {
            'FRONT': Vector((0.0, -1.0, 0.0)),
            'BACK': Vector((0.0, 1.0, 0.0)),
            'LEFT': Vector((-1.0, 0.0, 0.0)),
            'RIGHT': Vector((1.0, 0.0, 0.0)),
            'UP': Vector((0.0, 0.0, 1.0)),
            'DOWN': Vector((0.0, 0.0, -1.0)),
            # Front view diagonal directions
            'FRONT_LEFT_UP': Vector((-1.0, -1.0, 1.0)).normalized(),
            'FRONT_UP': Vector((0.0, -1.0, 1.0)).normalized(),
            'FRONT_RIGHT_UP': Vector((1.0, -1.0, 1.0)).normalized(),
            'FRONT_LEFT': Vector((-1.0, -1.0, 0.0)).normalized(),
            'FRONT_RIGHT': Vector((1.0, -1.0, 0.0)).normalized(),
            'FRONT_LEFT_DOWN': Vector((-1.0, -1.0, -1.0)).normalized(),
            'FRONT_DOWN': Vector((0.0, -1.0, -1.0)).normalized(),
            'FRONT_RIGHT_DOWN': Vector((1.0, -1.0, -1.0)).normalized(),
        }

        if self.preset != 'CUSTOM':
            normal = preset_directions[self.preset]
        else:
            normal = Vector(self.normal_direction).normalized()

        # Work with BMesh
        bm = bmesh.from_edit_mesh(mesh)

        # Collect loops from selected faces
        selected_loops = set()
        for face in bm.faces:
            if face.select:
                for loop in face.loops:
                    selected_loops.add(loop.index)

        if not selected_loops:
            self.report({'WARNING'}, "Please select faces")
            return {'CANCELLED'}

        # Switch to Object mode to apply normals
        bpy.ops.object.mode_set(mode='OBJECT')

        # Get existing normals (Blender 4.1+ API)
        normals = [Vector(cn.vector) for cn in mesh.corner_normals]

        # Modify normals for selected loops
        for loop_idx in selected_loops:
            normals[loop_idx] = normal

        # Apply normals
        mesh.normals_split_custom_set(normals)

        # Return to Edit mode
        bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, f"Normal set to {tuple(round(n, 3) for n in normal)}")
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "preset")
        if self.preset == 'CUSTOM':
            layout.prop(self, "normal_direction")


class MESH_OT_set_normal_from_face(bpy.types.Operator):
    """Copy normal from active face to all selected faces"""
    bl_idname = "mesh.set_normal_from_face"
    bl_label = "Copy Normal from Active Face"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data

        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()

        # Find active face
        active_face = bm.faces.active
        if active_face is None:
            self.report({'ERROR'}, "Please select an active face")
            return {'CANCELLED'}

        # Get active face normal (local space)
        source_normal = active_face.normal.copy()

        # Collect loops from selected faces
        selected_loops = set()
        for face in bm.faces:
            if face.select:
                for loop in face.loops:
                    selected_loops.add(loop.index)

        # Switch to Object mode to apply normals
        bpy.ops.object.mode_set(mode='OBJECT')

        # Get existing normals (Blender 4.1+ API)
        normals = [Vector(cn.vector) for cn in mesh.corner_normals]

        # Modify normals for selected loops
        for loop_idx in selected_loops:
            normals[loop_idx] = source_normal

        # Apply normals
        mesh.normals_split_custom_set(normals)

        # Return to Edit mode
        bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, "Active face normal copied to selected faces")
        return {'FINISHED'}


class MESH_OT_clear_custom_normals(bpy.types.Operator):
    """Remove custom normals and restore default normals"""
    bl_idname = "mesh.clear_custom_normals"
    bl_label = "Clear Custom Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object

        # Switch to Object mode if in Edit mode
        mode = obj.mode
        if mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Clear custom normals
        bpy.ops.mesh.customdata_custom_splitnormals_clear()

        # Return to original mode
        if mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, "Custom normals cleared")
        return {'FINISHED'}


class MESH_OT_average_normals(bpy.types.Operator):
    """Average normals of selected vertices"""
    bl_idname = "mesh.average_selected_normals"
    bl_label = "Average Selected Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data

        bm = bmesh.from_edit_mesh(mesh)

        # Collect selected vertices
        selected_verts = [v for v in bm.verts if v.select]
        if not selected_verts:
            self.report({'ERROR'}, "Please select vertices")
            return {'CANCELLED'}

        # Collect loops connected to selected vertices
        selected_loops = set()
        for vert in selected_verts:
            for loop in vert.link_loops:
                selected_loops.add(loop.index)

        bpy.ops.object.mode_set(mode='OBJECT')

        # Get existing normals (Blender 4.1+ API)
        normals = [Vector(cn.vector) for cn in mesh.corner_normals]

        # Calculate average normal
        avg_normal = Vector((0.0, 0.0, 0.0))
        for loop_idx in selected_loops:
            avg_normal += normals[loop_idx]

        if avg_normal.length > 0:
            avg_normal.normalize()
        else:
            avg_normal = Vector((0.0, 0.0, 1.0))

        # Set normals to average
        for loop_idx in selected_loops:
            normals[loop_idx] = avg_normal

        # Apply normals
        mesh.normals_split_custom_set(normals)

        bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, "Normals averaged")
        return {'FINISHED'}


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

        col = layout.column(align=True)
        col.label(text="Normal Direction (Front View):")

        # 3x3 direction grid
        row = col.row(align=True)
        op = row.operator("mesh.set_local_normal", text="↖")
        op.preset = 'FRONT_LEFT_UP'
        op = row.operator("mesh.set_local_normal", text="↑")
        op.preset = 'FRONT_UP'
        op = row.operator("mesh.set_local_normal", text="↗")
        op.preset = 'FRONT_RIGHT_UP'

        row = col.row(align=True)
        op = row.operator("mesh.set_local_normal", text="←")
        op.preset = 'FRONT_LEFT'
        op = row.operator("mesh.set_local_normal", text="●")
        op.preset = 'FRONT'
        op = row.operator("mesh.set_local_normal", text="→")
        op.preset = 'FRONT_RIGHT'

        row = col.row(align=True)
        op = row.operator("mesh.set_local_normal", text="↙")
        op.preset = 'FRONT_LEFT_DOWN'
        op = row.operator("mesh.set_local_normal", text="↓")
        op.preset = 'FRONT_DOWN'
        op = row.operator("mesh.set_local_normal", text="↘")
        op.preset = 'FRONT_RIGHT_DOWN'

        col.separator()

        # Custom direction
        op = col.operator("mesh.set_local_normal", text="Custom Direction...")
        op.preset = 'CUSTOM'

        col.separator()

        # Additional tools
        col.label(text="Tools:")
        col.operator("mesh.set_normal_from_face", text="Copy from Active Face")
        col.operator("mesh.average_selected_normals", text="Average Normals")
        col.operator("mesh.clear_custom_normals", text="Clear Custom Normals")


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


# Classes to register
classes = (
    MESH_OT_set_local_normal,
    MESH_OT_set_normal_from_face,
    MESH_OT_clear_custom_normals,
    MESH_OT_average_normals,
    VIEW3D_PT_local_normal_editor,
    VIEW3D_PT_local_normal_display,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
