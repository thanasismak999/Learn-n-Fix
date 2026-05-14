import bmesh

def detect_ngons(obj, bm):
    ngons = [f.index for f in bm.faces if len(f.verts) > 4]
    return {
        "name": "ngons",
        "indices": ngons,
        "status": "error" if ngons else "ok",
        "description": f"Βρέθηκαν {len(ngons)} N-gons" if ngons else "Δεν βρέθηκαν N-gons"
    }
