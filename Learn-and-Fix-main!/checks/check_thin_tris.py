import bmesh
import math

def detect_thin_tris(obj, aspect_threshold=10.0, angle_threshold=10.0):
    if obj is None or obj.type != 'MESH':
        return {
            "name": "thin_tris",
            "indices": [],
            "status": "no_mesh",
            "description": "No mesh object found"
        }

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    bad_faces = []
    epsilon = 1e-8

    for f in bm.faces:
        area = f.calc_area()
        
        if area < epsilon:
            bad_faces.append(f.index)
            continue

        if len(f.verts) == 3:
            verts = [v.co for v in f.verts]
            l = [ (verts[i] - verts[(i+1)%3]).length for i in range(3) ]
            l_max = max(l)

            aspect = (l_max * l_max) / (4.0 * math.sqrt(3) * area) if area > 0 else 999.0
            
            angles = []
            for i in range(3):
                a = verts[i] - verts[(i+1)%3]
                b = verts[i] - verts[(i+2)%3]
                ang = math.degrees(a.angle(b))
                angles.append(ang)
            min_angle = min(angles) if angles else 0.0

            if aspect > aspect_threshold or min_angle < angle_threshold:
                bad_faces.append(f.index)

    bm.free()

    status = "error" if bad_faces else "ok"
    description = (
        f"Found {len(bad_faces)} Zero-Area / Thin Faces"
        if bad_faces else "No Zero-Area or Thin Faces found"
    )

    return {
        "name": "thin_tris",
        "indices": bad_faces,
        "status": status,
        "description": description
    }