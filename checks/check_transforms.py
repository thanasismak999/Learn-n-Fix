def detect_unapplied_transforms(obj, bm):
    unapplied = []
    if any(s != 1.0 for s in obj.scale): unapplied.append("scale")
    if any(abs(r) > 1e-4 for r in obj.rotation_euler): unapplied.append("rotation")
    desc = "Unapplied " + " & ".join(unapplied) + " – Apply Transforms (Ctrl+A)" if unapplied else "OK"
    return {"description": desc, "indices": [], "status": "error" if unapplied else "ok"}
