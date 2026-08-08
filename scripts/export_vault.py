from pathlib import Path
import os
import re
import shutil
import yaml

SITE = Path(__file__).resolve().parents[1]

VAULT = Path(
    os.environ.get(
        "RESEARCHOS_VAULT",
        Path.home() / "Documents" / "ResearchOS-Vault"
    )
).expanduser()

DEST = SITE / "knowledge" / "vault"

ALLOWED_ROOTS = [
    "02 Literature/Papers",
    "03 Projects",
    "04 Ideas",
    "05 Methods",
    "06 Experiments",
    "11 Outputs/Publications",
    "11 Outputs/Conferences",
    "11 Outputs/Presentations",
]

FRONTMATTER = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?",
    re.DOTALL
)


def metadata(path):
    text = path.read_text(encoding="utf-8")

    match = FRONTMATTER.match(text)

    if not match:
        return {}

    data = yaml.safe_load(match.group(1))

    return data or {}


def export_note(path):

    data = metadata(path)

    if data.get("publish") is not True:
        return False

    relative = path.relative_to(VAULT)

    output = DEST / relative

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    shutil.copy2(
        path,
        output
    )

    print(f"PUBLISH  {relative}")

    return True


def main():

    if not VAULT.exists():
        raise SystemExit(
            f"Vault not found: {VAULT}"
        )

    if DEST.exists():
        shutil.rmtree(DEST)

    DEST.mkdir(
        parents=True,
        exist_ok=True
    )

    count = 0

    for root_name in ALLOWED_ROOTS:

        root = VAULT / root_name

        if not root.exists():
            continue

        for path in root.rglob("*.md"):

            if export_note(path):
                count += 1

    public_assets = (
        VAULT
        / "Attachments"
        / "Public"
    )

    if public_assets.exists():

        destination_assets = (
            DEST
            / "Attachments"
            / "Public"
        )

        shutil.copytree(
            public_assets,
            destination_assets,
            dirs_exist_ok=True
        )

    print()
    print(f"Published notes: {count}")
    print(f"Output: {DEST}")


if __name__ == "__main__":
    main()