from dataclasses import dataclass, field
from pathlib import Path

README_NAMES = {"readme.md", "readme", "readme.rst", "readme.txt"}
DEFAULT_SECTIONS = ("installation", "usage")


@dataclass(frozen=True)
class ReadmeReport:
    repo: Path
    status: str  # ok | missing | short | incomplete | unreadable
    lines: int = 0
    missing_sections: list[str] = field(default_factory=list)
    detail: str = ""


def find_readme(repo: Path) -> Path | None:
    for child in sorted(Path(repo).iterdir()):
        if child.is_file() and child.name.lower() in README_NAMES:
            return child
    return None


def audit_readme(repo: Path, min_lines: int = 10, sections=DEFAULT_SECTIONS) -> ReadmeReport:
    readme = find_readme(repo)
    if readme is None:
        return ReadmeReport(repo, "missing")
    try:
        lines = readme.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        return ReadmeReport(repo, "unreadable", detail=f"{readme.name}: {e}")
    if len(lines) < min_lines:
        return ReadmeReport(repo, "short", len(lines))
    headings = [line.lstrip("#").strip().lower() for line in lines if line.startswith("#")]
    missing = [s for s in sections if not any(s.lower() in h for h in headings)]
    return ReadmeReport(repo, "incomplete" if missing else "ok", len(lines), missing)
