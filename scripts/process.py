"""Run native commands and report failures from focused repository scripts."""

import shutil
import subprocess
import sys
from collections.abc import Callable

from repository import ROOT, require


def run(*command: str, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    executable = shutil.which(command[0])
    require(executable is not None, f"Missing {command[0]}; run mise install --locked")
    subprocess.run(
        [executable, *command[1:]],
        cwd=ROOT,
        check=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def cli(main: Callable[[], None]) -> None:
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        sys.exit(130)
    except (ValueError, subprocess.CalledProcessError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
