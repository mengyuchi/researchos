#!/usr/bin/env python3
"""
ResearchOS object creator.

Creates all ResearchOS objects from templates through one command:

    python scripts/new_item.py project ...
    python scripts/new_item.py paper ...
    python scripts/new_item.py idea ...
    python scripts/new_item.py experiment ...
    python scripts/new_item.py dataset ...
    python scripts/new_item.py literature ...
    python scripts/new_item.py method ...
    python scripts/new_item.py log

Numbered research objects use permanent IDs such as paper-001.
Research logs use date IDs such as log-2026-08-07.

The script uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]

NUMBERED_TYPES = {
    "project": {
        "folder": "projects",
        "template": "project.qmd",
        "prefix": "project",
    },
    "paper": {
        "folder": "papers",
        "template": "paper.qmd",
        "prefix": "paper",
    },
    "idea": {
        "folder": "ideas",
        "template": "idea.qmd",
        "prefix": "idea",
    },
    "experiment": {
        "folder": "experiments",
        "template": "experiment.qmd",
        "prefix": "exp",
    },
    "dataset": {
        "folder": "datasets",
        "template": "dataset.qmd",
        "prefix": "dataset",
    },
    "literature": {
        "folder": "literature",
        "template": "literature.qmd",
        "prefix": "lit",
    },
    "method": {
        "folder": "methods",
        "template": "method.qmd",
        "prefix": "method",
    },
}

ALL_TYPES = tuple(NUMBERED_TYPES) + ("log",)
OBJECT_FOLDERS = tuple(cfg["folder"] for cfg in NUMBERED_TYPES.values()) + ("logs",)


def fail(message: str) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def yaml_string(value: str) -> str:
    """Return a YAML-safe quoted scalar using JSON-compatible quoting."""
    return json.dumps(value, ensure_ascii=False)


def slugify(value: str) -> str:
    """
    Convert an English/Latin title to a stable lowercase URL slug.
    Non-Latin-only titles may result in an empty slug and will require --slug.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    return ascii_text.strip("-")


def validate_slug(slug: str) -> str:
    slug = slug.strip()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        fail(
            "invalid slug. Use lowercase ASCII letters, numbers, and single "
            "hyphens only, e.g. atmospheric-correction or sentinel-1."
        )
    return slug


def parse_iso_date(value: str) -> date_cls:
    try:
        return date_cls.fromisoformat(value)
    except ValueError:
        fail(f"invalid date '{value}'. Use YYYY-MM-DD.")
        raise AssertionError  # unreachable


def split_front_matter(text: str) -> tuple[list[str], list[str]]:
    """
    Split a QMD file into YAML front matter lines and body lines.
    The first and second exact '---' lines delimit the YAML block.
    """
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        fail("template does not begin with YAML front matter ('---').")

    closing = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing = i
            break

    if closing is None:
        fail("template YAML front matter has no closing '---'.")

    return lines[1:closing], lines[closing + 1 :]


def join_front_matter(front: list[str], body: list[str]) -> str:
    return "\n".join(["---", *front, "---", *body]).rstrip() + "\n"


def find_top_level_key(front: list[str], key: str) -> int | None:
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    for i, line in enumerate(front):
        if line and not line[0].isspace() and pattern.match(line):
            return i
    return None


def set_scalar(
    front: list[str],
    key: str,
    value: str,
    *,
    after: str | None = None,
) -> None:
    """
    Replace a top-level scalar key if present; otherwise insert it.
    `value` must already be rendered as YAML text.
    """
    idx = find_top_level_key(front, key)
    rendered = f"{key}: {value}"

    if idx is not None:
        front[idx] = rendered
        return

    insert_at = len(front)

    if after is not None:
        after_idx = find_top_level_key(front, after)
        if after_idx is not None:
            insert_at = after_idx + 1

    front.insert(insert_at, rendered)


