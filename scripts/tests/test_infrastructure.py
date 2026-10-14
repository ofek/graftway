"""Test source inventory, secret scans, navigation, and release gates."""

import os
import secrets
import string
import subprocess
import sys
from pathlib import Path

import pytest

import docs
import process
import release
import repository
import scan_secrets


@pytest.fixture
def git_repository(tmp_path):
    def git(*args):
        result = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Validation",
                "-c",
                "user.email=validation@example.invalid",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout.strip()

    git("init", "-q")
    return tmp_path, git


def test_source_inventory_excludes_unstaged_deletions(git_repository):
    root, git = git_repository
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    for name in [
        "tracked.txt",
        "tracked with spaces.txt",
        "deleted.txt",
        "untracked.txt",
        "ignored.txt",
    ]:
        (root / name).write_text("Source inventory fixture.\n", encoding="utf-8")
    git("add", "tracked.txt", "tracked with spaces.txt", "deleted.txt")
    (root / "deleted.txt").unlink()
    assert repository.source_paths(root) == [
        root / ".gitignore",
        root / "tracked with spaces.txt",
        root / "tracked.txt",
        root / "untracked.txt",
    ]


def test_secret_scan_rejects_current_and_deleted_history(git_repository, capfd):
    tmp_path, git = git_repository
    sample = "ghp_" + "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(36)
    )
    source = tmp_path / "token.txt"
    source.write_text(f"github_token = {sample}\n", encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError) as current:
        scan_secrets.secret_scan(tmp_path, "none")
    assert current.value.returncode == 200
    current_output = capfd.readouterr()
    assert "token.txt:1:" in current_output.err
    assert "github-pat" in current_output.err
    assert sample not in current_output.out + current_output.err
    report_command = current.value.cmd
    assert not Path(report_command[report_command.index("--output") + 1]).exists()
    git("add", "token.txt")
    git("commit", "-q", "-m", "test: record synthetic token")
    commit = git("rev-parse", "HEAD")
    source.unlink()
    git("add", "-u")
    git("commit", "-q", "-m", "test: remove synthetic token")
    with pytest.raises(subprocess.CalledProcessError) as history:
        scan_secrets.secret_scan(tmp_path, "full")
    assert history.value.returncode == 200
    history_output = capfd.readouterr()
    assert "token.txt:1:" in history_output.err
    assert "github-pat" in history_output.err
    assert f"commit {commit}" in history_output.err
    assert sample not in history_output.out + history_output.err


@pytest.mark.parametrize("working_tree", ["sanitized", "deleted"])
def test_secret_check_rejects_staged_secrets_in_linked_worktree(
    git_repository, monkeypatch, capfd, working_tree
):
    root, git = git_repository
    git("commit", "--allow-empty", "-q", "-m", "test: create clean baseline")
    worktree = root / "linked worktree"
    git("worktree", "add", "-q", "-b", "secret-scan", str(worktree))
    (worktree / ".kingfisher.yml").write_bytes(
        (repository.ROOT / ".kingfisher.yml").read_bytes()
    )
    empty_config = root / "empty-git-config"
    empty_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        for field in ("NAME", "EMAIL"):
            monkeypatch.delenv(f"GIT_{role}_{field}", raising=False)
    monkeypatch.setattr(scan_secrets, "ROOT", worktree)
    scan_secrets.main()

    sample = "ghp_" + "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(36)
    )
    source = worktree / "token with spaces.txt"
    source.write_text(f"github_token = {sample}\n", encoding="utf-8")
    git("-C", str(worktree), "add", source.name)
    if working_tree == "sanitized":
        source.write_text("Sanitized working tree.\n", encoding="utf-8")
    else:
        source.unlink()
    assert sample in git("-C", str(worktree), "show", f":{source.name}")
    staged_tree = git("-C", str(worktree), "write-tree")
    scan_secrets.secret_scan(worktree, "none")
    scan_secrets.secret_scan(worktree, "full")
    capfd.readouterr()

    with pytest.raises(subprocess.CalledProcessError) as staged:
        scan_secrets.main()
    assert staged.value.returncode == 200
    assert "--staged" in staged.value.cmd
    output = capfd.readouterr()
    assert f"{source.name}:1:" in output.err
    assert "github-pat" in output.err
    assert sample not in output.out + output.err
    report_command = staged.value.cmd
    assert not Path(report_command[report_command.index("--output") + 1]).exists()
    assert git("-C", str(worktree), "write-tree") == staged_tree

    git("-C", str(worktree), "add", "--all")
    scan_secrets.main()
    assert os.environ.get("GIT_AUTHOR_NAME") is None
    assert os.environ.get("GIT_COMMITTER_NAME") is None


