from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MobileSettings:
    db_path: Path = Path(".tmp/mobile/mobile.db")
    database_url: str = ""
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
    identity_secret: str = "change-me-in-production"
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 30 * 24 * 3600
    max_upload_bytes: int = 50 * 1024 * 1024
    worker_lease_seconds: int = 300
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

    @classmethod
    def from_env(cls) -> "MobileSettings":
        return cls(
            db_path=Path(os.getenv("MOBILE_DB_PATH", ".tmp/mobile/mobile.db")),
            database_url=os.getenv("MOBILE_DATABASE_URL", ""),
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
            identity_secret=os.getenv("MOBILE_IDENTITY_SECRET", "change-me-in-production"),
            access_token_ttl_seconds=int(os.getenv("MOBILE_ACCESS_TOKEN_TTL", "3600")),
            refresh_token_ttl_seconds=int(os.getenv("MOBILE_REFRESH_TOKEN_TTL", str(30 * 24 * 3600))),
            max_upload_bytes=int(os.getenv("MOBILE_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))),
            worker_lease_seconds=int(os.getenv("MOBILE_WORKER_LEASE_SECONDS", "300")),
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
        )

    def validate(self) -> None:
        if self.wechat_auth_mode not in {"disabled", "mock", "wechat"}:
            raise ValueError("WECHAT_AUTH_MODE must be disabled, mock, or wechat")
        if self.wechat_auth_mode == "wechat" and (not self.wechat_app_id or not self.wechat_app_secret):
            raise ValueError("WECHAT_APP_ID and WECHAT_APP_SECRET are required in wechat mode")
        if self.identity_secret == "change-me-in-production" and self.wechat_auth_mode == "wechat":
            raise ValueError("MOBILE_IDENTITY_SECRET must be changed in wechat mode")
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
        if self.wechat_notification_max_attempts < 1:
            raise ValueError("WECHAT_NOTIFICATION_MAX_ATTEMPTS must be positive")
