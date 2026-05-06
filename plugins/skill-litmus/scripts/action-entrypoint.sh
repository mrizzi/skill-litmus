#!/usr/bin/env bash
# GitHub Action entrypoint — routes by event type.
# Extracted from action.yml for testability.
#
# Required env vars (set by action.yml):
#   GITHUB_EVENT_NAME, ACTION_PATH, EVALS_DIR
# Optional env vars:
#   SKILLS_DIR, BASELINE_BRANCH, PR_NUMBER, PR_BASE_SHA, GITHUB_SHA,
#   COMMENT_ID, AUTHOR_ASSOC, PR_URL, RUNNER_TEMP

set -euo pipefail

SCRIPT_DIR="${ACTION_PATH}/plugins/skill-litmus/scripts"
WORKSPACE_ROOT="${RUNNER_TEMP:-/tmp}/skill-litmus-workspace"
mkdir -p "$WORKSPACE_ROOT"
EVENT="$GITHUB_EVENT_NAME"

if [[ "$EVENT" == "pull_request" ]]; then
  # --- PR mode: run changed skills via shared script ---
  if [[ -z "${PR_NUMBER:-}" ]]; then
    echo "Error: PR_NUMBER is required for pull_request events" >&2
    exit 1
  fi
  CHANGED=$(git diff --name-only "$PR_BASE_SHA"...HEAD)

  bash "$SCRIPT_DIR/run-pr-evals.sh" \
    --base-sha "$PR_BASE_SHA" \
    --evals-dir "${EVALS_DIR}" \
    --workspace-root "$WORKSPACE_ROOT" \
    --changed-files "$CHANGED" \
    --pr-number "$PR_NUMBER" \
    ${SKILLS_DIR:+--skills-dir "$SKILLS_DIR"} \
    ${BASELINE_BRANCH:+--baseline-branch "$BASELINE_BRANCH"}

elif [[ "$EVENT" == "push" ]]; then
  # --- Push mode: run all suites, commit baselines ---
  for evals_json in ${EVALS_DIR}*/evals.json; do
    [[ ! -f "$evals_json" ]] && continue
    skill_name=$(jq -r '.skill_name' "$evals_json")
    skill_dir="$(dirname "$evals_json")"
    ws="$WORKSPACE_ROOT/$skill_name"

    bash "$SCRIPT_DIR/run-evals.sh" \
      --evals "$evals_json" \
      --skill "$skill_name" \
      --workspace "$ws"

    bash "$SCRIPT_DIR/post-results.sh" baseline \
      --workspace "$ws" \
      --evals-dir "$skill_dir" \
      --commit-hash "$GITHUB_SHA"
  done

