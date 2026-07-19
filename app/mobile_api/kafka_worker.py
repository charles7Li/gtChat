from __future__ import annotations

import argparse
import time
from typing import Any

from .kafka_bus import OutboxPublisher, create_consumer, create_producer, decode_job_event, publish_json
from .service import MobileRuntime


class KafkaJobWorker:
    def __init__(self, runtime: MobileRuntime, consumer: Any, producer: Any) -> None:
        self.runtime = runtime
        self.consumer = consumer
        self.producer = producer
        self.settings = runtime.settings

    def handle(self, message: Any) -> None:
        try:
            payload = decode_job_event(message.value())
            self.runtime.run_job(payload["job_id"])
        except Exception as exc:
            payload = _best_effort_payload(message.value())
            attempt = int(payload.get("delivery_attempt", 0)) + 1
            payload["delivery_attempt"] = attempt
            payload["last_error"] = str(exc)[:1000]
            topic = self.settings.kafka_retry_topic if attempt < self.settings.kafka_max_attempts else self.settings.kafka_dlq_topic
            publish_json(self.producer, topic, str(payload.get("job_id") or "invalid"), payload)
        self.consumer.commit(message=message, asynchronous=False)

    def run_once(self, timeout: float = 1.0) -> bool:
        message = self.consumer.poll(timeout)
        if message is None:
            return False
        if message.error():
            raise RuntimeError(str(message.error()))
        self.handle(message)
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Mochi Scout Kafka mobile jobs")
    parser.add_argument("mode", choices=("outbox", "worker", "all"), default="all", nargs="?")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    runtime = MobileRuntime()
    if runtime.settings.queue_backend != "kafka":
        raise SystemExit("MOBILE_QUEUE_BACKEND must be kafka")
    producer = create_producer(runtime.settings)
    publisher = OutboxPublisher(runtime.store, producer)
    consumer = None
    if args.mode in {"worker", "all"}:
        consumer = create_consumer(runtime.settings)
        consumer.subscribe([runtime.settings.kafka_topic, runtime.settings.kafka_retry_topic])
    try:
        while True:
            acted = False
            if args.mode in {"outbox", "all"}:
                acted = bool(publisher.publish_once())
            if consumer is not None:
                acted = KafkaJobWorker(runtime, consumer, producer).run_once(0.2) or acted
            if args.once:
                return
            if not acted:
                time.sleep(max(args.interval, 0.2))
    finally:
        if consumer is not None:
            consumer.close()


def _best_effort_payload(value: bytes | str | None) -> dict[str, Any]:
    try:
        import json

        parsed = json.loads(value.decode("utf-8") if isinstance(value, bytes) else value or "{}")
        return parsed if isinstance(parsed, dict) else {"raw_value": str(parsed)}
    except Exception:
        return {"raw_value": repr(value)[:2000]}


if __name__ == "__main__":
    main()
