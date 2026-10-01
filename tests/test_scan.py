import io
import subprocess

import pytest

from conftest import fake_runner, git
from gittoolbox.cli import main
from gittoolbox.scan import mask, scan_repo, scan_text

# Every value below is fictional: documentation examples or numbers built to pass the checksums.
NIR = "1 85 05 78 006 084 91"
IBAN = "FR76 3000 6000 0112 3456 7890 189"
CARD = "4111 1111 1111 1111"


def kinds(text):
    return [f.kind for f in scan_text(text, "f.txt")]


# --- personal data ---------------------------------------------------------------

@pytest.mark.parametrize("text, kind", [
    ("contact: jean.dupont@exemple.fr", "email"),
    ("tél. 06 12 34 56 78", "phone-fr"),
    ("tel:+33 6 12 34 56 78", "phone-fr"),
    (f"NIR {NIR}", "nir"),
    (f"iban: {IBAN}", "iban"),
    (f"card={CARD}", "card"),
    ("ssn 123-45-6789", "ssn-us"),
])
def test_detects_personal_data(text, kind):
    assert kinds(text) == [kind]


@pytest.mark.parametrize("text", [
    "noreply@example.org test@example.com bot@users.noreply.github.com",
    "NIR 1 85 05 78 006 084 12",             # wrong key
    "FR76 3000 6000 0112 3456 7890 180",     # wrong IBAN checksum
    "4111 1111 1111 1112",                   # fails Luhn
    "0000 0000 0000 0000",                   # Luhn-valid but obviously fake
    "ssn 000-12-3456 666-12-3456",           # impossible SSN areas
    "version 2026-10-01, port 8080, 1234567890123",
])
def test_ignores_invalid_or_placeholder_values(text):
    assert kinds(text) == []


# --- secrets -----------------------------------------------------------------------

@pytest.mark.parametrize("text, kind", [
    ("-----BEGIN OPENSSH PRIVATE KEY-----", "private-key"),
    ("aws = AKIAABCDEFGHIJKLMNOP", "aws-key"),
    ("token ghp_" + "a1" * 18, "github-token"),
    ('password = "s3cr3t-Pa55w0rd!"', "secret-assignment"),
    ('apiKey: "0123456789abcdef0123456789abcdef"', "secret-assignment"),
    ('access_token = "MzMyODE1NDc2ODk1OtXQ2jm"', "secret-assignment"),
    ('headers = {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz012345"}', "bearer-token"),
    ('HTTPBasicAuth("someone", "pa55word!x")', "basic-auth"),
])
def test_detects_secrets(text, kind):
    assert kind in kinds(text)


@pytest.mark.parametrize("text", [
    'password = "changeme"',
    'password = "${DB_PASSWORD}"',
    'api_key = "your-api-key-here"',
    'token = "xxxxxxxxxxxxxxxx"',
    "token: ${{ secrets.GITHUB_TOKEN }}",
    'secret = os.environ["SECRET"]',
    'password = "<your password>"',
])
def test_ignores_placeholders_and_environment_lookups(text):
    assert kinds(text) == []


# --- reporting ----------------------------------------------------------------------

def test_findings_carry_line_numbers_and_masked_values():
    findings = scan_text("ok\nmail: jean.dupont@exemple.fr\n", "notes.md")
    assert [(f.file, f.line, f.kind) for f in findings] == [("notes.md", 2, "email")]
    assert "jean.dupont" not in findings[0].masked


def test_mask_keeps_only_the_edges():
    assert mask("jean.dupont@exemple.fr") == "je••••••••••••••••••fr"
    assert mask("abc") == "•••"


def test_inline_marker_skips_a_line():
    assert kinds("mail: jean.dupont@exemple.fr  # pii: ignore") == []


# --- scan_repo : working tree --------------------------------------------------------

def test_scan_repo_clean(local_repo):
    assert scan_repo(local_repo) == []


def test_scan_repo_reads_tracked_and_new_files_but_not_ignored_ones(local_repo):
    (local_repo / "tracked.txt").write_text("mail jean.dupont@exemple.fr\n")
    git(local_repo, "add", "tracked.txt")
    git(local_repo, "commit", "-q", "-m", "tracked")
    (local_repo / "new.txt").write_text(f"carte {CARD}\n")
    (local_repo / ".gitignore").write_text("secret.env\n")
    (local_repo / "secret.env").write_text('password = "s3cr3t-Pa55w0rd!"\n')

    found = {(f.file, f.kind) for f in scan_repo(local_repo)}

    assert found == {("tracked.txt", "email"), ("new.txt", "card")}


def test_scan_repo_skips_binary_files(local_repo):
    (local_repo / "image.bin").write_bytes(b"\x00\x01jean.dupont@exemple.fr")
    assert scan_repo(local_repo) == []


def test_scan_repo_honours_pii_ignore(local_repo):
    (local_repo / "tests").mkdir()
    (local_repo / "tests" / "fixtures.txt").write_text(f"{IBAN}\n")
    (local_repo / ".pii-ignore").write_text("# fictional test data\ntests/*\n")
    assert scan_repo(local_repo) == []


def test_scan_repo_tolerates_non_utf8_text(local_repo):
    (local_repo / "latin1.txt").write_bytes("café jean.dupont@exemple.fr\n".encode("latin-1"))
    assert [f.kind for f in scan_repo(local_repo)] == ["email"]


# --- scan_repo : history --------------------------------------------------------------

def test_history_finds_a_secret_removed_in_a_later_commit(local_repo):
    (local_repo / "config.py").write_text('password = "s3cr3t-Pa55w0rd!"\n')
    git(local_repo, "add", "config.py")
    git(local_repo, "commit", "-q", "-m", "add config")
    (local_repo / "config.py").write_text('password = os.environ["PASSWORD"]\n')
    git(local_repo, "commit", "-q", "-am", "use env")

    assert scan_repo(local_repo) == []
    history = scan_repo(local_repo, history=True)
    assert [(f.file, f.kind) for f in history] == [("config.py", "secret-assignment")]
    assert history[0].commit


def test_history_git_failure_is_reported_not_silenced(local_repo):
    runner = fake_runner(returncode=128, stderr="fatal: bad object")
    with pytest.raises(RuntimeError, match="bad object"):
        scan_repo(local_repo, history=True, runner=runner)


# --- CLI ---------------------------------------------------------------------------------

def run_cli(*argv):
    out = io.StringIO()
    return main(list(argv), out=out), out.getvalue()


def test_cli_scan_clean_exit_zero(local_repo):
    code, out = run_cli("--root", str(local_repo.parent), "scan")
    assert code == 0 and "clean" in out


def test_cli_scan_reports_masked_findings_and_fails(local_repo):
    (local_repo / "notes.md").write_text("mail jean.dupont@exemple.fr\n")
    code, out = run_cli("--root", str(local_repo.parent), "scan")
    assert code == 1
    assert "notes.md:1" in out and "email" in out
    assert "jean.dupont@exemple.fr" not in out
