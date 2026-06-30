from __future__ import annotations


def classify_motion(metadata: dict, scenes: list[dict]) -> dict:
    duration = float(metadata.get("duration_seconds") or 0)
    fps = float(metadata.get("fps") or 0)
    if duration <= 0 or fps <= 0:
        motion_type = "unknown"
    elif len(scenes) > 1:
        motion_type = "motion_clip"
    else:
        motion_type = "single_scene_clip"
    return {"motion_type": motion_type, "method": "metadata_scene_fallback"}
