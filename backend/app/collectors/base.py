"""Collector abstraction (PS3 Automation, 15 pts).

A Collector pulls evidence from a source system and NORMALISES it into the
Evidence schema the linker/quality engine consume. Two mock implementations
ship (BucketCollector, CloudTrailCollector); the architecture doc describes the
real boto3/GCS versions and scheduling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.models.ps3 import Evidence


class Collector(ABC):
    name: str = "collector"

    @abstractmethod
    def collect(self, since: datetime | None = None) -> list[Evidence]:
        """Return normalised Evidence collected from the source.

        ``since`` optionally filters to evidence collected on/after that date.
        """


def collect_all(collectors: list[Collector], since: datetime | None = None) -> list[Evidence]:
    evidence: list[Evidence] = []
    for collector in collectors:
        evidence.extend(collector.collect(since=since))
    return evidence
