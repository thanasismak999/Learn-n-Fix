import bpy
import bmesh
import time
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def detect_unapplied_transforms(obj):
    """ Εντοπίζει αν το αντικείμενο έχει unapplied scale ή rotation. """
    if obj is None or obj.type != 'MESH':
        return {"description": "No mesh found", "indices": [], "status": "no_mesh"}

    unapplied = []
    if obj.scale[0] != 1.0 or obj.scale[1] != 1.0 or obj.scale[2] != 1.0:
        unapplied.append("scale")

    if any(abs(r) > 1e-4 for r in obj.rotation_euler):
        unapplied.append("rotation")

    status = "error" if unapplied else "ok"
    if not unapplied:
        desc = "The mesh applied."
    else:
        desc = "The mesh is Unapplied " + " & ".join(unapplied)

    return {
        "name": "transforms",
        "description": desc,
        "indices": [],
        "status": status,
        "unapplied": unapplied
    }


def detect_thin_tris(obj, aspect_threshold=10.0, angle_threshold=10.0):

    if obj is None or obj.type != 'MESH':
        return {"name": "thin_tris", "indices": [], "status": "no_mesh", "description": "Not a mesh object"}

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    bad_faces = []

    for f in bm.faces:
        if len(f.verts) != 3:
            continue


        verts = [v.co for v in f.verts]
        l = [(verts[i] - verts[(i+1)%3]).length for i in range(3)]
        l_max = max(l)


        area = ((verts[1] - verts[0]).cross(verts[2] - verts[0])).length / 2.0
        if area < 1e-8:
            bad_faces.append(f.index)
            continue


        aspect = (l_max * l_max) / (4.0 * math.sqrt(3) * area)

        angles = []
        is_degenerate_angle = False
        for i in range(3):
            a = verts[i] - verts[(i+1)%3]
            b = verts[i] - verts[(i+2)%3]
            if a.length < 1e-8 or b.length < 1e-8:
                is_degenerate_angle = True
                break
            # Clamp για αποφυγή domain error στο acos
            val = max(-1.0, min(1.0, a.dot(b) / (a.length * b.length)))
            ang = math.degrees(math.acos(val))
            angles.append(ang)

        if is_degenerate_angle:
            bad_faces.append(f.index)
            continue

        min_angle = min(angles) if angles else 0.0

        if aspect > aspect_threshold or min_angle < angle_threshold:
            bad_faces.append(f.index)

    bm.free()

    status = "error" if bad_faces else "ok"
    description = (
        f"Found {len(bad_faces)} zero-area triangles"
        if bad_faces else "No Errors Found"
    )

    return {
        "name": "thin_tris",
        "indices": bad_faces,
        "status": status,
        "description": description
    }


def detect_ngons(obj):
    
    if obj is None or obj.type != 'MESH':
        return {"name": "ngons", "indices": [], "status": "no_mesh", "description": "Not a mesh object"}

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    ngons = [f.index for f in bm.faces if len(f.verts) > 4]

    bm.free()

    status = "error" if ngons else "ok"
    description = f"Found {len(ngons)} N-gons" if ngons else "No Errors Found"

    return {
        "name": "ngons",
        "indices": ngons,
        "status": status,
        "description": description
    }


def detect_self_intersections(obj):
    if obj is None or obj.type != 'MESH':
        return {"name": "self_intersect", "indices": [], "status": "no_mesh", "description": "No mesh object found"}

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    tree = BVHTree.FromBMesh(bm, epsilon=0.00001)
    overlap_pairs = tree.overlap(tree)

    intersecting_faces = set()

    for i1, i2 in overlap_pairs:
        if i1 == i2:
            continue
        
        f1 = bm.faces[i1]
        f2 = bm.faces[i2]

        share_verts = any(v in f2.verts for v in f1.verts)
        
        if not share_verts:
            intersecting_faces.add(i1)
            intersecting_faces.add(i2)

    del tree
    bm.free()

    indices = list(intersecting_faces)
    status = "error" if indices else "ok"
    description = (
        f"Found {len(indices)} self-intersecting faces"
        if indices else "No self-intersections found"
    )

    return {
        "name": "self_intersect",
        "indices": indices,
        "status": status,
        "description": description
    }

def run_benchmarks():
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        print("\n[!] Error: Please choose a viable MESH on the 3D Viewport.")
        return
    was_in_edit_mode = (obj.mode == 'EDIT')
    if was_in_edit_mode:
        bpy.ops.object.mode_set(mode='OBJECT')

    mesh = obj.data
    total_faces = len(mesh.polygons)
    total_verts = len(mesh.vertices)

    print("\n" + "=" * 70)
    print(f"  BENCHMARKING EXPERIMENT: {obj.name}")
    print(f"  Total Evaluated Faces: {total_faces:,} | Total Vertices: {total_verts:,}")
    print(f"  Current Scale: ({obj.scale.x:.3f}, {obj.scale.y:.3f}, {obj.scale.z:.3f})")
    print("=" * 70)

    # 1. Transforms Check
    t0 = time.perf_counter()
    res_transforms = detect_unapplied_transforms(obj)
    t_transforms = (time.perf_counter() - t0) * 1000

    # 2. Thin Tris / Zero-Area Check
    t0 = time.perf_counter()
    res_thin_tris = detect_thin_tris(obj)
    t_thin_tris = (time.perf_counter() - t0) * 1000

    # 3. N-Gons Check
    t0 = time.perf_counter()
    res_ngons = detect_ngons(obj)
    t_ngons = (time.perf_counter() - t0) * 1000

    # 4. Self-Intersections Check
    t0 = time.perf_counter()
    res_self = detect_self_intersections(obj)
    t_self = (time.perf_counter() - t0) * 1000

    total_latency = t_transforms + t_thin_tris + t_ngons + t_self

    print(f"1. Transforms:         {t_transforms:8.3f} ms | Status: {res_transforms['status'].upper():5} | {res_transforms['description']}")
    print(f"2. Thin Tris / Zero:   {t_thin_tris:8.3f} ms | Status: {res_thin_tris['status'].upper():5} | {res_thin_tris['description']}")
    print(f"3. N-Gons (>4 verts):  {t_ngons:8.3f} ms | Status: {res_ngons['status'].upper():5} | {res_ngons['description']}")
    print(f"4. Self-Intersections: {t_self:8.3f} ms | Status: {res_self['status'].upper():5} | {res_self['description']}")
    print("-" * 70)
    print(f"  TOTAL OBSERVER LATENCY: {total_latency:8.3f} ms")
    print("=" * 70 + "\n")

    if was_in_edit_mode:
        bpy.ops.object.mode_set(mode='EDIT')

run_benchmarks()