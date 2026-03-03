from pathlib import Path

from typer.testing import CliRunner

from replaypack.cli import app


def test_docs_commands_smoke(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = Path("tests/fixtures/claude_code/claude_session.jsonl").resolve()
    out_dir = tmp_path / "docs-pack"

    build = runner.invoke(
        app,
        ["pack", "build", "--input", str(fixture), "--out", str(out_dir)],
    )
    assert build.exit_code == 0, build.stdout

    validate = runner.invoke(app, ["pack", "validate", "--path", str(out_dir)])
    assert validate.exit_code == 0, validate.stdout

    diff_list = runner.invoke(app, ["pack", "diff", "--pack", str(out_dir), "--list"])
    assert diff_list.exit_code == 0, diff_list.stdout
