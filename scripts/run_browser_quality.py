"""Run existing fictional-data journeys, retaining exact per-script evidence."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNEYS = [
    "check_product_experience",
    "check_guided_routines",
    "check_communication_boards",
    "check_workspaces",
    "check_personalized_care",
    "check_journal_reports",
    "check_premium_control",
    "check_navigation_refinement",
    "check_premium_transformation",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=JOURNEYS)
    args = parser.parse_args()
    out = ROOT / "artifacts/day41-42/browser"
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "report.json"
    results = (
        json.loads(report_path.read_text())
        if args.only and report_path.exists()
        else []
    )
    for name in args.only or JOURNEYS:
        start = time.monotonic()
        command = [sys.executable, str(ROOT / "tests/browser" / f"{name}.py")]
        if name == "check_premium_transformation":
            command.append("--day-40-2")
        with (out / f"{name}.log").open("w") as log:
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=300,
                # Reviewed: selected local test scripts, no shell
            )  # nosec B603
        entry = dict(
            script=name,
            exit_code=result.returncode,
            seconds=round(time.monotonic() - start, 2),
        )
        results = [item for item in results if item["script"] != name]
        results.append(entry)
        (out / "report.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(entry), flush=True)
    if any(item["exit_code"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
