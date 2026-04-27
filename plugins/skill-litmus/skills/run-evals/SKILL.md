# Run Evals

Thin interactive wrapper around the deterministic eval engine.

## Inputs

The user provides:
- **Skill name** — the slash-command name of the skill to test
- **Evals path** — path to the `evals.json` file
- **Workspace** — directory where results are written

## Process

1. Resolve the path to `run-evals.sh` at `../../scripts/run-evals.sh`
   relative to this SKILL.md.
2. Invoke it via Bash:
   ```bash
   bash <scripts-dir>/run-evals.sh \
     --evals <evals-path> \
     --skill <skill-name> \
     --workspace <workspace>
   ```
3. Read `<workspace>/summary.md` and display its contents to the user.

## Rules

- Do not spawn subagents. The shell script handles all orchestration.
- Do not capture timing or aggregate results. The scripts do this.
- If `run-evals.sh` exits with a non-zero code, display the error
  output to the user.
