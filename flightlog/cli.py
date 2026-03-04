"""Flightlog command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from flightlog.assert_gate import run_assert_gate
from flightlog.audit_export import export_audit
from flightlog.diff_viewer import render_diff
from flightlog.ingest import select_ingestor
from flightlog.json_utils import canonical_json_dumps
from flightlog.llm.proxy import run_llm_proxy
from flightlog.llm.sdk_capture.install import install_sitecustomize, uninstall_sitecustomize
from flightlog.mcp.discovery import discover_servers
from flightlog.mcp.proxy_http import run_proxy as run_mcp_proxy
from flightlog.mcp.stub_server import serve_stub
from flightlog.mcp.stubgen import generate_stub_from_transcript, write_stub
from flightlog.mcp.wrap_http import run_wrap_http_blocking
from flightlog.mcp.wrap_stdio import run_wrap
from flightlog.normalize import ARTIFACT_THRESHOLD_BYTES, normalize_events
from flightlog.pack_compare import compare_packs, render_compare_text
from flightlog.pack_writer import create_pack, validate_pack
from flightlog.redaction import load_redaction_config, redact_artifacts
from flightlog.replay_runner import run_replay
from flightlog.signing import sign_pack, verify_pack
from flightlog.watch import watch_input

app = typer.Typer(help="Flightlog CLI")
pack_app = typer.Typer(help="Pack build and inspection commands")
mcp_app = typer.Typer(help="MCP capture/replay commands")
llm_app = typer.Typer(help="LLM capture commands")
stub_app = typer.Typer(help="MCP stub commands")
replay_app = typer.Typer(help="Replay commands")
export_app = typer.Typer(help="Export commands")
sdk_app = typer.Typer(help="Python SDK capture helpers")

app.add_typer(pack_app, name="pack")
app.add_typer(mcp_app, name="mcp")
app.add_typer(llm_app, name="llm")
app.add_typer(sdk_app, name="sdk")
app.add_typer(replay_app, name="replay")
app.add_typer(export_app, name="export")
mcp_app.add_typer(stub_app, name="stub")


def _emit(message: str, *, json_logs: bool, level: str = "info", **extra: Any) -> None:
    if json_logs:
        payload = {"level": level, "message": message}
        payload.update(extra)
        typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    else:
        typer.echo(message)


@app.callback()
def root(
    ctx: typer.Context,
    log_json: Annotated[
        bool,
        typer.Option("--log-json", help="Emit logs in JSON format"),
    ] = False,
) -> None:
    ctx.obj = {"log_json": log_json}


@app.command("watch")
def watch(
    input_path: Annotated[
        Path,
        typer.Option("--input", exists=True, file_okay=True, dir_okay=False),
    ],
    out: Annotated[Path | None, typer.Option("--out")] = None,
    redaction: Annotated[Path | None, typer.Option("--redaction")] = None,
    poll_interval: Annotated[float, typer.Option("--poll-interval")] = 0.25,
    max_events: Annotated[int | None, typer.Option("--max-events")] = None,
    idle_timeout: Annotated[float | None, typer.Option("--idle-timeout")] = None,
    from_start: Annotated[bool, typer.Option("--from-start")] = False,
    artifact_threshold_bytes: Annotated[
        int,
        typer.Option("--artifact-threshold-bytes"),
    ] = ARTIFACT_THRESHOLD_BYTES,
) -> None:
    def emit(line: str) -> None:
        typer.echo(line)

    emitted = watch_input(
        input_path=input_path,
        emit=emit,
        out_dir=out,
        redaction_path=redaction,
        poll_interval_seconds=poll_interval,
        max_events=max_events,
        idle_timeout_seconds=idle_timeout,
        from_start=from_start,
        artifact_threshold_bytes=artifact_threshold_bytes,
    )
    typer.echo(f"watch completed (emitted={emitted})")


@pack_app.command("build")
def pack_build(
    ctx: typer.Context,
    input_path: Annotated[
        Path,
        typer.Option("--input", exists=True, file_okay=True, dir_okay=False),
    ],
    out: Annotated[Path, typer.Option("--out")],
    zip_output: Annotated[bool, typer.Option("--zip")] = False,
    redaction: Annotated[Path | None, typer.Option("--redaction")] = None,
    workspace_before: Annotated[
        Path | None, typer.Option("--workspace-before", exists=True)
    ] = None,
    workspace_after: Annotated[Path | None, typer.Option("--workspace-after", exists=True)] = None,
    artifact_threshold_bytes: Annotated[
        int,
        typer.Option(
            "--artifact-threshold-bytes",
            help="Inline payload size threshold before moving content to artifacts",
        ),
    ] = ARTIFACT_THRESHOLD_BYTES,
) -> None:
    json_logs = bool((ctx.obj or {}).get("log_json", False))

    ingestor = select_ingestor(input_path)
    _emit(f"Detected ingestor: {ingestor.name}", json_logs=json_logs, ingestor=ingestor.name)

    events = list(ingestor.iter_events(input_path))
    ingest_artifacts = ingestor.extract_artifacts(input_path)

    normalized_events, normalized_artifacts = normalize_events(
        events,
        artifact_threshold_bytes=artifact_threshold_bytes,
        workspace_before=workspace_before,
        workspace_after=workspace_after,
    )

    artifacts = dict(ingest_artifacts)
    artifacts.update(normalized_artifacts)

    redaction_config = load_redaction_config(redaction)
    redacted_artifacts, report = redact_artifacts(artifacts, redaction_config)

    result = create_pack(
        output_dir=out,
        events_iter=normalized_events,
        artifacts=redacted_artifacts,
        redaction_report=report,
        extra_sections={"ingestor": ingestor.name},
        zip_output=zip_output,
    )

    if zip_output:
        assert result.zip_path is not None
        _emit(str(result.zip_path), json_logs=json_logs, output=str(result.zip_path))
    else:
        _emit(str(result.pack_dir), json_logs=json_logs, output=str(result.pack_dir))


@pack_app.command("validate")
def pack_validate(
    path: Annotated[Path, typer.Option("--path", exists=True)],
    allow_major: Annotated[
        bool,
        typer.Option("--allow-major", help="Attempt validation even if MAJOR version differs"),
    ] = False,
) -> None:
    ok, errors = validate_pack(path, allow_major=allow_major)
    if ok:
        typer.echo("Pack is valid")
        raise typer.Exit(0)

    for error in errors:
        typer.echo(error)
    raise typer.Exit(1)


@pack_app.command("diff")
def pack_diff(
    pack: Annotated[Path, typer.Option("--pack", exists=True)],
    file_path: Annotated[str | None, typer.Option("--file")] = None,
    event: Annotated[str | None, typer.Option("--event")] = None,
    list_only: Annotated[bool, typer.Option("--list")] = False,
) -> None:
    code, output = render_diff(pack, file_path=file_path, event_id=event, list_only=list_only)
    typer.echo(output)
    raise typer.Exit(code)


@pack_app.command("compare")
def pack_compare(
    baseline: Annotated[Path, typer.Option("--baseline", exists=True)],
    candidate: Annotated[Path, typer.Option("--candidate", exists=True)],
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format"),
    ] = "text",
) -> None:
    report = compare_packs(baseline, candidate)
    if output_format == "json":
        typer.echo(canonical_json_dumps(report.to_dict()))
    else:
        typer.echo(render_compare_text(report))


@app.command("assert")
def assert_cmd(
    baseline: Annotated[Path, typer.Option("--baseline", exists=True)],
    candidate: Annotated[Path, typer.Option("--candidate", exists=True)],
    policy: Annotated[Path | None, typer.Option("--policy")] = None,
    output_format: Annotated[Literal["text", "json"], typer.Option("--format")] = "text",
) -> None:
    result = run_assert_gate(
        baseline_path=baseline,
        candidate_path=candidate,
        policy_path=policy,
    )
    payload = {
        "passed": result.passed,
        "violations": result.violations,
        "policy": result.policy,
        "compare": result.report.to_dict(),
    }

    if output_format == "json":
        typer.echo(canonical_json_dumps(payload))
    else:
        if result.passed:
            typer.echo("assertion passed")
        else:
            typer.echo("assertion failed")
            for violation in result.violations:
                typer.echo(f"- {violation}")
    raise typer.Exit(0 if result.passed else 1)


@mcp_app.command(
    "wrap",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def mcp_wrap(
    ctx: typer.Context,
    name: Annotated[str, typer.Option("--name")],
    out: Annotated[Path, typer.Option("--out")] = Path("."),
) -> None:
    cmd = list(ctx.args)
    if not cmd:
        typer.echo("No command supplied. Use -- <cmd ...>")
        raise typer.Exit(2)
    code, transcript = run_wrap(name=name, cmd=cmd, output_root=out)
    typer.echo(str(transcript))
    raise typer.Exit(code)


@mcp_app.command("proxy")
def mcp_proxy(
    listen: Annotated[str, typer.Option("--listen")],
    upstream: Annotated[str, typer.Option("--upstream")],
    name: Annotated[str, typer.Option("--name")],
    out: Annotated[Path, typer.Option("--out")] = Path("."),
    redaction: Annotated[Path | None, typer.Option("--redaction")] = None,
    otel: Annotated[
        bool, typer.Option("--otel", help="Write OTel spans to <out>/otel/spans.jsonl")
    ] = False,
) -> None:
    span_recorder = None
    if otel:
        from flightlog.otel.span_export import SpanRecorder

        span_recorder = SpanRecorder(out)
    run_mcp_proxy(
        listen=listen,
        upstream=upstream,
        name=name,
        output_root=out,
        redaction_config_path=redaction,
        span_recorder=span_recorder,
    )


@mcp_app.command("wrap-http")
def mcp_wrap_http(
    name: Annotated[str, typer.Option("--name")],
    listen: Annotated[str, typer.Option("--listen")],
    upstream: Annotated[str, typer.Option("--upstream")],
    out: Annotated[Path, typer.Option("--out")] = Path("."),
    redaction: Annotated[Path | None, typer.Option("--redaction")] = None,
) -> None:
    """Record an HTTP MCP server's traffic (wrap semantics over HTTP proxy)."""
    run_wrap_http_blocking(
        name=name,
        listen=listen,
        upstream=upstream,
        output_root=out,
        redaction_config_path=redaction,
    )


