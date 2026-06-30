from __future__ import annotations


def transcribe_local_audio(video_path: str, *, enabled: bool = False) -> dict:
    if not enabled:
        return {"full_text": "", "segments": [], "word_count": 0, "language": "", "status": "skipped"}
    return {"full_text": "", "segments": [], "word_count": 0, "language": "", "status": "not_configured"}
