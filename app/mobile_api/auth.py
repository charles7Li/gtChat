from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .settings import MobileSettings


class WeChatAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeChatIdentity:
    openid: str
    unionid: str | None = None


class WeChatGateway:
    def __init__(self, settings: MobileSettings) -> None:
        self.settings = settings

    def exchange_code(self, code: str) -> WeChatIdentity:
        if not code.strip():
            raise WeChatAuthError("empty login code")
        if self.settings.wechat_auth_mode == "mock":
            return WeChatIdentity(openid=f"mock:{code.strip()}")
        if self.settings.wechat_auth_mode != "wechat":
            raise WeChatAuthError("wechat login is not configured")

        query = urllib.parse.urlencode(
            {
                "appid": self.settings.wechat_app_id,
                "secret": self.settings.wechat_app_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            }
        )
        request = urllib.request.Request(
            f"https://api.weixin.qq.com/sns/jscode2session?{query}",
            headers={"accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise WeChatAuthError("wechat login service unavailable") from exc

        if payload.get("errcode") or not payload.get("openid"):
            raise WeChatAuthError(f"wechat login rejected: {payload.get('errcode', 'invalid_response')}")
        return WeChatIdentity(openid=str(payload["openid"]), unionid=payload.get("unionid"))

