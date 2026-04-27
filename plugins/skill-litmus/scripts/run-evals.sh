#!/usr/bin/env bash
# Deterministic orchestrator.
# See docs/specs/2026-04-24-standalone-eval-runner-design.md Section 2.
#
# Usage:
#   run-evals.sh --evals <path> --skill <name> --workspace <dir> \
#                [--plugin <namespace>] [--baseline <path>]

set -euo pipefail

EVALS_PATH=""
SKILL_NAME=""
WORKSPACE=""
PLUGIN=""
BASELINE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --evals)     EVALS_PATH="$2";  shift 2 ;;
        --skill)     SKILL_NAME="$2";  shift 2 ;;
        --workspace) WORKSPACE="$2";   shift 2 ;;
        --plugin)    PLUGIN="$2";      shift 2 ;;
        --baseline)  BASELINE="$2";    shift 2 ;;
        *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -z "$EVALS_PATH" ]] && echo "Error: --evals required" >&2 && exit 1
[[ -z "$SKILL_NAME" ]] && echo "Error: --skill required" >&2 && exit 1
[[ -z "$WORKSPACE" ]]  && echo "Error: --workspace required" >&2 && exit 1

# Resolve evals.json path
if [[ -d "$EVALS_PATH" ]]; then
    EVALS_FILE="$EVALS_PATH/evals.json"
else
    EVALS_FILE="$EVALS_PATH"
fi
[[ ! -f "$EVALS_FILE" ]] && echo "Error: $EVALS_FILE not found" >&2 && exit 1
EVALS_DIR="$(cd "$(dirname "$EVALS_FILE")" && pwd)"
EVALS_FILE="$EVALS_DIR/$(basename "$EVALS_FILE")"

# Auto-detect plugin namespace
if [[ -z "$PLUGIN" ]]; then
    PLUGIN=$(jq -r '.plugin // empty' "$EVALS_FILE")
fi
if [[ -z "$PLUGIN" ]]; then
    search_dir="$EVALS_DIR"
    while [[ "$search_dir" != "/" ]]; do
        if [[ -f "$search_dir/.claude-plugin/plugin.json" ]]; then
            PLUGIN=$(jq -r '.name' "$search_dir/.claude-plugin/plugin.json")
            break
        fi
        search_dir="$(dirname "$search_dir")"
    done
fi
if [[ -z "$PLUGIN" ]]; then
    echo "Error: could not detect plugin namespace. Use --plugin." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_CMD="/$PLUGIN:$SKILL_NAME"

# Parse and validate IDs
EVAL_IDS=$(jq -r '.evals[].id' "$EVALS_FILE")
if [[ -z "$EVAL_IDS" ]]; then
    echo "Error: no cases found in $EVALS_FILE" >&2
    exit 1
fi
for id in $EVAL_IDS; do
    if ! [[ "$id" =~ ^[0-9]+$ ]]; then
        echo "Error: invalid eval id: $id (must be a positive integer)" >&2
        exit 1
    fi
done

# Create workspace layout
mkdir -p "$WORKSPACE"
for id in $EVAL_IDS; do
    mkdir -p "$WORKSPACE/eval-$id/outputs"
done

NUM_EVALS=$(echo "$EVAL_IDS" | wc -w | tr -d ' ')
echo "Running $NUM_EVALS cases for skill $SKILL_CMD"

# --- Execute cases in parallel ---
pids=()
for id in $EVAL_IDS; do
    (
        case_json=$(jq ".evals[] | select(.id == $id)" "$EVALS_FILE")
        prompt=$(echo "$case_json" | jq -r '.prompt')
        expected=$(echo "$case_json" | jq -r '.expected_output')
        files_json=$(echo "$case_json" | jq -r '.files // []')

        # Build the execution prompt
        exec_prompt="You are running case $id for the skill $SKILL_CMD.

User prompt for the skill:
$prompt

Expected output:
$expected"

        # Append fixture file contents (with path traversal guard)
        file_count=$(echo "$files_json" | jq -r 'length')
        for (( i=0; i<file_count; i++ )); do
            rel_path=$(echo "$files_json" | jq -r ".[$i]")
            abs_path="$(cd "$EVALS_DIR" && python3 -c "import os,sys; print(os.path.normpath(os.path.join(sys.argv[1], sys.argv[2])))" "$EVALS_DIR" "$rel_path")"
            if [[ "$abs_path" != "$EVALS_DIR/"* ]]; then
                echo "Error: fixture path escapes evals directory: $rel_path" >&2
                exit 1
            fi
            if [[ -f "$abs_path" ]]; then
                exec_prompt="$exec_prompt

--- Fixture: $rel_path ---
$(cat "$abs_path")"
            else
                echo "Warning: fixture $abs_path not found" >&2
            fi
        done

        exec_prompt="$exec_prompt

Instructions:
1. Copy any fixture files above into the current working directory.
2. Invoke the skill $SKILL_CMD with the user prompt shown above.
3. Save all skill outputs into: $WORKSPACE/eval-$id/outputs/
4. Do not grade or assess the output. Just execute and capture."

        # Capture wall-clock timing via Python (portable across macOS and Linux)
        start=$(python3 -c "import time; print(time.time())")

        claude -p "$exec_prompt" \
            --permission-mode dontAsk \
            --allowedTools "Read,Write,Bash,Skill,Agent,Glob,Edit" \
            > "$WORKSPACE/eval-$id/execution.log" 2>&1 || true

        end=$(python3 -c "import time; print(time.time())")
        duration=$(python3 -c "print(round($end - $start, 1))")

        cat > "$WORKSPACE/eval-$id/timing.json" <<TIMING_EOF
{
  "eval_id": $id,
  "duration_seconds": $duration
}
TIMING_EOF

        echo "  eval-$id executed (${duration}s)"
    ) &
    pids+=($!)
