import pytest

from conftest import NOW, OLD, RECENT, commit, git
from gittoolbox.cleanup import DEFAULT_PROTECTED, default_branch, delete_branches, find_stale
from gittoolbox.errors import ToolboxError


def branch(repo, name, date, merge=True):
    """Create a branch with one commit at `date`, optionally merged back into main."""
    git(repo, "switch", "-q", "-c", name)
    commit(repo, f"{name}.txt", date=date)
    git(repo, "switch", "-q", "main")
    if merge:
        git(repo, "merge", "-q", "--no-ff", "-m", f"merge {name}", name, date=date)


def names(candidates):
    return sorted(c.name for c in candidates)


# --- default_branch -------------------------------------------------------------

def test_default_branch_from_origin_head(setup):
    assert default_branch(setup.work) == "main"


def test_default_branch_falls_back_to_master(tmp_path):
    git(tmp_path, "init", "-q", "-b", "master")
    commit(tmp_path, "a.txt")
    assert default_branch(tmp_path) == "master"


def test_default_branch_unknown(tmp_path):
    git(tmp_path, "init", "-q", "-b", "trunk")
    commit(tmp_path, "a.txt")
    with pytest.raises(ToolboxError, match="default branch"):
        default_branch(tmp_path)


# --- find_stale : local -------------------------------------------------------------

def test_only_old_merged_branches_are_candidates(local_repo):
    branch(local_repo, "old-merged", OLD)
    branch(local_repo, "recent-merged", RECENT)
    branch(local_repo, "old-unmerged", OLD, merge=False)

    candidates = find_stale(local_repo, days=60, now=NOW)

    assert names(candidates) == ["old-merged"]
    assert candidates[0].age_days == 90 and candidates[0].remote is False


def test_age_threshold_is_configurable(local_repo):
    branch(local_repo, "recent-merged", RECENT)
    assert names(find_stale(local_repo, days=5, now=NOW)) == ["recent-merged"]


def test_protected_and_current_branches_are_kept(local_repo):
    branch(local_repo, "develop", OLD)
    branch(local_repo, "keep-me", OLD)
    branch(local_repo, "current", OLD)
    git(local_repo, "switch", "-q", "current")

    candidates = find_stale(local_repo, days=60, now=NOW, protected=DEFAULT_PROTECTED | {"keep-me"})

    assert names(candidates) == []


def test_find_stale_is_a_dry_run(local_repo):
    branch(local_repo, "old-merged", OLD)
    find_stale(local_repo, days=60, now=NOW)
    assert "old-merged" in git(local_repo, "branch", "--list")


# --- find_stale : remote -------------------------------------------------------------

def push_merged_branch(setup, name, date):
    branch(setup.other, name, date)
    git(setup.other, "push", "-q", "origin", "main", name)
    git(setup.work, "fetch", "-q")
    git(setup.work, "merge", "-q", "--ff-only", "origin/main")


def test_remote_branches_only_with_include_remote(setup):
    push_merged_branch(setup, "old-remote", OLD)
    assert find_stale(setup.work, days=60, now=NOW) == []
    candidates = find_stale(setup.work, days=60, now=NOW, include_remote=True)
    assert [(c.name, c.remote) for c in candidates] == [("old-remote", True)]


# --- delete_branches -------------------------------------------------------------------

def test_delete_local_branch(local_repo):
    branch(local_repo, "old-merged", OLD)
    outcomes = delete_branches(local_repo, find_stale(local_repo, days=60, now=NOW))
    assert [(o.candidate.name, o.ok) for o in outcomes] == [("old-merged", True)]
    assert "old-merged" not in git(local_repo, "branch", "--list")


def test_delete_remote_branch(setup):
    push_merged_branch(setup, "old-remote", OLD)
    delete_branches(setup.work, find_stale(setup.work, days=60, now=NOW, include_remote=True))
    assert "old-remote" not in git(setup.remote, "branch", "--list")


def test_failed_remote_deletion_is_reported_and_others_continue(setup, tmp_path):
    push_merged_branch(setup, "old-remote", OLD)
    branch(setup.work, "old-local", OLD)
    candidates = find_stale(setup.work, days=60, now=NOW, include_remote=True)
    git(setup.work, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    outcomes = {o.candidate.name: o for o in delete_branches(setup.work, candidates)}

    assert outcomes["old-remote"].ok is False and outcomes["old-remote"].detail
    assert outcomes["old-local"].ok is True
