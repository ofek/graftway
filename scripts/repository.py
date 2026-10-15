"""Shared repository paths, configuration, and Git source inventory."""

import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def source_paths(root: Path = ROOT) -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
    )
    paths = {root / name.decode() for name in output.split(b"\0") if name}
    # Git's cached inventory includes tracked files deleted from the working tree.
    return sorted(path for path in paths if path.exists())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)