@pytest.mark.parametrize("directory_target", [False, True])
def test_secret_check_preserves_symlinks(git_repository, monkeypatch, directory_target):
    root, git = git_repository
    target = root / "link target"
    if directory_target:
        target.mkdir()
        (target / "source.txt").write_text("Clean source.\n", encoding="utf-8")
    else:
        target.write_text("Clean source.\n", encoding="utf-8")
    link = root / "a relative link"
    try:
        link.symlink_to(target.name, target_is_directory=directory_target)
    except OSError as error:
        if os.name == "nt" and error.winerror == 1314:
            pytest.skip(
                "Creating Windows symlinks requires Developer Mode or privilege"
            )
        raise
    (root / ".kingfisher.yml").write_bytes(
        (repository.ROOT / ".kingfisher.yml").read_bytes()
    )
    git("-c", "core.symlinks=true", "add", ".")
    git("commit", "-q", "-m", "test: record symlink")
    monkeypatch.setattr(scan_secrets, "ROOT", root)
    original_scan = scan_secrets.secret_scan

    def check_snapshot(path, history, *, staged=False):
        if path != root:
            snapshot_link = path / link.name
            assert snapshot_link.is_symlink()
            assert snapshot_link.readlink() == link.readlink()
            assert snapshot_link.is_dir() == directory_target
            assert snapshot_link.is_file() != directory_target
        original_scan(path, history, staged=staged)

    monkeypatch.setattr(scan_secrets, "secret_scan", check_snapshot)
    scan_secrets.main()


def test_failed_secret_scan_without_report_propagates(tmp_path, monkeypatch):
    def failed_run(*command, **_kwargs):
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(scan_secrets, "run", failed_run)
    with pytest.raises(subprocess.CalledProcessError) as error:
        scan_secrets.secret_scan(tmp_path, "none")
    assert error.value.returncode == 2


@pytest.mark.parametrize(
    ("name", "version", "metadata", "expected"),
    [
        ("license-probe", "1.0.0", "License-Expression: MIT", 0),
        (
            "license-probe",
            "1.0.0",
            "License-Expression: Apache-2.0 OR BSD-2-Clause",
            0,
        ),
        ("license-probe", "1.0.0", "License-Expression: GPL-3.0-only", 1),
        ("license-probe", "1.0.0", "License-Expression: MIT AND GPL-3.0-only", 1),
        ("license-probe", "1.0.0", "", 1),
        (
            "Jinja2",
            "3.1.7",
            "Classifier: License :: OSI Approved :: BSD License",
            1,
        ),
        (
            "colorama",
            "0.4.7",
            "Classifier: License :: OSI Approved :: BSD License",
            1,
        ),
    ],
)
def test_license_policy_checks_metadata_and_exception_versions(
    tmp_path, name, version, metadata, expected
):
    # Add synthetic installed metadata without changing the project's environment.
    distribution = tmp_path / f"{name}-{version}.dist-info"
    distribution.mkdir()
    (distribution / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{metadata}\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(tmp_path), environment.get("PYTHONPATH")])
    )
    result = subprocess.run(
        [sys.executable, "-m", "piplicenses"],
        cwd=repository.ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == expected, result.stdout + result.stderr
    if expected:
        assert name.lower() in result.stderr.lower()


@pytest.mark.parametrize(
    "failure", ["fetch_failed", "scan_partial", "scan_failed", "pending"]
)
def test_incomplete_secret_scan_is_rejected(failure):
    summary = {
        "scan_succeeded": 1,
        "fetch_failed": 0,
        "scan_partial": 0,
        "scan_failed": 0,
        "pending": 0,
    }
    summary[failure] = 1
    with pytest.raises(ValueError, match="complete"):
        scan_secrets.check_secret_scan({"audit": {"summary": summary}})


def test_interrupted_script_fails(capsys):
    def interrupt():
        raise KeyboardInterrupt

    with pytest.raises(SystemExit) as stopped:
        process.cli(interrupt)
    assert stopped.value.code == 130
    assert "Stopped." in capsys.readouterr().err


@pytest.mark.parametrize("navigation", ["absent.md", "index.md"])
def test_navigation_must_match_source_pages(tmp_path, monkeypatch, navigation):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Home\n", encoding="utf-8")
    if navigation == "index.md":
        (tmp_path / "docs" / "unlisted.md").write_text("# Unlisted\n", encoding="utf-8")
    configuration = repository.read_toml(repository.ROOT / "zensical.toml")
    configuration["project"]["nav"] = [{"Home": navigation}]
    monkeypatch.setattr(docs, "read_toml", lambda path: configuration)
    with pytest.raises(ValueError, match="navigation"):
        docs.check_documentation(tmp_path)


def test_bootstrap_configuration_and_publication_gate():
    release.validate_configuration()
    with pytest.raises(ValueError, match="Release blocked"):
        release.verify(tag="v0.1.0")


@pytest.mark.parametrize("version", ["0.1.0", "0.1.0-rc.1", "0.1.0+build.1"])
def test_tag_matches_workspace_version(version):
    release.verify_tag(version, f"v{version}")


@pytest.mark.parametrize(
    ("version", "tag"),
    [
        ("0.1.0", "v0.2.0"),
        ("01.1.0", "v01.1.0"),
        ("0.1.0-rc..1", "v0.1.0-rc..1"),
        ("0.1.0-rc.01", "v0.1.0-rc.01"),
    ],
)
def test_invalid_tag_or_version_fails(version, tag):
    with pytest.raises(ValueError):
        release.verify_tag(version, tag)


def test_enabling_publication_fails(monkeypatch):
    configuration = repository.read_toml(repository.ROOT / "release.toml")
    configuration["publication-enabled"] = True
    monkeypatch.setattr(release, "read_toml", lambda path: configuration)
    with pytest.raises(ValueError, match="Artifact jobs"):
        release.validate_configuration()
