"""Small fictional Flask/SQLite latency sample; not a hosted load/capacity test."""

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from test_communication import CommunicationTests
from support import login


def main():
    fixture = CommunicationTests()
    fixture.setUp()
    report = {
        "environment": "local Flask test client, temporary SQLite, fictional accounts",
        "limitations": "Five sequential requests per path, no network/TLS/concurrency; not production capacity",
        "samples": {},
    }
    try:
        paths = {
            "dashboard": "/",
            "routines": "/routines",
            "observations": "/observations",
            "calendar": "/calendar",
            "reports": "/observations/reports",
        }
        for label, path in paths.items():
            durations, statuses = [], []
            for _ in range(5):
                start = time.perf_counter()
                response = fixture.client.get(path, follow_redirects=True)
                durations.append(round((time.perf_counter() - start) * 1000, 2))
                statuses.append(response.status_code)
            if statuses != [200] * 5:
                raise RuntimeError("Sample path did not succeed: " + label)
            report["samples"][label] = {
                "n": 5,
                "median_ms": statistics.median(durations),
                "max_ms": max(durations),
                "status": 200,
            }
        durations = []
        for _ in range(5):
            client = fixture.app.test_client()
            start = time.perf_counter()
            response = login(client, "fiction-board@example.com")
            durations.append(round((time.perf_counter() - start) * 1000, 2))
            if response.status_code != 302:
                raise RuntimeError("Login sample failed")
        report["samples"]["login_with_csrf_page"] = dict(
            n=5,
            median_ms=statistics.median(durations),
            max_ms=max(durations),
            status=302,
        )
        output = ROOT / "artifacts/day43/local-performance.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    main()
