"""Use supplied PostgreSQL binaries to test fresh private socket-only databases.

Never opens an operator-supplied database. Preserves private temporary files for
inspection, stops the server in finally, and does not install a system service.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", required=True, type=Path)
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run complete pytest suite; default is the two live PostgreSQL cases",
    )
    parser.add_argument("--append-coverage", action="store_true")
    parser.add_argument(
        "--artifact-dir", type=Path, default=ROOT / "artifacts/day41-42"
    )
    args = parser.parse_args()
    binary = args.bin_dir.resolve()
    for name in [
        "postgres",
        "initdb",
        "pg_ctl",
        "createdb",
        "pg_dump",
        "pg_restore",
        "psql",
    ]:
        if not (binary / name).is_file():
            parser.error("Missing required PostgreSQL binary: " + name)
    directory = Path(tempfile.mkdtemp(prefix="olumira-pg-qa-", dir="/tmp"))
    directory.chmod(0o700)
    data = directory / "data"
    sock = directory / "socket"
    sock.mkdir(mode=0o700)
    output = args.artifact_dir
    output.mkdir(parents=True, exist_ok=True)

    def run(command, **kwargs):
        # Selected supplied binaries + argv, no shell and no database credentials.
        return subprocess.run(
            [str(binary / command[0]), *command[1:]], check=True, **kwargs
        )  # nosec B603

    version = run(
        ["postgres", "--version"], capture_output=True, text=True
    ).stdout.strip()
    run(
        [
            "initdb",
            "-D",
            str(data),
            "--no-locale",
            "--encoding=UTF8",
            "--username=qa",
            "-A",
            "trust",
        ],
        stdout=subprocess.DEVNULL,
    )
    started = False
    try:
        run(
            [
                "pg_ctl",
                "-D",
                str(data),
                "-l",
                str(directory / "server.log"),
                "-o",
                f"-k {sock} -h '' -p 55461",
                "-w",
                "start",
            ]
        )
        started = True
        for name in ["olumira_test", "olumira_security_test"]:
            run(["createdb", "-h", str(sock), "-p", "55461", "-U", "qa", name])
        environment = dict(
            os.environ,
            APP_ENV="testing",
            TEST_POSTGRES_URL=f"postgresql+psycopg://qa@/olumira_test?host={sock}&port=55461",
            TEST_POSTGRES_SECURITY_URL=f"postgresql+psycopg://qa@/olumira_security_test?host={sock}&port=55461",
        )
        command = [sys.executable, "-m", "pytest", "-q"]
        if not args.full:
            command += ["tests/test_postgres.py", "tests/test_postgres_security.py"]
        command += [
            "--cov",
            "--cov-report=json",
            "--cov-report=xml",
            f'--junitxml={output / ("pytest-final.xml" if args.full else "postgres.xml")}',
        ]
        if args.append_coverage:
            command.append("--cov-append")
        result = subprocess.run(command, cwd=ROOT, env=environment)  # nosec B603
        if result.returncode:
            raise SystemExit(result.returncode)
        run(
            [
                "pg_dump",
                "-h",
                str(sock),
                "-p",
                "55461",
                "-U",
                "qa",
                "-Fc",
                "-f",
                str(directory / "synthetic.dump"),
                "olumira_security_test",
            ]
        )
        run(
            [
                "createdb",
                "-h",
                str(sock),
                "-p",
                "55461",
                "-U",
                "qa",
                "olumira_release_test",
            ]
        )
        release_environment = dict(
            environment,
            MIGRATION_DATABASE_URL=f"postgresql+psycopg://qa@/olumira_release_test?host={sock}&port=55461",
        )
        subprocess.run(
            [sys.executable, "scripts/migrate_release.py"],
            cwd=ROOT,
            env=release_environment,
            check=True,
        )  # nosec B603
        release_head = run(
            [
                "psql",
                "-h",
                str(sock),
                "-p",
                "55461",
                "-U",
                "qa",
                "-At",
                "-c",
                "SELECT version_num FROM alembic_version",
                "olumira_release_test",
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if release_head != "0021":
            raise RuntimeError("Release runner did not produce the reviewed schema")
        # Authenticate an encrypted copy before restoring its decrypted bytes.
        from cryptography.fernet import Fernet
        from scripts.encrypted_backup import write_encrypted

        key = Fernet.generate_key()
        payload = (directory / "synthetic.dump").read_bytes()
        write_encrypted(payload, directory / "synthetic.dump.enc", key)
        recovered = Fernet(key).decrypt((directory / "synthetic.dump.enc").read_bytes())
        if recovered != payload:
            raise RuntimeError("Encrypted backup round trip differed")
        with open(directory / "recovered.dump", "xb") as handle:
            os.chmod(handle.name, 0o600)
            handle.write(recovered)
        run(
            [
                "createdb",
                "-h",
                str(sock),
                "-p",
                "55461",
                "-U",
                "qa",
                "olumira_restore_test",
            ]
        )
        run(
            [
                "pg_restore",
                "-h",
                str(sock),
                "-p",
                "55461",
                "-U",
                "qa",
                "-d",
                "olumira_restore_test",
                str(directory / "recovered.dump"),
            ]
        )
        query = [
            "psql",
            "-h",
            str(sock),
            "-p",
            "55461",
            "-U",
            "qa",
            "-At",
            "-c",
            "SELECT version_num FROM alembic_version; SELECT count(*) FROM communication_boards; SELECT count(*) FROM users;",
        ]
        original = run(query + ["olumira_security_test"], capture_output=True).stdout
        restored = run(query + ["olumira_restore_test"], capture_output=True).stdout
        if original != restored:
            raise RuntimeError("Synthetic restore counts/schema differ")
        report = dict(
            version=version,
            transport="private Unix socket, TCP disabled",
            tls="not tested",
            dump_restore="passed",
            encrypted_round_trip="Fernet authenticated, restored decrypted copy",
            migration_runner_fresh_head=release_head,
            schema_and_counts=original.decode().splitlines(),
            private_directory=str(directory),
        )
        (output / "postgres-restore.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        if started:
            run(["pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop"])


if __name__ == "__main__":
    main()
