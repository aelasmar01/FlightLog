"""Live watcher for appended JSONL session logs."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from flightlog.ingest import select_ingestor
from flightlog.json_utils import canonical_json_dumps
from flightlog.normalize import ARTIFACT_THRESHOLD_BYTES, normalize_events
from flightlog.pack_writer import create_pack
from flightlog.redaction import load_redaction_config, redact_artifacts


def _write_pack_snapshot(
    *,
    input_path: Path,
    out_dir: Path,
    artifact_threshold_bytes: int,
    redaction_path: Path | None,
) -> None:
    ingestor = select_ingestor(input_path)
    events = list(ingestor.iter_events(input_path))
    ingest_artifacts = ingestor.extract_artifacts(input_path)
    normalized_events, normalized_artifacts = normalize_events(
        events,
        artifact_threshold_bytes=artifact_threshold_bytes,
    )
    artifacts = dict(ingest_artifacts)
    artifacts.update(normalized_artifacts)

    redaction_config = load_redaction_config(redaction_path)
    redacted_artifacts, report = redact_artifacts(artifacts, redaction_config)

    with TemporaryDirectory(prefix="flightlog_watch_pack_") as tmp_dir:
        tmp_pack = Path(tmp_dir) / "pack"
        create_pack(
            output_dir=tmp_pack,
            events_iter=normalized_events,
            artifacts=redacted_artifacts,
            redaction_report=report,
            extra_sections={"ingestor": ingestor.name, "mode": "watch"},
            zip_output=False,
        )

        if out_dir.exists():
            if not out_dir.is_dir():
                raise ValueError(f"--out must be a directory path: {out_dir}")
            shutil.rmtree(out_dir)
        shutil.move(str(tmp_pack), str(out_dir))


def watch_input(
    *,
    input_path: Path,
    emit: Callable[[str], None],
    out_dir: Path | None,
    redaction_path: Path | None,
    poll_interval_seconds: float,
    max_events: int | None,
    idle_timeout_seconds: float | None,
    from_start: bool,
    artifact_threshold_bytes: int = ARTIFACT_THRESHOLD_BYTES,
) -> int:
    ingestor = select_ingestor(input_path)
    initial_events = list(ingestor.iter_events(input_path))
    seen_events = 0 if from_start else len(initial_events)
    emitted_events = 0
    last_change = time.monotonic()

    if out_dir is not None:
        _write_pack_snapshot(
            input_path=input_path,
            out_dir=out_dir,
            artifact_threshold_bytes=artifact_threshold_bytes,
            redaction_path=redaction_path,
        )

    while True:
        current_events = list(ingestor.iter_events(input_path))

        if len(current_events) < seen_events:
            # Handle truncation/log rotation by resetting seen pointer.
            seen_events = 0

        if len(current_events) > seen_events:
            new_events = current_events[seen_events:]
            if max_events is not None:
                remaining = max_events - emitted_events
                if remaining <= 0:
                    break
                new_events = new_events[:remaining]

            for event in new_events:
                emit(canonical_json_dumps(event.to_dict()))

            emitted_events += len(new_events)
            seen_events += len(new_events)
            last_change = time.monotonic()

            if out_dir is not None:
                _write_pack_snapshot(
                    input_path=input_path,
                    out_dir=out_dir,
                    artifact_threshold_bytes=artifact_threshold_bytes,
                    redaction_path=redaction_path,
                )

            if max_events is not None and emitted_events >= max_events:
                break
        else:
            if idle_timeout_seconds is not None:
                idle = time.monotonic() - last_change
                if idle >= idle_timeout_seconds:
                    break

        time.sleep(poll_interval_seconds)

    return emitted_events
