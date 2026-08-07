#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python}"
QUARTO="${QUARTO:-quarto}"

echo
echo "ResearchOS preview preparation"
echo "=============================="

"$PYTHON" -m py_compile scripts/validate_metadata.py scripts/build_dashboard.py
"$PYTHON" scripts/validate_metadata.py --strict
rm -rf "_generated"
"$PYTHON" scripts/build_dashboard.py

echo
echo "Starting Quarto preview..."
echo

exec "$QUARTO" preview
