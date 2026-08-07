#!/usr/bin/env python3
"""
Validate ResearchOS metadata before rendering or committing.

Checks:
- YAML front matter parsing
- required fields
- object_type / ID / directory consistency
- UUID validity and uniqueness
- ID uniqueness
- status and priority vocabularies
- ISO dates and offset-aware timestamps
- updated >= created
- relationship fields and missing targets
- forbidden/deprecated metadata names
- template placeholders
- research-log filename/date/ID consistency
- optional dashboard metadata: research_progress, next_action, due
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML is required.\n"
        "Install it with:\n\n"
        "    python -m pip install pyyaml\n",
        file=sys.stderr,
    )
    raise SystemExit(2)


ROOT = Path(__file__).resolve().parents[1]
PRIORITIES = {"critical", "high", "medium", "low"}

OBJECT_RULES = {
    "project": {
        "folder": "projects",
        "prefix": "project",
        "statuses": {"planning", "active", "paused", "completed", "archived"},
    },
    "paper": {
        "folder": "papers",
        "prefix": "paper",
        "statuses": {
            "idea", "analysis", "drafting", "internal-review", "submitted",
            "revision", "accepted", "published", "archived",
        },
    },
    "idea": {
        "folder": "ideas",
        "prefix": "idea",
        "statuses": {
            "inbox", "evaluating", "accepted", "converted", "rejected", "archived",
        },
    },
    "experiment": {
        "folder": "experiments",
        "prefix": "exp",
        "statuses": {
            "planned", "ready", "running", "blocked", "completed", "failed", "archived",
        },
    },
    "dataset": {
        "folder": "datasets",
        "prefix": "dataset",
        "statuses": {
            "planned", "acquiring", "available", "processing", "frozen", "archived",
        },
    },
    "literature": {
        "folder": "literature",
        "prefix": "lit",
        "statuses": {"inbox", "reading", "read", "synthesized", "cited", "archived"},
    },
    "method": {
        "folder": "methods",
        "prefix": "method",
        "statuses": {"draft", "validating", "stable", "deprecated"},
    },
}

RELATION_FIELDS = {
    "projects": "project-",
    "papers": "paper-",
    "ideas": "idea-",
    "experiments": "exp-",
    "datasets": "dataset-",
    "literature": "lit-",
    "methods": "method-",
}

FORBIDDEN_KEYS = {
    "type": "use 'object_type'",
    "progress": "use 'research_progress' for ResearchOS completion percentage",
    "journal": "use 'publication' for a literature source",
    "author": "use 'authors' for literature-source authors",
    "project": "use plural relationship field 'projects'",
    "paper": "use plural relationship field 'papers'",
    "idea": "use plural relationship field 'ideas'",
    "experiment": "use plural relationship field 'experiments'",
    "dataset": "use plural relationship field 'datasets'",
    "method": "use plural relationship field 'methods'",
}

PLACEHOLDERS = (
    "XXX", "YYYY-MM-DD", "PROJECT TITLE", "PAPER TITLE", "IDEA TITLE",
    "EXPERIMENT TITLE", "DATASET TITLE", "ARTICLE TITLE", "METHOD TITLE",
)


@dataclass
class Record:
    path: Path
    data: dict[str, Any]
    text: str


@dataclass
class Finding:
    level: str
    path: Path | None
    message: str


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def split_front_matter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("file does not begin with YAML front matter ('---')")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    raise ValueError("YAML front matter has no closing '---'")


def read_record(path: Path) -> Record:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(split_front_matter(text))
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("YAML front matter must be a mapping/object")
    return Record(path=path, data=data, text=text)


def discover_object_paths() -> list[Path]:
    paths: list[Path] = []
    for rule in OBJECT_RULES.values():
        base = ROOT / rule["folder"]
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            qmd = child / "index.qmd"
            if qmd.is_file():
                paths.append(qmd)

    logs = ROOT / "logs"
    if logs.exists():
        for qmd in sorted(logs.glob("[0-9][0-9][0-9][0-9]/*.qmd")):
            if qmd.is_file():
                paths.append(qmd)
    return paths


def parse_date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt


def is_valid_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if value != value.strip():
        return False
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def add(findings: list[Finding], level: str, path: Path | None, message: str) -> None:
    findings.append(Finding(level=level, path=path, message=message))


def validate_dashboard_fields(record: Record, findings: list[Finding]) -> None:
    d = record.data
    path = record.path

    if "research_progress" in d and d["research_progress"] not in (None, ""):
        value = d["research_progress"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            add(findings, "ERROR", path, "'research_progress' must be numeric from 0 to 100")
        elif not 0 <= float(value) <= 100:
            add(findings, "ERROR", path, "'research_progress' must be between 0 and 100")

    if "next_action" in d and d["next_action"] is not None and not isinstance(d["next_action"], str):
        add(findings, "ERROR", path, "'next_action' must be a string")

    if "due" in d and d["due"] not in (None, ""):
        if parse_date_value(d["due"]) is None:
            add(findings, "ERROR", path, "'due' must be YYYY-MM-DD")


def validate_common(record: Record, findings: list[Finding]) -> None:
    d = record.data
    path = record.path

    for key in ("id", "uid", "object_type", "title"):
        if key not in d or d[key] in (None, ""):
            add(findings, "ERROR", path, f"missing required field '{key}'")

    if d.get("title") is not None and not isinstance(d.get("title"), str):
        add(findings, "ERROR", path, "'title' must be a string")

    uid = d.get("uid")
    if uid is not None and not is_valid_uuid(uid):
        add(findings, "ERROR", path, f"invalid UUID in 'uid': {uid!r}")

    for key, suggestion in FORBIDDEN_KEYS.items():
        if key in d:
            add(findings, "ERROR", path, f"forbidden/deprecated field '{key}'; {suggestion}")

    for token in PLACEHOLDERS:
        if token in record.text:
            add(findings, "ERROR", path, f"template placeholder still present: {token!r}")

    if d.get("categories") is not None and not isinstance(d.get("categories"), list):
        add(findings, "ERROR", path, "'categories' must be a YAML list")

    for field in RELATION_FIELDS:
        if field not in d:
            continue
        value = d[field]
        if value is None:
            add(findings, "WARNING", path, f"relationship field '{field}' is null; prefer []")
        elif not isinstance(value, list):
            add(findings, "ERROR", path, f"relationship field '{field}' must be a YAML list")
        else:
            for item in value:
                if not isinstance(item, str):
                    add(findings, "ERROR", path, f"'{field}' entries must be strings; found {item!r}")

    validate_dashboard_fields(record, findings)


def validate_numbered(record: Record, findings: list[Finding]) -> None:
    d = record.data
    path = record.path
    object_type = d.get("object_type")

    if object_type not in OBJECT_RULES:
        add(findings, "ERROR", path, f"unknown numbered object_type: {object_type!r}")
        return

    rule = OBJECT_RULES[object_type]
    expected_folder = ROOT / rule["folder"]

    if path.parent.parent.resolve() != expected_folder.resolve():
        add(findings, "ERROR", path, f"object_type '{object_type}' must live under {rule['folder']}/")

    object_id = d.get("id")
    id_pattern = re.compile(rf"^{re.escape(rule['prefix'])}-\d{{3}}$")

    if not isinstance(object_id, str) or not id_pattern.fullmatch(object_id):
        add(findings, "ERROR", path, f"'id' must match {rule['prefix']}-NNN; found {object_id!r}")
    else:
        dirname = path.parent.name
        dir_pattern = re.compile(rf"^{re.escape(object_id)}-[a-z0-9]+(?:-[a-z0-9]+)*$")
        if not dir_pattern.fullmatch(dirname):
            add(
                findings, "ERROR", path,
                f"directory '{dirname}' must begin with '{object_id}-' and use a lowercase ASCII slug"
            )

    for key in ("status", "priority", "created", "updated", "created_at", "updated_at"):
        if key not in d or d[key] in (None, ""):
            add(findings, "ERROR", path, f"missing required field '{key}'")

    status = d.get("status")
    if status is not None and status not in rule["statuses"]:
        add(
            findings, "ERROR", path,
            f"invalid status {status!r} for {object_type}; allowed: {', '.join(sorted(rule['statuses']))}"
        )

    priority = d.get("priority")
    if priority is not None and priority not in PRIORITIES:
        add(
            findings, "ERROR", path,
            f"invalid priority {priority!r}; allowed: {', '.join(sorted(PRIORITIES))}"
        )

    created = parse_date_value(d.get("created"))
    updated = parse_date_value(d.get("updated"))

    if d.get("created") is not None and created is None:
        add(findings, "ERROR", path, "'created' must be YYYY-MM-DD")
    if d.get("updated") is not None and updated is None:
        add(findings, "ERROR", path, "'updated' must be YYYY-MM-DD")
    if created and updated and updated < created:
        add(findings, "ERROR", path, "'updated' is earlier than 'created'")

    created_at = parse_timestamp(d.get("created_at"))
    updated_at = parse_timestamp(d.get("updated_at"))

    if d.get("created_at") is not None and created_at is None:
        add(findings, "ERROR", path, "'created_at' must be an offset-aware ISO 8601 timestamp")
    if d.get("updated_at") is not None and updated_at is None:
        add(findings, "ERROR", path, "'updated_at' must be an offset-aware ISO 8601 timestamp")
    if created_at and updated_at and updated_at < created_at:
        add(findings, "ERROR", path, "'updated_at' is earlier than 'created_at'")

    if object_type == "literature":
        if "authors" not in d:
            add(findings, "WARNING", path, "literature record has no 'authors' field")
        if "publication" not in d:
            add(findings, "WARNING", path, "literature record has no 'publication' field")


def validate_log(record: Record, findings: list[Finding]) -> None:
    d = record.data
    path = record.path

    if d.get("object_type") != "research-log":
        add(findings, "ERROR", path, "log object_type must be 'research-log'")

    for key in ("id", "uid", "title", "date", "created_at", "updated_at"):
        if key not in d or d[key] in (None, ""):
            add(findings, "ERROR", path, f"missing required log field '{key}'")

    log_date = parse_date_value(d.get("date"))
    if d.get("date") is not None and log_date is None:
        add(findings, "ERROR", path, "'date' must be YYYY-MM-DD")

    if log_date:
        ds = log_date.isoformat()
        if d.get("id") != f"log-{ds}":
            add(findings, "ERROR", path, f"log id must be 'log-{ds}'")
        if path.name != f"{ds}.qmd":
            add(findings, "ERROR", path, f"log filename must be '{ds}.qmd'")
        if path.parent.name != str(log_date.year):
            add(findings, "ERROR", path, f"log must be stored under logs/{log_date.year}/")

    created_at = parse_timestamp(d.get("created_at"))
    updated_at = parse_timestamp(d.get("updated_at"))

    if d.get("created_at") is not None and created_at is None:
        add(findings, "ERROR", path, "'created_at' must be an offset-aware ISO 8601 timestamp")
    if d.get("updated_at") is not None and updated_at is None:
        add(findings, "ERROR", path, "'updated_at' must be an offset-aware ISO 8601 timestamp")
    if created_at and updated_at and updated_at < created_at:
        add(findings, "ERROR", path, "'updated_at' is earlier than 'created_at'")


def validate_uniqueness(records: list[Record], findings: list[Finding]) -> None:
    by_id: dict[str, list[Path]] = {}
    by_uid: dict[str, list[Path]] = {}

    for record in records:
        object_id = record.data.get("id")
        uid = record.data.get("uid")
        if isinstance(object_id, str) and object_id:
            by_id.setdefault(object_id, []).append(record.path)
        if isinstance(uid, str) and uid:
            by_uid.setdefault(uid, []).append(record.path)

    for object_id, paths in sorted(by_id.items()):
        if len(paths) > 1:
            add(findings, "ERROR", None, f"duplicate ID '{object_id}': " + ", ".join(rel(p) for p in paths))

    for uid, paths in sorted(by_uid.items()):
        if len(paths) > 1:
            add(findings, "ERROR", None, f"duplicate UUID '{uid}': " + ", ".join(rel(p) for p in paths))


def validate_relations(records: list[Record], findings: list[Finding]) -> None:
    existing_ids = {
        r.data.get("id") for r in records if isinstance(r.data.get("id"), str)
    }

    for record in records:
        for field, prefix in RELATION_FIELDS.items():
            values = record.data.get(field)
            if not isinstance(values, list):
                continue
            for target in values:
                if not isinstance(target, str):
                    continue
                if not target.startswith(prefix):
                    add(
                        findings, "ERROR", record.path,
                        f"relationship '{field}' contains '{target}', which should start with '{prefix}'"
                    )
                elif target not in existing_ids:
                    add(
                        findings, "ERROR", record.path,
                        f"relationship '{field}' references missing object '{target}'"
                    )


def validate_templates(findings: list[Finding]) -> None:
    templates = ROOT / "_templates"
    required = {
        "project.qmd", "paper.qmd", "idea.qmd", "experiment.qmd",
        "dataset.qmd", "literature.qmd", "method.qmd", "research-log.qmd",
    }

    if not templates.is_dir():
        add(findings, "ERROR", templates, "_templates directory is missing")
        return

    present = {p.name for p in templates.glob("*.qmd")}
    for name in sorted(required - present):
        add(findings, "ERROR", templates / name, "required template is missing")

    literature_template = templates / "literature.qmd"
    if literature_template.exists():
        try:
            record = read_record(literature_template)
            if "journal" in record.data:
                add(findings, "ERROR", literature_template, "template uses reserved 'journal'; use 'publication'")
            if "author" in record.data:
                add(findings, "ERROR", literature_template, "template uses Quarto 'author'; use 'authors'")
        except Exception as exc:
            add(findings, "ERROR", literature_template, f"cannot parse template: {exc}")


def run_validation(strict: bool = False) -> int:
    findings: list[Finding] = []
    records: list[Record] = []

    for path in discover_object_paths():
        try:
            record = read_record(path)
        except Exception as exc:
            add(findings, "ERROR", path, f"cannot parse YAML front matter: {exc}")
            continue

        records.append(record)
        validate_common(record, findings)

        if "logs" in path.relative_to(ROOT).parts:
            validate_log(record, findings)
        else:
            validate_numbered(record, findings)

    validate_uniqueness(records, findings)
    validate_relations(records, findings)
    validate_templates(findings)

    errors = [f for f in findings if f.level == "ERROR"]
    warnings = [f for f in findings if f.level == "WARNING"]

    print()
    print("ResearchOS metadata validation")
    print("==============================")
    print(f"Root:            {ROOT}")
    print(f"Objects scanned: {len(records)}")
    print(f"Errors:          {len(errors)}")
    print(f"Warnings:        {len(warnings)}")
    print()

    for finding in findings:
        location = rel(finding.path) if finding.path is not None else "GLOBAL"
        print(f"[{finding.level}] {location}")
        print(f"        {finding.message}")

    if not findings:
        print("[OK] All ResearchOS metadata checks passed.")
    print()

    if errors:
        print("Validation FAILED.")
        return 1
    if strict and warnings:
        print("Validation FAILED in --strict mode because warnings are present.")
        return 1

    print("Validation PASSED with warnings." if warnings else "Validation PASSED.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate ResearchOS object metadata and relationships."
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    args = parser.parse_args()
    raise SystemExit(run_validation(strict=args.strict))


if __name__ == "__main__":
    main()
