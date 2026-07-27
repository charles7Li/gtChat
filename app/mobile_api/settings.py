from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MobileSettings:
    environment: str = "development"
    db_path: Path = Path(".tmp/mobile/mobile.db")
    database_url: str = ""
    auto_migrate: bool = True
    object_root: Path = Path(".tmp/mobile/objects")
    object_backend: str = "local"
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_session_token: str = ""
    s3_prefix: str = "mochi-scout"
    upload_url_ttl_seconds: int = 900
    workflow_root: Path = Path("outputs/mobile_runs")
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_auth_mode: str = "disabled"
    wechat_task_template_id: str = ""
    wechat_task_template_title_key: str = "thing1"
    wechat_task_template_status_key: str = "phrase2"
    wechat_task_template_time_key: str = "time3"
    wechat_content_security_enabled: bool = False
    wechat_notification_max_attempts: int = 5
    media_moderation_mode: str = "disabled"
    media_moderation_url: str = ""
    media_moderation_token: str = ""
    require_legal_consent: bool = False
    legal_consent_version: str = "2026-07-20"
    event_retention_days: int = 7
    audit_retention_days: int = 90
    identity_secret: str = "change-me-in-production"
    identity_previous_secrets: tuple[str, ...] = ()
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 30 * 24 * 3600
    max_upload_bytes: int = 50 * 1024 * 1024
    accept_new_jobs: bool = True
    worker_lease_seconds: int = 300
    login_rate_limit_per_minute: int = 30
    job_rate_limit_per_minute: int = 10
    upload_rate_limit_per_minute: int = 30
    queue_backend: str = "database"
    kafka_bootstrap_servers: str = ""
    kafka_topic: str = "mochi.mobile.jobs.v1"
    kafka_retry_topic: str = "mochi.mobile.jobs.retry.v1"
    kafka_dlq_topic: str = "mochi.mobile.jobs.dlq.v1"
    kafka_group_id: str = "mochi-mobile-workers-v1"
    kafka_client_id: str = "mochi-mobile"
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: str = "PLAIN"
    kafka_sasl_username: str = ""
    kafka_sasl_password: str = ""
    kafka_max_attempts: int = 3
    kafka_max_poll_interval_ms: int = 3_600_000

    @classmethod
    def from_env(cls) -> "MobileSettings":
        return cls(
            environment=os.getenv("MOCHI_ENV", "development").lower(),
            db_path=Path(os.getenv("MOBILE_DB_PATH", ".tmp/mobile/mobile.db")),
            database_url=os.getenv("MOBILE_DATABASE_URL", ""),
            auto_migrate=os.getenv(
                "MOBILE_AUTO_MIGRATE",
                "false" if os.getenv("MOCHI_ENV", "development").lower() == "production" else "true",
            ).lower()
            in {"1", "true", "yes"},
            object_root=Path(os.getenv("MOBILE_OBJECT_ROOT", ".tmp/mobile/objects")),
            object_backend=os.getenv("MOBILE_OBJECT_BACKEND", "local").lower(),
            s3_bucket=os.getenv("MOBILE_S3_BUCKET", ""),
            s3_region=os.getenv("MOBILE_S3_REGION", ""),
            s3_endpoint_url=os.getenv("MOBILE_S3_ENDPOINT_URL", ""),
            s3_access_key_id=os.getenv("MOBILE_S3_ACCESS_KEY_ID", ""),
            s3_secret_access_key=os.getenv("MOBILE_S3_SECRET_ACCESS_KEY", ""),
            s3_session_token=os.getenv("MOBILE_S3_SESSION_TOKEN", ""),
            s3_prefix=os.getenv("MOBILE_S3_PREFIX", "mochi-scout"),
            upload_url_ttl_seconds=int(os.getenv("MOBILE_UPLOAD_URL_TTL", "900")),
            workflow_root=Path(os.getenv("MOBILE_WORKFLOW_ROOT", "outputs/mobile_runs")),
            wechat_app_id=os.getenv("WECHAT_APP_ID", ""),
            wechat_app_secret=os.getenv("WECHAT_APP_SECRET", ""),
            wechat_auth_mode=os.getenv("WECHAT_AUTH_MODE", "disabled").lower(),
            wechat_task_template_id=os.getenv("WECHAT_TASK_TEMPLATE_ID", ""),
            wechat_task_template_title_key=os.getenv("WECHAT_TASK_TEMPLATE_TITLE_KEY", "thing1"),
            wechat_task_template_status_key=os.getenv("WECHAT_TASK_TEMPLATE_STATUS_KEY", "phrase2"),
            wechat_task_template_time_key=os.getenv("WECHAT_TASK_TEMPLATE_TIME_KEY", "time3"),
            wechat_content_security_enabled=os.getenv("WECHAT_CONTENT_SECURITY_ENABLED", "false").lower()
            in {"1", "true", "yes"},
            wechat_notification_max_attempts=int(os.getenv("WECHAT_NOTIFICATION_MAX_ATTEMPTS", "5")),
            media_moderation_mode=os.getenv("MOBILE_MEDIA_MODERATION_MODE", "disabled").lower(),
            media_moderation_url=os.getenv("MOBILE_MEDIA_MODERATION_URL", ""),
            media_moderation_token=os.getenv("MOBILE_MEDIA_MODERATION_TOKEN", ""),
            require_legal_consent=os.getenv(
                "MOBILE_REQUIRE_LEGAL_CONSENT",
                "true" if os.getenv("MOCHI_ENV", "development").lower() == "production" else "false",
            ).lower()
            in {"1", "true", "yes"},
            legal_consent_version=os.getenv("MOBILE_LEGAL_CONSENT_VERSION", "2026-07-20"),
            event_retention_days=int(os.getenv("MOBILE_EVENT_RETENTION_DAYS", "7")),
            audit_retention_days=int(os.getenv("MOBILE_AUDIT_RETENTION_DAYS", "90")),
            identity_secret=os.getenv("MOBILE_IDENTITY_SECRET", "change-me-in-production"),
            identity_previous_secrets=tuple(
                value.strip()
                for value in os.getenv("MOBILE_IDENTITY_PREVIOUS_SECRETS", "").split(",")
                if value.strip()
            ),
            access_token_ttl_seconds=int(os.getenv("MOBILE_ACCESS_TOKEN_TTL", "3600")),
            refresh_token_ttl_seconds=int(os.getenv("MOBILE_REFRESH_TOKEN_TTL", str(30 * 24 * 3600))),
            max_upload_bytes=int(os.getenv("MOBILE_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))),
            accept_new_jobs=os.getenv("MOBILE_ACCEPT_NEW_JOBS", "true").lower() in {"1", "true", "yes"},
            worker_lease_seconds=int(os.getenv("MOBILE_WORKER_LEASE_SECONDS", "300")),
            login_rate_limit_per_minute=int(os.getenv("MOBILE_LOGIN_RATE_LIMIT_PER_MINUTE", "30")),
            job_rate_limit_per_minute=int(os.getenv("MOBILE_JOB_RATE_LIMIT_PER_MINUTE", "10")),
            upload_rate_limit_per_minute=int(os.getenv("MOBILE_UPLOAD_RATE_LIMIT_PER_MINUTE", "30")),
            queue_backend=os.getenv("MOBILE_QUEUE_BACKEND", "database").lower(),
            kafka_bootstrap_servers=os.getenv("MOBILE_KAFKA_BOOTSTRAP_SERVERS", ""),
            kafka_topic=os.getenv("MOBILE_KAFKA_TOPIC", "mochi.mobile.jobs.v1"),
            kafka_retry_topic=os.getenv("MOBILE_KAFKA_RETRY_TOPIC", "mochi.mobile.jobs.retry.v1"),
            kafka_dlq_topic=os.getenv("MOBILE_KAFKA_DLQ_TOPIC", "mochi.mobile.jobs.dlq.v1"),
            kafka_group_id=os.getenv("MOBILE_KAFKA_GROUP_ID", "mochi-mobile-workers-v1"),
            kafka_client_id=os.getenv("MOBILE_KAFKA_CLIENT_ID", "mochi-mobile"),
            kafka_security_protocol=os.getenv("MOBILE_KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
            kafka_sasl_mechanism=os.getenv("MOBILE_KAFKA_SASL_MECHANISM", "PLAIN"),
            kafka_sasl_username=os.getenv("MOBILE_KAFKA_SASL_USERNAME", ""),
            kafka_sasl_password=os.getenv("MOBILE_KAFKA_SASL_PASSWORD", ""),
            kafka_max_attempts=int(os.getenv("MOBILE_KAFKA_MAX_ATTEMPTS", "3")),
            kafka_max_poll_interval_ms=int(os.getenv("MOBILE_KAFKA_MAX_POLL_INTERVAL_MS", "3600000")),
        )

    def validate(self) -> None:
        if self.environment not in {"development", "staging", "production"}:
            raise ValueError("MOCHI_ENV must be development, staging, or production")
        if self.wechat_auth_mode not in {"disabled", "mock", "wechat"}:
            raise ValueError("WECHAT_AUTH_MODE must be disabled, mock, or wechat")
        if self.wechat_auth_mode == "wechat" and (not self.wechat_app_id or not self.wechat_app_secret):
            raise ValueError("WECHAT_APP_ID and WECHAT_APP_SECRET are required in wechat mode")
        if self.identity_secret == "change-me-in-production" and self.wechat_auth_mode == "wechat":
            raise ValueError("MOBILE_IDENTITY_SECRET must be changed in wechat mode")
        if self.identity_secret in self.identity_previous_secrets:
            raise ValueError("MOBILE_IDENTITY_PREVIOUS_SECRETS must not include the current secret")
        if self.max_upload_bytes <= 0:
            raise ValueError("MOBILE_MAX_UPLOAD_BYTES must be positive")
        if self.object_backend not in {"local", "s3"}:
            raise ValueError("MOBILE_OBJECT_BACKEND must be local or s3")
        if self.object_backend == "s3" and not self.s3_bucket:
            raise ValueError("MOBILE_S3_BUCKET is required for s3 object storage")
        if self.wechat_auth_mode == "wechat" and not self.database_url:
            raise ValueError("MOBILE_DATABASE_URL is required in wechat mode")
        if self.wechat_auth_mode == "wechat" and self.object_backend != "s3":
            raise ValueError("MOBILE_OBJECT_BACKEND=s3 is required in wechat mode")
        if self.worker_lease_seconds < 30:
            raise ValueError("MOBILE_WORKER_LEASE_SECONDS must be at least 30")
        if min(self.login_rate_limit_per_minute, self.job_rate_limit_per_minute, self.upload_rate_limit_per_minute) < 1:
            raise ValueError("mobile rate limits must be positive")
        if self.queue_backend not in {"database", "kafka"}:
            raise ValueError("MOBILE_QUEUE_BACKEND must be database or kafka")
        if self.queue_backend == "kafka" and not self.kafka_bootstrap_servers:
            raise ValueError("MOBILE_KAFKA_BOOTSTRAP_SERVERS is required for the kafka queue")
        if self.queue_backend == "kafka" and not self.database_url:
            raise ValueError("MOBILE_DATABASE_URL is required for the kafka queue")
        if self.queue_backend == "kafka" and self.kafka_security_protocol.upper().startswith("SASL"):
            if not self.kafka_sasl_username or not self.kafka_sasl_password:
                raise ValueError("Kafka SASL username and password are required for SASL security protocols")
        if self.kafka_max_attempts < 1:
            raise ValueError("MOBILE_KAFKA_MAX_ATTEMPTS must be positive")
        if self.kafka_max_poll_interval_ms < 300_000:
            raise ValueError("MOBILE_KAFKA_MAX_POLL_INTERVAL_MS must be at least 300000")
        if self.wechat_notification_max_attempts < 1:
            raise ValueError("WECHAT_NOTIFICATION_MAX_ATTEMPTS must be positive")
        if min(self.event_retention_days, self.audit_retention_days) < 1:
            raise ValueError("mobile retention periods must be positive")
        if self.media_moderation_mode not in {"disabled", "webhook"}:
            raise ValueError("MOBILE_MEDIA_MODERATION_MODE must be disabled or webhook")
        if self.media_moderation_mode == "webhook" and not self.media_moderation_url:
            raise ValueError("MOBILE_MEDIA_MODERATION_URL is required for webhook moderation")
        if self.environment == "production":
            if self.wechat_auth_mode != "wechat":
                raise ValueError("WECHAT_AUTH_MODE=wechat is required in production")
            if self.queue_backend != "kafka":
                raise ValueError("MOBILE_QUEUE_BACKEND=kafka is required in production")
            if not self.wechat_task_template_id:
                raise ValueError("WECHAT_TASK_TEMPLATE_ID is required in production")
            if not self.wechat_content_security_enabled:
                raise ValueError("WECHAT_CONTENT_SECURITY_ENABLED=true is required in production")
            if self.media_moderation_mode != "webhook":
                raise ValueError("MOBILE_MEDIA_MODERATION_MODE=webhook is required in production")
            if not self.require_legal_consent:
                raise ValueError("MOBILE_REQUIRE_LEGAL_CONSENT=true is required in production")
