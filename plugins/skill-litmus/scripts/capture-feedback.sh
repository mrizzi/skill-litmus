#!/usr/bin/env bash
# Parse per-eval feedback and write feedback.json.
# See docs/specs/2026-04-30-human-review-design.md Section 3.2.
#
# Usage:
#   capture-feedback.sh --output <path> --eval <id> "<text>" [--eval <id> "<text>" ...]
#   capture-feedback.sh --output <path> --comment "<body>"
#   capture-feedback.sh --output <path> --comment-file <file>

set -euo pipefail

OUTPUT=""
COMMENT=""
COMMENT_FILE=""
declare -a EVAL_IDS=()
declare -a EVAL_TEXTS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)       OUTPUT="$2";       shift 2 ;;
        --comment)      COMMENT="$2";      shift 2 ;;
        --comment-file) COMMENT_FILE="$2"; shift 2 ;;
        --eval)
            [[ $# -lt 3 ]] && echo "Error: --eval requires <id> and <text> arguments" >&2 && exit 1
            EVAL_IDS+=("$2")
            EVAL_TEXTS+=("$3")
            shift 3
            ;;
        *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -z "$OUTPUT" ]] && echo "Error: --output required" >&2 && exit 1

if [[ "$OUTPUT" == *".."* ]]; then
    echo "Error: --output path must not contain '..'" >&2
    exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"

if [[ -n "$COMMENT_FILE" ]]; then
    COMMENT=$(cat "$COMMENT_FILE" 2>/dev/null) || { echo "Error: could not read $COMMENT_FILE" >&2; exit 1; }
fi

if [[ -n "$COMMENT" ]]; then
    while IFS= read -r line; do
        if [[ "$line" =~ ^eval-([0-9]+):[[:space:]]*(.*) ]]; then
            EVAL_IDS+=("${BASH_REMATCH[1]}")
            EVAL_TEXTS+=("${BASH_REMATCH[2]}")
        fi
    done <<< "$COMMENT"
fi

if [[ ${#EVAL_IDS[@]} -eq 0 ]]; then
    echo "Error: no feedback entries provided" >&2
    exit 1
fi

python3 - "$OUTPUT" "${EVAL_IDS[@]}" -- "${EVAL_TEXTS[@]}" <<'PYEOF'
import json
import os
import sys

args = sys.argv[1:]
output_path = args[0]
rest = args[1:]
sep = rest.index("--")
ids = rest[:sep]
texts = rest[sep + 1:]

new_feedback = {f"eval-{i}": t for i, t in zip(ids, texts)}

if os.path.exists(output_path):
    with open(output_path) as f:
        existing = json.load(f)
    existing.update(new_feedback)
    merged = existing
else:
    merged = new_feedback

with open(output_path, "w") as f:
    json.dump(merged, f, indent=2)
    f.write("\n")
PYEOF

echo "Feedback written to $OUTPUT"
