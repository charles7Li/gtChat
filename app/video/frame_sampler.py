from __future__ import annotations

import subprocess
from pathlib import Path


def sample_keyframes(video_path: str | Path, scenes: list[dict], output_dir: str | Path, *, max_keyframes: int = 20) -> list[str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frames = []
    for scene in scenes[: max(0, int(max_keyframes or 0))]:
        index = int(scene.get("index") or len(frames))
        midpoint = (float(scene.get("start_time") or 0) + float(scene.get("end_time") or 0)) / 2
        frame_path = output / f"frame_{index:04d}.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{midpoint:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(frame_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        frames.append(str(frame_path))
    return frames
