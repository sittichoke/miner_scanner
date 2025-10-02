# scanner.py

import argparse
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from antminer.discover import LocalMiners
from collector import Collector
from db import DB
from rest_client import RestClient
from dotenv import load_dotenv

load_dotenv()

SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))
MAX_WORKERS = 32


def parse_args():
    p = argparse.ArgumentParser(description="ASIC‑miner scanner")
    p.add_argument(
        "-s", "--subnet",
        help="IPv4 subnet (CIDR or wildcard) to scan, "
             "e.g. 192.168.2.0/24 or 192.168.2.*  "
             "(overrides SUBNET env)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    subnet = args.subnet or os.getenv("SUBNET", "192.168.0.*")

    # ─── Configure sinks ────────────────────────────────────────────────
    db = DB() if os.getenv("ENABLE_DB", "true").lower() == "true" else None

    rest = None
    if api_url := os.getenv("API_URL"):
        rest = RestClient(
            base_url=api_url,
            api_key=os.getenv("API_KEY"),
            timeout=int(os.getenv("API_TIMEOUT", "10")),
        )

    collector = Collector(db=db, rest_client=rest)
    network = LocalMiners()

    while True:
        cycle_start = time.perf_counter()
        try:
            miners = network.discover(subnet)
            print(f"[Scanner] subnet {subnet} → {len(miners)} device(s) online")

            if miners:
                # Optional: parallelize stats fetching here, but collect_all calls stats() internally
                collector.collect_all_online(miners)

        except Exception:
            traceback.print_exc()

        time_spent = time.perf_counter() - cycle_start
        time.sleep(max(0, SCAN_INTERVAL - time_spent))


if __name__ == "__main__":
    main()
