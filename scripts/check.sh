#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo
echo "========================================"
echo "ResearchOS full check"
echo "========================================"
echo

# Validation and dashboard generation run automatically through Quarto pre-render.
quarto render

echo
echo "Checking dashboard output..."

test -f "_site/index.html"
grep -q "Research Activity" "_site/index.html"
grep -q "Paper Pipeline" "_site/index.html"
grep -q "Today's Focus" "_site/index.html"

echo
echo "Checking key object pages..."

required_pages=(
  "_site/projects/project-001-phd-nrw-insar/index.html"
  "_site/papers/paper-001-atmospheric-correction/index.html"
  "_site/ideas/idea-001-atmospheric-residual-diagnostics/index.html"
  "_site/experiments/exp-001-fusion-loocv/index.html"
  "_site/datasets/dataset-001-sentinel1/index.html"
  "_site/literature/lit-001-murray-2019/index.html"
  "_site/methods/method-001-fusion-atmospheric-correction/index.html"
)

for page in "${required_pages[@]}"; do
  if [[ ! -f "$page" ]]; then
    echo "ERROR: missing rendered page: $page" >&2
    exit 1
  fi
done

echo
echo "========================================"
echo "ResearchOS check PASSED"
echo "========================================"
