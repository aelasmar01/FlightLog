"""Install/uninstall the Flightlog SDK capture .pth hook into a Python venv."""

from __future__ import annotations

import sys
from pathlib import Path

PTH_NAME = "flightlog_sdk_capture.pth"
PTH_CONTENT = "import flightlog.llm.sdk_capture.sitecustomize\n"


def _site_packages(venv_path: Path) -> Path:
    """Return the site-packages directory for the given venv root."""
    candidates = [
        venv_path
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages",
        venv_path / "lib" / f"python{sys.version_info.major}" / "site-packages",
        venv_path / "Lib" / "site-packages",  # Windows
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"Cannot locate site-packages under {venv_path}. "
        "Ensure the venv exists and was created with 'python -m venv' or 'uv venv'."
    )


def install_sitecustomize(venv_path: Path) -> Path:
    """Write the .pth hook into *venv_path*/lib/.../site-packages.

    Returns the path of the written .pth file.
    """
    site_packages = _site_packages(venv_path)
    pth_path = site_packages / PTH_NAME
    pth_path.write_text(PTH_CONTENT, encoding="utf-8")
    return pth_path


def uninstall_sitecustomize(venv_path: Path) -> Path | None:
    """Remove the .pth hook from *venv_path*.

    Returns the removed path, or None if no hook was installed.
    """
    try:
        site_packages = _site_packages(venv_path)
    except FileNotFoundError:
        return None
    pth_path = site_packages / PTH_NAME
    if pth_path.exists():
        pth_path.unlink()
        return pth_path
    return None
