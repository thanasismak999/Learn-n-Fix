bl_info = {
    "name": "TestLearnNFix",
    "author": "Athanasios Makridis",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Header > Learn&Fix",
    "description": "Optimized smart educational workflow assistant.",
    "category": "3D View",
}

import bpy
import bmesh
import json
import time
import os
import sys
import subprocess
import bpy.utils.previews
from bpy.app.handlers import persistent
from mathutils import Vector

addon_start_time = 0.0

from .checks.check_ngons import detect_ngons
from .checks.check_selfintersect import detect_self_intersections
from .checks.check_thin_tris import detect_thin_tris
from .checks.check_transforms import detect_unapplied_transforms

preview_collections = {}

ISSUE_DISPLAY_NAMES = {
    'NGONS': "N-Gons",
    'THINTRIS': "Thin Triangles",
    'SELFINTERSECT': "Self-Intersections",
    'TRANSFORMS': "Unapplied Scale"
}

IMAGE_MAPPING = {
    'NGONS': "NGONS.png",
    'THINTRIS': "THIN_FACES.png",
    'SELFINTERSECT': "SELF_INTERSECT.png",
    'TRANSFORMS': "UNAPPLIED_SCALE.png"
}

CHECKS_MAPPING = [
    ('check_ngons', detect_ngons, 'NGONS'),
    ('check_thin_tris', detect_thin_tris, 'THINTRIS'),
    ('check_selfintersect', detect_self_intersections, 'SELFINTERSECT'),
    ('check_transforms', detect_unapplied_transforms, 'TRANSFORMS'),
]

YOUTUBE_URLS = {
    'NGONS': "https://www.youtube.com/results?search_query=blender+why+ngons+are+bad",
    'THINTRIS': "https://www.youtube.com/results?search_query=blender+bad+topology+thin+triangles",
    'SELFINTERSECT': "https://www.youtube.com/results?search_query=blender+fix+self+intersecting",
    'TRANSFORMS': "https://www.youtube.com/results?search_query=blender+apply+scale"
}

def get_smart_explanation(issue, mode, count):
    why = "Causes issues."
    fix = "Fix manually."

    if issue == 'NGONS':
        if mode == 'ANIMATION':
            why = "Unpredictable deformation during bending."
        else:
            why = "May cause concave shading errors."
        if count > 50:
            fix = "Mass Error: Use 'Triangulate' Modifier."
        else:
            fix = "Select Face > Ctrl+T or Knife Tool (K)."

    elif issue == 'THINTRIS':
        why = "Bad physics collision or shading artifacts."
        if count > 100:
            fix = "Mass Error: Use 'Decimate' Modifier (Collapse)."
        else:
            fix = "Slide Vertices (GG) to merge."

    elif issue == 'SELFINTERSECT':
        why = "Impossible to 3D Print or bad physics."
        fix = "Sculpt Mode > Smooth or 'Remesh' Modifier."

    elif issue == 'TRANSFORMS':
        why = "Modifiers (Bevel/Array) will distort."
        fix = "Ctrl+A > Apply Scale."

    return f"PROBLEM: {ISSUE_DISPLAY_NAMES.get(issue, issue)}\nWHY: {why}\nFIX: {fix}"

WORKFLOW_RULES = { 'PRINTING': { 'defaults': {'check_thin_tris': True, 'check_selfintersect': True} } }

def update_workflow(self, context):
    mode = self.workflow_mode
    if mode == 'SELECT' or mode == 'CUSTOM': return
    rules = WORKFLOW_RULES.get(mode)
    if rules:
        defaults = rules['defaults']
        for prop_name, value in defaults.items():
            if hasattr(self, prop_name): setattr(self, prop_name, value)

def load_preview_icons():
    global preview_collections
    pcoll = bpy.utils.previews.new()
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    if os.path.exists(os.path.join(icons_dir, "learnfix_logo.png")):
        pcoll.load("learnfix_logo", os.path.join(icons_dir, "learnfix_logo.png"), 'IMAGE')
    for key, filename in IMAGE_MAPPING.items():
        path = os.path.join(icons_dir, filename)
        if os.path.exists(path): pcoll.load(key, path, 'IMAGE')
    preview_collections["main"] = pcoll

