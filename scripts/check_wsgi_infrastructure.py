"""Real Gunicorn socket smoke test; isolated testing config, no normal DB or SMTP."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    # Reserve an ephemeral local port, then release it immediately for Gunicorn.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="olumira-wsgi-") as folder:
        log_path = Path(folder) / "server.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "gunicorn",
                    "--config",
                    "gunicorn.conf.py",
                    "--bind",
                    f"127.0.0.1:{port}",
                    "app:app",
                ],
                cwd=ROOT,
                env=dict(os.environ, APP_ENV="testing"),
                stdout=log,
                stderr=log,
            )
            try:
                origin = f"http://127.0.0.1:{port}"
                for attempt in range(100):
                    try:
                        with urllib.request.urlopen(
                            origin + "/health/live?token=fictional-private-marker",
                            timeout=2,
                        ) as response:
                            assert response.status == 200
                            assert json.load(response) == {"status": "alive"}
                            assert len(response.headers["X-Request-ID"]) == 32
                        break
                    except urllib.error.URLError:
                        if process.poll() is not None:
                            raise RuntimeError("WSGI process exited") from None
                        time.sleep(0.1)
                else:
                    raise RuntimeError("WSGI startup deadline")
                try:
                    urllib.request.urlopen(origin + "/health/ready", timeout=3)
                except urllib.error.HTTPError as error:
                    assert error.code == 503
                    assert json.load(error) == {"status": "unavailable"}
                else:
                    raise RuntimeError("Unmigrated database incorrectly ready")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        contents = log_path.read_text()
        assert "fictional-private-marker" not in contents
        assert process.returncode == 0
    output = ROOT / "artifacts/day43/wsgi-smoke.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            dict(
                server="Gunicorn gthread, one worker/two threads",
                live=200,
                unmigrated_ready=503,
                query_redaction="passed",
                graceful_shutdown="passed",
            ),
            indent=2,
        )
    )
    print(output.read_text())


if __name__ == "__main__":
    main()
