#!/usr/bin/env bash
set -euo pipefail

echo "🧮 Counting real code lines (git-tracked)…"

# LedgerQuant source/document formats that count toward project LOC.
PATTERNS=(
  "*.py"
  "*.cs"
  "*.ts"
  "*.tsx"
  "*.js"
  "*.mjs"
  "*.rs"
  "*.cpp"
  "*.h"
  "*.json"
  "*.yaml"
  "*.yml"
  "*.toml"
  "*.sql"
  "*.md"
  "*.txt"
)

# Project birth date.
BIRTH_DATE="2026-10-08"

# ---------------------------------------------------------------------------
# Get all tracked files once.
# ---------------------------------------------------------------------------

mapfile -t TRACKED_FILES < <(git ls-files)

matches_patterns() {
  local file="$1"
  local pattern

  for pattern in "${PATTERNS[@]}"; do
    if [[ "$file" == $pattern ]]; then
      return 0
    fi
  done

  return 1
}

count_files() {
  local total=0
  local file

  for file in "$@"; do
    [[ -f "$file" ]] || continue
    matches_patterns "$file" || continue

    local lines
    lines=$(wc -l < "$file" 2>/dev/null || printf '0')
    total=$((total + lines))
  done

  printf '%d\n' "$total"
}

files_for_area() {
  local area="$1"
  local file

  for file in "${TRACKED_FILES[@]}"; do
    case "$area" in
      backend)
        [[ "$file" == src/ledgerquant/* ]] && printf '%s\n' "$file"
        ;;

      cbots)
        [[ "$file" == cbots/* ]] && printf '%s\n' "$file"
        ;;

      frontend)
        [[ "$file" == apps/web/* ]] && printf '%s\n' "$file"
        ;;

      tests)
        [[ "$file" == tests/* ]] && printf '%s\n' "$file"
        ;;

      migrations)
        [[ "$file" == migrations/* ]] && printf '%s\n' "$file"
        ;;

      deploy)
        [[ "$file" == deploy/* ]] && printf '%s\n' "$file"
        ;;

      docs)
        [[ "$file" == documents/* ]] && printf '%s\n' "$file"
        ;;

      scripts)
        [[ "$file" == scripts/* ]] && printf '%s\n' "$file"
        ;;

      root)
        case "$file" in
          */*) ;;
          *) printf '%s\n' "$file" ;;
        esac
        ;;
    esac
  done
}

count_area() {
  local area="$1"
  local -a files=()

  mapfile -t files < <(files_for_area "$area")
  count_files "${files[@]}"
}

# ---------------------------------------------------------------------------
# Count total project LOC.
# ---------------------------------------------------------------------------

TOTAL=0


for file in "${TRACKED_FILES[@]}"; do
  [[ -f "$file" ]] || continue
  matches_patterns "$file" || continue

  case "$file" in
  .claude/skills/*|.codex/skills/*)
    continue
    ;;
  esac

  lines=$(wc -l < "$file" 2>/dev/null || printf '0')
  TOTAL=$((TOTAL + lines))
done

# ---------------------------------------------------------------------------
# Project age.
# ---------------------------------------------------------------------------

TODAY=$(date -u +%F)

BIRTH_SECONDS=$(date -u -d "$BIRTH_DATE" +%s)
TODAY_SECONDS=$(date -u -d "$TODAY" +%s)

AGE_DAYS=$(( (TODAY_SECONDS - BIRTH_SECONDS) / 86400 ))

# Include birth day, same convention as FX-Algo.
AGE_DAYS=$((AGE_DAYS + 1))

# ---------------------------------------------------------------------------
# Header.
# ---------------------------------------------------------------------------

echo
echo "LedgerQuant AI multi-agent quant research platform made by solo developer Darth Padletut"
echo "Actually just asking Darth GPT some questions"
echo "📅 LedgerQuant was born at ${BIRTH_DATE} and is ⏳ (${AGE_DAYS} days young)"
echo "😎 Total lines: ${TOTAL}"
echo

# ---------------------------------------------------------------------------
# Areas.
# ---------------------------------------------------------------------------

AREAS=(
  backend
  cbots
  frontend
  tests
  migrations
  deploy
  docs
  scripts
  root
)

declare -A COUNTS

for area in "${AREAS[@]}"; do
  COUNTS["$area"]=$(count_area "$area")
done

printf "%-14s %10s %8s\n" "Area" "LOC" "Share"
printf "%-14s %10s %8s\n" "--------------" "----------" "--------"

for area in "${AREAS[@]}"; do
  loc="${COUNTS[$area]}"

  if (( TOTAL > 0 )); then
    share=$(awk -v n="$loc" -v total="$TOTAL" \
      'BEGIN { printf "%.1f%%", (n / total) * 100 }')
  else
    share="0.0%"
  fi

  printf "%-14s %10d %8s\n" "$area" "$loc" "$share"
done

# ---------------------------------------------------------------------------
# cBot breakdown.
# ---------------------------------------------------------------------------

echo
echo "🤖 cBot breakdown:"

for dir in cbots/*; do
  [[ -d "$dir" ]] || continue

  name=$(basename "$dir")

  mapfile -t files < <(
    printf '%s\n' "${TRACKED_FILES[@]}" |
      awk -v prefix="$dir/" 'index($0, prefix) == 1'
  )

  loc=$(count_files "${files[@]}")

  printf "   %-28s %8d\n" "$name:" "$loc"
done

# ---------------------------------------------------------------------------
# Test breakdown.
# ---------------------------------------------------------------------------

echo
echo "🧪 Test breakdown:"

for area in unit contract integration dotnet end_to_end; do
  dir="tests/$area"

  if [[ -d "$dir" ]]; then
    mapfile -t files < <(
      printf '%s\n' "${TRACKED_FILES[@]}" |
        awk -v prefix="$dir/" 'index($0, prefix) == 1'
    )

    loc=$(count_files "${files[@]}")

    printf "   %-16s %8d\n" "$area:" "$loc"
  fi
done

# ---------------------------------------------------------------------------
# Research/data metadata.
# Do NOT count raw datasets as LOC.
# ---------------------------------------------------------------------------

echo
echo "🔬 Research:"
printf "   %-20s %8d\n" "research docs:" "$(count_area docs)"

DESKTOP_REF="data/ctrader_tick_exports/desktop_reference/LedgerQuant.LiveCapture EURUSD t1 20180522-20261008.csv"

if [[ -f "$DESKTOP_REF" ]]; then
  bytes=$(stat -c '%s' "$DESKTOP_REF")

  echo
  echo "💾 Research data:"
  printf "   EURUSD Desktop: %'d bytes\n" "$bytes"
fi
