#!/usr/bin/env python3
"""Validate the active server-npd documentation structure."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]+\]\((?P<target>[^)]+)\)")
DATE_HEADING_RE = re.compile(r"^### (?P<date>\d{4}-\d{2}-\d{2})(?:/\d{2})?", re.M)


def active_markdown_files() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "ansible" / "README.md", ROOT / "work" / "README.md"]
    files.extend((ROOT / "docs").rglob("*.md"))
    files.extend((ROOT / "infra").rglob("*.md"))
    files.extend((ROOT / "evidence").rglob("*.md"))
    return sorted({path for path in files if path.is_file()})


def check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = match.group("target").strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local = unquote(target.split("#", 1)[0])
            if not local:
                continue
            if not (path.parent / local).resolve().exists():
                errors.append(f"broken link: {path.relative_to(ROOT)} -> {target}")
    return errors


def check_metadata() -> list[str]:
    errors: list[str] = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        if path.parent == ROOT / "docs" / "history" and path.name.startswith("operations-"):
            continue
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:12]).lower()
        if "статус:" not in head:
            errors.append(f"missing Status: {path.relative_to(ROOT)}")
        if "источник истины для:" not in head:
            errors.append(f"missing source-of-truth field: {path.relative_to(ROOT)}")
        if not any(
            marker in head
            for marker in ("последняя", "последний", "last tested", "дата решения", "дата принятия")
        ):
            errors.append(f"missing freshness/date field: {path.relative_to(ROOT)}")
    return errors


def check_history() -> list[str]:
    errors: list[str] = []
    for path in sorted((ROOT / "docs" / "history").glob("operations-????-??.md")):
        expected_month = path.stem.removeprefix("operations-")
        dates = [date.fromisoformat(value) for value in DATE_HEADING_RE.findall(path.read_text(encoding="utf-8"))]
        if not dates:
            errors.append(f"history has no dated entries: {path.relative_to(ROOT)}")
            continue
        if dates != sorted(dates):
            errors.append(f"history is not chronological: {path.relative_to(ROOT)}")
        wrong_month = [value.isoformat() for value in dates if value.strftime("%Y-%m") != expected_month]
        if wrong_month:
            errors.append(f"history contains dates outside {expected_month}: {path.relative_to(ROOT)}")
    return errors


def check_root_markdown() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    root_docs = [Path(value) for value in result.stdout.splitlines() if Path(value).parent == Path(".")]
    unexpected = [path.as_posix() for path in root_docs if path.name != "README.md"]
    return [f"tracked Markdown file must leave repository root: {path}" for path in unexpected]


def main() -> int:
    files = active_markdown_files()
    errors = check_links(files) + check_metadata() + check_history() + check_root_markdown()
    if errors:
        print("Documentation checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Documentation checks passed: {len(files)} active Markdown files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
