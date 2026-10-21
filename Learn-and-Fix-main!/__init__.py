bl_info = {
    "name": "Learn&Fix",
    "author": "Athanasios Makridis",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Header > Learn&Fix",
    "description": "Smart educational workflow assistant.",
    "category": "3D View",
}

import bpy
import bmesh
import json
import time
import os
import sys
import subprocess
import urllib.request
import urllib.error
import threading
import bpy.utils.previews
from bpy.app.handlers import persistent
from mathutils import Vector

addon_start_time = 0.5
last_user_activity_time = time.time()
flashing_state = True

from .checks.check_ngons import detect_ngons
from .checks.check_thin_tris import detect_thin_tris
from .checks.check_selfintersect import detect_self_intersections
from .checks.check_transforms import detect_unapplied_transforms

preview_collections = {}

ISSUE_DISPLAY_NAMES = {
    'NGONS': "N-Gons",
    'THINTRIS': "Zero-Area Faces",
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
    ('check_transforms', detect_unapplied_transforms, 'TRANSFORMS'),
    ('check_thin_tris', detect_thin_tris, 'THINTRIS'),
    ('check_selfintersect', detect_self_intersections, 'SELFINTERSECT'),
    ('check_ngons', detect_ngons, 'NGONS'),
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
        why = "Bad physics collision." if mode == 'GAMES' else "Shading artifacts."
        if count > 100:
            fix = "Mass Error: Use 'Decimate' Modifier (Collapse)."
        else:
            fix = "Slide Vertices (GG) to merge."
    elif issue == 'SELFINTERSECT':
        why = "Impossible to 3D Print." if mode == 'PRINTING' else "Bad physics, the mesh may react unreliably."
        fix = "Sculpt Mode > Smooth or 'Remesh' Modifier."
    elif issue == 'TRANSFORMS':
        why = "Modifiers (Bevel/Array) will distort."
        fix = "Ctrl+A > Apply Scale."

    return f"PROBLEM: {ISSUE_DISPLAY_NAMES.get(issue, issue)}\nWHY: {why}\nFIX: {fix}"

WORKFLOW_RULES = { 'PRINTING': { 'defaults': {'check_thin_tris': True} } }

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

# --- BACKGROUND IDLE SYNC ΓΙΑ ΤΑ DOCS ---
def background_sync_docs():
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
        
    for issue_code in IMAGE_MAPPING.keys():
        url = f"https://raw.githubusercontent.com/thanasismak999/Learn-n-Fix/main/docs/{issue_code}.txt"
        file_path = os.path.join(docs_dir, f"{issue_code}.txt")
        try:
            req = urllib.request.urlopen(url, timeout=3)
            text_data = req.read().decode('utf-8')
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text_data)
        except:
            pass

def idle_sync_timer():
    global last_user_activity_time
    idle_duration = time.time() - last_user_activity_time
    if idle_duration > 300:
        threading.Thread(target=background_sync_docs, daemon=True).start()
        last_user_activity_time = time.time()
    return 60.0

# --- FLASHING TIMER (2 t/s για τα πρώτα 10 δευτερόλεπτα) ---
def flashing_indicator_timer():
    global addon_start_time, flashing_state
    elapsed = time.time() - addon_start_time
    if elapsed > 10.0:
        return None # Σταματάει μετά από 10 δευτερόλεπτα
    
    flashing_state = not flashing_state
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return 0.25 # Ρυθμός 2t/s (ανά 0.25 sec αλλαγή κατάστασης)

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
    
    check_ngons: bpy.props.BoolProperty(name="N-Gons", default=True)
    check_thin_tris: bpy.props.BoolProperty(name="Zero-Area Faces", default=True)
    thintris_threshold: bpy.props.FloatProperty(name="Threshold", default=10.0)
    check_selfintersect: bpy.props.BoolProperty(name="Self-Intersections", default=True)
    check_transforms: bpy.props.BoolProperty(name="Unapplied Transforms", default=True)

    results: bpy.props.CollectionProperty(type=MeshCheckerResultItem)
    issue_type: bpy.props.EnumProperty(name="Issue Type", items=[(k, v, "") for k,v in ISSUE_DISPLAY_NAMES.items()], update=_update_issue_type)
    current_index: bpy.props.IntProperty(default=0)
    current_indices: bpy.props.CollectionProperty(type=MeshCheckerIndexItem)
    baseline_stats: bpy.props.StringProperty(default="{}")
    total_score: bpy.props.FloatProperty(default=1.0, min=0.0, max=1.0, subtype='PERCENTAGE')

@persistent
def on_depsgraph_update(scene, depsgraph):
    global last_user_activity_time
    last_user_activity_time = time.time()
    
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
    issue = props.issue_type; data = {}
    func = None
    for prop, f, code in CHECKS_MAPPING:
        if code == issue: func = f; break
    if func:
        d = func(obj, props.thintris_threshold) if issue=='THINTRIS' else func(obj)
        data = d
    if data.get("indices"): 
        for i in data["indices"]: item=props.current_indices.add(); item.value=i
    props.current_index = 0

def visualize_current(context):
    obj = context.active_object
    props = context.scene.mesh_checker_props
    ensure_indices_for_issue(obj, props)
    if not props.current_indices: return
    if props.current_index >= len(props.current_indices): props.current_index = len(props.current_indices)-1
    idx = props.current_indices[props.current_index].value
    mw = obj.matrix_world; rot = mw.to_3x3()
    pos = Vector((0,0,0)); norm = None
    highlight_generic(obj, [idx], 'faces')
    bm = bmesh.from_edit_mesh(obj.data); bm.faces.ensure_lookup_table()
    if idx < len(bm.faces):
        f = bm.faces[idx]
        pos = mw @ f.calc_center_median()
        norm = rot @ f.normal
    view_controller.start_animation(context, pos, norm)

class MESH_OT_RunChecks(bpy.types.Operator):
    bl_idname = "mesh.run_checks"; bl_label = "Check Mesh"
    def execute(self, context):
        global last_user_activity_time
        last_user_activity_time = time.time()
        
        obj = context.active_object
        props = context.scene.mesh_checker_props
        props.results.clear()
        if not obj or obj.type != 'MESH': return {'CANCELLED'}
        
        props.is_internal_operation = True
        
        prev_mode = obj.mode
        if prev_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
            
        try: base = json.loads(props.baseline_stats)
        except: base = {}
        curr = 0; base_tot = 0; first = None
        
        for prop, func, code in CHECKS_MAPPING:
            if getattr(props, prop):
                d = func(obj, props.thintris_threshold) if code == 'THINTRIS' else func(obj)
                cnt = 0; has = False
                if d.get("indices"): 
                    cnt = len(d["indices"])
                    has = True
                elif d.get("status") == "error": 
                    cnt = 1
                    has = True
                if has:
                    it = props.results.add()
                    it.name = d["description"]
                    it.issue_type = code
                    it.count = cnt
                    if not first: first = code
                    if code not in base: base[code] = cnt
                    if base[code] > 0: it.improvement = max(0.0, 1.0 - (cnt / base[code]))
                    curr += cnt
                    base_tot += base[code]
                elif code in base: 
                    base_tot += base[code]
                    
        if prev_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
            
        if first: props.issue_type = first
        if curr == 0: 
            props.baseline_stats = "{}"
            props.total_score = 1.0
        else: 
            props.baseline_stats = json.dumps(base)
            props.total_score = max(0.0, 1.0 - (curr / base_tot)) if base_tot > 0 else 0.0
            
        props.current_indices.clear()
        props.current_index = 0
        return {'FINISHED'}

class MESH_OT_RefreshActive(bpy.types.Operator):
    bl_idname = "mesh.refresh_active"; bl_label = "Refresh Active"
    def execute(self, context):
        obj = context.active_object
        props = context.scene.mesh_checker_props
        active_type = props.issue_type
        props.is_internal_operation = True
        
        prev_mode = obj.mode
        if prev_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
            
        func = None
        for p, f, c in CHECKS_MAPPING:
            if c == active_type: func = f; break
            
        if func:
            d = func(obj, props.thintris_threshold) if active_type == 'THINTRIS' else func(obj)
            cnt = 0
            if d.get("indices"): cnt = len(d["indices"])
            elif d.get("status") == "error": cnt = 1
            item = next((r for r in props.results if r.issue_type == active_type), None)
            if item:
                item.count = cnt
                try: base = json.loads(props.baseline_stats)
                except: base = {}
                if active_type in base and base[active_type] > 0: 
                    item.improvement = max(0.0, 1.0 - (cnt / base[active_type]))
                if cnt == 0: 
                    self.report({'INFO'}, f"{ISSUE_DISPLAY_NAMES[active_type]} Fixed!")
                    
        if prev_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
            
        props.current_indices.clear()
        props.current_index = 0
        return {'FINISHED'}

