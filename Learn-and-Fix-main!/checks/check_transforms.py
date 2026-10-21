import bpy

def detect_unapplied_transforms(obj):

    if obj is None or obj.type != 'MESH':
        return {
            "name": "transforms",
            "indices": [],
            "status": "no_mesh",
            "description": "No mesh was detected"
        }

    unapplied = []

    if not (abs(obj.scale[0] - 1.0) < 1e-4 and abs(obj.scale[1] - 1.0) < 1e-4 and abs(obj.scale[2] - 1.0) < 1e-4):
        unapplied.append("scale")

    # Έλεγχος rotation
    if any(abs(r) > 1e-4 for r in obj.rotation_euler):
        unapplied.append("rotation")

    has_error = len(unapplied) > 0
    status = "error" if has_error else "ok"
    
    if not has_error:
        desc = "All transforms are applied."
    else:
        desc = "Unapplied " + " & ".join(unapplied) + " Press Ctrl+A -> Apply Transforms."

    return {
        "name": "transforms",
        "indices": [],  # Object-level check, δεν έχει face/vertex indices
        "status": status,
        "description": desc
    }