from __future__ import annotations

from .postgres_store import PostgresMobileStore
from .settings import MobileSettings


def main() -> None:
    settings = MobileSettings.from_env()
    settings.validate()
    if not settings.database_url:
        raise SystemExit("MOBILE_DATABASE_URL is required")
    store = PostgresMobileStore(
        settings.database_url,
        settings.identity_secret,
        outbox_topic=settings.kafka_topic if settings.queue_backend == "kafka" else None,
        notifications_enabled=bool(settings.wechat_task_template_id),
        initialize_schema=True,
        previous_identity_secrets=settings.identity_previous_secrets,
    )
    store.close()
    print("mobile database migration complete")


if __name__ == "__main__":
    main()
