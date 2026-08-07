#!/usr/bin/env bash

set -euo pipefail

echo
echo "========================================"
echo "ResearchOS metadata validation"
echo "========================================"

python scripts/validate_metadata.py --strict

echo
echo "========================================"
echo "Quarto render"
echo "========================================"

quarto render

echo
echo "========================================"
echo "ResearchOS check PASSED"
echo "========================================"
