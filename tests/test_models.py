from datetime import UTC, datetime

from flightlog.json_utils import canonical_json_dumps
from flightlog.models import NormalizedEvent, RedactionReport, FlightlogManifest


def test_models_round_trip() -> None:
    event = NormalizedEvent(
        event_id="evt-1",
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        source="codex_cli",
        type="model.request",
        session_id="s1",
        run_id="r1",
        payload={"a": 1},
    )
    event2 = NormalizedEvent.model_validate(event.to_dict())
    assert event2.to_dict() == event.to_dict()

    report = RedactionReport(patterns_matched={"token": 2}, replacements=2)
    report2 = RedactionReport.model_validate(report.to_dict())
    assert report2.to_dict() == report.to_dict()

    manifest = FlightlogManifest(schema_version="1.0.0", timeline_sha256="abc")
    manifest2 = FlightlogManifest.model_validate(manifest.to_dict())
    assert manifest2.to_dict() == manifest.to_dict()


def test_canonical_json_key_ordering() -> None:
    payload = {"z": 1, "a": 2}
    assert canonical_json_dumps(payload) == '{"a":2,"z":1}'
