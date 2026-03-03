from pathlib import Path

from typer.testing import CliRunner

from flightlog.cli import app


def test_pack_diff_list_and_file(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = Path("tests/fixtures/diffs/log_derived/log_diff.jsonl").resolve()
    out_dir = tmp_path / "pack"

    build = runner.invoke(
        app,
        ["pack", "build", "--input", str(input_path), "--out", str(out_dir)],
    )
    assert build.exit_code == 0, build.stdout

    listed = runner.invoke(app, ["pack", "diff", "--pack", str(out_dir), "--list"])
    assert listed.exit_code == 0
    assert "src/main.py" in listed.stdout

    shown = runner.invoke(
        app,
        ["pack", "diff", "--pack", str(out_dir), "--file", "src/main.py"],
    )
    assert shown.exit_code == 0
    assert "---" in shown.stdout
    assert "+++" in shown.stdout
    assert "@@" in shown.stdout

    missing = runner.invoke(
        app,
        ["pack", "diff", "--pack", str(out_dir), "--file", "missing.py"],
    )
    assert missing.exit_code != 0
