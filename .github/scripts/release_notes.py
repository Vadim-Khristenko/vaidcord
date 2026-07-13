#!/usr/bin/env python3
"""Generate categorized release notes for a VaidCord package release.

Reads the git history between the previous tag and the released tag,
groups conventional-commit subjects into sections, and renders a polished
markdown document with the release card, highlights, and install snippet.

Used by the release workflows; runnable locally for previews.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

SECTIONS = (
    ("feat", "## ✨ Features"),
    ("fix", "## 🐛 Fixes"),
    ("perf", "## ⚡ Performance"),
    ("docs", "## 📝 Documentation"),
    ("refactor", "## 🧹 Refactoring"),
    ("test", "## ✅ Tests"),
    ("chore", "## 🧰 Maintenance"),
    ("ci", "## 🧰 Maintenance"),
    ("build", "## 🧰 Maintenance"),
)
FALLBACK_SECTION = "## 🔀 Other changes"

INSTALL_SNIPPETS = {
    "python": "```bash\npip install 'vaidcord[voice]=={version}'\n```",
    "rust": "```bash\ncargo add vaidcord@{version}\n```",
    "go": "```bash\ngo get github.com/Vadim-Khristenko/vaidcord/vaidcord-go@v{version}\n```",
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def previous_tag(tag: str, patterns: list[str]) -> str:
    """Latest reachable tag before ``tag`` matching any pattern (may be empty)."""
    try:
        tags = _git(
            "tag", "--list", *(patterns or ["*"]), "--sort=-creatordate", "--merged", f"{tag}^"
        ).splitlines()
    except subprocess.CalledProcessError:
        return ""
    return next((t for t in tags if t != tag), "")


def collect_commits(range_spec: str, paths: list[str]) -> list[tuple[str, str]]:
    args = ["log", "--no-merges", "--pretty=%s\x1f%h", range_spec]
    if paths:
        args += ["--", *paths]
    out = _git(*args)
    commits = []
    for line in out.splitlines():
        subject, _, sha = line.partition("\x1f")
        commits.append((subject.strip(), sha.strip()))
    return commits


def categorize(commits: list[tuple[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for subject, sha in commits:
        match = re.match(r"^(\w+)(\([^)]*\))?!?:\s*(.+)$", subject)
        section = FALLBACK_SECTION
        text = subject
        if match:
            prefix, scope, rest = match.group(1).lower(), match.group(2), match.group(3)
            for key, title in SECTIONS:
                if prefix == key:
                    section = title
                    scope_text = f"**{scope[1:-1]}**: " if scope else ""
                    text = f"{scope_text}{rest}"
                    break
        grouped.setdefault(section, []).append(f"- {text} (`{sha}`)")
    return grouped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--language", required=True, choices=["python", "rust", "go"])
    parser.add_argument(
        "--tag-pattern",
        action="append",
        default=[],
        help="glob(s) for previous-tag lookup; repeatable",
    )
    parser.add_argument("--path", action="append", default=[], help="limit log to paths")
    parser.add_argument("--card-url", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--highlight", action="append", default=[])
    parser.add_argument("--repo", default="Vadim-Khristenko/vaidcord")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    prev = previous_tag(args.tag, args.tag_pattern)
    range_spec = f"{prev}..{args.tag}" if prev else args.tag
    commits = collect_commits(range_spec, args.path)
    grouped = categorize(commits)

    lines: list[str] = [f"# {args.package} {args.version}", ""]
    if args.card_url:
        lines += [f"![{args.package} {args.version} release card]({args.card_url})", ""]
    if args.summary:
        lines += [args.summary.strip(), ""]
    if args.highlight:
        lines += ["## 🌟 Highlights", ""]
        lines += [f"- {h.strip()}" for h in args.highlight if h.strip()]
        lines += [""]

    lines += ["## 📦 Install", "", INSTALL_SNIPPETS[args.language].format(version=args.version), ""]

    ordered_titles = list(dict.fromkeys(title for _, title in SECTIONS)) + [FALLBACK_SECTION]
    for title in ordered_titles:
        entries = grouped.get(title)
        if entries:
            lines += [title, "", *entries, ""]

    if prev:
        lines += [
            "---",
            "",
            f"**Full changelog**: https://github.com/{args.repo}/compare/{prev}...{args.tag}",
        ]
    else:
        lines += ["---", "", f"First tagged release of {args.package}."]

    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(commits)} commits, previous tag: {prev or 'none'})")


if __name__ == "__main__":
    main()
