#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python}"
QUARTO="${QUARTO:-quarto}"

COLLECTIONS=(
  projects
  papers
  ideas
  experiments
  datasets
  literature
  methods
)

fail() {
  echo
  echo "ERROR: $*" >&2
  exit 1
}

ok() {
  echo "  [OK] $*"
}

section() {
  echo
  echo "========================================"
  echo "$*"
  echo "========================================"
}

section "ResearchOS full check"
echo "Root: $ROOT"

section "1/8 Environment and source checks"

command -v "$PYTHON" >/dev/null 2>&1 \
  || fail "Python executable not found: $PYTHON"

command -v "$QUARTO" >/dev/null 2>&1 \
  || fail "Quarto executable not found: $QUARTO"

"$PYTHON" -c "import yaml" >/dev/null 2>&1 \
  || fail "PyYAML is not available in the current Python environment"

[[ -f "_quarto.yml" ]] || fail "_quarto.yml is missing"
[[ -f "index.qmd" ]] || fail "index.qmd is missing"
[[ -f "scripts/validate_metadata.py" ]] || fail "scripts/validate_metadata.py is missing"
[[ -f "scripts/build_dashboard.py" ]] || fail "scripts/build_dashboard.py is missing"

[[ ! -f "README_INSTALL.md" ]] \
  || fail "README_INSTALL.md is still in the project root and would be rendered as a website page"

ok "Required tools and source files are available"

section "2/8 Python syntax checks"

python_scripts=(
  scripts/new_item.py
  scripts/validate_metadata.py
  scripts/build_dashboard.py
)

if [[ -f "scripts/upgrade_dashboard_metadata.py" ]]; then
  python_scripts+=(scripts/upgrade_dashboard_metadata.py)
fi

for script in "${python_scripts[@]}"; do
  [[ -f "$script" ]] || fail "Missing Python script: $script"
  "$PYTHON" -m py_compile "$script" \
    || fail "Python syntax check failed: $script"
  ok "$script"
done

section "3/8 ResearchOS metadata validation"

"$PYTHON" scripts/validate_metadata.py --strict \
  || fail "ResearchOS metadata validation failed"

ok "ResearchOS metadata validation passed"

section "4/8 Generate dashboard source"

rm -rf "_generated"

"$PYTHON" scripts/build_dashboard.py \
  || fail "Dashboard generation failed"

[[ -f "_generated/dashboard.md" ]] \
  || fail "_generated/dashboard.md was not generated"

"$PYTHON" - <<'PY'
from pathlib import Path

path = Path("_generated/dashboard.md")
text = path.read_text(encoding="utf-8")

if not text.startswith("```{=html}\n"):
    raise SystemExit(
        "ERROR: _generated/dashboard.md does not start with a Pandoc raw HTML block"
    )

if not text.rstrip().endswith("```"):
    raise SystemExit(
        "ERROR: _generated/dashboard.md does not end with a raw HTML closing fence"
    )

if text.count("```{=html}") != 1:
    raise SystemExit(
        "ERROR: dashboard should contain exactly one raw HTML opening fence"
    )

required = [
    "Today's Focus",
    "Research Activity",
    "Paper Pipeline",
    "Experiment Status",
    "Literature Reading",
    "Project Progress",
    "Paper Progress",
    "Experiment Progress",
    "Recently Updated",
]

missing = [item for item in required if item not in text]
if missing:
    raise SystemExit(
        "ERROR: generated dashboard is missing section(s): "
        + ", ".join(missing)
    )

print("  [OK] Dashboard raw HTML wrapper and required sections")
PY

section "5/8 Clean Quarto render"

rm -rf "_site"

"$QUARTO" render \
  || fail "quarto render failed"

[[ -f "_site/index.html" ]] \
  || fail "_site/index.html was not generated"

ok "Clean Quarto render completed"

section "6/8 Dashboard DOM rendering checks"

INDEX="_site/index.html"

DOM_REPORT="$(
"$PYTHON" - <<'PY'
from html.parser import HTMLParser
from pathlib import Path

path = Path("_site/index.html")
html = path.read_text(encoding="utf-8")

escaped_patterns = [
    '&lt;h1',
    '&lt;h2',
    '&lt;div class="ros-progress-label',
    '&lt;span class="ros-heat-cell',
    '&lt;a class="ros-item-title',
]

bad = [p for p in escaped_patterns if p in html]
if bad:
    raise SystemExit(
        "ERROR: dashboard contains escaped HTML source: "
        + ", ".join(bad)
    )

class DashboardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture_card_title = False
        self.card_title_parts = []
        self.card_titles = []
        self.progress_labels = 0
        self.heat_cells = 0
        self.item_titles = 0
        self.dashboard_roots = 0

    @staticmethod
    def classes(attrs):
        return set(dict(attrs).get("class", "").split())

    def handle_starttag(self, tag, attrs):
        classes = self.classes(attrs)

        if "ros-dashboard" in classes:
            self.dashboard_roots += 1

        if tag == "h2" and "ros-card-title" in classes:
            self.capture_card_title = True
            self.card_title_parts = []

        if "ros-progress-label" in classes:
            self.progress_labels += 1

        if "ros-heat-cell" in classes:
            self.heat_cells += 1

        if "ros-item-title" in classes:
            self.item_titles += 1

    def handle_data(self, data):
        if self.capture_card_title:
            self.card_title_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "h2" and self.capture_card_title:
            title = " ".join("".join(self.card_title_parts).split())
            if title:
                self.card_titles.append(title)
            self.capture_card_title = False
            self.card_title_parts = []

parser = DashboardParser()
parser.feed(html)

