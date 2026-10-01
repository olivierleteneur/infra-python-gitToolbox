"""Find personal data and secrets in a repository, before it goes public.

Checksums (IBAN mod 97, French NIR key, Luhn) and placeholder filters keep false
positives low; values are always reported masked. Nothing can reliably spot a name
next to a birth date: that still needs a human review.
"""

import fnmatch
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from gittoolbox.git import run_git

IGNORE_FILE = ".pii-ignore"
INLINE_IGNORE = "pii: ignore"
MAX_FILE_BYTES = 2_000_000
HISTORY_TIMEOUT = 300

PLACEHOLDER_HINTS = ("changeme", "your", "xxx", "example", "dummy", "placeholder", "redacted",
                     "<", ">", "${", "{{", "****")
IGNORED_EMAIL_DOMAINS = re.compile(r"(^|\.)(example(\.\w+)?|localhost|test|invalid|users\.noreply\.github\.com)$", re.I)
IGNORED_EMAIL_USERS = {"noreply", "no-reply"}


@dataclass(frozen=True)
class Finding:
    kind: str
    file: str
    line: int
    masked: str
    commit: str = ""

    @property
    def where(self):
        location = f"{self.file}:{self.line}"
        return f"{self.commit} {location}" if self.commit else location


def mask(value):
    if len(value) <= 4:
        return "•" * len(value)
    return value[:2] + "•" * (len(value) - 4) + value[-2:]


def _digits(value):
    return re.sub(r"[ .-]", "", value)


def _is_placeholder(value):
    lowered = value.lower()
    return any(hint in lowered for hint in PLACEHOLDER_HINTS) or len(set(value)) <= 2


def _luhn(number):
    total = 0
    for i, digit in enumerate(int(c) for c in reversed(number)):
        total += digit if i % 2 == 0 else (digit * 2 - 9 if digit > 4 else digit * 2)
    return total % 10 == 0


def _valid_card(value):
    number = _digits(value)
    return number[0] in "3456" and len(set(number)) > 1 and _luhn(number)


def _valid_iban(value):
    compact = value.replace(" ", "")
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def _valid_nir(value):
    compact = value.replace(" ", "").upper()
    body, key = compact[:13], int(compact[13:])
    body = body.replace("2A", "19").replace("2B", "18")
    return 97 - int(body) % 97 == key


def _valid_ssn(value):
    area, group, serial = value.split("-")
    return area not in ("000", "666") and not area.startswith("9") and group != "00" and serial != "0000"


def _valid_email(value):
    user, _, domain = value.rpartition("@")
    return user.lower() not in IGNORED_EMAIL_USERS and not IGNORED_EMAIL_DOMAINS.search(domain)


# (kind, pattern, group holding the value, validator). Order matters: earlier detectors
# claim their span, so a valid IBAN is not also reported as a card or a phone number.
DETECTORS = [
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"), 0, None),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0, None),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b"), 0, None),
    ("bearer-token", re.compile(r"\bBearer\s+([A-Za-z0-9._~+/-]{20,}=*)"), 1, lambda v: not _is_placeholder(v)),
    ("basic-auth", re.compile(r"HTTPBasicAuth\(\s*[\"'][^\"']*[\"']\s*,\s*[\"']([^\"']{6,})[\"']"), 1,
     lambda v: not _is_placeholder(v)),
    ("secret-assignment", re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|client[_-]?secret|token|access[_-]?token|auth[_-]?token|api[_-]?key)\b"
        r"[\"']?\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']"), 1, lambda v: not _is_placeholder(v)),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b"), 0, _valid_iban),
    ("nir", re.compile(r"(?<!\d)(?<!\d )[12] ?\d{2} ?(?:0[1-9]|1[0-2]|[2-9]\d) ?(?:\d{2}|2[AB]) ?\d{3} ?\d{3} ?\d{2}(?! ?\d)"),
     0, _valid_nir),
    ("card", re.compile(r"(?<!\d)(?<!\d[ -])(?:\d[ -]?){12,18}\d(?![ -]?\d)"), 0, _valid_card),
    ("phone-fr", re.compile(r"(?<![\d+])(?<!\d[ .-])(?:\+33[ .-]?|0)[1-9](?:[ .-]?\d{2}){4}(?![ .-]?\d)"), 0, None),
    ("ssn-us", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 0, _valid_ssn),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), 0, _valid_email),
]


def _scan_line(line):
    claimed = []
    for kind, pattern, group, validator in DETECTORS:
        for match in pattern.finditer(line):
            start, end = match.span()
            if any(start < c_end and c_start < end for c_start, c_end in claimed):
                continue
            value = match.group(group)
            if validator and not validator(value):
                continue
            claimed.append((start, end))
            yield kind, value


def scan_text(text, file, commit="", first_line=1):
    findings = []
    for number, line in enumerate(text.splitlines(), start=first_line):
        if INLINE_IGNORE in line:
            continue
        findings.extend(Finding(kind, file, number, mask(value), commit) for kind, value in _scan_line(line))
    return findings


def _ignore_patterns(repo):
    ignore = Path(repo) / IGNORE_FILE
    if not ignore.is_file():
        return []
    lines = (line.strip() for line in ignore.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _ignored(path, patterns):
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _git_or_raise(repo, *args, runner, timeout=60):
    result = run_git(repo, *args, runner=runner, timeout=timeout)
    if not result.ok:
        raise RuntimeError(f"git {args[0]} failed: {result.err}")
    return result.out


def _scan_tree(repo, patterns, runner):
    listing = _git_or_raise(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z", runner=runner)
    findings = []
    for name in filter(None, listing.split("\0")):
        path = Path(repo) / name
        if _ignored(name, patterns) or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        findings.extend(scan_text(data.decode("utf-8", errors="replace"), name))
    return findings


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def _scan_history(repo, patterns, runner):
    log = _git_or_raise(repo, "log", "-p", "--all", "--no-color", "--no-ext-diff", "-U0", "--format=commit %h",
                        runner=runner, timeout=HISTORY_TIMEOUT)
    findings, commit, file, line_no = [], "", None, 0
    for line in log.splitlines():
        if line.startswith("commit "):
            commit, file = line.split()[1], None
        elif line.startswith("+++ "):
            file = line[6:] if line.startswith("+++ b/") else None
        elif (hunk := HUNK.match(line)):
            line_no = int(hunk.group(1))
        elif line.startswith("+") and file and not _ignored(file, patterns):
            findings.extend(scan_text(line[1:], file, commit, line_no))
            line_no += 1
    return findings


def scan_repo(repo, history=False, runner=subprocess.run):
    """Findings in the working tree (tracked and new files, .gitignore respected), plus every
    line ever added in any commit when `history` is true. Raises RuntimeError if git fails."""
    patterns = _ignore_patterns(repo)
    findings = _scan_tree(repo, patterns, runner)
    if history:
        findings += _scan_history(repo, patterns, runner)
    return findings