done

for pid in "${pids[@]}"; do
    wait "$pid" || true
done

# --- Grade cases in parallel ---
echo "Grading..."
pids=()
for id in $EVAL_IDS; do
    (
        case_json=$(jq ".evals[] | select(.id == $id)" "$EVALS_FILE")
        expected=$(echo "$case_json" | jq -r '.expected_output')

        # Build assertion list
        assertion_list=""
        while IFS= read -r line; do
            assertion_list="$assertion_list
- $line"
        done < <(echo "$case_json" | jq -r '.assertions[]')

        # Collect output file contents
        output_contents=""
        if [[ -d "$WORKSPACE/eval-$id/outputs" ]]; then
            while IFS= read -r f; do
                [[ -z "$f" ]] && continue
                output_contents="$output_contents

--- $(basename "$f") ---
$(cat "$f")"
            done < <(find "$WORKSPACE/eval-$id/outputs" -type f 2>/dev/null)
        fi

        if [[ -z "$output_contents" ]]; then
            output_contents="(no output files found)"
        fi

        grading_prompt="You are grading case $id. Grade each assertion as passed or failed based on the actual outputs.

Expected output description:
$expected

Assertions to grade:
$assertion_list

Actual outputs:
$output_contents

Respond with ONLY valid JSON in this exact format (no markdown fences, no extra text):
{
  \"eval_id\": $id,
  \"assertions\": [
    {\"assertion\": \"<text>\", \"passed\": true, \"reasoning\": \"<brief>\"}
  ]
}

Grade each assertion independently. Be strict."

        claude -p "$grading_prompt" \
            --permission-mode dontAsk \
            --allowedTools "Read,Bash,Glob" \
            > "$WORKSPACE/eval-$id/grading_raw.txt" 2>&1 || true

        # Extract JSON from grading response
        python3 - "$WORKSPACE/eval-$id" "$id" <<'PYEOF'
import json, re, sys

eval_dir = sys.argv[1]
eval_id = int(sys.argv[2])
raw_path = f"{eval_dir}/grading_raw.txt"
out_path = f"{eval_dir}/grading.json"

try:
    text = open(raw_path).read()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        data = json.loads(match.group())
        data["eval_id"] = eval_id
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    else:
        raise ValueError("No JSON object found in grading response")
except Exception as e:
    fallback = {
        "eval_id": eval_id,
        "assertions": [],
        "error": str(e),
    }
    with open(out_path, "w") as f:
        json.dump(fallback, f, indent=2)
        f.write("\n")
    print(f"Warning: grading parse failed for eval-{eval_id}: {e}", file=sys.stderr)
PYEOF

        echo "  eval-$id graded"
    ) &
    pids+=($!)
done

for pid in "${pids[@]}"; do
    wait "$pid" || true
done

# --- Create empty feedback.json ---
echo '{}' > "$WORKSPACE/feedback.json"

# --- Aggregate ---
echo "Aggregating results..."
python3 "$SCRIPT_DIR/aggregate_benchmark.py" --results "$WORKSPACE"

# --- Render summary ---
baseline_args=()
if [[ -n "$BASELINE" ]]; then
    baseline_args=(--baseline "$BASELINE")
fi
python3 "$SCRIPT_DIR/render_summary.py" --results "$WORKSPACE" ${baseline_args[@]+"${baseline_args[@]}"}

echo ""
echo "Run complete. Results: $WORKSPACE/summary.md"
