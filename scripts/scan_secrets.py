"""Scan working files, staged changes, and Git history with redacted diagnostics."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from process import cli, run
from repository import ROOT, require, source_paths


def report_secret_findings(report: dict, path: Path) -> None:
    for item in report["findings"]:
        finding = item["finding"]
        location = Path(finding["path"])
        if location.is_absolute() and location.is_relative_to(path):
            location = location.relative_to(path)
        commit = finding.get("git_metadata", {}).get("commit", {}).get("id")
        history = f" (commit {commit})" if commit else ""
        print(
            f"Secret finding: {location}:{finding['line']}:{finding['column_start']}: "
            f"{item['rule']['id']}{history}",
            file=sys.stderr,
            flush=True,
        )


def check_secret_scan(report: dict) -> None:
    summary = report["audit"]["summary"]
    require(
        summary["scan_succeeded"] > 0
        and all(
            summary[key] == 0
            for key in ("fetch_failed", "scan_partial", "scan_failed", "pending")
        ),
        "Kingfisher did not complete the requested scan",
    )


def secret_scan(path: Path, history: str, *, staged: bool = False) -> None:
    environment = os.environ.copy()
    if staged:
        # Kingfisher creates a temporary commit to scan the index.
        for role in ("AUTHOR", "COMMITTER"):
            environment[f"GIT_{role}_NAME"] = "Kingfisher"
            environment[f"GIT_{role}_EMAIL"] = "kingfisher@example.invalid"
    with tempfile.TemporaryDirectory(prefix="graftway-secrets-report-") as directory:
        report_path = Path(directory) / "report.json"
        try:
            run(
                "kingfisher",
                "scan",
                str(path),
                "--config",
                str(ROOT / ".kingfisher.yml"),
                "--git-history",
                history,
                *(["--staged"] if staged else []),
                "--no-validate",
                "--no-update-check",
                "--redact",
                "--format",
                "json",
                "--output",
                str(report_path),
                env=environment,
            )
        except subprocess.CalledProcessError:
            if report_path.is_file():
                report_secret_findings(
                    json.loads(report_path.read_text(encoding="utf-8")), path
                )
            raise
        report = json.loads(report_path.read_text(encoding="utf-8"))
        check_secret_scan(report)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="graftway-secrets-") as directory:
        for source in source_paths(ROOT):
            destination = Path(directory) / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                # Windows needs the link type before its relative target is copied.
                destination.symlink_to(
                    source.readlink(), target_is_directory=source.is_dir()
                )
            else:
                shutil.copyfile(source, destination)
        secret_scan(Path(directory), "none")
    secret_scan(ROOT, "none", staged=True)
    secret_scan(ROOT, "full")


if __name__ == "__main__":
    cli(main)
