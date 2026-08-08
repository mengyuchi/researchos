#!/usr/bin/env bash
set -Eeuo pipefail

# Resolve project root.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

QUARTO="${QUARTO:-quarto}"

# ---------------------------------------------------------------------------
# Resolve Python
#
# Priority:
#   1. Explicit PYTHON environment variable
#   2. Project-local .venv/bin/python
#   3. python3 from PATH
#   4. python from PATH
# ---------------------------------------------------------------------------

if [[ -n "${PYTHON:-}" ]]; then
  :
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
else
  echo
  echo "ERROR: No Python executable found." >&2
  echo "Expected one of:" >&2
  echo "  $ROOT/.venv/bin/python" >&2
  echo "  python3" >&2
  echo "  python" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------

echo
echo "ResearchOS preview preparation"
echo "=============================="
echo "Root:   $ROOT"
echo "Python: $PYTHON"
echo "Quarto: $QUARTO"
echo

if [[ "$PYTHON" == */* ]]; then
  if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: Python executable not found or not executable: $PYTHON" >&2
    exit 1
  fi
else
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: $PYTHON" >&2
    exit 1
  fi
fi

if ! command -v "$QUARTO" >/dev/null 2>&1; then
  echo "ERROR: Quarto executable not found: $QUARTO" >&2
  exit 1
fi

if ! "$PYTHON" -c "import yaml" >/dev/null 2>&1; then
  echo "ERROR: PyYAML is not available in the selected Python environment." >&2
  echo "Python: $PYTHON" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Required source files
# ---------------------------------------------------------------------------

required_files=(
  "scripts/validate_metadata.py"
  "scripts/build_dashboard.py"
  "_quarto.yml"
  "index.qmd"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "ERROR: Required file is missing: $file" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Lightweight preparation checks
# ---------------------------------------------------------------------------

echo "1. Checking Python syntax..."

"$PYTHON" -m py_compile \
  scripts/validate_metadata.py \
  scripts/build_dashboard.py

if [[ -f "scripts/export_vault.py" ]]; then
  "$PYTHON" -m py_compile scripts/export_vault.py
fi

echo "   [OK] Python syntax"

echo
echo "2. Validating ResearchOS metadata..."

"$PYTHON" scripts/validate_metadata.py --strict

echo "   [OK] Metadata validation"

echo
echo "3. Rebuilding dashboard source..."

rm -rf "_generated"

"$PYTHON" scripts/build_dashboard.py

if [[ ! -f "_generated/dashboard.md" ]]; then
  echo "ERROR: _generated/dashboard.md was not generated." >&2
  exit 1
fi

echo "   [OK] Dashboard generated"

# ---------------------------------------------------------------------------
# Start Quarto preview
# ---------------------------------------------------------------------------

echo
echo "Starting Quarto preview..."
echo "Press Ctrl+C to stop the preview server."
echo

exec "$QUARTO" preview