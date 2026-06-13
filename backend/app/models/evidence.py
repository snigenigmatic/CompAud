from pydantic import Field

from app.models.base import APIModel


class EvidenceArtifact(APIModel):
    name: str
    extension: str
    chunk_count: int


class EvidenceChunk(APIModel):
    artifact: str
    location: str
    text: str
    normalized_text: str
    hash: str
    parsed_fields: dict[str, str] = Field(default_factory=dict)


class EvidencePackage(APIModel):
    uploaded_filename: str
    artifacts: list[EvidenceArtifact]
    chunks: list[EvidenceChunk]


class EvidenceCitation(APIModel):
    artifact: str
    location: str
    hash: str
    excerpt: str
    matched_terms: list[str]