def unload_preview_icons():
    for pcoll in preview_collections.values(): bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

def get_icon(name):
    pcoll = preview_collections.get("main")
    if pcoll and name in pcoll: return pcoll[name].icon_id
    return 0

class MeshCheckerIndexItem(bpy.types.PropertyGroup): value: bpy.props.IntProperty()
class MeshCheckerResultItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    issue_type: bpy.props.StringProperty()
    count: bpy.props.IntProperty()
    improvement: bpy.props.FloatProperty(min=0.0, max=1.0, subtype='PERCENTAGE')

def _update_issue_type(self, context):
    self.current_index = 0
    self.current_indices.clear()

class MeshCheckerProperties(bpy.types.PropertyGroup):
    workflow_mode: bpy.props.EnumProperty(name="Usage Goal", items=[('SELECT', "Select a Workflow...", ""), ('PRINTING', "3D Printing", ""), ('ANIMATION', "Animation", ""), ('GAMES', "Game Asset", ""), ('CUSTOM', "Expert", "")], default='SELECT', update=update_workflow)
    show_explanation: bpy.props.BoolProperty(name="Info", default=False, description="Show detailed explanation")
    auto_check_enabled: bpy.props.BoolProperty(name="Auto-Check", default=False)
    auto_check_threshold: bpy.props.IntProperty(name="Every X Moves", default=10, min=1, max=100)
    edit_operation_count: bpy.props.IntProperty(default=0)
    is_internal_operation: bpy.props.BoolProperty(default=False)
    show_topology: bpy.props.BoolProperty(default=True)
    show_geometry: bpy.props.BoolProperty(default=True)
    show_workflow: bpy.props.BoolProperty(default=True)
    check_ngons: bpy.props.BoolProperty(name="N-Gons", default=True)
    check_thin_tris: bpy.props.BoolProperty(name="Long Thin Triangles", default=True)
    thintris_threshold: bpy.props.FloatProperty(name="Threshold", default=10.0)
    check_selfintersect: bpy.props.BoolProperty(name="Self-Intersect", default=True)
    check_transforms: bpy.props.BoolProperty(name="Transforms", default=True)
    results: bpy.props.CollectionProperty(type=MeshCheckerResultItem)
    issue_type: bpy.props.EnumProperty(name="Issue Type", items=[(k, v, "") for k,v in ISSUE_DISPLAY_NAMES.items()], update=_update_issue_type)
    current_index: bpy.props.IntProperty(default=0)
    current_indices: bpy.props.CollectionProperty(type=MeshCheckerIndexItem)
    baseline_stats: bpy.props.StringProperty(default="{}")
    total_score: bpy.props.FloatProperty(default=1.0, min=0.0, max=1.0, subtype='PERCENTAGE')

@persistent
def on_depsgraph_update(scene, depsgraph):
    props = scene.mesh_checker_props
    if props.is_internal_operation:
        props.is_internal_operation = False 
        return
    if not props.auto_check_enabled: return
    obj = bpy.context.active_object
    if not obj or obj.mode != 'EDIT': return
    for update in depsgraph.updates:
        if update.id.original == obj:
            if update.is_updated_geometry:
                props.edit_operation_count += 1
                if props.edit_operation_count >= props.auto_check_threshold:
                    props.edit_operation_count = 0
                    bpy.app.timers.register(trigger_auto_check, first_interval=0.1)
                break 

def trigger_auto_check():
    if bpy.context.active_object: bpy.ops.mesh.run_checks()
    return None

class SmoothViewController:
    def __init__(self):
        self._timer = None; self.start_time = 0; self.duration = 0.8; self.region_3d = None
    def start_animation(self, context, target_center, target_normal=None, dist=3.5):
        if self._timer: 
            try: bpy.app.timers.unregister(self._timer)
            except: pass
        area = context.area
        if area.type == 'VIEW_3D':
            for s in area.spaces: 
                if s.type == 'VIEW_3D': self.region_3d = s.region_3d; break
        if not self.region_3d: return
        self.start_loc = self.region_3d.view_location.copy()
        self.start_dist = self.region_3d.view_distance
        self.start_rot = self.region_3d.view_rotation.copy()
        self.target_loc = target_center; self.target_dist = dist
        self.target_rot = target_normal.to_track_quat('Z', 'Y') if target_normal else self.start_rot.copy()
        self.start_time = time.time()
        self._timer = self._tick
        bpy.app.timers.register(self._timer)
    def _tick(self):
        if not self.region_3d: return None
        elapsed = time.time() - self.start_time
        t = elapsed / self.duration
        if t >= 1.0:
            self.region_3d.view_location = self.target_loc; self.region_3d.view_distance = self.target_dist
            self.region_3d.view_rotation = self.target_rot; self._timer = None; return None
        prog = 1 - (1 - t) ** 3
        self.region_3d.view_location = self.start_loc.lerp(self.target_loc, prog)
        self.region_3d.view_distance = self.start_dist + (self.target_dist - self.start_dist) * prog
        self.region_3d.view_rotation = self.start_rot.slerp(self.target_rot, prog)
        return 0.01
view_controller = SmoothViewController()

def highlight_generic(obj, indices, mode_type):
    if obj.mode != 'EDIT': bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    if mode_type=='faces': bm.faces.ensure_lookup_table(); [setattr(f, 'select', i in indices) for i,f in enumerate(bm.faces)]
    elif mode_type=='verts': bm.verts.ensure_lookup_table(); [setattr(v, 'select', i in indices) for i,v in enumerate(bm.verts)]
    elif mode_type=='edges': bm.edges.ensure_lookup_table(); [setattr(e, 'select', i in indices) for i,e in enumerate(bm.edges)]
    bmesh.update_edit_mesh(obj.data)

def ensure_indices_for_issue(obj, props):
    if len(props.current_indices) > 0: return
    issue = props.issue_type; func = None
    for prop, f, code in CHECKS_MAPPING:
        if code == issue: func = f; break
    if func:
        bm = bmesh.new()
        if obj.mode == 'EDIT': bm = bmesh.from_edit_mesh(obj.data)
        else: bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        
        d = func(obj, bm, props.thintris_threshold) if issue=='THINTRIS' else func(obj, bm)
        indices = d.get("indices", [])
        if indices: 
            for i in indices: item=props.current_indices.add(); item.value=i
        if obj.mode != 'EDIT': bm.free()
    props.current_index = 0

def visualize_current(context):
    obj = context.active_object; props = context.scene.mesh_checker_props
    ensure_indices_for_issue(obj, props)
    if not props.current_indices: return
    idx = props.current_indices[min(props.current_index, len(props.current_indices)-1)].value
    issue = props.issue_type; mw = obj.matrix_world; rot = mw.to_3x3()
    pos = Vector((0,0,0)); norm = None
    if issue in ['NGONS', 'THINTRIS', 'SELFINTERSECT']:
        highlight_generic(obj, [idx], 'faces'); bm=bmesh.from_edit_mesh(obj.data); bm.faces.ensure_lookup_table()
        if idx<len(bm.faces): f=bm.faces[idx]; pos=mw@f.calc_center_median(); norm=rot@f.normal
    view_controller.start_animation(context, pos, norm)

class MESH_OT_RunChecks(bpy.types.Operator):
    bl_idname = "mesh.run_checks"; bl_label = "Check Mesh"
    def execute(self, context):
        obj = context.active_object; props = context.scene.mesh_checker_props; props.results.clear()
        if not obj or obj.type!='MESH': return {'CANCELLED'}
        props.is_internal_operation = True 
        bm = bmesh.new()
        if obj.mode == 'EDIT': bm = bmesh.from_edit_mesh(obj.data)
        else: bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        try: base=json.loads(props.baseline_stats)
        except: base={}
        curr=0; base_tot=0; first=None
        for prop, func, code in CHECKS_MAPPING:
            if getattr(props, prop):
                d = func(obj, bm, props.thintris_threshold) if code=='THINTRIS' else func(obj, bm)
                cnt = len(d.get("indices", [])) if d.get("indices") is not None else (1 if d.get("status")=="error" else 0)
                if cnt > 0 or d.get("status")=="error":
                    it=props.results.add(); it.name=d["description"]; it.issue_type=code; it.count=cnt
                    if not first: first=code
                    if code not in base: base[code]=cnt
                    if base[code]>0: it.improvement=max(0.0, 1.0-(cnt/base[code]))
                    curr+=cnt; base_tot+=base[code]
                elif code in base: base_tot+=base[code]
        if first: props.issue_type=first
        if curr==0: props.baseline_stats="{}"; props.total_score=1.0
        else: props.baseline_stats=json.dumps(base); props.total_score=max(0.0,1.0-(curr/base_tot)) if base_tot>0 else 0.0
        props.current_indices.clear(); props.current_index=0
        if obj.mode != 'EDIT': bm.free()
        return {'FINISHED'}

class MESH_OT_RefreshActive(bpy.types.Operator):
    bl_idname = "mesh.refresh_active"; bl_label = "Refresh Active"
    def execute(self, context):
        obj = context.active_object; props = context.scene.mesh_checker_props
        active_type = props.issue_type; props.is_internal_operation = True
        bm = bmesh.new()
        if obj.mode == 'EDIT': bm = bmesh.from_edit_mesh(obj.data)
        else: bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        func = next((f for p, f, c in CHECKS_MAPPING if c == active_type), None)
        if func:
            d = func(obj, bm, props.thintris_threshold) if active_type=='THINTRIS' else func(obj, bm)
            cnt = len(d.get("indices", [])) if d.get("indices") is not None else (1 if d.get("status")=="error" else 0)
            item = next((r for r in props.results if r.issue_type == active_type), None)
            if item:
                item.count = cnt
                try: base=json.loads(props.baseline_stats)
                except: base={}
                if active_type in base and base[active_type]>0: item.improvement = max(0.0, 1.0-(cnt/base[active_type]))
                if cnt == 0: self.report({'INFO'}, f"{ISSUE_DISPLAY_NAMES[active_type]} Fixed!")
        props.current_indices.clear(); props.current_index = 0
        if obj.mode != 'EDIT': bm.free()
        return {'FINISHED'}

class MESH_OT_OpenSpecificDoc(bpy.types.Operator):
    bl_idname = "mesh.open_specific_doc"; bl_label = "Open Explanation Doc"; issue_type: bpy.props.StringProperty()
    def execute(self, context):
        addon_dir = os.path.dirname(__file__); filepath = os.path.join(addon_dir, "docs", f"{self.issue_type}.rtf")
        if not os.path.exists(filepath): self.report({'ERROR'}, f"File not found"); return {'CANCELLED'}
        try:
            if sys.platform == 'win32': os.startfile(filepath)
            elif sys.platform == 'darwin': subprocess.call(('open', filepath))
            else: subprocess.call(('xdg-open', filepath))
        except: return {'CANCELLED'}
        return {'FINISHED'}

class MESH_OT_NavType(bpy.types.Operator):
    bl_idname = "mesh.nav_type"; bl_label = "Nav Type"; direction: bpy.props.IntProperty()
    def execute(self, context):
        props = context.scene.mesh_checker_props
        bpy.ops.mesh.run_checks()
        if not props.results: return {'FINISHED'}
        cur_idx = next((i for i, r in enumerate(props.results) if r.issue_type == props.issue_type), 0)
        props.issue_type = props.results[(cur_idx + self.direction) % len(props.results)].issue_type
        props.current_indices.clear(); props.current_index = 0
        return {'FINISHED'}