@llm_app.command("proxy")
def llm_proxy(
    listen: Annotated[str, typer.Option("--listen")],
    upstream: Annotated[str, typer.Option("--upstream")],
    out: Annotated[Path, typer.Option("--out")] = Path("."),
    provider_family: Annotated[
        Literal["anthropic", "openai_compat", "gemini"],
        typer.Option("--provider-family"),
    ] = "openai_compat",
) -> None:
    run_llm_proxy(
        listen=listen,
        upstream=upstream,
        output_root=out,
        provider_family=provider_family,
    )


@mcp_app.command("list")
def mcp_list(
    client: Annotated[
        str,
        typer.Option(
            "--client",
            help="Backend to query: auto | claude_desktop | cursor | zed",
        ),
    ] = "auto",
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Parse this config file directly"),
    ] = None,
) -> None:
    try:
        discovered = discover_servers(client=client, config_path=config)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    if not discovered:
        typer.echo("No MCP servers found")
        return
    for item in discovered:
        typer.echo(
            "\t".join(
                [
                    str(item.get("client", "")),
                    str(item.get("name", "")),
                    str(item.get("command", "")),
                    json.dumps(item.get("args", []), separators=(",", ":")),
                    str(item.get("config_path", "")),
                ]
            )
        )


@export_app.command("audit")
def export_audit_cmd(
    pack: Annotated[Path, typer.Option("--pack", exists=True)],
    out: Annotated[Path, typer.Option("--out")],
    csv_path: Annotated[Path | None, typer.Option("--csv")] = None,
    config: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    export_audit(
        pack_path=pack,
        out_json=out,
        out_csv=csv_path,
        config_path=config,
    )
    typer.echo(str(out))


@app.command("sign")
def sign(
    pack: Annotated[Path, typer.Option("--pack", exists=True)],
    key: Annotated[Path, typer.Option("--key", exists=True)],
    signature: Annotated[Path | None, typer.Option("--signature")] = None,
) -> None:
    signature_path = sign_pack(pack_path=pack, private_key_path=key, signature_path=signature)
    typer.echo(str(signature_path))


@app.command("verify")
def verify(
    pack: Annotated[Path, typer.Option("--pack", exists=True)],
    key: Annotated[Path, typer.Option("--key", exists=True)],
    signature: Annotated[Path | None, typer.Option("--signature")] = None,
) -> None:
    ok, errors = verify_pack(pack_path=pack, public_key_path=key, signature_path=signature)
    if ok:
        typer.echo("signature verified")
        raise typer.Exit(0)
    for error in errors:
        typer.echo(error)
    raise typer.Exit(1)


@stub_app.command("generate")
def mcp_stub_generate(
    transcript: Annotated[Path, typer.Option("--transcript", exists=True)],
    out: Annotated[Path, typer.Option("--out")],
    server: Annotated[str | None, typer.Option("--server")] = None,
) -> None:
    stub = generate_stub_from_transcript(transcript, server_name=server)
    write_stub(out, stub)
    typer.echo(str(out))


@stub_app.command("serve")
def mcp_stub_serve(
    stub: Annotated[Path, typer.Option("--stub", exists=True)],
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Fail if call count exceeds captured sequence"),
    ] = False,
) -> None:
    code = serve_stub(stub, strict=strict)
    raise typer.Exit(code)