elif [[ "$EVENT" == "issue_comment" ]]; then
  # --- Comment mode: parse /skill-litmus commands ---
  if [[ -z "${PR_URL:-}" ]]; then
    echo "Comment is not on a PR — skipping."
    exit 0
  fi

  COMMENT_BODY_FILE="$RUNNER_TEMP/comment_body.txt"
  if [[ ! -f "$COMMENT_BODY_FILE" ]]; then
    echo "Error: comment body file not found" >&2
    exit 1
  fi

  FIRST_LINE=$(head -1 "$COMMENT_BODY_FILE")
  if ! echo "$FIRST_LINE" | grep -qE '^/skill-litmus[[:space:]]+(feedback|rerun|iterate)'; then
    echo "Comment does not match /skill-litmus command — skipping."
    exit 0
  fi

  COMMAND=$(echo "$FIRST_LINE" | grep -oE '(feedback|rerun|iterate)' | head -1)
  CMD_SKILL=$(echo "$FIRST_LINE" | sed -E "s,^/skill-litmus[[:space:]]+(feedback|rerun|iterate)[[:space:]]*,," | xargs)

  if [[ ! "$COMMENT_ID" =~ ^[0-9]+$ ]]; then
    echo "Error: invalid comment ID" >&2
    exit 1
  fi

  # Permission gate: all commands require OWNER, MEMBER, or COLLABORATOR
  if [[ "$AUTHOR_ASSOC" != "OWNER" && "$AUTHOR_ASSOC" != "MEMBER" && "$AUTHOR_ASSOC" != "COLLABORATOR" ]]; then
    bash "$SCRIPT_DIR/post-results.sh" comment-reply \
      --comment-id "$COMMENT_ID" --reaction "-1" \
      --body "Only repository collaborators can use /skill-litmus commands."
    exit 0
  fi

  if [[ -z "${PR_NUMBER:-}" ]]; then
    echo "Error: PR_NUMBER is required for issue_comment events on PRs" >&2
    exit 1
  fi

  # React with eyes to acknowledge (after permission check)
  bash "$SCRIPT_DIR/post-results.sh" comment-reply \
    --comment-id "$COMMENT_ID" --reaction "eyes"

  # --- Enumerate valid skills from evals directory ---
  list_valid_skills() {
    for f in ${EVALS_DIR}*/evals.json; do
      [[ ! -f "$f" ]] && continue
      local sn dir_name
      sn=$(jq -r '.skill_name' "$f")
      dir_name=$(basename "$(dirname "$f")")
      [[ ! "$sn" =~ ^[a-zA-Z0-9_-]+$ ]] && continue
      [[ "$sn" != "$dir_name" ]] && continue
      echo "$sn"
    done
  }

  # --- Resolve skill name (shared by feedback and iterate) ---
  # Sets RESOLVED_SKILL or exits with error reply.
  resolve_skill() {
    local cmd_label="$1"
    RESOLVED_SKILL=""
    if [[ -n "$CMD_SKILL" ]]; then
      if [[ ! "$CMD_SKILL" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        bash "$SCRIPT_DIR/post-results.sh" comment-reply \
          --comment-id "$COMMENT_ID" --reaction "-1" \
          --body "Error: invalid skill name: \`$CMD_SKILL\`"
        exit 1
      fi
      if [[ -f "${EVALS_DIR}${CMD_SKILL}/evals.json" ]]; then
        RESOLVED_SKILL="$CMD_SKILL"
      else
        local display
        display=$(list_valid_skills | paste -sd', ')
        bash "$SCRIPT_DIR/post-results.sh" comment-reply \
          --comment-id "$COMMENT_ID" --reaction "-1" \
          --body "Error: skill \`$CMD_SKILL\` not found. Available: ${display:-none}"
        exit 1
      fi
      return
    fi

    local found
    mapfile -t found < <(list_valid_skills)
    if [[ ${#found[@]} -eq 1 ]]; then
      RESOLVED_SKILL="${found[0]}"
    elif [[ ${#found[@]} -gt 1 ]]; then
      local skill_list
      skill_list=$(printf ', `%s`' "${found[@]}")
      bash "$SCRIPT_DIR/post-results.sh" comment-reply \
        --comment-id "$COMMENT_ID" --reaction "-1" \
        --body "Multiple skills found: ${skill_list:2}. Specify one: \`/skill-litmus $cmd_label <skill-name>\`"
      exit 1
    else
      bash "$SCRIPT_DIR/post-results.sh" comment-reply \
        --comment-id "$COMMENT_ID" --reaction "-1" \
        --body "Error: no valid evals.json found in ${EVALS_DIR}."
      exit 1
    fi
  }

  case "$COMMAND" in
    feedback)
      resolve_skill "feedback"
      SKILL_NAME="$RESOLVED_SKILL"
      FEEDBACK_PATH="${EVALS_DIR}${SKILL_NAME}/feedback.json"

      gh pr checkout "$PR_NUMBER" --force

      bash "$SCRIPT_DIR/capture-feedback.sh" \
        --output "$FEEDBACK_PATH" \
        --comment-file "$COMMENT_BODY_FILE"

      git add "$FEEDBACK_PATH"
      git diff --cached --quiet && { echo "No feedback changes to commit"; exit 0; }
      git commit "$FEEDBACK_PATH" -m "chore: capture human review feedback"
      git push

      EVAL_LIST=$(jq -r 'keys | sort | join(", ")' "$FEEDBACK_PATH")

      bash "$SCRIPT_DIR/post-results.sh" comment-reply \
        --comment-id "$COMMENT_ID" --reaction "+1" \
        --body "Feedback captured for ${EVAL_LIST}. Run \`/skill-litmus iterate\` to generate improvement suggestions."
      ;;

    rerun)
      gh pr checkout "$PR_NUMBER" --force

      BASE_SHA=$(gh pr view "$PR_NUMBER" --json baseRefOid -q '.baseRefOid')
      CHANGED=$(git diff --name-only "$BASE_SHA"...HEAD)

      bash "$SCRIPT_DIR/run-pr-evals.sh" \
        --base-sha "$BASE_SHA" \
        --evals-dir "${EVALS_DIR}" \
        --workspace-root "$WORKSPACE_ROOT" \
        --changed-files "$CHANGED" \
        --pr-number "$PR_NUMBER" \
        ${SKILLS_DIR:+--skills-dir "$SKILLS_DIR"} \
        ${BASELINE_BRANCH:+--baseline-branch "$BASELINE_BRANCH"}

      bash "$SCRIPT_DIR/post-results.sh" comment-reply \
        --comment-id "$COMMENT_ID" --reaction "+1"
      ;;

    iterate)
      resolve_skill "iterate"
      SKILL_NAME="$RESOLVED_SKILL"
      FEEDBACK_PATH="${EVALS_DIR}${SKILL_NAME}/feedback.json"

      if [[ ! -f "$FEEDBACK_PATH" ]]; then
        bash "$SCRIPT_DIR/post-results.sh" comment-reply \
          --comment-id "$COMMENT_ID" --reaction "-1" \
          --body "No feedback found. Post \`/skill-litmus feedback\` first."
        exit 0
      fi

      SKILL_MD=""
      if [[ -n "${SKILLS_DIR:-}" ]]; then
        SKILL_MD=$(find "$SKILLS_DIR" -path "*/$SKILL_NAME/SKILL.md" -print -quit 2>/dev/null || true)
      fi
      if [[ -z "$SKILL_MD" ]]; then
        SKILL_MD=$(find . -path "*/$SKILL_NAME/SKILL.md" -not -path "*/node_modules/*" -print -quit 2>/dev/null || true)
      fi

      GRADING_CONTEXT=""
      while IFS= read -r -d '' grading; do
        GRADING_CONTEXT="$GRADING_CONTEXT
--- $(basename "$(dirname "$grading")") ---
$(cat "$grading")"
      done < <(find "$WORKSPACE_ROOT" -name "grading.json" -print0 2>/dev/null)

      SKILL_CONTENT=""
      [[ -n "$SKILL_MD" && -f "$SKILL_MD" ]] && SKILL_CONTENT=$(cat "$SKILL_MD")

      PROMPT_FILE="$WORKSPACE_ROOT/iterate_prompt.txt"
      cat > "$PROMPT_FILE" <<PROMPT_EOF
You are iterating on a skill based on results and human feedback.

Current SKILL.md:
$SKILL_CONTENT

Human feedback (per-eval):
$(cat "$FEEDBACK_PATH")

Grading results:
$GRADING_CONTEXT

Propose specific improvements to SKILL.md following these principles:
- Generalize from feedback — fixes should address underlying issues broadly
- Keep instructions lean — fewer, better instructions outperform exhaustive rules
- Explain the why — reasoning-based instructions work better than rigid directives

Respond with ONLY the proposed changes as a unified diff block.
PROMPT_EOF

      if ! ITERATE_RESULT=$(cat "$PROMPT_FILE" | claude -p \
        --permission-mode dontAsk \
        --allowedTools "Read,Glob" 2>&1); then
        bash "$SCRIPT_DIR/post-results.sh" comment-reply \
          --comment-id "$COMMENT_ID" --reaction "-1" \
          --body "Error: iteration failed. See workflow logs for details."
        exit 1
      fi

      REPLY_BODY="## Proposed SKILL.md Improvements

Based on feedback for ${SKILL_NAME}:

$ITERATE_RESULT

> Apply these changes manually if they look good. Then run \`/skill-litmus rerun\` to verify."

      bash "$SCRIPT_DIR/post-results.sh" comment-reply \
        --comment-id "$COMMENT_ID" --reaction "+1" \
        --body "$REPLY_BODY"
      ;;
  esac

else
  echo "Unsupported event: $EVENT -- skipping."
  exit 0
fi
