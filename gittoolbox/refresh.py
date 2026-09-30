import subprocess
from dataclasses import dataclass
from pathlib import Path

from gittoolbox.git import run_git


@dataclass(frozen=True)
class RefreshResult:
    repo: Path
    status: str  # updated | up-to-date | skipped | failed
    detail: str = ""


def refresh_repo(repo: Path, runner=subprocess.run) -> RefreshResult:
    """Fetch then fast-forward the current branch. Never merges, rebases or touches local changes."""
    def git(*args):
        return run_git(repo, *args, runner=runner)

    status = git("status", "--porcelain")
    if not status.ok:
        return RefreshResult(repo, "failed", f"status: {status.err}")
    if status.out:
        return RefreshResult(repo, "skipped", "uncommitted changes")
    if not git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").ok:
        return RefreshResult(repo, "skipped", "no upstream branch")

    before = git("rev-parse", "--short", "HEAD").out
    for step in (("fetch", "--prune"), ("pull", "--ff-only")):
        result = git(*step)
        if not result.ok:
            return RefreshResult(repo, "failed", f"{step[0]}: {result.err.splitlines()[-1] if result.err else 'error'}")
    after = git("rev-parse", "--short", "HEAD").out
    if before == after:
        return RefreshResult(repo, "up-to-date")
    return RefreshResult(repo, "updated", f"{before}..{after}")
