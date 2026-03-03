from pathlib import Path

import pytest
from typer.testing import CliRunner

from flightlog.cli import app
from flightlog.ingest.http_capture_jsonl import detect, extract_artifacts, iter_events
from flightlog.json_utils import canonical_json_dumps
from flightlog.pack_writer import validate_pack

FIXTURES = (
    "anthropic_capture",
    "openai_compat_capture",
    "gemini_capture",
)


@pytest.mark.parametrize("name", FIXTURES)
def test_http_capture_ingest_golden(name: str) -> None:
    fixture_dir = Path("tests/fixtures/http_capture")
    fixture = fixture_dir / f"{name}.jsonl"
    expected = fixture_dir / f"{name}.expected_timeline.jsonl"

    assert detect(fixture)
    actual_lines = [canonical_json_dumps(event.to_dict()) for event in iter_events(fixture)]
    expected_lines = [
        line.strip() for line in expected.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert actual_lines == expected_lines


@pytest.mark.parametrize("name", FIXTURES)
def test_http_capture_extract_artifacts(name: str) -> None:
    fixture = Path("tests/fixtures/http_capture") / f"{name}.jsonl"
    artifacts = extract_artifacts(fixture)
    assert artifacts
    assert any(key.endswith("_request.json") for key in artifacts)
    assert any(key.endswith("_response.json") for key in artifacts)


@pytest.mark.parametrize("name", FIXTURES)
def test_http_capture_pack_build_and_validate(tmp_path: Path, name: str) -> None:
    fixture_dir = Path("tests/fixtures/http_capture")
    fixture = fixture_dir / f"{name}.jsonl"
    expected = fixture_dir / f"{name}.expected_timeline.jsonl"
    out_dir = tmp_path / f"{name}-pack"

    runner = CliRunner()
    build = runner.invoke(
        app,
        ["pack", "build", "--input", str(fixture), "--out", str(out_dir)],
    )
    assert build.exit_code == 0, build.stdout

    ok, errors = validate_pack(out_dir)
    assert ok, errors

    timeline_lines = [
        line.strip()
        for line in (out_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_lines = [
        line.strip() for line in expected.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert sorted(timeline_lines) == sorted(expected_lines)
