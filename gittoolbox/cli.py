"""git-toolbox: keep a folder full of git repositories tidy."""

DESCRIPTION = "Keep a folder full of git repositories tidy."

import argparse
import subprocess
import sys
from pathlib import Path

from gittoolbox.branches import count_branches
from gittoolbox.cleanup import DEFAULT_PROTECTED, delete_branches, find_stale
from gittoolbox.errors import ToolboxError
from gittoolbox.readme import DEFAULT_SECTIONS, audit_readme
from gittoolbox.refresh import refresh_repo
from gittoolbox.repos import discover, is_repo, load_list


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="git-toolbox", description=DESCRIPTION)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="folder holding the repositories (default: .)")
    parser.add_argument("--list", type=Path, help="file listing repositories, one path per line, relative to --root")
    parser.add_argument("--depth", type=int, default=3, help="how deep to look for repositories (default: 3)")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("refresh", help="fetch and fast-forward every repository")
    commands.add_parser("branches", help="count local and remote branches")

    cleanup = commands.add_parser("cleanup", help="find merged branches older than N days (dry run by default)")
    cleanup.add_argument("--days", type=int, default=60, help="minimum age in days (default: 60)")
    cleanup.add_argument("--protect", action="append", default=[], metavar="BRANCH",
                         help=f"never delete this branch (always kept: {', '.join(sorted(DEFAULT_PROTECTED))})")
    cleanup.add_argument("--remote", action="store_true", help="also consider branches on origin")
    cleanup.add_argument("--apply", action="store_true", help="actually delete the branches")

    readme = commands.add_parser("readme", help="audit README files")
    readme.add_argument("--min-lines", type=int, default=10, help="minimum number of lines (default: 10)")
    readme.add_argument("--section", action="append", metavar="NAME",
                        help=f"required heading, repeatable (default: {', '.join(DEFAULT_SECTIONS)})")
    return parser


def _refresh(repos, args, ctx):
    failed = False
    for r in repos:
        result = refresh_repo(r, runner=ctx["runner"])
        ctx["line"](r, result.status, result.detail)
        failed |= result.status == "failed"
    return 1 if failed else 0


def _branches(repos, args, ctx):
    failed = False
    for r in repos:
        count = count_branches(r, runner=ctx["runner"])
        if count.error:
            ctx["line"](r, "failed", count.error)
            failed = True
        else:
            ctx["line"](r, f"local {count.local}", f"remote {count.remote}")
    return 1 if failed else 0


def _cleanup(repos, args, ctx):
    failed = False
    protected = DEFAULT_PROTECTED | set(args.protect)
    found = 0
    for r in repos:
        try:
            candidates = find_stale(r, args.days, now=ctx["now"], protected=protected,
                                    include_remote=args.remote, runner=ctx["runner"])
        except ToolboxError as e:
            ctx["line"](r, "failed", str(e))
            failed = True
            continue
        found += len(candidates)
        if not args.apply:
            for c in candidates:
                ctx["line"](r, "would delete", f"{_label(c)} ({c.age_days} days old)")
            continue
        for o in delete_branches(r, candidates, runner=ctx["runner"]):
            ctx["line"](r, "deleted" if o.ok else "failed", " ".join(filter(None, [_label(o.candidate), o.detail])))
            failed |= not o.ok
    if found and not args.apply:
        ctx["say"](f"\n{found} branch(es) would be deleted. Run again with --apply to delete them.")
    elif not found:
        ctx["say"](f"No merged branch older than {args.days} days.")
    return 1 if failed else 0


def _label(candidate):
    return f"origin/{candidate.name}" if candidate.remote else candidate.name


def _readme(repos, args, ctx):
    sections = tuple(args.section) if args.section else DEFAULT_SECTIONS
    issues = False
    for r in repos:
        report = audit_readme(r, min_lines=args.min_lines, sections=sections)
        detail = report.detail or (f"missing: {', '.join(report.missing_sections)}" if report.missing_sections
                                   else f"{report.lines} lines" if report.lines else "")
        ctx["line"](r, report.status, detail)
        issues |= report.status != "ok"
    return 1 if issues else 0


COMMANDS = {"refresh": _refresh, "branches": _branches, "cleanup": _cleanup, "readme": _readme}


def main(argv=None, runner=subprocess.run, now=None, out=None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)

    def say(text):
        print(text, file=out)

    try:
        root = args.root.resolve()
        repos = load_list(args.list, root) if args.list else discover(root, args.depth)
        if not repos:
            say(f"No git repository found under {root}")
            return 1
        width = max(len(_name(r, root)) for r in repos)

        def line(repo, status, detail=""):
            say(f"{_name(repo, root):<{width}}  {status:<12}  {detail}".rstrip())

        invalid = [r for r in repos if not is_repo(r)]
        for r in invalid:
            line(r, "failed", "not a git repository")
        valid = [r for r in repos if r not in invalid]
        code = COMMANDS[args.command](valid, args, {"runner": runner, "now": now, "line": line, "say": say})
        return 1 if invalid else code
    except ToolboxError as e:
        say(f"Error: {e}")
        return 2


def _name(repo, root):
    try:
        return repo.relative_to(root).as_posix() or repo.name
    except ValueError:
        return str(repo)


if __name__ == "__main__":
    sys.exit(main())
