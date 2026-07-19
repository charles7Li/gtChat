from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from .settings import MobileSettings
from .store import MobileStore


def producer_config(settings: MobileSettings) -> dict[str, Any]:
    config: dict[str, Any] = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": settings.kafka_client_id,
        "enable.idempotence": True,
        "acks": "all",
    }
    _add_security(config, settings)
    return config


def consumer_config(settings: MobileSettings) -> dict[str, Any]:
    config: dict[str, Any] = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": f"{settings.kafka_client_id}-worker",
        "group.id": settings.kafka_group_id,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    }
    _add_security(config, settings)
    return config


def create_producer(settings: MobileSettings) -> Any:
    try:
        from confluent_kafka import Producer
    except ImportError as exc:  # pragma: no cover - production dependency
        raise RuntimeError("Kafka requires the mobile-prod dependency extra") from exc
    return Producer(producer_config(settings))


def create_consumer(settings: MobileSettings) -> Any:
    try:
        from confluent_kafka import Consumer
    except ImportError as exc:  # pragma: no cover - production dependency
        raise RuntimeError("Kafka requires the mobile-prod dependency extra") from exc
    return Consumer(consumer_config(settings))


class OutboxPublisher:
    """Publishes committed database events to Kafka with retryable leases."""

    def __init__(self, store: MobileStore, producer: Any, *, publisher_id: str | None = None) -> None:
        self.store = store
        self.producer = producer
        self.publisher_id = publisher_id or f"outbox-{uuid4().hex[:12]}"

    def publish_once(self, limit: int = 100) -> int:
        events = self.store.claim_outbox(self.publisher_id, limit=limit)
        published = 0
        for event in events:
            try:
                publish_json(
                    self.producer,
                    event["topic"],
                    event["message_key"],
                    event["payload"],
                    headers={"event_id": event["id"], "event_type": event["event_type"]},
                )
            except Exception as exc:
                self.store.release_outbox(event["id"], self.publisher_id, str(exc))
            else:
                self.store.mark_outbox_published(event["id"], self.publisher_id)
                published += 1
        return published


def publish_json(
    producer: Any,
    topic: str,
    key: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> None:
    delivery_error: list[Exception] = []

    def delivered(error: Any, _message: Any) -> None:
        if error is not None:
            delivery_error.append(RuntimeError(str(error)))

    producer.produce(
        topic=topic,
        key=key.encode("utf-8"),
        value=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers=list((headers or {}).items()),
        on_delivery=delivered,
    )
    remaining = producer.flush(10)
    if remaining:
        raise TimeoutError(f"Kafka delivery timed out with {remaining} message(s) pending")
    if delivery_error:
        raise delivery_error[0]


def decode_job_event(value: bytes | str | None) -> dict[str, Any]:
    if value is None:
        raise ValueError("Kafka event has no value")
    try:
        payload = json.loads(value.decode("utf-8") if isinstance(value, bytes) else value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Kafka event is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported Kafka event schema")
    if payload.get("event_type") != "mobile.job.queued" or not isinstance(payload.get("job_id"), str):
        raise ValueError("invalid mobile job event")
    return payload


def _add_security(config: dict[str, Any], settings: MobileSettings) -> None:
    protocol = settings.kafka_security_protocol.upper()
    config["security.protocol"] = protocol
    if protocol.startswith("SASL"):
        config["sasl.mechanism"] = settings.kafka_sasl_mechanism
        config["sasl.username"] = settings.kafka_sasl_username
        config["sasl.password"] = settings.kafka_sasl_password
