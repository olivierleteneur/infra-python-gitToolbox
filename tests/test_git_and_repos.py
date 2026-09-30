import subprocess
from pathlib import Path

import pytest

from conftest import fake_runner, git
from gittoolbox.errors import GitNotFound, ToolboxError
from gittoolbox.git import run_git
from gittoolbox.repos import discover, load_list


# --- run_git ------------------------------------------------------------------

def test_run_git_success(local_repo):
    result = run_git(local_repo, "rev-parse", "--abbrev-ref", "HEAD")
    assert result.ok and result.out == "main"


def test_run_git_failure_keeps_stderr(local_repo):
    result = run_git(local_repo, "rev-parse", "no-such-ref")
    assert not result.ok and result.err


def test_run_git_timeout_is_a_failure_not_a_crash(tmp_path):
    runner = fake_runner(raises=subprocess.TimeoutExpired(["git"], 5))
    result = run_git(tmp_path, "fetch", runner=runner, timeout=5)
    assert not result.ok and "timed out after 5s" in result.err


def test_run_git_missing_binary(tmp_path):
    with pytest.raises(GitNotFound, match="git executable not found"):
        run_git(tmp_path, "status", runner=fake_runner(raises=FileNotFoundError("git")))


# --- discover -------------------------------------------------------------------

def test_discover_finds_nested_repos_sorted(tmp_path):
    for path in ["b", "a", "group/c"]:
        (tmp_path / path).mkdir(parents=True)
        git(tmp_path / path, "init", "-q")
    assert [p.relative_to(tmp_path).as_posix() for p in discover(tmp_path)] == ["a", "b", "group/c"]


def test_discover_does_not_descend_into_a_repo(tmp_path):
    git(tmp_path, "init", "-q", "outer")
    (tmp_path / "outer" / "vendor" / "inner").mkdir(parents=True)
    git(tmp_path / "outer" / "vendor" / "inner", "init", "-q")
    assert [p.name for p in discover(tmp_path)] == ["outer"]


def test_discover_respects_max_depth_and_skips_hidden(tmp_path):
    (tmp_path / "a" / "b" / "deep").mkdir(parents=True)
    git(tmp_path / "a" / "b" / "deep", "init", "-q")
    (tmp_path / ".cache" / "repo").mkdir(parents=True)
    git(tmp_path / ".cache" / "repo", "init", "-q")
    assert discover(tmp_path, max_depth=2) == []
    assert [p.name for p in discover(tmp_path, max_depth=3)] == ["deep"]


def test_discover_root_is_itself_a_repo(local_repo):
    assert discover(local_repo) == [local_repo]


def test_discover_missing_root(tmp_path):
    with pytest.raises(ToolboxError, match="not a directory"):
        discover(tmp_path / "missing")


def test_discover_empty_root(tmp_path):
    assert discover(tmp_path) == []


# --- load_list ------------------------------------------------------------------

def test_load_list_resolves_relative_paths_and_ignores_comments(tmp_path):
    lst = tmp_path / "repos.lst"
    lst.write_text("# my repos\nalpha\n\n  group/beta  \n/abs/gamma\n")
    assert load_list(lst, tmp_path) == [tmp_path / "alpha", tmp_path / "group/beta", Path("/abs/gamma")]


def test_load_list_missing_file(tmp_path):
    with pytest.raises(ToolboxError, match="cannot read"):
        load_list(tmp_path / "absent.lst", tmp_path)