@replay_app.command("run")
def replay_run(
    pack: Annotated[Path, typer.Option("--pack", exists=True)],
    offline: Annotated[bool, typer.Option("--offline")] = False,
) -> None:
    ok, mismatches, events = run_replay(pack, offline=offline)
    if not ok:
        for mismatch in mismatches:
            typer.echo(mismatch)
        raise typer.Exit(1)
    typer.echo(f"Replay successful ({events} events)")


@sdk_app.command("install-sitecustomize")
def sdk_install(
    venv: Annotated[Path, typer.Option("--venv", help="Path to the target Python venv root")],
) -> None:
    """Install the Flightlog SDK capture .pth hook into a venv's site-packages."""
    try:
        pth_path = install_sitecustomize(venv)
        typer.echo(f"Installed: {pth_path}")
        typer.echo("Enable capture by setting FLIGHTLOG=1 before running your Python process.")
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc


@sdk_app.command("uninstall-sitecustomize")
def sdk_uninstall(
    venv: Annotated[Path, typer.Option("--venv", help="Path to the target Python venv root")],
) -> None:
    """Remove the Flightlog SDK capture .pth hook from a venv's site-packages."""
    try:
        removed = uninstall_sitecustomize(venv)
        if removed:
            typer.echo(f"Removed: {removed}")
        else:
            typer.echo("No hook installed.")
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
