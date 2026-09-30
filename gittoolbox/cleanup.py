import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from gittoolbox.errors import ToolboxError
from gittoolbox.git import run_git

DEFAULT_PROTECTED = frozenset({"main", "master", "develop", "staging", "production"})
DAY = 86400


@dataclass(frozen=True)
class Candidate:
    name: str
    age_days: int
    remote: bool = False


@dataclass(frozen=True)
class Outcome:
    candidate: Candidate
    ok: bool
    detail: str = ""


def default_branch(repo: Path, runner=subprocess.run) -> str:
    head = run_git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", runner=runner)
    if head.ok:
        return head.out.removeprefix("origin/")
    for name in ("main", "master"):
        if run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}", runner=runner).ok:
            return name
    raise ToolboxError("cannot guess the default branch (no origin/HEAD, main or master)")


def _merged(repo, base, namespace, runner):
    result = run_git(repo, "for-each-ref", "--merged", base,
                     "--format=%(refname:short)%09%(committerdate:unix)", namespace, runner=runner)
    if not result.ok:
        raise ToolboxError(result.err)
    for line in result.out.splitlines():
        name, timestamp = line.split("\t")
        yield name, int(timestamp)


def find_stale(repo: Path, days: int, now: float | None = None, protected=DEFAULT_PROTECTED,
               include_remote: bool = False, runner=subprocess.run) -> list[Candidate]:
    """Branches merged into the default branch whose last commit is older than `days`. Deletes nothing."""
    now = time.time() if now is None else now
    base = default_branch(repo, runner)
    current = run_git(repo, "branch", "--show-current", runner=runner).out
    keep = set(protected) | {base, current}

    def age(timestamp):
        return int((now - timestamp) // DAY)

    candidates = [Candidate(name, age(ts)) for name, ts in _merged(repo, base, "refs/heads", runner)
                  if name not in keep and age(ts) > days]
    if include_remote and run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{base}",
                                  runner=runner).ok:
        for ref, ts in _merged(repo, f"origin/{base}", "refs/remotes/origin", runner):
            name = ref.removeprefix("origin/")
            if name not in keep and name not in ("HEAD", "origin") and age(ts) > days:
                candidates.append(Candidate(name, age(ts), remote=True))
    return sorted(candidates, key=lambda c: (c.remote, c.name))


def delete_branches(repo: Path, candidates: list[Candidate], runner=subprocess.run) -> list[Outcome]:
    """Delete local branches with the safe `branch -d`, remote ones with `push --delete`."""
    outcomes = []
    for c in candidates:
        args = ("push", "origin", "--delete", c.name) if c.remote else ("branch", "-d", c.name)
        result = run_git(repo, *args, runner=runner)
        outcomes.append(Outcome(c, result.ok, "" if result.ok else result.err))
    return outcomes
