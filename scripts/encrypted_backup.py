"""Bounded encrypted logical backup; operator supplies libpq environment, never URL args.

No uploads or retention deletion. Transfer the encrypted output to reviewed durable storage.
For databases over 64 MiB use a reviewed streaming backup service instead.
"""

import os
import subprocess
import threading
from pathlib import Path

from cryptography.fernet import Fernet

MAX_DUMP = 64 * 1024 * 1024


def write_encrypted(payload, destination, key):
    if not payload.startswith(b"PGDMP") or len(payload) > MAX_DUMP:
        raise ValueError("Unsupported or oversized backup")
    encrypted = Fernet(key).encrypt(payload)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encrypted)
        handle.flush()
        os.fsync(handle.fileno())
    # Authenticate a read-back before reporting success. Never print contents.
    if Fernet(key).decrypt(Path(destination).read_bytes()) != payload:
        raise ValueError("Backup verification failed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    key = os.environ["BACKUP_ENCRYPTION_KEY"].encode()
    Fernet(key)  # Validate before contacting PostgreSQL.
    if os.environ.get("PGSSLMODE") != "verify-full":
        raise ValueError("PGSSLMODE=verify-full required")
    if not all(os.environ.get(k) for k in ("PGHOST", "PGDATABASE", "PGUSER")):
        raise ValueError("Explicit libpq host/database/user required")
    with subprocess.Popen(
        ["pg_dump", "--format=custom", "--no-owner", "--no-acl"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as process:
        deadline = threading.Timer(240, process.kill)
        deadline.start()
        try:
            payload = process.stdout.read(MAX_DUMP + 1)
            if len(payload) > MAX_DUMP:
                raise ValueError(
                    "Use a reviewed streaming backup for this database size"
                )
            if process.wait(timeout=60):
                raise ValueError("pg_dump failed")
            write_encrypted(payload, args.output, key)
        finally:
            deadline.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
    print(
        "Encrypted backup authenticated locally. Durable upload and retention remain operator responsibilities."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "Backup failed; no connection details or payload logged."
        ) from None
