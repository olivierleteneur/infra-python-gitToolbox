import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.org",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.org",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}
OLD = "2026-01-01T12:00:00+00:00"     # 90 days before NOW
RECENT = "2026-03-25T12:00:00+00:00"  # 7 days before NOW
NOW = 1775044800                       # 2026-04-01T12:00:00Z


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    """Tests never read the developer's git config, and the tool inherits the same env."""
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


def git(cwd, *args, date=None):
    env = {**os.environ, **GIT_ENV}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo, name, date=OLD):
    (Path(repo) / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name, date=date)
    return git(repo, "rev-parse", "HEAD")


@dataclass
class Setup:
    remote: Path   # bare repository playing "origin"
    other: Path    # another clone, used to push changes to origin
    work: Path     # the clone the tool works on, inside root
    root: Path


@pytest.fixture
def setup(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    commit(other, "first.txt")
    git(other, "push", "-q", "origin", "main")
    root = tmp_path / "root"
    root.mkdir()
    work = root / "project"
    git(tmp_path, "clone", "-q", str(remote), str(work))
    return Setup(remote, other, work, root)


@pytest.fixture
def local_repo(tmp_path):
    repo = tmp_path / "root" / "solo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "first.txt")
    return repo


def fake_runner(returncode=0, stdout="", stderr="", raises=None):
    def run(cmd, **kwargs):
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    return run
