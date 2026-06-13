"""Loads parsed policy requirements (PS3). Mirrors control_catalog_service:
@lru_cache, validation, duplicate-id guard. Parses once per process.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.config import PS3_POLICY_DOCUMENTS_PATH, get_settings
from app.agents.ps3_policy_parser import normalize_requirement_text, parse_policy_text
from app.models.ps3 import Requirement

logger = logging.getLogger(__name__)

REQUIREMENTS_SOURCE = "Problem_03_Compliance_Evidence/sample_data/policy_documents.txt"


class RequirementCatalogError(RuntimeError):
    pass


def _policy_path() -> Path:
    settings = get_settings()
    if settings.ps3_policy_documents_path:
        return Path(settings.ps3_policy_documents_path)
    return PS3_POLICY_DOCUMENTS_PATH


@lru_cache
def load_requirements() -> list[Requirement]:
    path = _policy_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RequirementCatalogError(f"Policy document not found: {path}") from exc

    requirements = parse_policy_text(text)
    if not requirements:
        raise RequirementCatalogError(f"No requirements parsed from {path}")

    ids = [req.id for req in requirements]
    duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
    if duplicates:
        raise RequirementCatalogError(
            f"Parsed requirements contain duplicate IDs: {', '.join(duplicates)}"
        )

    settings = get_settings()
    if settings.ps3_llm_normalize_requirements and settings.openai_enabled:
        for req in requirements:
            req.text = normalize_requirement_text(req.raw_text)

    logger.info("Loaded %d PS3 requirements from %s", len(requirements), path)
    return requirements


def export_requirements_json(destination: Path) -> Path:
    """Dump parsed requirements to JSON for review / notebook use."""
    requirements = load_requirements()
    payload = [req.model_dump() for req in requirements]
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination
