import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from flightlog.assert_gate import run_assert_gate
from flightlog.cli import app
from flightlog.mcp.stubgen import params_hash
from flightlog.models import NormalizedEvent, RedactionReport
from flightlog.pack_compare import compare_packs
from flightlog.pack_writer import create_pack


def _event(event_id: str, event_type: str, payload: dict[str, object]) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        source="test",
        type=event_type,
        session_id="s",
        run_id="r",
        payload=payload,
    )


def _build_pack(pack_dir: Path, events: list[NormalizedEvent], include_beta_stub: bool) -> Path:
    create_pack(pack_dir, events, {}, RedactionReport())

    stub_file = pack_dir / "mcp" / "stubs" / "demo" / "session.json"
    stub_file.parent.mkdir(parents=True, exist_ok=True)

    methods: dict[str, dict[str, dict[str, object]]] = {
        "tool.alpha": {
            params_hash({"x": 1}): {"result": {"ok": True}},
        }
    }
    if include_beta_stub:
        methods["tool.beta"] = {
            params_hash({"x": 2}): {"result": {"ok": True}},
        }

    stub_file.write_text(
        json.dumps({"schema_version": "1", "methods": methods}),
        encoding="utf-8",
    )
    return pack_dir


def test_pack_compare_detects_regressions(tmp_path: Path) -> None:
    baseline_events = [
        _event("e1", "model.request", {"text": "hi"}),
        _event(
            "e2",
            "mcp.request",
            {"server": "demo", "method": "tool.alpha", "params": {"x": 1}},
        ),
    ]
    candidate_events = [
        _event("e1", "model.request", {"text": "hi"}),
        _event(
            "e2",
            "mcp.request",
            {"server": "demo", "method": "tool.alpha", "params": {"x": 1}},
        ),
        _event(
            "e3",
            "mcp.request",
            {"server": "demo", "method": "tool.beta", "params": {"x": 2}},
        ),
        _event("e4", "tool.call", {"tool": "shell"}),
    ]

    baseline = _build_pack(tmp_path / "baseline", baseline_events, include_beta_stub=False)
    candidate = _build_pack(tmp_path / "candidate", candidate_events, include_beta_stub=False)

    report = compare_packs(baseline, candidate)
    assert "tool.call" in report.added_event_types
    assert "tool.beta" in report.new_mcp_methods
    assert len(report.new_missing_stub_mappings) == 1


def test_pack_compare_cli_json_output(tmp_path: Path) -> None:
    runner = CliRunner()
    baseline = _build_pack(
        tmp_path / "baseline",
        [_event("e1", "model.request", {"text": "x"})],
        include_beta_stub=False,
    )
    candidate = _build_pack(
        tmp_path / "candidate",
        [_event("e1", "model.request", {"text": "x"})],
        include_beta_stub=False,
    )

    result = runner.invoke(
        app,
        [
            "pack",
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "baseline" in payload
    assert "candidate" in payload


def test_assert_gate_pass_and_fail(tmp_path: Path) -> None:
    baseline_events = [
        _event(
            "e1",
            "mcp.request",
            {"server": "demo", "method": "tool.alpha", "params": {"x": 1}},
        ),
    ]
    candidate_events = [
        _event(
            "e1",
            "mcp.request",
            {"server": "demo", "method": "tool.alpha", "params": {"x": 1}},
        ),
        _event(
            "e2",
            "mcp.request",
            {"server": "demo", "method": "tool.beta", "params": {"x": 2}},
        ),
    ]

    baseline = _build_pack(tmp_path / "baseline", baseline_events, include_beta_stub=False)
    candidate_fail = _build_pack(
        tmp_path / "candidate_fail",
        candidate_events,
        include_beta_stub=False,
    )
    candidate_pass = _build_pack(
        tmp_path / "candidate_pass",
        candidate_events,
        include_beta_stub=True,
    )

    fail_result = run_assert_gate(
        baseline_path=baseline,
        candidate_path=candidate_fail,
        policy_path=None,
    )
    assert not fail_result.passed

    pass_result = run_assert_gate(
        baseline_path=baseline,
        candidate_path=candidate_pass,
        policy_path=None,
    )
    assert pass_result.passed


def test_assert_cli_exit_codes(tmp_path: Path) -> None:
    runner = CliRunner()
    baseline = _build_pack(
        tmp_path / "baseline",
        [
            _event(
                "e1",
                "mcp.request",
                {"server": "demo", "method": "tool.alpha", "params": {"x": 1}},
            )
        ],
        include_beta_stub=False,
    )
    candidate = _build_pack(
        tmp_path / "candidate",
        [
            _event(
                "e1",
                "mcp.request",
                {"server": "demo", "method": "tool.beta", "params": {"x": 2}},
            )
        ],
        include_beta_stub=False,
    )

    result = runner.invoke(
        app,
        [
            "assert",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
        ],
    )
    assert result.exit_code == 1
