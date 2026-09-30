import io

from conftest import NOW, OLD, commit, git
from gittoolbox.cli import main
from test_cleanup import branch


def run(*argv, now=NOW):
    out = io.StringIO()
    code = main(list(argv), now=now, out=out)
    return code, out.getvalue()


def test_no_repository_found(tmp_path):
    code, out = run("--root", str(tmp_path), "branches")
    assert code == 1 and "No git repository found" in out


def test_missing_list_file_is_a_usage_error(tmp_path):
    code, out = run("--root", str(tmp_path), "--list", str(tmp_path / "absent.lst"), "branches")
    assert code == 2 and "cannot read" in out


def test_refresh_reports_every_repo_and_fails_if_one_failed(setup, tmp_path):
    broken = setup.root / "broken"
    git(tmp_path, "clone", "-q", str(setup.remote), str(broken))
    git(broken, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    code, out = run("--root", str(setup.root), "refresh")

    assert code == 1
    assert "broken" in out and "failed" in out
    assert "project" in out and "up-to-date" in out


def test_refresh_uses_the_list_file(setup, tmp_path):
    lst = tmp_path / "repos.lst"
    lst.write_text("project\n")
    code, out = run("--root", str(setup.root), "--list", str(lst), "refresh")
    assert code == 0 and "project" in out


def test_branches(setup):
    code, out = run("--root", str(setup.root), "branches")
    assert code == 0 and "project" in out and "local 1" in out and "remote 1" in out


def test_cleanup_is_dry_run_by_default(local_repo):
    branch(local_repo, "old-merged", OLD)
    code, out = run("--root", str(local_repo.parent), "cleanup")
    assert code == 0 and "--apply" in out
    assert any(l.split()[1:] == ["would", "delete", "old-merged", "(90", "days", "old)"] for l in out.splitlines())
    assert "old-merged" in git(local_repo, "branch", "--list")


def test_cleanup_apply_deletes(local_repo):
    branch(local_repo, "old-merged", OLD)
    code, out = run("--root", str(local_repo.parent), "cleanup", "--apply")
    assert code == 0 and any(l.split()[1:3] == ["deleted", "old-merged"] for l in out.splitlines())
    assert "old-merged" not in git(local_repo, "branch", "--list")


def test_cleanup_protect_option(local_repo):
    branch(local_repo, "old-merged", OLD)
    code, out = run("--root", str(local_repo.parent), "cleanup", "--protect", "old-merged")
    assert "old-merged" not in out


def test_cleanup_repo_without_default_branch_is_reported(tmp_path):
    repo = tmp_path / "trunk"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "trunk")
    commit(repo, "a.txt")
    code, out = run("--root", str(tmp_path), "cleanup")
    assert code == 1 and "default branch" in out


def test_readme_exit_code_reflects_findings(tmp_path):
    ok = tmp_path / "ok"
    ok.mkdir()
    git(ok, "init", "-q")
    (ok / "README.md").write_text("# Ok\n## Installation\n## Usage\n" + "x\n" * 10)
    assert run("--root", str(tmp_path), "readme")[0] == 0

    bad = tmp_path / "bad"
    bad.mkdir()
    git(bad, "init", "-q")
    code, out = run("--root", str(tmp_path), "readme")
    assert code == 1 and "bad" in out and "missing" in out


def test_list_entry_that_is_not_a_repo_is_reported_and_others_continue(setup, tmp_path):
    lst = tmp_path / "repos.lst"
    lst.write_text("project\nvanished\n")
    code, out = run("--root", str(setup.root), "--list", str(lst), "refresh")
    assert code == 1
    assert "vanished" in out and "not a git repository" in out
    assert "up-to-date" in out
