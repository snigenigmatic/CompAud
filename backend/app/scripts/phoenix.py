import argparse
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Phoenix for trace viewing.")
    parser.add_argument(
        "phoenix_args",
        nargs=argparse.REMAINDER,
        help="Optional extra args passed after `phoenix serve`.",
    )
    args = parser.parse_args()

    phoenix_bin = shutil.which("phoenix")
    if not phoenix_bin:
        print("Phoenix CLI was not found. Run `uv sync` first.", file=sys.stderr)
        return 1

    return subprocess.call([phoenix_bin, "serve", *args.phoenix_args])
