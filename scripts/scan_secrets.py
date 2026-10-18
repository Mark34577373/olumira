"""Conservative local tracked/history secret scan. Never emit matched values.

This detects high-confidence key/token formats, not arbitrary passwords. Findings
require private review and rotation; zero matches is not proof of no secrets.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "private-key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "aws-access-key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "github-token": re.compile(
        rb"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,})\b"
    ),
    "provider-secret": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b"),
}


def matches(data, location):
    return [
        dict(location=location, line=data[: m.start()].count(b"\n") + 1, kind=kind)
        for kind, pattern in PATTERNS.items()
        for m in pattern.finditer(data)
    ]


def git(*args):
    # Reviewed: fixed local git argv; no shell, no external input
    return subprocess.run(
        ["git", *args], check=True, capture_output=True
    ).stdout  # nosec B603,B607


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--output", default="artifacts/day41-42/secrets.json")
    args = parser.parse_args()
    findings = []
    scanned = 0
    # Include new implementation files while excluding ignored data/venvs/artifacts.
    for name in git(
        "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    ).split(b"\0"):
        if not name:
            continue
        path = Path(name.decode())
        if path.is_file():
            findings.extend(matches(path.read_bytes(), str(path)))
            scanned += 1
    history_blobs = 0
    if args.history:
        # Content-addressed blobs are scanned once across all reachable history.
        objects = git("rev-list", "--objects", "--all").splitlines()
        for item in objects:
            parts = item.split(b" ", 1)
            if len(parts) != 2:
                continue
            oid, name = parts
            if git("cat-file", "-t", oid.decode()).strip() != b"blob":
                continue
            history_blobs += 1
            findings.extend(
                matches(
                    git("cat-file", "blob", oid.decode()),
                    "history:" + oid.decode() + ":" + name.decode(errors="replace"),
                )
            )
    report = dict(
        working_files=scanned,
        history_blobs=history_blobs,
        findings=findings,
        limitation="High-confidence pattern scan; arbitrary credentials and unreachable Git objects require separate operator review.",
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            dict(
                working_files=scanned,
                history_blobs=history_blobs,
                finding_count=len(findings),
            )
        )
    )
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
