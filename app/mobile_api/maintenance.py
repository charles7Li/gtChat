from __future__ import annotations

import argparse
import time
from uuid import uuid4

from .service import MobileRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean expired Mochi Scout mobile delivery and audit records")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=3600)
    args = parser.parse_args()
    runtime = MobileRuntime()
    worker_id = f"maintenance-{uuid4().hex[:12]}"
    while True:
        runtime.store.heartbeat(worker_id, "maintenance")
        removed = runtime.store.run_maintenance(
            runtime.settings.event_retention_days,
            runtime.settings.audit_retention_days,
        )
        print("mobile maintenance", " ".join(f"{key}={value}" for key, value in sorted(removed.items())))
        if args.once:
            return
        time.sleep(max(args.interval, 60))


if __name__ == "__main__":
    main()
