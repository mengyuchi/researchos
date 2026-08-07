#!/usr/bin/env python3
"""
One-time ResearchOS v0.2 metadata upgrade.

Adds optional dashboard fields without changing existing values:
- research_progress:
- next_action: ""
- due:

The script updates both real objects and templates and makes *.v01.bak backups.
Run once, inspect with git diff, then delete backups after confirmation.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OBJECT_TYPES = {
    "project": ("projects", ["research_progress:", 'next_action: ""', "due:"]),
    "paper": ("papers", ["research_progress:", 'next_action: ""', "due:"]),
    "idea": ("ideas", ['next_action: ""', "due:"]),
    "experiment": ("experiments", ["research_progress:", 'next_action: ""', "due:"]),
    "dataset": ("datasets", ["research_progress:", 'next_action: ""', "due:"]),
    "literature": ("literature", ['next_action: ""']),
    "method": ("methods", ["research_progress:", 'next_action: ""', "due:"]),
}

TEMPLATES = {
    "project": "project.qmd",
    "paper": "paper.qmd",
    "idea": "idea.qmd",
    "experiment": "experiment.qmd",
    "dataset": "dataset.qmd",
    "literature": "literature.qmd",
    "method": "method.qmd",
}


def split_file(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML front matter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[: i + 1], lines[i + 1 :]
    raise ValueError("unclosed YAML front matter")


def has_key(front: list[str], key: str) -> bool:
    return any(re.match(rf"^{re.escape(key)}\s*:", line) for line in front)


def patch(path: Path, fields: list[str]) -> bool:
    text = path.read_text(encoding="utf-8")
    front, body = split_file(text)

    missing = []
    for rendered in fields:
        key = rendered.split(":", 1)[0]
        if not has_key(front, key):
            missing.append(rendered)

    if not missing:
        return False

    # Insert immediately before categories if possible; otherwise before closing ---.
    insert_at = len(front) - 1
    for i, line in enumerate(front):
        if re.match(r"^categories\s*:", line):
            insert_at = i
            break

    block = ["", "# Dashboard metadata", *missing]
    front[insert_at:insert_at] = block

    backup = path.with_suffix(path.suffix + ".v01.bak")
    if not backup.exists():
        shutil.copy2(path, backup)

    path.write_text("\n".join(front + body).rstrip() + "\n", encoding="utf-8")
    return True


def main() -> None:
    changed = []

    for object_type, (folder, fields) in OBJECT_TYPES.items():
        base = ROOT / folder
        if base.exists():
            for qmd in sorted(base.glob("*/index.qmd")):
                if patch(qmd, fields):
                    changed.append(qmd)

        template = ROOT / "_templates" / TEMPLATES[object_type]
        if template.exists() and patch(template, fields):
            changed.append(template)

    print(f"ResearchOS v0.2 metadata upgrade: {len(changed)} file(s) changed")
    for path in changed:
        print(f"  - {path.relative_to(ROOT)}")
    print("Backups use the suffix .qmd.v01.bak")


if __name__ == "__main__":
    main()
