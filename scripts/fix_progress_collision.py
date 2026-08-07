#!/usr/bin/env python3
"""
One-time fix for the ResearchOS v0.2 Quarto metadata collision:

    progress: 10

conflicts with Quarto's own boolean `progress` option. This migrates the
ResearchOS custom field to:

    research_progress: 10

It updates:
- numbered ResearchOS object QMD front matter
- object templates
- collection Listing front matter (if `progress` was already added)
- scripts/build_dashboard.py
- scripts/validate_metadata.py
- scripts/upgrade_dashboard_metadata.py

It does NOT touch Markdown body content, CSS class names, or human-visible
"Progress" labels.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]

COLLECTIONS = [
    "projects",
    "papers",
    "ideas",
    "experiments",
    "datasets",
    "literature",
    "methods",
    "logs",
]


def patch_front_matter(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        return False

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break

    if end is None:
        raise RuntimeError(f"Unclosed YAML front matter: {path}")

    changed = False
    for i in range(1, end):
        line = lines[i]

        # YAML mapping key:
        # progress: 10
        #   progress: "Progress (%)"
        new_line = re.sub(
            r"^(\s*)progress(\s*):",
            r"\1research_progress\2:",
            line,
        )

        # YAML list item:
        #   - progress
        new_line = re.sub(
            r"^(\s*-\s*)progress(\s*)$",
            r"\1research_progress\2",
            new_line,
        )

        if new_line != line:
            lines[i] = new_line
            changed = True

    if changed:
        path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")

    return changed


def patch_python(path: Path, replacements: list[tuple[str, str]]) -> bool:
    text = path.read_text(encoding="utf-8")
    new = text
    for old, replacement in replacements:
        new = new.replace(old, replacement)

    if new == text:
        return False

    path.write_text(new, encoding="utf-8")
    py_compile.compile(str(path), doraise=True)
    return True


def main() -> None:
    changed: list[Path] = []

    # Real objects and Listing pages.
    for folder in COLLECTIONS:
        base = ROOT / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.qmd")):
            if patch_front_matter(path):
                changed.append(path)

    # Templates.
    templates = ROOT / "_templates"
    if templates.exists():
        for path in sorted(templates.glob("*.qmd")):
            if patch_front_matter(path):
                changed.append(path)

    # Dashboard reader: change only the metadata lookup.
    build = ROOT / "scripts" / "build_dashboard.py"
    if build.exists() and patch_python(
        build,
        [
            ('record.data.get("progress")', 'record.data.get("research_progress")'),
        ],
    ):
        changed.append(build)

    # Validator: validate the new custom field.
    validator = ROOT / "scripts" / "validate_metadata.py"
    if validator.exists() and patch_python(
        validator,
        [
            (
                "- optional dashboard metadata: progress, next_action, due",
                "- optional dashboard metadata: research_progress, next_action, due",
            ),
            ('if "progress" in d and d["progress"] not in (None, ""):',
             'if "research_progress" in d and d["research_progress"] not in (None, ""):'),
            ('value = d["progress"]', 'value = d["research_progress"]'),
            ("'progress' must be numeric from 0 to 100",
             "'research_progress' must be numeric from 0 to 100"),
            ("'progress' must be between 0 and 100",
             "'research_progress' must be between 0 and 100"),
            (
                '"type": "use \'object_type\'",',
                '"type": "use \'object_type\'",\n'
                '    "progress": "use \'research_progress\' for ResearchOS completion percentage",',
            ),
        ],
    ):
        changed.append(validator)

    # One-time metadata upgrader: future runs must add the safe name.
    upgrader = ROOT / "scripts" / "upgrade_dashboard_metadata.py"
    if upgrader.exists() and patch_python(
        upgrader,
        [
            ("- progress:", "- research_progress:"),
            ('["progress:",', '["research_progress:",'),
        ],
    ):
        changed.append(upgrader)

    print("ResearchOS progress-field collision fix")
    print("=======================================")
    print(f"Root: {ROOT}")
    print(f"Changed files: {len(changed)}")
    for path in changed:
        print(f"  - {path.relative_to(ROOT)}")

    print()
    print("Expected custom field after migration:")
    print("  research_progress: 10")
    print()
    print("Next:")
    print("  python scripts/validate_metadata.py --strict")
    print("  python scripts/build_dashboard.py")
    print("  ./scripts/check.sh")


if __name__ == "__main__":
    main()
