import bmesh
from mathutils.bvhtree import BVHTree

def detect_self_intersections(obj, bm):
    tree = BVHTree.FromBMesh(bm, epsilon=0.00001)
    overlap_pairs = tree.overlap(tree)
    intersecting_faces = set()
    for i1, i2 in overlap_pairs:
        if i1 == i2: continue
        f1, f2 = bm.faces[i1], bm.faces[i2]
        if not any(v in f2.verts for v in f1.verts):
            intersecting_faces.add(i1); intersecting_faces.add(i2)
    indices = list(intersecting_faces)
    return {
        "name": "self_intersect",
        "indices": indices,
        "status": "error" if indices else "ok",
        "description": f"Βρέθηκαν {len(indices)} self-intersecting faces" if indices else "Καθαρό"
    }
