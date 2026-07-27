from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .settings import MobileSettings


class MediaModerationError(RuntimeError):
    pass


class MediaModerationRejected(ValueError):
    pass


class MediaModerationGateway:
    """Provider-neutral synchronous contract for image and video moderation."""

    def __init__(self, settings: MobileSettings) -> None:
        self.settings = settings

    def check(self, asset: dict[str, Any], object_url: str) -> None:
        if self.settings.media_moderation_mode == "disabled":
            return
        payload = {
            "asset_id": asset["id"],
            "file_type": asset["file_type"],
            "content_type": asset["content_type"],
            "size": int(asset["size"]),
            "object_url": object_url,
        }
        headers = {"content-type": "application/json", "accept": "application/json"}
        if self.settings.media_moderation_token:
            headers["authorization"] = f"Bearer {self.settings.media_moderation_token}"
        request = urllib.request.Request(
            self.settings.media_moderation_url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MediaModerationError("media moderation service is unavailable") from exc
        if not isinstance(result, dict):
            raise MediaModerationError("media moderation service returned an invalid response")
        suggest = str(result.get("suggest") or "").lower()
        if suggest == "pass":
            return
        if suggest in {"review", "block", "risky"}:
            raise MediaModerationRejected("uploaded media did not pass content moderation")
        raise MediaModerationError("media moderation service returned an unknown decision")
