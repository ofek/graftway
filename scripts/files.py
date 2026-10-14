"""Pass Git's source inventory to tools without shell splitting or globbing."""

import argparse

from process import cli, run
from repository import ROOT, source_paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["format", "check", "links"])
    mode = parser.parse_args().mode
    paths = [str(path.relative_to(ROOT)) for path in source_paths()]
    if mode == "links":
        run(
            "lychee",
            "--offline",
            "--include-fragments",
            "--no-progress",
            *(path for path in paths if path.endswith(".md")),
        )
    else:
        run(
            "editorconfig-checker",
            *(["-fix"] if mode == "format" else []),
            "-disable-indent-size",
            *paths,
        )


if __name__ == "__main__":
    cli(main)
