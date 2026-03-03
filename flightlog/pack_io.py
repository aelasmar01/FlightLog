"""Helpers for opening replay packs from directories or zip files."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile


@contextmanager
def open_pack(pack_path: Path) -> Iterator[Path]:
    if pack_path.is_dir():
        yield pack_path
        return

    if pack_path.suffix == ".zip" and pack_path.is_file():
        with TemporaryDirectory(prefix="flightlog_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            with ZipFile(pack_path, "r") as archive:
                archive.extractall(tmp_path)
            yield tmp_path
        return

    raise FileNotFoundError(f"Unsupported pack path: {pack_path}")
