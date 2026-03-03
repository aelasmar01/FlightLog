"""Pack writer and validator."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from replaypack.json_utils import canonical_json_dumps, sha256_bytes, sha256_file
from replaypack.models import NormalizedEvent, RedactionReport, ReplayPackManifest
from replaypack.pack_io import open_pack
from replaypack.schema_version import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS


@dataclass(slots=True)
class PackBuildResult:
    pack_dir: Path
    zip_path: Path | None


def _safe_artifact_key(key: str) -> str:
    normalized = key.replace("\\", "/").lstrip("/")
    if normalized.startswith("..") or "/../" in normalized:
        raise ValueError(f"Unsafe artifact key: {key}")
    return normalized


def _write_pack_dir(
    pack_dir: Path,
    events_iter: Iterable[NormalizedEvent],
    artifacts: Mapping[str, bytes | str],
    redaction_report: RedactionReport,
    extra_sections: Mapping[str, Any] | None,
) -> ReplayPackManifest:
    pack_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = pack_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    timeline_path = pack_dir / "timeline.jsonl"
    with timeline_path.open("w", encoding="utf-8") as handle:
        for event in events_iter:
            handle.write(canonical_json_dumps(event.to_dict()))
            handle.write("\n")

    artifact_hashes: dict[str, str] = {}
    for key, value in sorted(artifacts.items()):
        safe_key = _safe_artifact_key(key)
        disk_path = artifacts_dir / safe_key
        disk_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            payload = value
        else:
            payload = value.encode("utf-8")
        disk_path.write_bytes(payload)
        artifact_hashes[f"artifacts/{safe_key}"] = sha256_bytes(payload)

    redaction_path = pack_dir / "redaction_report.json"
    redaction_payload = canonical_json_dumps(redaction_report.to_dict()) + "\n"
    redaction_path.write_text(redaction_payload, encoding="utf-8")

    manifest = ReplayPackManifest(
        schema_version=SCHEMA_VERSION,
        timeline_sha256=sha256_file(timeline_path),
        artifacts=artifact_hashes,
        extra_sections=dict(extra_sections or {}),
    )
    manifest_path = pack_dir / "manifest.json"
    manifest_payload = canonical_json_dumps(manifest.to_dict()) + "\n"
    manifest_path.write_text(manifest_payload, encoding="utf-8")
    return manifest


def _zip_dir(source_dir: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))


def create_pack(
    output_dir: Path,
    events_iter: Iterable[NormalizedEvent],
    artifacts: Mapping[str, bytes | str],
    redaction_report: RedactionReport,
    extra_sections: Mapping[str, Any] | None = None,
    zip_output: bool = False,
) -> PackBuildResult:
    if zip_output:
        with TemporaryDirectory(prefix="replaypack_build_") as tmp_dir:
            tmp_path = Path(tmp_dir) / "pack"
            _write_pack_dir(tmp_path, events_iter, artifacts, redaction_report, extra_sections)
            if output_dir.suffix == ".zip":
                zip_path = output_dir
            else:
                zip_path = output_dir / "pack.zip"
            _zip_dir(tmp_path, zip_path)
            return PackBuildResult(pack_dir=zip_path.parent, zip_path=zip_path)

    _write_pack_dir(output_dir, events_iter, artifacts, redaction_report, extra_sections)
    return PackBuildResult(pack_dir=output_dir, zip_path=None)


def validate_pack(path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    with open_pack(path) as pack_dir:
        manifest_path = pack_dir / "manifest.json"
        timeline_path = pack_dir / "timeline.jsonl"
        if not manifest_path.exists():
            return False, ["manifest.json missing"]
        if not timeline_path.exists():
            return False, ["timeline.jsonl missing"]

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = ReplayPackManifest.model_validate(manifest_data)
        except Exception as exc:  # pragma: no cover - defensive validation path
            return False, [f"manifest parse error: {exc}"]

        if manifest.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            errors.append(f"unsupported schema version: {manifest.schema_version}")

        actual_timeline_hash = sha256_file(timeline_path)
        if actual_timeline_hash != manifest.timeline_sha256:
            errors.append("timeline hash mismatch")

        for artifact_path, expected_hash in sorted(manifest.artifacts.items()):
            disk_path = pack_dir / artifact_path
            if not disk_path.exists():
                errors.append(f"missing artifact: {artifact_path}")
                continue
            actual_hash = sha256_file(disk_path)
            if actual_hash != expected_hash:
                errors.append(f"artifact hash mismatch: {artifact_path}")

        # Ensure timeline is valid JSONL so replay and diff workflows are safe.
        with timeline_path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    json.loads(stripped)
                except json.JSONDecodeError:
                    errors.append(f"timeline line {index} is invalid JSON")
                    break

    return len(errors) == 0, errors