class MESH_OT_NavIssue(bpy.types.Operator):
    bl_idname = "mesh.nav_issue"; bl_label = "Nav Issue"; direction: bpy.props.IntProperty()
    def execute(self, context):
        props = context.scene.mesh_checker_props; obj = context.active_object
        props.is_internal_operation = True
        bm = bmesh.new()
        if obj.mode == 'EDIT': bm = bmesh.from_edit_mesh(obj.data)
        else: bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        func = next((f for p, f, c in CHECKS_MAPPING if c == props.issue_type), None)
        if func:
            d = func(obj, bm, props.thintris_threshold) if props.issue_type=='THINTRIS' else func(obj, bm)
            indices = d.get("indices", [])
            item = next((r for r in props.results if r.issue_type == props.issue_type), None)
            if item: item.count = len(indices)
            if not indices: self.report({'INFO'}, "All fixed!"); props.current_indices.clear(); return {'FINISHED'}
            props.current_indices.clear()
            for i in indices: it = props.current_indices.add(); it.value = i
        if props.current_indices:
            props.current_index = (props.current_index + self.direction) % len(props.current_indices)
            visualize_current(context)
        if obj.mode != 'EDIT': bm.free()
        return {'FINISHED'}

class MESH_OT_Show(bpy.types.Operator):
    bl_idname = "mesh.show_vis"; bl_label = "Show"
    def execute(self, context): visualize_current(context); return {'FINISHED'}

class MESH_OT_SelectAll(bpy.types.Operator):
    bl_idname = "mesh.select_all_issues"; bl_label = "Select All"
    def execute(self, context):
        obj = context.active_object; props = context.scene.mesh_checker_props
        ensure_indices_for_issue(obj, props)
        if not props.current_indices: return {'CANCELLED'}
        highlight_generic(obj, [item.value for item in props.current_indices], 'faces')
        return {'FINISHED'}

class MESH_OT_OpenHUD(bpy.types.Operator):
    bl_idname = "mesh.open_hud"; bl_label = "Learn & Fix"; bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context): return {'FINISHED'}
    def invoke(self, context, event): return context.window_manager.invoke_props_dialog(self, width=400)
    def draw(self, context):
        layout = self.layout; props = context.scene.mesh_checker_props; mode = props.workflow_mode
        header = layout.row(); icon_id = get_icon("learnfix_logo")
        if icon_id: header.label(text="", icon_value=icon_id)
        else: header.label(text="L&F", icon="SHADERFX")
        layout.separator()
        box = layout.box(); box.label(text="Step 1: Choose Workflow", icon="CHECKBOX_HLT")
        box.row().prop(props, "workflow_mode", text="")
        if mode=='SELECT': return
        layout.separator(); layout.label(text="Step 2: Detect Errors", icon="VIEWZOOM")
        if mode=='CUSTOM':
            b=layout.box(); b.prop(props,"show_topology",icon="TRIA_DOWN" if props.show_topology else "TRIA_RIGHT", emboss=False); b.label(text="Topology")
            if props.show_topology: c=b.column(align=True); c.prop(props,"check_ngons"); c.prop(props,"check_thin_tris")
            b=layout.box(); b.prop(props,"show_geometry",icon="TRIA_DOWN" if props.show_geometry else "TRIA_RIGHT", emboss=False); b.label(text="Geometry")
            if props.show_geometry: c=b.column(align=True); c.prop(props,"check_selfintersect")
            b=layout.box(); b.prop(props,"show_workflow",icon="TRIA_DOWN" if props.show_workflow else "TRIA_RIGHT", emboss=False); b.label(text="Transforms")
            if props.show_workflow: c=b.column(align=True); c.prop(props,"check_transforms")
        row=layout.row(); row.scale_y=1.5; row.operator("mesh.run_checks", text="Check Mesh", icon="CHECKMARK")
        layout.separator(); row = layout.row(align=True); row.prop(props, "auto_check_enabled", toggle=True, text="Auto-Check")
        if props.auto_check_enabled: row.prop(props, "auto_check_threshold", text="Moves")
        if props.results:
            layout.separator(); box=layout.box(); row=box.row(); row.label(text="Health:")
            row.prop(props,"total_score",text=f"{int(props.total_score*100)}%",slider=True)
            col=box.column(); active = next((r for r in props.results if r.issue_type==props.issue_type), None)
            idx = next((i+1 for i,r in enumerate(props.results) if r.issue_type==props.issue_type), 0)
            nav=col.row(align=True); nav.scale_y=1.2; nav.alignment='CENTER'
            nav.operator("mesh.nav_type",text="",icon="TRIA_LEFT").direction=-1
            nav.label(text=f"  {ISSUE_DISPLAY_NAMES.get(props.issue_type, props.issue_type)} ({idx}/{len(props.results)})  ", icon="FILE_TEXT")
            nav.operator("mesh.nav_type",text="",icon="TRIA_RIGHT").direction=1
            if active:
                ibox=col.box(); h_row = ibox.row(); h_row.label(text=f"{active.name} [{active.count}]")
                h_row.operator("mesh.refresh_active", text="", icon="FILE_REFRESH")
                if active.improvement>0: ibox.prop(active,"improvement",text="Fixed",slider=True,emboss=False)
                r=ibox.row(align=True); r.operator("mesh.nav_issue",text="Prev").direction=-1
                r.operator("mesh.show_vis",text="Show"); r.operator("mesh.nav_issue",text="Next").direction=1
                ibox.operator("mesh.select_all_issues", text=f"Select All", icon="RESTRICT_SELECT_OFF")
                ibox.prop(props, "show_explanation", text="How to Fix & Tutorials", icon="INFO", toggle=True) 
                if props.show_explanation:
                    info_box = ibox.box(); pcoll = preview_collections.get("main")
                    if pcoll and props.issue_type in pcoll:
                        row_icon = info_box.row(); row_icon.alignment = 'CENTER'
                        row_icon.template_icon(icon_value=pcoll[props.issue_type].icon_id, scale=8.0); info_box.separator()
                    for line in get_smart_explanation(props.issue_type, mode, active.count).split('\n'): info_box.label(text=line)
                    info_box.separator(); edu_row = info_box.row(); edu_row.scale_y=1.3
                    op = edu_row.operator("wm.url_open", text="Tutorial", icon="URL"); op.url = YOUTUBE_URLS.get(props.issue_type, "https://youtube.com")
                    doc_op = edu_row.operator("mesh.open_specific_doc", text="Theory", icon="FILE_TEXT"); doc_op.issue_type = props.issue_type
        elif props.total_score==1.0 and mode!='SELECT': layout.box().label(text="Perfect Score!", icon="CHECKMARK")

