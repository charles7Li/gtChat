from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .settings import MobileSettings


class WeChatApiError(RuntimeError):
    def __init__(self, message: str, errcode: int | None = None) -> None:
        super().__init__(message)
        self.errcode = errcode


class ContentSafetyRejected(ValueError):
    pass


class WeChatServerApi:
    """Small server-side client for stable tokens, text checks, and subscriptions."""

    def __init__(self, settings: MobileSettings) -> None:
        self.settings = settings
        self._access_token = ""
        self._access_token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def check_text(self, openid: str, content: str, *, scene: int = 2) -> None:
        if not self.settings.wechat_content_security_enabled:
            return
        for chunk in _utf8_chunks(content, 2400):
            payload = self._authorized_post(
                "/wxa/msg_sec_check",
                {"content": chunk, "version": 2, "scene": scene, "openid": openid},
            )
            suggest = str((payload.get("result") or {}).get("suggest") or "").lower()
            if suggest != "pass":
                raise ContentSafetyRejected("content did not pass the WeChat safety check")

    def send_job_completed(self, openid: str, job: dict[str, Any]) -> None:
        template_id = self.settings.wechat_task_template_id
        if not template_id:
            raise WeChatApiError("task completion template is not configured")
        created_at = _display_time(str(job.get("updated_at") or job.get("created_at") or ""))
        data = {
            self.settings.wechat_task_template_title_key: {"value": _template_text(str(job.get("query") or "分析任务"), 20)},
            self.settings.wechat_task_template_status_key: {"value": "已完成"},
            self.settings.wechat_task_template_time_key: {"value": created_at},
        }
        self._authorized_post(
            "/cgi-bin/message/subscribe/send",
            {
                "touser": openid,
                "template_id": template_id,
                "page": f"pages/job-detail/index?id={urllib.parse.quote(str(job['id']))}",
                "miniprogram_state": "formal" if self.settings.wechat_auth_mode == "wechat" else "developer",
                "lang": "zh_CN",
                "data": data,
            },
        )

    def _authorized_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        separator = "&" if "?" in path else "?"
        for attempt in range(2):
            token = self._get_access_token()
            try:
                return self._post_json(
                    f"https://api.weixin.qq.com{path}{separator}access_token={urllib.parse.quote(token)}",
                    payload,
                )
            except WeChatApiError as exc:
                if attempt == 0 and exc.errcode in {40001, 40014, 42001}:
                    with self._token_lock:
                        self._access_token = ""
                        self._access_token_expires_at = 0.0
                    continue
                raise
        raise WeChatApiError("WeChat access token refresh failed")

    def _get_access_token(self) -> str:
        now = time.monotonic()
        if self._access_token and now < self._access_token_expires_at:
            return self._access_token
        with self._token_lock:
            now = time.monotonic()
            if self._access_token and now < self._access_token_expires_at:
                return self._access_token
            payload = self._post_json(
                "https://api.weixin.qq.com/cgi-bin/stable_token",
                {
                    "grant_type": "client_credential",
                    "appid": self.settings.wechat_app_id,
                    "secret": self.settings.wechat_app_secret,
                    "force_refresh": False,
                },
            )
            token = str(payload.get("access_token") or "")
            if not token:
                raise WeChatApiError("WeChat stable access token response was invalid")
            expires_in = max(int(payload.get("expires_in") or 7200), 600)
            self._access_token = token
            self._access_token_expires_at = time.monotonic() + expires_in - 300
            return token

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={"content-type": "application/json", "accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WeChatApiError("WeChat server API is unavailable") from exc
        if not isinstance(result, dict):
            raise WeChatApiError("WeChat server API returned an invalid response")
        errcode = int(result.get("errcode") or 0)
        if errcode:
            raise WeChatApiError(f"WeChat server API rejected the request ({errcode})", errcode)
        return result


def _utf8_chunks(content: str, max_bytes: int) -> list[str]:
    if not content:
        return []
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for character in content:
        encoded_size = len(character.encode("utf-8"))
        if current and size + encoded_size > max_bytes:
            chunks.append("".join(current))
            current = []
            size = 0
        current.append(character)
        size += encoded_size
    if current:
        chunks.append("".join(current))
    return chunks


def _template_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized[:limit] or "分析任务"


def _display_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
