"""One finite cron invocation. DB is the durable queue; no process-local timers."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = (
    ["process-reminders"],
    ["mail-send-pending", "--limit", "100"],
    ["mail-retention", "--apply"],
    ["privacy-maintenance"],
)


def main():
    failed = False
    for command in COMMANDS:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "flask", "--app", "app", *command],
                cwd=ROOT,
                timeout=240,
                check=False,
            )
            failed |= result.returncode != 0
        except subprocess.TimeoutExpired:
            print(
                "Operational command exceeded its deadline; inspect private operator console.",
                file=sys.stderr,
            )
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
