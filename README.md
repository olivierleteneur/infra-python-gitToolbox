# git-toolbox

Keep a folder full of git repositories tidy: refresh them all, count and clean branches, audit READMEs.

It replaces a handful of copy-pasted shell scripts with one tested command. Pure Python standard library, no dependency, works on Linux and macOS.

## Installation

```bash
uv tool install git+https://github.com/olivierleteneur/infra-python-gitToolbox
```

Or run it from a clone with `uv run git-toolbox ...`. Requires Python 3.11+ and git.

## Usage

Repositories are found under `--root` (default: current folder, 3 levels deep), or read from a list file with `--list` (one path per line, relative to `--root`, `#` for comments).

```bash
git-toolbox --root ~/Repositories refresh
```

| Command | What it does |
|---|---|
| `refresh` | `git fetch --prune` then `git pull --ff-only` on every repository. Skips repositories with uncommitted changes or no upstream, never merges or rebases |
| `branches` | Counts local and remote-tracking branches |
| `cleanup` | Lists branches **merged** into the default branch and older than `--days` (60). Dry run unless `--apply`; `--remote` also covers `origin`; `--protect NAME` keeps a branch. `main`, `master`, `develop`, `staging`, `production` and the current branch are always kept. Local branches are removed with the safe `git branch -d` |
| `readme` | Flags READMEs that are missing, shorter than `--min-lines` (10) or lack the `--section` headings (`installation`, `usage`) |

```text
$ git-toolbox cleanup --days 30 --remote
api    would delete  feature/login (94 days old)
api    would delete  fix/typo (41 days old)
api    would delete  origin/fix/typo (41 days old)

3 branch(es) would be deleted. Run again with --apply to delete them.
```

Each command prints one line per repository and exits with `1` if something failed or needs attention, so it can run in a cron job or a CI step.

## Development

```bash
uv run pytest
```

Tests run real git commands against temporary repositories (with a local bare "origin") and cover failure paths: unreachable remote, diverged history, git timeout, missing git binary, unreadable README. CI runs them on Ubuntu and macOS with Python 3.11 and 3.14.

Released under the MIT License, see [LICENSE](LICENSE).
