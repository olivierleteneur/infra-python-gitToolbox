import pytest

from gittoolbox.readme import audit_readme

GOOD = "# Tool\n\nIntro\n\n## Installation\n\nuv sync\n\n## Usage\n\nrun it\n"


def write(repo, text, name="README.md"):
    repo.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")


def test_ok(tmp_path):
    write(tmp_path, GOOD)
    report = audit_readme(tmp_path, min_lines=10)
    assert (report.status, report.lines, report.missing_sections) == ("ok", 11, [])


def test_missing(tmp_path):
    assert audit_readme(tmp_path).status == "missing"


@pytest.mark.parametrize("name", ["readme.md", "Readme.md", "README", "README.rst"])
def test_readme_name_variants(tmp_path, name):
    write(tmp_path, GOOD, name=name)
    assert audit_readme(tmp_path).status == "ok"


def test_short(tmp_path):
    write(tmp_path, "# Tool\n")
    report = audit_readme(tmp_path, min_lines=10)
    assert (report.status, report.lines) == ("short", 1)


def test_incomplete_lists_missing_sections_case_insensitive(tmp_path):
    write(tmp_path, GOOD.replace("## Usage", "## USAGE") + "\n" * 5)
    report = audit_readme(tmp_path, sections=("installation", "usage", "license"))
    assert (report.status, report.missing_sections) == ("incomplete", ["license"])


def test_section_must_be_a_heading_not_a_mention(tmp_path):
    write(tmp_path, GOOD + "See the license file.\n")
    assert audit_readme(tmp_path, sections=("license",)).missing_sections == ["license"]


def test_no_section_check_when_none_requested(tmp_path):
    write(tmp_path, "line\n" * 10)
    assert audit_readme(tmp_path, sections=()).status == "ok"


def test_unreadable_file_is_reported_not_raised(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "README.md").write_bytes(b"\xff\xfe\x00binary")
    report = audit_readme(tmp_path)
    assert report.status == "unreadable" and report.detail
