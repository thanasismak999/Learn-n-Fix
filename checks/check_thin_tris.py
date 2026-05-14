import bmesh
import math

def detect_thin_tris(obj, bm, aspect_threshold=10.0, angle_threshold=10.0):
    bad_faces = []
    for f in bm.faces:
        if len(f.verts) != 3: continue
        verts = [v.co for v in f.verts]
        l = [(verts[i] - verts[(i+1)%3]).length for i in range(3)]
        l_max = max(l)
        area = ((verts[1] - verts[0]).cross(verts[2] - verts[0])).length / 2.0
        if area < 1e-8:
            bad_faces.append(f.index); continue
        aspect = (l_max * l_max) / (4.0 * math.sqrt(3) * area)
        angles = []
        for i in range(3):
            a, b = verts[i] - verts[(i+1)%3], verts[i] - verts[(i+2)%3]
            angles.append(math.degrees(a.angle(b)))
        if aspect > aspect_threshold or min(angles) < angle_threshold:
            bad_faces.append(f.index)
    return {
        "name": "thin_tris",
        "indices": bad_faces,
        "status": "error" if bad_faces else "ok",
        "description": f"Βρέθηκαν {len(bad_faces)} long thin triangles" if bad_faces else "Δεν βρέθηκαν"
    }
