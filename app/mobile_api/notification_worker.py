from __future__ import annotations

import argparse
import time
from typing import Any
from uuid import uuid4

from .service import MobileRuntime
from .wechat_services import WeChatApiError, WeChatServerApi


class NotificationWorker:
    def __init__(self, runtime: MobileRuntime, sender: WeChatServerApi | None = None) -> None:
        self.runtime = runtime
        self.store = runtime.store
        self.sender = sender or runtime.wechat_server
        self.worker_id = f"notify-{uuid4().hex[:12]}"

    def run_once(self) -> bool:
        self.store.heartbeat(self.worker_id, "wechat-notifier")
        notification = self.store.claim_notification(self.worker_id)
        if not notification:
            return False
        try:
            consent = self.store.reserve_notification_consent(notification["id"], self.worker_id)
            if not consent:
                self.store.finish_notification(notification["id"], self.worker_id, "skipped", "no one-time consent")
                return True
            job = self.store.get_job_internal(notification["job_id"])
            openid = self.store.get_user_openid(notification["user_id"])
            if not job or not openid:
                self.store.finish_notification(notification["id"], self.worker_id, "failed", "recipient is unavailable")
                return True
            self.sender.send_job_completed(openid, job)
            self.store.finish_notification(notification["id"], self.worker_id, "sent")
        except WeChatApiError as exc:
            self._retry_or_fail(notification, exc)
        except Exception as exc:
            self._retry_or_fail(notification, exc)
        return True

    def _retry_or_fail(self, notification: dict[str, Any], exc: Exception) -> None:
        attempts = int(notification.get("attempts") or 1)
        if attempts >= self.runtime.settings.wechat_notification_max_attempts:
            self.store.finish_notification(notification["id"], self.worker_id, "failed", str(exc))
            return
        delay = min(30 * (2 ** max(attempts - 1, 0)), 900)
        self.store.retry_notification(notification["id"], self.worker_id, str(exc), delay)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Mochi Scout WeChat subscription notifications")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    runtime = MobileRuntime()
    if not runtime.settings.wechat_task_template_id:
        raise SystemExit("WECHAT_TASK_TEMPLATE_ID is required")
    worker = NotificationWorker(runtime)
    while True:
        acted = worker.run_once()
        if args.once:
            return
        if not acted:
            time.sleep(max(args.interval, 0.2))


if __name__ == "__main__":
    main()
