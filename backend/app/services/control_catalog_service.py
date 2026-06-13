import json
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from app.config import REPO_ROOT
from app.models.controls import ControlRequirement


CONTROL_REQUIREMENTS_PATH = REPO_ROOT / "docs" / "control_requirements.json"
CONTROL_REQUIREMENTS_SOURCE = "docs/control_requirements.json"


class ControlCatalogError(RuntimeError):
    pass


@lru_cache
def load_control_requirements(
    path: Path = CONTROL_REQUIREMENTS_PATH,
) -> list[ControlRequirement]:
    try:
        raw_controls = json.loads(path.read_text(encoding="utf-8"))
        controls = TypeAdapter(list[ControlRequirement]).validate_python(raw_controls)
    except FileNotFoundError as exc:
        raise ControlCatalogError(f"Control requirements file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ControlCatalogError(f"Control requirements file is invalid JSON: {path}") from exc
    except ValidationError as exc:
        raise ControlCatalogError(f"Control requirements schema validation failed: {path}") from exc

    control_ids = [control.id for control in controls]
    duplicate_ids = sorted(
        control_id for control_id in set(control_ids) if control_ids.count(control_id) > 1
    )
    if duplicate_ids:
        raise ControlCatalogError(
            f"Control requirements contain duplicate IDs: {', '.join(duplicate_ids)}"
        )

    return controls