class MESH_OT_ToggleTheory(bpy.types.Operator):
    bl_idname = "mesh.toggle_theory"
    bl_label = "Toggle Theory & Diagram"
    issue_type: bpy.props.StringProperty()

    def execute(self, context):
        global last_user_activity_time
        last_user_activity_time = time.time()
        
        screen = context.screen
        if not screen:
            return {'CANCELLED'}

        # Έλεγχος αν είναι ήδη ανοιχτά τα image editors για να τα κλείσουμε
        open_image_areas = []
        for area in screen.areas:
            if area.type == 'IMAGE_EDITOR' and area.spaces.active.image and area.spaces.active.image.name.startswith("Theory_"):
                open_image_areas.append(area)

        if open_image_areas:
            for area in open_image_areas:
                with context.temp_override(area=area):
                    try:
                        bpy.ops.screen.area_close()
                    except:
                        pass
            return {'FINISHED'}

        # Φόρτωση εικόνας
        addon_dir = os.path.dirname(__file__)
        image_filename = IMAGE_MAPPING.get(self.issue_type)
        img = None
        if image_filename:
            img_path = os.path.join(addon_dir, "icons", image_filename)
            if os.path.exists(img_path):
                img = bpy.data.images.get(image_filename) or bpy.data.images.load(img_path)
                # Δίνουμε μοναδικό όνομα για εύκολο κλείσιμο
                img.name = f"Theory_{self.issue_type}"

        # Σταθερό διπλό split στα 2 μέρη: Κάθετο (1/4 αριστερά) και οριζόντιο στο αριστερό
        target_area = None
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                target_area = area
                break

        if target_area:
            initial_areas = set(screen.areas)

            # Πρώτο split: Κάθετο (1/4 αριστερά)
            with context.temp_override(window=context.window, area=target_area):
                bpy.ops.screen.area_split(direction='VERTICAL', factor=0.25)
            
            new_areas = set(screen.areas) - initial_areas
            left_area = list(new_areas)[0] if new_areas else screen.areas[-1]

            # Δεύτερο split: Οριζόντιο ΜΟΝΟ στο αριστερό κομμάτι (μοιράζεται στα 2: πάνω και κάτω)
            with context.temp_override(window=context.window, area=left_area):
                bpy.ops.screen.area_split(direction='HORIZONTAL', factor=0.5)

            top_area = screen.areas[-1]
            bottom_area = left_area

            # Και τα δύο γίνονται Image Editors με καθαρή εμφάνιση (χωρίς headers/toolbars)
            for area in (top_area, bottom_area):
                area.type = 'IMAGE_EDITOR'
                if img:
                    area.spaces.active.image = img
                    area.spaces.active.show_region_ui = False
                    area.spaces.active.show_region_header = False

        return {'FINISHED'}

class MESH_OT_NavType(bpy.types.Operator):
    bl_idname = "mesh.nav_type"; bl_label = "Nav Type"; direction: bpy.props.IntProperty()
    def execute(self, context):
        props = context.scene.mesh_checker_props; current_type = props.issue_type
        bpy.ops.mesh.run_checks()
        if len(props.results) == 0: return {'FINISHED'}
        cur_idx = 0
        for i, r in enumerate(props.results):
            if r.issue_type == current_type: cur_idx = i; break
        new_idx = (cur_idx + self.direction) % len(props.results)
        props.issue_type = props.results[new_idx].issue_type
        props.current_indices.clear(); props.current_index = 0
        return {'FINISHED'}

class MESH_OT_NavIssue(bpy.types.Operator):
    bl_idname = "mesh.nav_issue"; bl_label = "Nav Issue"; direction: bpy.props.IntProperty()
    def execute(self, context):
        props = context.scene.mesh_checker_props; obj = context.active_object
        props.is_internal_operation = True
        prev_mode = obj.mode
        if prev_mode == 'EDIT': bpy.ops.object.mode_set(mode='OBJECT')
        
        active_type = props.issue_type; func = None
        for p, f, c in CHECKS_MAPPING:
            if c == active_type: func = f; break
        if func:
            d = func(obj, props.thintris_threshold) if active_type=='THINTRIS' else func(obj)
            new_indices = d.get("indices", [])
            item = next((r for r in props.results if r.issue_type == active_type), None)
            if item: item.count = len(new_indices)
            if len(new_indices) == 0: 
                if prev_mode == 'EDIT': bpy.ops.object.mode_set(mode='EDIT')
                self.report({'INFO'}, "All fixed!"); props.current_indices.clear(); return {'FINISHED'}
            props.current_indices.clear()
            for i in new_indices: it = props.current_indices.add(); it.value = i
            
        if prev_mode == 'EDIT': bpy.ops.object.mode_set(mode='EDIT')
        
        if len(props.current_indices) > 0:
            new_idx = (props.current_index + self.direction) % len(props.current_indices)
            props.current_index = new_idx
            visualize_current(context)
        return {'FINISHED'}

