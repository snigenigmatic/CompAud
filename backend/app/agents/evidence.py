import csv
import hashlib
import json
import re
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from app.models.evidence import EvidenceArtifact, EvidenceChunk, EvidencePackage


SUPPORTED_ARTIFACT_EXTENSIONS = {".csv", ".json", ".log", ".txt"}
ZIP_EXTENSION = ".zip"


class EvidenceError(RuntimeError):
    pass


class UnsupportedEvidenceTypeError(EvidenceError):
    pass


class UnsafeEvidenceArchiveError(EvidenceError):
    pass


class EvidenceParseError(EvidenceError):
    pass


def parse_evidence_upload(filename: str, content: bytes) -> EvidencePackage:
    extension = _extension(filename)
    if extension == ZIP_EXTENSION:
        return _parse_zip_upload(filename, content)

    if extension not in SUPPORTED_ARTIFACT_EXTENSIONS:
        raise UnsupportedEvidenceTypeError(
            f"Unsupported evidence file type '{extension}' for {filename}"
        )

    chunks = _parse_artifact(filename, content)
    return EvidencePackage(
        uploaded_filename=filename,
        artifacts=[_artifact_summary(filename, chunks)],
        chunks=chunks,
    )


def _parse_zip_upload(filename: str, content: bytes) -> EvidencePackage:
    artifacts: list[EvidenceArtifact] = []
    chunks: list[EvidenceChunk] = []

    try:
        with ZipFile(BytesIO(content)) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue

                artifact_name = _safe_zip_member_name(member.filename)
                if _extension(artifact_name) not in SUPPORTED_ARTIFACT_EXTENSIONS:
                    raise UnsupportedEvidenceTypeError(
                        f"Unsupported evidence file type in ZIP: {artifact_name}"
                    )

                artifact_content = archive.read(member)
                artifact_chunks = _parse_artifact(artifact_name, artifact_content)
                artifacts.append(_artifact_summary(artifact_name, artifact_chunks))
                chunks.extend(artifact_chunks)
    except BadZipFile as exc:
        raise EvidenceParseError(f"Invalid ZIP evidence package: {filename}") from exc

    return EvidencePackage(
        uploaded_filename=filename,
        artifacts=artifacts,
        chunks=chunks,
    )


def _parse_artifact(artifact_name: str, content: bytes) -> list[EvidenceChunk]:
    extension = _extension(artifact_name)
    text = _decode_text(artifact_name, content)

    if extension == ".csv":
        return _parse_csv_artifact(artifact_name, text)
    if extension in {".log", ".txt"}:
        return _parse_line_artifact(artifact_name, text)
    if extension == ".json":
        return _parse_json_artifact(artifact_name, text)

    raise UnsupportedEvidenceTypeError(
        f"Unsupported evidence file type '{extension}' for {artifact_name}"
    )


def _parse_csv_artifact(artifact_name: str, text: str) -> list[EvidenceChunk]:
    reader = csv.DictReader(StringIO(text))
    chunks: list[EvidenceChunk] = []

    for row_number, row in enumerate(reader, start=1):
        parsed_fields = {
            str(key).strip(): str(value).strip()
            for key, value in row.items()
            if key is not None and value is not None and str(value).strip()
        }
        if not parsed_fields:
            continue

        chunk_text = ", ".join(
            f"{key}={value}" for key, value in parsed_fields.items()
        )
        chunks.append(
            _build_chunk(
                artifact=artifact_name,
                location=f"row {row_number}",
                text=chunk_text,
                parsed_fields=parsed_fields,
            )
        )

    return chunks


def _parse_line_artifact(artifact_name: str, text: str) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        chunk_text = line.strip()
        if not chunk_text:
            continue

        chunks.append(
            _build_chunk(
                artifact=artifact_name,
                location=f"line {line_number}",
                text=chunk_text,
            )
        )

    return chunks


def _parse_json_artifact(artifact_name: str, text: str) -> list[EvidenceChunk]:
    try:
        parsed_json = json.loads(text)
    except json.JSONDecodeError:
        return _parse_line_artifact(artifact_name, text)

    if isinstance(parsed_json, list):
        return [
            _json_chunk(artifact_name, f"item {index}", item)
            for index, item in enumerate(parsed_json, start=1)
        ]

    if isinstance(parsed_json, dict):
        if all(not isinstance(value, (dict, list)) for value in parsed_json.values()):
            return [_json_chunk(artifact_name, "json document", parsed_json)]

        return [
            _json_chunk(artifact_name, f"key {key}", value)
            for key, value in parsed_json.items()
        ]

    return [_json_chunk(artifact_name, "json document", parsed_json)]


def _json_chunk(artifact_name: str, location: str, value: object) -> EvidenceChunk:
    parsed_fields = (
        {str(key): str(item) for key, item in value.items()}
        if isinstance(value, dict)
        else {}
    )
    chunk_text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _build_chunk(
        artifact=artifact_name,
        location=location,
        text=chunk_text,
        parsed_fields=parsed_fields,
    )


def _safe_zip_member_name(member_name: str) -> str:
    if "\x00" in member_name or "\\" in member_name:
        raise UnsafeEvidenceArchiveError(f"Unsafe ZIP member path: {member_name}")

    path = PurePosixPath(member_name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeEvidenceArchiveError(f"Unsafe ZIP member path: {member_name}")

    return str(path)


def _artifact_summary(artifact_name: str, chunks: list[EvidenceChunk]) -> EvidenceArtifact:
    return EvidenceArtifact(
        name=artifact_name,
        extension=_extension(artifact_name),
        chunk_count=len(chunks),
    )


def _build_chunk(
    artifact: str,
    location: str,
    text: str,
    parsed_fields: dict[str, str] | None = None,
) -> EvidenceChunk:
    return EvidenceChunk(
        artifact=artifact,
        location=location,
        text=text,
        normalized_text=_normalize_text(text),
        hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        parsed_fields=parsed_fields or {},
    )


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _decode_text(artifact_name: str, content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceParseError(f"Evidence artifact is not UTF-8 text: {artifact_name}") from exc


def _extension(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix
