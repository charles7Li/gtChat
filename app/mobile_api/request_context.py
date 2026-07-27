from __future__ import annotations

from contextvars import ContextVar, Token


_REQUEST_ID: ContextVar[str] = ContextVar("mobile_request_id", default="")


def set_request_id(request_id: str) -> Token[str]:
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _REQUEST_ID.reset(token)


def get_request_id() -> str | None:
    return _REQUEST_ID.get() or None