class MESH_OT_Show(bpy.types.Operator):
    bl_idname = "mesh.show_vis"; bl_label = "Show"
    def execute(self, context): visualize_current(context); return {'FINISHED'}

class MESH_OT_SelectAll(bpy.types.Operator):
    bl_idname = "mesh.select_all_issues"; bl_label = "Select All"
    def execute(self, context):
        obj = context.active_object; props = context.scene.mesh_checker_props
        ensure_indices_for_issue(obj, props)
        if not props.current_indices: self.report({'INFO'}, "No issues to select."); return {'CANCELLED'}
        all_indices = [item.value for item in props.current_indices]; issue = props.issue_type
        highlight_generic(obj, all_indices, 'faces')
        self.report({'INFO'}, f"Selected {len(all_indices)} {issue} elements.")
        return {'FINISHED'}

class MESH_OT_ToggleSidebar(bpy.types.Operator):
    bl_idname = "wm.toggle_learnfix_sidebar"
    bl_label = "Toggle Learn & Fix Panel"
    
    def execute(self, context):
        for window in context.window_manager.windows:
            for screen in window.screen.areas:
                if screen.type == 'VIEW_3D':
                    for space in screen.spaces:
                        if space.type == 'VIEW_3D':
                            space.show_region_ui = not space.show_region_ui
                            return {'FINISHED'}
        return {'FINISHED'}

def draw_ui_layout(layout, context):
    props = context.scene.mesh_checker_props
    mode = props.workflow_mode
    
    header = layout.row()
    header.alignment = 'EXPAND'
    icon_id = get_icon("learnfix_logo")
    if icon_id:
        header.label(text="", icon_value=icon_id)
    else:
        header.label(text="L&F", icon="SHADERFX")
    header.label(text="Learn & Fix")
    
    layout.separator()

    box = layout.box()
    box.label(text="Step 1: Choose Workflow", icon="CHECKBOX_HLT")
    box.row().prop(props, "workflow_mode", text="")
    if mode == 'SELECT': return

    layout.separator()
    layout.label(text="Step 2: Detect Errors", icon="VIEWZOOM")
    if mode == 'CUSTOM':
        b = layout.box()
        b.label(text="Active Checks", icon="MODIFIER")
        c = b.column(align=True)
        c.prop(props, "check_ngons", text="N-Gons")
        c.prop(props, "check_thin_tris", text="Zero-Area Faces")
        c.prop(props, "check_selfintersect", text="Self-Intersections")
        c.prop(props, "check_transforms", text="Unapplied Transforms")

    row = layout.row()
    row.scale_y = 1.5
    row.operator("mesh.run_checks", text="Check Mesh", icon="CHECKMARK")
    
    layout.separator()
    row = layout.row(align=True)
    row.prop(props, "auto_check_enabled", toggle=True, text="Auto-Check")
    if props.auto_check_enabled:
         row.prop(props, "auto_check_threshold", text="Moves")
    
    if len(props.results) > 0:
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text="Health:")
        row.prop(props, "total_score", text=f"{int(props.total_score*100)}%", slider=True)
        
        col = box.column()
        idx = 0
        active = None
        for i, r in enumerate(props.results):
            if r.issue_type == props.issue_type: 
                idx = i + 1
                active = r
                break
                
        nav = col.row(align=True)
        nav.scale_y = 1.2
        nav.alignment = 'CENTER'
        nav.operator("mesh.nav_type", text="", icon="TRIA_LEFT").direction = -1
        lbl = f"{ISSUE_DISPLAY_NAMES.get(active.issue_type, active.issue_type)} ({idx}/{len(props.results)})" if active else "Select Error"
        nav.label(text=f"  {lbl}  ", icon="FILE_TEXT")
        nav.operator("mesh.nav_type", text="", icon="TRIA_RIGHT").direction = 1
        col.separator()

        if active:
            ibox = col.box()
            h_row = ibox.row()
            h_row.label(text=f"{active.name} [{active.count}]")
            h_row.operator("mesh.refresh_active", text="", icon="FILE_REFRESH")
            
            if active.improvement > 0:
                ibox.prop(active, "improvement", text="Fixed", slider=True, emboss=False)
            
            r = ibox.row(align=True)
            r.operator("mesh.nav_issue", text="Prev").direction = -1
            r.operator("mesh.show_vis", text="Show")
            r.operator("mesh.nav_issue", text="Next").direction = 1
            
            ibox.operator("mesh.select_all_issues", text="Select All", icon="RESTRICT_SELECT_OFF")

            info_row = ibox.row()
            info_row.prop(props, "show_explanation", text="Explain & Fix", icon="INFO", toggle=True) 

            if props.show_explanation:
                info_box = ibox.box()
                explanation = get_smart_explanation(active.issue_type, mode, active.count)
                
                col = info_box.column()
                for line in explanation.split('\n'):
                    col.label(text=line)
                
                info_box.separator()
                edu_row = info_box.row()
                edu_row.scale_y = 1.3
                
                op = edu_row.operator("wm.url_open", text="Tutorial", icon="URL")
                op.url = YOUTUBE_URLS.get(active.issue_type, "https://youtube.com")
                
                is_theory_open = False
                for area in context.screen.areas:
                    if area.type == 'TEXT_EDITOR' and area.spaces.active.text and area.spaces.active.text.name.startswith("Theory:"):
                        is_theory_open = True
                        break
                
                if is_theory_open:
                    doc_op = edu_row.operator("mesh.toggle_theory", text="Close Theory", icon="CANCEL")
                else:
                    doc_op = edu_row.operator("mesh.toggle_theory", text="Theory & Diagram", icon="FILE_TEXT")
                doc_op.issue_type = active.issue_type
            
    elif props.total_score == 1.0 and mode != 'SELECT':
        layout.box().label(text="Perfect Score!", icon="CHECKMARK")

