from __future__ import annotations


def detect_scenes(metadata: dict) -> list[dict]:
    duration = float(metadata.get("duration_seconds") or 0)
    if duration <= 0:
        return []
    return [
        {
            "index": 0,
            "start_time": 0.0,
            "end_time": round(duration, 3),
            "duration_seconds": round(duration, 3),
        }
    ]


def pacing_profile(scenes: list[dict]) -> dict:
    if not scenes:
        return {"scene_count": 0, "average_scene_seconds": 0, "pace": "unknown"}
    average = sum(float(scene.get("duration_seconds") or 0) for scene in scenes) / len(scenes)
    if average <= 2:
        pace = "fast"
    elif average <= 6:
        pace = "medium"
    else:
        pace = "slow"
    return {"scene_count": len(scenes), "average_scene_seconds": round(average, 3), "pace": pace}
