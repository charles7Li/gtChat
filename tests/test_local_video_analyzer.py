import json
from pathlib import Path
from types import SimpleNamespace

from app.video import analyze_local_video
from app.video.local_metadata import read_local_metadata


def test_read_local_metadata_parses_ffprobe(monkeypatch, tmp_path):
    video = tmp_path / "reference.mp4"
    video.write_text("fake", encoding="utf-8")

    def fake_run(command, **kwargs):
        assert command[0] == "ffprobe"
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "format": {"duration": "12.5"},
                    "streams": [
                        {"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "30000/1001"},
                        {"codec_type": "audio"},
                    ],
                }
            )
        )

    monkeypatch.setattr("app.video.local_metadata.subprocess.run", fake_run)

    metadata = read_local_metadata(video)

    assert metadata["duration_seconds"] == 12.5
    assert metadata["resolution"] == "1080x1920"
    assert metadata["fps"] == 29.97
    assert metadata["has_audio"] is True


def test_analyze_local_video_writes_brief_and_keyframe(monkeypatch, tmp_path):
    video = tmp_path / "reference.mp4"
    output_dir = tmp_path / "analysis"
    video.write_text("fake", encoding="utf-8")

    def fake_run(command, **kwargs):
        if command[0] == "ffprobe":
            return SimpleNamespace(
                stdout=json.dumps(
                    {
                        "format": {"duration": "8"},
                        "streams": [{"codec_type": "video", "width": 720, "height": 1280, "avg_frame_rate": "25/1"}],
                    }
                )
            )
        if command[0] == "ffmpeg":
            Path(command[-1]).write_text("jpg", encoding="utf-8")
            return SimpleNamespace(stdout="")
        raise AssertionError(command)

    monkeypatch.setattr("app.video.local_metadata.subprocess.run", fake_run)

    brief = analyze_local_video(video, output_dir=output_dir, max_keyframes=1)
    saved = json.loads((output_dir / "video_analysis_brief.json").read_text(encoding="utf-8"))

    assert brief["source"]["local_path"] == str(video)
    assert brief["structure_analysis"]["total_scenes"] == 1
    assert brief["structure_analysis"]["scenes"][0]["duration_seconds"] == 8
    assert brief["keyframes"] == ["keyframes/frame_0000.jpg"]
    assert saved["style_profile"]["motion"]["motion_type"] == "single_scene_clip"
