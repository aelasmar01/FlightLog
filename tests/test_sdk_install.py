"""Tests for flightlog sdk install-sitecustomize / uninstall-sitecustomize."""

from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

from flightlog.cli import app
from flightlog.llm.sdk_capture.install import (
    PTH_CONTENT,
    PTH_NAME,
    install_sitecustomize,
    uninstall_sitecustomize,
)


def _make_fake_venv(tmp_path: Path) -> Path:
    """Create a minimal fake venv directory with a site-packages folder."""
    venv = tmp_path / "venv"
    site = (
        venv / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    )
    site.mkdir(parents=True)
    return venv


def test_install_writes_pth_file(tmp_path: Path) -> None:
    venv = _make_fake_venv(tmp_path)
    pth_path = install_sitecustomize(venv)
    assert pth_path.exists()
    assert pth_path.name == PTH_NAME
    assert pth_path.read_text(encoding="utf-8") == PTH_CONTENT


def test_uninstall_removes_pth_file(tmp_path: Path) -> None:
    venv = _make_fake_venv(tmp_path)
    install_sitecustomize(venv)
    removed = uninstall_sitecustomize(venv)
    assert removed is not None
    assert not removed.exists()


def test_uninstall_when_not_installed_returns_none(tmp_path: Path) -> None:
    venv = _make_fake_venv(tmp_path)
    result = uninstall_sitecustomize(venv)
    assert result is None


def test_install_missing_venv_raises(tmp_path: Path) -> None:
    import pytest

    missing = tmp_path / "no-such-venv"
    with pytest.raises(FileNotFoundError):
        install_sitecustomize(missing)


def test_cli_install_and_uninstall(tmp_path: Path) -> None:
    venv = _make_fake_venv(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["sdk", "install-sitecustomize", "--venv", str(venv)])
    assert result.exit_code == 0, result.output
    assert "Installed" in result.output

    result = runner.invoke(app, ["sdk", "uninstall-sitecustomize", "--venv", str(venv)])
    assert result.exit_code == 0, result.output
    assert "Removed" in result.output
