# Develop Eval

Generate and maintain eval suites for Claude Code skills.

## Inputs

The user provides one of:
- A path to a SKILL.md file
- A request to "create evals for my skill" (triggers auto-discovery)

Optionally:
- A workspace path with existing eval results (triggers iteration mode)

## Process

### First-time generation

#### Discovery

1. If no SKILL.md path provided, scan the repo for `**/SKILL.md` files.
2. If multiple found, list them and ask which skill to target.
3. If one found, confirm with the user.

#### Analysis

4. Read the target SKILL.md thoroughly. Identify:
   - Inputs and their sources (user prompts, files, MCP tools)
   - Expected outputs (files, formats, structures)
   - Failure modes (missing input, malformed data, edge cases)
   - External dependencies (APIs, MCP servers, file systems)
   - Prompt injection surfaces (user-controlled input that the skill processes)
5. Determine which test case categories apply:
   - **Standard** (always) — golden path with well-formed input.
   - **Adversarial** (always) — prompt injection in the input data.
   - Additional categories based on analysis: incomplete or ambiguous
     input, complex multi-source input, edge cases specific to the
     skill's domain.

#### Generation

6. For each test case, generate:
   - A realistic `prompt` that exercises the skill.
   - Fixture files in `evals/<skill>/files/` that simulate the skill's
     expected inputs.
   - An `expected_output` description.
   - Concrete assertions grounded in what the skill's SKILL.md promises.
7. Assemble `evals.json` following the schema at `evals.schema.json`.
8. Write `evals/<skill>/README.md` documenting what each case tests.

#### CI setup

9. If `.github/workflows/eval.yml` does not exist, copy the template
   from `../../templates/eval-workflow.yml` into the adopter's repo.
   Tell the user to add their `ANTHROPIC_API_KEY` secret.

#### Validation

10. Validate the generated `evals.json` against `evals.schema.json`.
11. Offer to run the eval suite immediately via `run-evals.sh`.

### Iteration mode

When the user provides a workspace with existing results:

1. Read `eval-*/grading.json` files — identify failed assertions.
2. Read `feedback.json` — pick up human review notes.
3. Read the skill's SKILL.md — understand current instructions.
4. Propose SKILL.md improvements following agentskills.io principles:
   generalize from feedback, keep instructions lean, explain the why.
5. Present proposed changes to the user for review before applying.
6. If failures reveal a gap in test coverage, propose a new test case.
7. If an assertion always passes in both current and baseline, flag it
   for removal.

## Idempotency

- If `evals.json` exists, read it first. Analyze which test case
  categories are covered. Only generate cases for missing categories.
  Preserve existing cases, IDs, and assertions.
- If fixture files exist, do not regenerate them. New cases get new
  fixture files with non-colliding names.
- If `eval-workflow.yml` exists, skip the copy.
- Explicit user request required to regenerate an existing case.

## Rules

- Do not auto-apply SKILL.md changes — present to the user for review.
- Do not remove existing test cases without asking — only flag them.
- Do not run evals — tell the user to run `/skill-litmus:run-evals`
  after applying changes.
- Assertions must be specific and grounded. "The output is correct" is
  too vague. "The output file contains a section titled 'Dependencies'"
  is specific.
- Adversarial fixtures must include the comment
  `<!-- ADVERSARIAL TEST FIXTURE — <purpose> -->`.
- Synthetic data fixtures must include the comment
  `<!-- SYNTHETIC TEST DATA — <purpose> -->`.
