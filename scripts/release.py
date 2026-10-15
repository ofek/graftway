"""Fail-closed validation of the release framework; no artifact production."""

import argparse
import os
import re
from pathlib import Path

from process import cli
from repository import ROOT, read_toml, require


def validate_configuration(root: Path = ROOT) -> dict:
    release = read_toml(root / "release.toml")
    require(release["schema-version"] == 1, "Unsupported release configuration schema")
    require(
        release["publication-enabled"] is False, "Artifact jobs are not implemented"
    )
    require(
        release["version-source"] == "workspace.package.version",
        "Invalid version source",
    )
    require(release["tag-prefix"] == "v", "Release tags must use the v prefix")
    require(
        len(release["cli"]) == 5, "Review changes to the five intended CLI platforms"
    )
    targets = {item["target"] for item in release["cli"]}
    require(len(targets) == len(release["cli"]), "Duplicate release targets")
    for item in release["cli"]:
        require(item["archive"] in {"zip", "tar.gz"}, "Unsupported archive type")
        require(bool(item["runner"]), "Every target needs an explicit runner")
    require(
        release["oci"]["platforms"] == ["linux/amd64", "linux/arm64"],
        "OCI runtime goals must remain Linux only",
    )
    require(
        release["oci"]["components"] == ["server", "indexing-worker"],
        "Review changes to the intended OCI components",
    )
    return release


def verify_tag(version: str, tag: str) -> None:
    match = re.fullmatch(
        r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
        r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?",
        version,
    )
    require(
        match is not None,
        f"Invalid release version: {version}",
    )
    if match[1]:
        require(
            all(
                not (part.isdigit() and len(part) > 1 and part[0] == "0")
                for part in match[1].split(".")
            ),
            f"Invalid numeric prerelease identifier: {version}",
        )
    require(
        tag == f"v{version}", f"Tag {tag!r} does not match workspace version {version}"
    )


def dry_run(root: Path = ROOT) -> None:
    configuration = validate_configuration(root)
    for target in configuration["cli"]:
        print(
            f"Future CLI: {target['target']} on {target['runner']} "
            f"({target['archive']})"
        )
    print("Future OCI: server and indexing-worker for linux/amd64 and linux/arm64")
    print(
        "Configuration valid. Publication disabled; "
        "no runtime artifacts were built or verified."
    )


def verify(root: Path = ROOT, tag: str = "") -> None:
    validate_configuration(root)
    version = (
        read_toml(root / "Cargo.toml")["workspace"].get("package", {}).get("version")
    )
    if version:
        require(
            bool(tag), "Set GRAFTWAY_RELEASE_TAG to the proposed v-prefixed release tag"
        )
        verify_tag(version, tag)
    raise ValueError(
        "Release blocked: no releasable runtime or artifact-producing jobs exist. "
        "Implement and test the artifact, compatibility, smoke-test, checksum, "
        "provenance, SBOM, license, and build-metadata gates "
        "before enabling publication."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["dry-run", "verify"])
    if parser.parse_args().mode == "dry-run":
        dry_run()
    else:
        verify(tag=os.environ.get("GRAFTWAY_RELEASE_TAG", ""))


if __name__ == "__main__":
    cli(main)
