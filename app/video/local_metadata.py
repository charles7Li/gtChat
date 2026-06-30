from __future__ import annotations

import json
import subprocess
from pathlib import Path


def read_local_metadata(video_path: str | Path) -> dict:
    path = Path(video_path)
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout or "{}")
    video_stream = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), {})
    has_audio = any(stream.get("codec_type") == "audio" for stream in data.get("streams", []))
    duration = _float((data.get("format") or {}).get("duration") or video_stream.get("duration"))
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    return {
        "local_path": str(path),
        "duration_seconds": round(duration, 3),
        "resolution": f"{width}x{height}" if width and height else "",
        "fps": _fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        "has_audio": has_audio,
    }


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fps(value) -> float:
    if not value:
        return 0.0
    text = str(value)
    if "/" not in text:
        return round(_float(text), 3)
    numerator, denominator = text.split("/", 1)
    bottom = _float(denominator)
    return round(_float(numerator) / bottom, 3) if bottom else 0.0
