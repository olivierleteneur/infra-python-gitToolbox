from conftest import commit, fake_runner, git
from gittoolbox.branches import count_branches


def test_counts_local_and_remote_without_origin_head(setup):
    for name in ["feature-a", "feature-b"]:
        git(setup.other, "switch", "-q", "-c", name)
        commit(setup.other, f"{name}.txt")
        git(setup.other, "push", "-q", "origin", name)
    git(setup.work, "fetch", "-q")
    git(setup.work, "switch", "-q", "-c", "local-only")

    count = count_branches(setup.work)

    assert (count.local, count.remote, count.error) == (2, 3, "")


def test_repo_without_remote(local_repo):
    count = count_branches(local_repo)
    assert (count.local, count.remote) == (1, 0)


def test_git_failure_is_reported(tmp_path):
    count = count_branches(tmp_path, runner=fake_runner(returncode=128, stderr="not a git repository"))
    assert count.local is None and "not a git repository" in count.error
