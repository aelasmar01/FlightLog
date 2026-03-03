from pathlib import Path

from typer.testing import CliRunner

from replaypack.cli import app


def test_help_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

    result2 = runner.invoke(app, ["pack", "--help"])
    assert result2.exit_code == 0


def test_pack_build_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = Path("tests/fixtures/claude_code/claude_session.jsonl").resolve()
    out_dir = tmp_path / "pack"

    result = runner.invoke(
        app,
        [
            "pack",
            "build",
            "--input",
            str(input_path),
            "--out",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "timeline.jsonl").exists()


def test_pack_build_zip_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = Path("tests/fixtures/claude_code/claude_session.jsonl").resolve()
    zip_path = tmp_path / "pack.zip"

    result = runner.invoke(
        app,
        [
            "pack",
            "build",
            "--input",
            str(input_path),
            "--out",
            str(zip_path),
            "--zip",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert zip_path.exists()
