import subprocess

from conftest import commit, fake_runner, git
from gittoolbox.refresh import refresh_repo


def test_up_to_date(setup):
    result = refresh_repo(setup.work)
    assert (result.status, result.detail) == ("up-to-date", "")


def test_updated_when_origin_moved(setup):
    before = git(setup.work, "rev-parse", "--short", "HEAD")
    commit(setup.other, "second.txt")
    git(setup.other, "push", "-q", "origin", "main")

    result = refresh_repo(setup.work)

    after = git(setup.work, "rev-parse", "--short", "HEAD")
    assert result.status == "updated"
    assert result.detail == f"{before}..{after}"
    assert (setup.work / "second.txt").exists()


def test_skipped_with_uncommitted_changes(setup):
    (setup.work / "first.txt").write_text("edited")
    result = refresh_repo(setup.work)
    assert (result.status, result.detail) == ("skipped", "uncommitted changes")


def test_skipped_without_upstream(local_repo):
    result = refresh_repo(local_repo)
    assert (result.status, result.detail) == ("skipped", "no upstream branch")


def test_skipped_on_detached_head(setup):
    git(setup.work, "checkout", "-q", "--detach")
    assert refresh_repo(setup.work).status == "skipped"


def test_failed_when_remote_unreachable(setup, tmp_path):
    git(setup.work, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    result = refresh_repo(setup.work)
    assert result.status == "failed" and result.detail.startswith("fetch:")


def test_failed_on_diverged_history_leaves_local_commits_alone(setup):
    commit(setup.other, "theirs.txt", date="2026-02-01T12:00:00+00:00")
    git(setup.other, "push", "-q", "origin", "main")
    mine = commit(setup.work, "mine.txt", date="2026-02-02T12:00:00+00:00")

    result = refresh_repo(setup.work)

    assert result.status == "failed" and result.detail.startswith("pull:")
    assert git(setup.work, "rev-parse", "HEAD") == mine


def test_failed_on_timeout_without_crashing(tmp_path):
    runner = fake_runner(raises=subprocess.TimeoutExpired(["git"], 60))
    result = refresh_repo(tmp_path, runner=runner)
    assert result.status == "failed" and "timed out" in result.detail
