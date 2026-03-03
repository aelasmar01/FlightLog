"""ReplayPack command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from replaypack.diff_viewer import render_diff
from replaypack.ingest import select_ingestor
from replaypack.mcp.discovery import discover_servers
from replaypack.mcp.proxy_http import run_proxy
from replaypack.mcp.stub_server import serve_stub
from replaypack.mcp.stubgen import generate_stub_from_transcript, write_stub
from replaypack.mcp.wrap_stdio import run_wrap
from replaypack.normalize import ARTIFACT_THRESHOLD_BYTES, normalize_events
from replaypack.pack_writer import create_pack, validate_pack
from replaypack.redaction import load_redaction_config, redact_artifacts
from replaypack.replay_runner import run_replay

app = typer.Typer(help="ReplayPack CLI")
pack_app = typer.Typer(help="Pack build and inspection commands")
mcp_app = typer.Typer(help="MCP capture/replay commands")
stub_app = typer.Typer(help="MCP stub commands")
replay_app = typer.Typer(help="Replay commands")

app.add_typer(pack_app, name="pack")
app.add_typer(mcp_app, name="mcp")
app.add_typer(replay_app, name="replay")
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
def pack_validate(path: Annotated[Path, typer.Option("--path", exists=True)]) -> None:
    ok, errors = validate_pack(path)
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
) -> None:
    run_proxy(
        listen=listen,
        upstream=upstream,
        name=name,
        output_root=out,
        redaction_config_path=redaction,
    )


@mcp_app.command("list")
def mcp_list() -> None:
    discovered = discover_servers()
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
def mcp_stub_serve(stub: Annotated[Path, typer.Option("--stub", exists=True)]) -> None:
    code = serve_stub(stub)
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