def redraw_header_timer():
    if time.time() - addon_start_time > 10.0: return None 
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D': area.tag_redraw()
    return 0.1

def draw_header_button(self, context):
    layout = self.layout; elapsed = time.time() - addon_start_time; is_flashing = (elapsed < 10.0 and int(elapsed * 4) % 2 == 0)
    if is_flashing: layout.alert = True
    icon_id = get_icon("learnfix_logo")
    layout.operator("mesh.open_hud", text="Learn & Fix", icon_value=icon_id if icon_id else 0, icon="HELP" if not icon_id else "NONE")
    if is_flashing: layout.alert = False

classes = (MeshCheckerIndexItem, MeshCheckerResultItem, MeshCheckerProperties, MESH_OT_RunChecks, MESH_OT_RefreshActive, MESH_OT_NavType, MESH_OT_NavIssue, MESH_OT_Show, MESH_OT_SelectAll, MESH_OT_OpenSpecificDoc, MESH_OT_OpenHUD)

def register():
    global addon_start_time; addon_start_time = time.time(); load_preview_icons()
    for c in classes: bpy.utils.register_class(c)
    bpy.types.Scene.mesh_checker_props=bpy.props.PointerProperty(type=MeshCheckerProperties)
    bpy.types.VIEW3D_HT_header.append(draw_header_button); bpy.app.timers.register(redraw_header_timer, first_interval=0.1)
    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post: bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)

def unregister():
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post: bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    bpy.types.VIEW3D_HT_header.remove(draw_header_button); unload_preview_icons(); del bpy.types.Scene.mesh_checker_props
    for c in reversed(classes): bpy.utils.unregister_class(c)

if __name__ == "__main__": register()
