"""Policy document parser (PS3 Policy Extraction, 25 pts).

Parses the structured policy_documents.txt into Requirement objects using
deterministic regex (the skeleton is reliably labelled). An optional LLM pass
can normalise the requirement sentence, but it is OFF by default so extraction
stays deterministic, offline-safe, and testable.
"""

from __future__ import annotations

import logging
import re

from app.models.ps3 import Requirement

logger = logging.getLogger(__name__)


AUDIT_FREQUENCY_SLA_DAYS: dict[str, int] = {
    "continuous": 1,
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "annually": 365,
    "annual": 365,
    "yearly": 365,
}
DEFAULT_SLA_DAYS = 90


# Order matters: more specific tokens first. Normalised to the evidence-side
# vocabulary {GDPR, HIPAA, ISO27001, NIST, PCI-DSS, SOX} plus CIS (policy-only).
_FRAMEWORK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bPCI[\s-]?DSS\b", re.IGNORECASE), "PCI-DSS"),
    (re.compile(r"\bISO[\s-]?27001\b", re.IGNORECASE), "ISO27001"),
    (re.compile(r"\bGDPR\b", re.IGNORECASE), "GDPR"),
    (re.compile(r"\bNIST\b", re.IGNORECASE), "NIST"),
    (re.compile(r"\bSOX\b", re.IGNORECASE), "SOX"),
    (re.compile(r"\bCIS\b", re.IGNORECASE), "CIS"),
    (re.compile(r"\bHIPAA\b", re.IGNORECASE), "HIPAA"),
]

_POLICY_HEADER = re.compile(
    r"^POLICY:\s*(?P<name>.+?)\s*\n+POLICY_ID:\s*(?P<pid>\S+)",
    re.IGNORECASE | re.MULTILINE,
)
_REQUIREMENT_HEADER = re.compile(
    r"^REQUIREMENT\s+(?P<num>\d+)\s*:\s*(?P<text>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_FIELD_LABELS = {
    "responsible": "Responsible",
    "scope": "Scope",
    "evidence_source": "Evidence Source",
    "audit_frequency": "Audit Frequency",
    "compliance_mapping": "Compliance Mapping",
}


def parse_policy_text(text: str) -> list[Requirement]:
    """Parse policy document text into a list of Requirement objects."""
    requirements: list[Requirement] = []

    for policy_name, policy_id, section in _split_policies(text):
        for num, req_text, block in _split_requirements(section):
            fields = {
                key: _extract_field(block, label)
                for key, label in _FIELD_LABELS.items()
            }
            audit_frequency = fields["audit_frequency"]
            requirements.append(
                Requirement(
                    id=f"{policy_id}-R{num}",
                    policy_id=policy_id,
                    policy_name=policy_name,
                    text=req_text,
                    raw_text=req_text,
                    responsible=fields["responsible"],
                    scope=fields["scope"],
                    evidence_source=fields["evidence_source"],
                    audit_frequency=audit_frequency,
                    frameworks=_extract_frameworks(fields["compliance_mapping"]),
                    compliance_mapping_raw=fields["compliance_mapping"],
                    freshness_sla_days=sla_days_for_frequency(audit_frequency),
                )
            )

    return requirements


def sla_days_for_frequency(audit_frequency: str) -> int:
    return AUDIT_FREQUENCY_SLA_DAYS.get(audit_frequency.strip().lower(), DEFAULT_SLA_DAYS)


def _split_policies(text: str) -> list[tuple[str, str, str]]:
    headers = list(_POLICY_HEADER.finditer(text))
    sections: list[tuple[str, str, str]] = []
    for index, match in enumerate(headers):
        start = match.start()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        sections.append(
            (match.group("name").strip(), match.group("pid").strip(), text[start:end])
        )
    return sections


def _split_requirements(section: str) -> list[tuple[int, str, str]]:
    headers = list(_REQUIREMENT_HEADER.finditer(section))
    blocks: list[tuple[int, str, str]] = []
    for index, match in enumerate(headers):
        start = match.start()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(section)
        blocks.append((int(match.group("num")), match.group("text").strip(), section[start:end]))
    return blocks


def _extract_field(block: str, label: str) -> str:
    pattern = re.compile(
        rf"^\s*[-*]?\s*{re.escape(label)}\s*:\s*(?P<value>.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(block)
    return match.group("value").strip() if match else ""


def _extract_frameworks(compliance_mapping: str) -> list[str]:
    found: list[str] = []
    for pattern, name in _FRAMEWORK_PATTERNS:
        if pattern.search(compliance_mapping) and name not in found:
            found.append(name)
    return found


def normalize_requirement_text(raw_text: str) -> str:
    """Optional LLM polish of a requirement sentence. Falls back to raw on any error."""
    from app.llm.client import llm_json
    from app.llm.ps3_prompts import POLICY_NORMALIZE_SYSTEM, POLICY_NORMALIZE_USER

    try:
        result = llm_json(
            system_prompt=POLICY_NORMALIZE_SYSTEM,
            user_prompt=POLICY_NORMALIZE_USER.format(requirement=raw_text),
        )
        normalized = str(result.get("requirement", "")).strip()
        return normalized or raw_text
    except Exception:
        logger.warning("LLM requirement normalisation failed; using raw text", exc_info=True)
        return raw_text
