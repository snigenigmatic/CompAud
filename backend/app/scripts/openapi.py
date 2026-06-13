import argparse
import json
from pathlib import Path

from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the backend OpenAPI spec.")
    parser.add_argument("--output", default="openapi.json")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote OpenAPI spec to {output_path}")
