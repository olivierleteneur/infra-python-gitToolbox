from pathlib import Path

from gittoolbox.errors import ToolboxError


def is_repo(path: Path) -> bool:
    return (path / ".git").exists()


def discover(root: Path, max_depth: int = 3) -> list[Path]:
    """Git repositories under `root`, without descending into a repository or hidden folders."""
    root = Path(root)
    if not root.is_dir():
        raise ToolboxError(f"{root} is not a directory")
    found = []

    def walk(folder: Path, depth: int) -> None:
        if is_repo(folder):
            found.append(folder)
            return
        if depth == max_depth:
            return
        for child in sorted(folder.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                walk(child, depth + 1)

    walk(root, 0)
    return found


def load_list(path: Path, root: Path) -> list[Path]:
    """Repository paths from a list file: one per line, relative to `root`, `#` for comments."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise ToolboxError(f"cannot read {path}: {e}")
    entries = [line.strip() for line in lines]
    return [Path(root) / entry for entry in entries if entry and not entry.startswith("#")]
