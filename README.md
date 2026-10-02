# git-toolbox

Keep a folder full of git repositories tidy: refresh them all, count and clean branches, audit READMEs, and scan for personal data and secrets before publishing.

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
| `scan` | Finds personal data and secrets in tracked and new files (`.gitignore` respected); `--history` also checks every line ever committed. Values are always printed **masked** |

```text
$ git-toolbox cleanup --days 30 --remote
api    would delete  feature/login (94 days old)
api    would delete  fix/typo (41 days old)
api    would delete  origin/fix/typo (41 days old)

3 branch(es) would be deleted. Run again with --apply to delete them.
```

### Scanning before you publish

```text
$ git-toolbox --root ~/Repositories scan --history
api      2 findings
    config.py:12  secret-assignment  s3••••••••••••d!
    9f2c1ab config.py:12  secret-assignment  s3••••••••••••d!
blog     clean
```

| Kind | What is detected | False positives avoided by |
|---|---|---|
| `email` | Email addresses | Ignoring `example.*`, `localhost`, local network names (`.local`, `.lan`, `.home.arpa`, typical of SSH targets) and `noreply@…` |
| `phone-fr` | French phone numbers (`06 12 34 56 78`, `+33 6…`) | Separators and boundaries | <!-- pii: ignore -->
| `nir` | French social security numbers | Checking the 2-digit key |
| `iban` | IBANs | The mod 97 checksum |
| `rib` | French bank account numbers (RIB: bank, branch, account, key) | Checking the RIB key |
| `siret`, `siren` | French company and establishment numbers | Luhn checksum, no single repeated digit; SIREN only right after the word "SIREN" |
| `card` | Payment card numbers | Luhn checksum, network prefix (3 to 6) |
| `ssn-us` | US social security numbers | Rejecting impossible ranges |
| `private-key`, `aws-key`, `github-token` | Well-known key and token formats | Exact formats |
| `secret-assignment`, `bearer-token`, `basic-auth` | Hard-coded `password = "…"`, `apiKey: "…"`, `Bearer …`, `HTTPBasicAuth(…)` | Skipping placeholders (`changeme`, `${VAR}`, `your-…`, `insert…`, `replace…`) and environment lookups |

Add a `.pii-ignore` file (one path pattern per line, `#` for comments) for fictional test data, or put `pii: ignore` on a line to skip it. A secret found in `--history` stays readable in the repository even after its removal: revoke it, then rewrite the history if the repository is to be published. No tool reliably spots a name next to a birth date; keep a human review for that.

Each command prints one line per repository and exits with `1` if something failed or needs attention, so it can run in a cron job or a CI step.

## Development

```bash
uv run pytest
```

Tests run real git commands against temporary repositories (with a local bare "origin") and cover failure paths: unreachable remote, diverged history, git timeout, missing git binary, unreadable README. The scan tests use only fictional values built to pass the checksums (listed in `.pii-ignore`). CI runs them on Ubuntu and macOS with Python 3.11 and 3.14.

Released under the MIT License, see [LICENSE](LICENSE).
