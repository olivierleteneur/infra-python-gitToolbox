import subprocess
from dataclasses import dataclass
from pathlib import Path

from gittoolbox.errors import GitNotFound

DEFAULT_TIMEOUT = 60


@dataclass(frozen=True)
class GitResult:
    ok: bool
    out: str
    err: str


def run_git(repo: Path, *args: str, runner=subprocess.run, timeout: int = DEFAULT_TIMEOUT) -> GitResult:
    """Run git in `repo`. Failures and timeouts are returned, never raised; a missing git binary is."""
    try:
        proc = runner(["git", *args], cwd=repo, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise GitNotFound("git executable not found in PATH")
    except subprocess.TimeoutExpired:
        return GitResult(False, "", f"timed out after {timeout}s")
    return GitResult(proc.returncode == 0, proc.stdout.strip(), proc.stderr.strip())
