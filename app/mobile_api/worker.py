from __future__ import annotations

import argparse
import time

from .service import MobileRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Mochi Scout mobile workflow jobs")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    runtime = MobileRuntime()
    runtime.store.heartbeat(runtime.worker_id, "database-worker")
    if args.once:
        runtime.run_next_job()
        return
    while True:
        runtime.store.heartbeat(runtime.worker_id, "database-worker")
        if runtime.run_next_job() is None:
            time.sleep(max(args.interval, 0.2))


if __name__ == "__main__":
    main()