required_titles = {
    "Today's Focus",
    "Upcoming / Blocked",
    "Research Activity",
    "Paper Pipeline",
    "Experiment Status",
    "Literature Reading",
    "Project Progress",
    "Paper Progress",
    "Experiment Progress",
    "Recently Updated",
}

missing = sorted(required_titles - set(parser.card_titles))
if missing:
    print("Found dashboard card titles:", file=__import__("sys").stderr)
    for title in parser.card_titles:
        print(f"  - {title}", file=__import__("sys").stderr)
    raise SystemExit(
        "ERROR: missing dashboard DOM card title(s): "
        + ", ".join(missing)
    )

if parser.dashboard_roots < 1:
    raise SystemExit("ERROR: no ros-dashboard root DOM element found")

if parser.progress_labels < 1:
    raise SystemExit("ERROR: no ros-progress-label DOM elements found")

if parser.heat_cells < 365:
    raise SystemExit(
        f"ERROR: only {parser.heat_cells} heatmap cells found; expected at least 365"
    )

if parser.item_titles < 1:
    raise SystemExit("ERROR: no ros-item-title DOM elements found")

print(f"card_titles={len(parser.card_titles)}")
print(f"progress_labels={parser.progress_labels}")
print(f"heat_cells={parser.heat_cells}")
print(f"item_titles={parser.item_titles}")
print(f"dashboard_roots={parser.dashboard_roots}")
PY
)" || fail "Dashboard DOM validation failed"

card_titles="$(printf '%s\n' "$DOM_REPORT" | sed -n 's/^card_titles=//p')"
progress_labels="$(printf '%s\n' "$DOM_REPORT" | sed -n 's/^progress_labels=//p')"
heat_cells="$(printf '%s\n' "$DOM_REPORT" | sed -n 's/^heat_cells=//p')"
item_titles="$(printf '%s\n' "$DOM_REPORT" | sed -n 's/^item_titles=//p')"
dashboard_roots="$(printf '%s\n' "$DOM_REPORT" | sed -n 's/^dashboard_roots=//p')"

ok "Dashboard root DOM elements: $dashboard_roots"
ok "Dashboard card titles:      $card_titles"
ok "Progress components:        $progress_labels"
ok "Heatmap cells:              $heat_cells"
ok "Recent-item links:          $item_titles"
ok "No escaped dashboard HTML detected"

section "7/8 Website pages and Listings"

top_pages=(
  "_site/index.html"
  "_site/about.html"
  "_site/projects/index.html"
  "_site/papers/index.html"
  "_site/ideas/index.html"
  "_site/experiments/index.html"
  "_site/datasets/index.html"
  "_site/literature/index.html"
  "_site/methods/index.html"
  "_site/logs/index.html"
)

for page in "${top_pages[@]}"; do
  [[ -f "$page" ]] \
    || fail "Missing rendered top-level page: $page"
done

ok "All top-level pages exist"

object_count=0

for collection in "${COLLECTIONS[@]}"; do
  listing="_site/${collection}/index.html"

  while IFS= read -r -d '' qmd; do
    object_count=$((object_count + 1))

    object_dir="$(dirname "$qmd")"
    expected_html="_site/${object_dir}/index.html"

    [[ -f "$expected_html" ]] \
      || fail "Missing rendered object page: $expected_html"

    object_id="$(
      grep -m1 '^id:[[:space:]]*' "$qmd" \
      | sed 's/^id:[[:space:]]*//' \
      | tr -d "\"'"
    )"

    [[ -n "$object_id" ]] \
      || fail "Could not read object id from: $qmd"

    grep -Fq "$object_id" "$listing" \
      || fail "Listing ${collection}/ does not contain object ID: $object_id"

  done < <(
    find "$collection" \
      -mindepth 2 \
      -maxdepth 2 \
      -type f \
      -name 'index.qmd' \
      -print0 \
      | sort -z
  )

  ok "${collection}/ Listing and object pages"
done

log_count=0

while IFS= read -r -d '' qmd; do
  log_count=$((log_count + 1))

  rel="${qmd%.qmd}"
  expected_html="_site/${rel}.html"

  [[ -f "$expected_html" ]] \
    || fail "Missing rendered research log page: $expected_html"

  log_date="$(basename "$qmd" .qmd)"
  grep -Fq "$log_date" "_site/logs/index.html" \
    || fail "Research Log Listing does not contain date: $log_date"

done < <(
  find logs \
    -mindepth 2 \
    -maxdepth 2 \
    -type f \
    -name '*.qmd' \
    -print0 \
    | sort -z
)

ok "Checked $object_count numbered object page(s)"
ok "Checked $log_count research log page(s)"

section "8/8 Repository hygiene"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  repo_root="$(git rev-parse --show-toplevel)"

  [[ "$repo_root" == "$ROOT" ]] \
    || fail "Git repository root is '$repo_root', expected '$ROOT'"

  git check-ignore -q "_site" \
    || fail "_site/ is not ignored by Git"

  git check-ignore -q "_generated" \
    || fail "_generated/ is not ignored by Git"

  if git ls-files --error-unmatch "_site/index.html" >/dev/null 2>&1; then
    fail "_site/index.html is tracked by Git"
  fi

  if git ls-files "_generated/*" | grep -q .; then
    fail "_generated/ contains Git-tracked generated files"
  fi

  ok "Git root and generated-file ignore rules"
else
  echo "  [WARN] Not inside a Git working tree; Git hygiene checks skipped"
fi

section "ResearchOS check PASSED"

echo "Objects checked: $object_count"
echo "Logs checked:    $log_count"
echo "Heatmap cells:   $heat_cells"
echo