def read_frontmatter_id(path: Path) -> str | None:
    """Read only the top-level id field from a QMD file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    try:
        front, _ = split_front_matter(text)
    except SystemExit:
        return None

    idx = find_top_level_key(front, "id")
    if idx is None:
        return None

    raw = front[idx].split(":", 1)[1].strip()

    if (
        len(raw) >= 2
        and raw[0] == raw[-1]
        and raw[0] in {"'", '"'}
    ):
        raw = raw[1:-1]

    return raw or None


def iter_object_qmds() -> list[Path]:
    """Return QMD files that may contain ResearchOS object metadata."""
    paths: list[Path] = []

    for folder_name in OBJECT_FOLDERS:
        folder = ROOT / folder_name
        if not folder.exists():
            continue

        for path in folder.rglob("*.qmd"):
            # Keep listing index pages in the scan; they normally have no `id`.
            # Explicitly exclude generated/hidden material if nested later.
            if "_site" in path.parts or "_templates" in path.parts:
                continue
            paths.append(path)

    return paths


def find_id_conflict(permanent_id: str, destination: Path) -> Path | None:
    """Return another QMD file already using this permanent ID, if any."""
    destination = destination.resolve()

    for qmd in iter_object_qmds():
        if qmd.resolve() == destination:
            continue

        if read_frontmatter_id(qmd) == permanent_id:
            return qmd

    return None


def next_number(folder: Path, prefix: str) -> int:
    """
    Find the next sequence number from both directory names and metadata IDs.
    Deleted historical numbers are not reused automatically.
    """
    numbers: set[int] = set()
    dir_pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)(?:-|$)")

    if folder.exists():
        for child in folder.iterdir():
            if not child.is_dir():
                continue
            match = dir_pattern.match(child.name)
            if match:
                numbers.add(int(match.group(1)))

    id_pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for qmd in iter_object_qmds():
        object_id = read_frontmatter_id(qmd)
        if not object_id:
            continue
        match = id_pattern.match(object_id)
        if match:
            numbers.add(int(match.group(1)))

    return max(numbers, default=0) + 1


def load_template(template: Path) -> tuple[list[str], list[str]]:
    if not template.exists():
        fail(f"template not found: {template.relative_to(ROOT)}")

    text = template.read_text(encoding="utf-8")
    return split_front_matter(text)


def local_timestamp() -> str:
    """Return an offset-aware local timestamp."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def create_numbered_item(args: argparse.Namespace) -> None:
    cfg = NUMBERED_TYPES[args.object_type]
    base_folder = ROOT / cfg["folder"]
    template = ROOT / "_templates" / cfg["template"]

    title = args.title
    if not title:
        title = input("Title: ").strip()
    if not title:
        fail("title cannot be empty.")

    slug = args.slug or slugify(title)
    if not slug:
        slug = input(
            "Slug (lowercase ASCII, e.g. atmospheric-correction): "
        ).strip()
    slug = validate_slug(slug)

    if args.number is not None and args.number < 1:
        fail("--number must be >= 1.")

    number = (
        args.number
        if args.number is not None
        else next_number(base_folder, cfg["prefix"])
    )

    sequence = f"{number:03d}"
    permanent_id = f"{cfg['prefix']}-{sequence}"
    directory_name = f"{permanent_id}-{slug}"

    destination_dir = base_folder / directory_name
    destination = destination_dir / "index.qmd"

    if destination.exists():
        fail(
            f"object already exists: {destination.relative_to(ROOT)}"
        )

    conflict = find_id_conflict(permanent_id, destination)
    if conflict is not None:
        fail(
            f"permanent ID {permanent_id} is already used by "
            f"{conflict.relative_to(ROOT)}"
        )

    front, body = load_template(template)

    now = local_timestamp()
    today = datetime.now().astimezone().date().isoformat()
    uid = str(uuid4())

    set_scalar(front, "id", permanent_id)
    set_scalar(front, "uid", yaml_string(uid), after="id")
    set_scalar(front, "object_type", args.object_type, after="uid")
    set_scalar(front, "title", yaml_string(title))
    set_scalar(front, "created", today)
    set_scalar(front, "updated", today)
    set_scalar(front, "created_at", yaml_string(now), after="created")
    set_scalar(front, "updated_at", yaml_string(now), after="updated")

    rendered = join_front_matter(front, body)

    if args.dry_run:
        print(rendered)
        return

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")

    print()
    print("ResearchOS object created")
    print("-------------------------")
    print(f"Type:       {args.object_type}")
    print(f"ID:         {permanent_id}")
    print(f"UID:        {uid}")
    print(f"Created:    {now}")
    print(f"Directory:  {destination_dir.relative_to(ROOT)}")
    print(f"File:       {destination.relative_to(ROOT)}")
    print()


