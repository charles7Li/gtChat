from __future__ import annotations

import os
import urllib.parse

from .settings import MobileSettings


def main() -> None:
    settings = MobileSettings.from_env()
    settings.validate()
    errors: list[str] = []
    if settings.environment != "production":
        errors.append("MOCHI_ENV must be production")
    if settings.auto_migrate:
        errors.append("MOBILE_AUTO_MIGRATE must be false for application processes")
    if len(settings.identity_secret) < 32:
        errors.append("MOBILE_IDENTITY_SECRET must contain at least 32 characters")
    if len(os.getenv("MOCHI_WEB_ADMIN_TOKEN", "")) < 24:
        errors.append("MOCHI_WEB_ADMIN_TOKEN must contain at least 24 characters")
    if settings.kafka_security_protocol.upper() not in {"SSL", "SASL_SSL"}:
        errors.append("production Kafka must use SSL or SASL_SSL")
    for name, value in (
        ("MOBILE_MEDIA_MODERATION_URL", settings.media_moderation_url),
        ("MOBILE_S3_ENDPOINT_URL", settings.s3_endpoint_url),
    ):
        if value and urllib.parse.urlparse(value).scheme.lower() != "https":
            errors.append(f"{name} must use https")
    if errors:
        raise SystemExit("production preflight failed:\n- " + "\n- ".join(errors))
    print("production preflight passed")
    print("configuration: postgres + s3 + kafka + wechat + moderation + notification")


if __name__ == "__main__":
    main()
