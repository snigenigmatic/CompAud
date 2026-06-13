import argparse
import shutil
import signal
import subprocess
import sys
import time

from app.config import get_settings


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Run backend API and Phoenix together for local demo work."
    )
    parser.add_argument("--host", default=settings.api_host)
    parser.add_argument("--port", type=int, default=settings.api_port)
    parser.add_argument("--reload", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-phoenix", action="store_true")
    args = parser.parse_args()

    processes: list[tuple[str, subprocess.Popen]] = []
    try:
        if not args.no_phoenix:
            phoenix_bin = shutil.which("phoenix")
            if not phoenix_bin:
                print("Phoenix CLI was not found. Run `uv sync` first.", file=sys.stderr)
                return 1
            processes.append(("phoenix", subprocess.Popen([phoenix_bin, "serve"])))

        api_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ]
        if args.reload:
            api_cmd.append("--reload")
        processes.append(("api", subprocess.Popen(api_cmd)))

        return _wait_for_processes(processes)
    except KeyboardInterrupt:
        return 130
    finally:
        _stop_processes(processes)


def _wait_for_processes(processes: list[tuple[str, subprocess.Popen]]) -> int:
    while True:
        for name, process in processes:
            return_code = process.poll()
            if return_code is not None:
                print(f"{name} exited with code {return_code}")
                return return_code
        time.sleep(0.5)


def _stop_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    for _, process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)

    for _, process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
