#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"

if [ -f ".researchos-local.env" ]; then
    source ".researchos-local.env"
fi

export RESEARCHOS_VAULT

echo
echo "=== Export Obsidian public notes ==="

"$ROOT/.venv/bin/python" \
    "$ROOT/scripts/export_vault.py"

echo
echo "=== Quarto render ==="

quarto render

echo
echo "=== Git status ==="

git status --short