def create_log(args: argparse.Namespace) -> None:
    if args.number is not None:
        fail("--number is not used for research logs.")
    if args.slug is not None:
        fail("--slug is not used for research logs.")
    if args.title is not None:
        fail("--title is not used for research logs.")

    log_date = (
        parse_iso_date(args.date)
        if args.date
        else datetime.now().astimezone().date()
    )

    date_string = log_date.isoformat()
    year = str(log_date.year)

    permanent_id = f"log-{date_string}"
    template = ROOT / "_templates" / "research-log.qmd"
    destination_dir = ROOT / "logs" / year
    destination = destination_dir / f"{date_string}.qmd"

    if destination.exists():
        fail(
            f"research log already exists: {destination.relative_to(ROOT)}"
        )

    conflict = find_id_conflict(permanent_id, destination)
    if conflict is not None:
        fail(
            f"log ID {permanent_id} is already used by "
            f"{conflict.relative_to(ROOT)}"
        )

    front, body = load_template(template)

    now = local_timestamp()
    uid = str(uuid4())

    set_scalar(front, "id", permanent_id)
    set_scalar(front, "uid", yaml_string(uid), after="id")
    set_scalar(front, "object_type", "research-log", after="uid")
    set_scalar(front, "title", yaml_string(date_string))
    set_scalar(front, "date", date_string)
    set_scalar(front, "created_at", yaml_string(now), after="date")
    set_scalar(front, "updated_at", yaml_string(now), after="created_at")

    rendered = join_front_matter(front, body)

    if args.dry_run:
        print(rendered)
        return

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")

    print()
    print("ResearchOS research log created")
    print("-------------------------------")
    print(f"ID:         {permanent_id}")
    print(f"UID:        {uid}")
    print(f"Log date:   {date_string}")
    print(f"Created:    {now}")
    print(f"File:       {destination.relative_to(ROOT)}")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create ResearchOS objects from _templates using permanent IDs, "
            "UUIDs, and local timestamps."
        )
    )

    parser.add_argument(
        "object_type",
        choices=ALL_TYPES,
        help=(
            "Object type: project, paper, idea, experiment, dataset, "
            "literature, method, or log."
        ),
    )

    parser.add_argument(
        "--title",
        help=(
            "Human-readable title for numbered objects. "
            "If omitted, the script prompts interactively."
        ),
    )

    parser.add_argument(
        "--slug",
        help=(
            "Stable lowercase URL slug. If omitted, an English/Latin slug "
            "is generated from the title when possible."
        ),
    )

    parser.add_argument(
        "--number",
        type=int,
        help=(
            "Force a sequence number for rebuilding/importing an object, "
            "e.g. --number 1. Normally omit this option."
        ),
    )

    parser.add_argument(
        "--date",
        help=(
            "Research-log date in YYYY-MM-DD format. "
            "Only valid for object_type=log. Defaults to today's local date."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated QMD without writing a file.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.object_type != "log" and args.date is not None:
        fail("--date is only valid for object_type=log.")

    if args.object_type == "log":
        create_log(args)
    else:
        create_numbered_item(args)


if __name__ == "__main__":
    main()
