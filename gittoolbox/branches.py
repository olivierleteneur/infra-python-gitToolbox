import subprocess
from dataclasses import dataclass
from pathlib import Path

from gittoolbox.git import run_git


@dataclass(frozen=True)
class BranchCount:
    repo: Path
    local: int | None
    remote: int | None
    error: str = ""


def count_branches(repo: Path, runner=subprocess.run) -> BranchCount:
    """Local and remote-tracking branches, as known locally (run `refresh` first for fresh numbers)."""
    result = run_git(repo, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes", runner=runner)
    if not result.ok:
        return BranchCount(repo, None, None, result.err)
    refs = result.out.splitlines()
    local = sum(ref.startswith("refs/heads/") for ref in refs)
    remote = sum(ref.startswith("refs/remotes/") and not ref.endswith("/HEAD") for ref in refs)
    return BranchCount(repo, local, remote)
