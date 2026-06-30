from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .frame_sampler import sample_keyframes
from .local_metadata import read_local_metadata
from .motion import classify_motion
from .scene_detector import detect_scenes, pacing_profile
from .transcriber import transcribe_local_audio


def analyze_local_video(
    video_path: str | Path,
    *,
    output_dir: str | Path = "outputs/video_analysis",
    max_keyframes: int = 20,
    transcribe: bool = False,
) -> dict:
    source_path = Path(video_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output = Path(output_dir)
    keyframe_dir = output / "keyframes"
    metadata = read_local_metadata(source_path)
    scenes = detect_scenes(metadata)
    keyframes = sample_keyframes(source_path, scenes, keyframe_dir, max_keyframes=max_keyframes) if scenes else []
    transcript = transcribe_local_audio(str(source_path), enabled=transcribe)
    motion = classify_motion(metadata, scenes)

    brief = {
        "source": metadata,
        "transcript": transcript,
        "structure_analysis": {
            "total_scenes": len(scenes),
            "pacing_profile": pacing_profile(scenes),
            "scenes": scenes,
        },
        "keyframes": [_relative_to(path, output) for path in keyframes],
        "style_profile": {"motion": motion, "visual_patterns": []},
        "replication_guidance": {},
        "_analysis_meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "output_path": str(output / "video_analysis_brief.json"),
            "analyzer": "local_video_analyzer",
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "video_analysis_brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    return brief


def _relative_to(path: str | Path, root: Path) -> str:
    try:
        return str(Path(path).relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)
