"""Validate documentation navigation and links under the deployment subpath."""

import argparse
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from process import cli, run
from repository import ROOT, read_toml, require


def nav_paths(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return set().union(*(nav_paths(item) for item in value))
    if isinstance(value, dict):
        return set().union(*(nav_paths(item) for item in value.values()))
    raise ValueError(f"Invalid documentation navigation: {value}")


def check_documentation(root: Path = ROOT) -> None:
    # Zensical's strict mode does not reject missing navigation pages.
    documentation = read_toml(root / "zensical.toml")["project"]
    directory = root / documentation["docs_dir"]
    actual = {
        path.relative_to(directory).as_posix() for path in directory.rglob("*.md")
    }
    navigation = nav_paths(documentation["nav"])
    require(
        navigation == actual,
        f"Docs navigation differs from source pages: "
        f"missing files={sorted(navigation - actual)}, "
        f"unlisted pages={sorted(actual - navigation)}",
    )


def check_links() -> None:
    configuration = read_toml(ROOT / "zensical.toml")["project"]
    site = ROOT / configuration["site_dir"]
    url = configuration["site_url"]
    prefix = urlsplit(url).path
    # Mirror the deployment subpath without requiring Windows symlink privileges.
    with tempfile.TemporaryDirectory(prefix="graftway-site-") as directory:
        deployment = Path(directory) / prefix.strip("/")
        shutil.copytree(site, deployment, dirs_exist_ok=True)
        run(
            "lychee",
            "--offline",
            "--include-fragments",
            "--no-progress",
            "--no-ignore",
            "--index-files",
            "index.html",
            "--root-dir",
            directory,
            "--remap",
            f"^{re.escape(url)} {deployment.as_uri()}/",
            str(deployment),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["navigation", "links"])
    if parser.parse_args().mode == "navigation":
        check_documentation()
    else:
        check_links()


if __name__ == "__main__":
    cli(main)
