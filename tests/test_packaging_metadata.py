import tomllib
from pathlib import Path


def test_pyproject_contains_cli_entrypoint() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    scripts = data.get("project", {}).get("scripts", {})
    assert scripts.get("flightlog") == "flightlog.cli:main"
