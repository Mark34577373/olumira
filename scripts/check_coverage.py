"""Security-sensitive and core branch-aware coverage gates from actual pytest JSON."""

import argparse
import json
from pathlib import Path

SECURITY = {
    "authentication",
    "account_recovery",
    "collaboration",
    "workspaces",
    "privacy",
    "email_delivery",
    "security_recovery",
    "care_plans",
    "handoff_drafts",
}
SECURITY_HTTP = {
    "olumira/__init__.py",
    "olumira/config.py",
    "olumira/forms.py",
    "olumira/privacy_logging.py",
    "olumira/infrastructure.py",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="artifacts/day41-42/coverage.json")
    args = parser.parse_args()
    files = json.loads(Path(args.report).read_text())["files"]
    required = (
        {str(path) for path in Path("services").glob("*.py")}
        | SECURITY_HTTP
        | {str(path) for path in Path("olumira/routes").glob("*.py")}
    )
    missing = sorted(required - set(files))
    if missing:
        print(json.dumps({"missing_coverage_files": missing}))
        raise SystemExit(1)
    groups = {"security": [], "core": []}
    for name, data in files.items():
        if name.startswith("services/"):
            groups["core"].append(data["summary"])
        if (
            (name.startswith("services/") and Path(name).stem in SECURITY)
            or name in SECURITY_HTTP
            or name.startswith("olumira/routes/")
        ):
            groups["security"].append(data["summary"])
    results = {}
    for group, target in [("security", 85), ("core", 80)]:
        summaries = groups[group]
        total = sum(s["num_statements"] + s["num_branches"] for s in summaries)
        covered = sum(s["covered_lines"] + s["covered_branches"] for s in summaries)
        percent = 100 * covered / total if total else 0
        results[group] = dict(
            percent=round(percent, 2),
            target=target,
            passed=bool(total and percent >= target),
        )
    print(json.dumps(results, indent=2))
    if not all(r["passed"] for r in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