class VIEW3D_PT_LearnFixPanel(bpy.types.Panel):
    bl_label = "Learn & Fix"
    bl_idname = "VIEW3D_PT_learn_fix_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Learn & Fix"

    def draw(self, context):
        draw_ui_layout(self.layout, context)

def draw_header_button(self, context):
    global flashing_state
    layout = self.layout
    icon_id = get_icon("learnfix_logo")
    
    elapsed = time.time() - addon_start_time
    is_flashing = (elapsed <= 10.0 and flashing_state)
    
    # Ανάβει κόκκινο alert όταν είναι σε φάση flashing
    row = layout.row()
    row.alert = is_flashing
    
    if icon_id:
        row.operator("wm.toggle_learnfix_sidebar", text="Learn & Fix", icon_value=icon_id)
    else:
        row.operator("wm.toggle_learnfix_sidebar", text="Learn & Fix", icon="HELP")

classes = (
    MeshCheckerIndexItem, MeshCheckerResultItem, MeshCheckerProperties, 
    MESH_OT_RunChecks, MESH_OT_RefreshActive, MESH_OT_NavType, MESH_OT_NavIssue, 
    MESH_OT_Show, MESH_OT_SelectAll, MESH_OT_ToggleTheory, MESH_OT_ToggleSidebar, VIEW3D_PT_LearnFixPanel
)

def register():
    global addon_start_time
    addon_start_time = time.time()
    load_preview_icons()
    for c in classes: bpy.utils.register_class(c)
    bpy.types.Scene.mesh_checker_props = bpy.props.PointerProperty(type=MeshCheckerProperties)
    bpy.types.VIEW3D_HT_header.append(draw_header_button)
    
    # Ενεργοποίηση αυτόματου ανοίγματος του N-Panel (sidebar) στην καρτέλα Learn & Fix κατά την εκκίνηση
    def auto_open_sidebar():
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.show_region_ui = True
        return None
    bpy.app.timers.register(auto_open_sidebar, first_interval=0.5)

    if not bpy.app.timers.is_registered(idle_sync_timer):
        bpy.app.timers.register(idle_sync_timer, first_interval=60.0)
        
    if not bpy.app.timers.is_registered(flashing_indicator_timer):
        bpy.app.timers.register(flashing_indicator_timer, first_interval=0.25)
        
    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)

def unregister():
    if bpy.app.timers.is_registered(idle_sync_timer):
        bpy.app.timers.unregister(idle_sync_timer)
    if bpy.app.timers.is_registered(flashing_indicator_timer):
        bpy.app.timers.unregister(flashing_indicator_timer)
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    bpy.types.VIEW3D_HT_header.remove(draw_header_button)
    unload_preview_icons()
    del bpy.types.Scene.mesh_checker_props
    for c in reversed(classes): bpy.utils.unregister_class(c)

if __name__ == "__main__": register()