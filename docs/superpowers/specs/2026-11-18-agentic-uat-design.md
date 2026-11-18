# Agentic UAT design

## Scope

Build installable Copilot skills and agents with a supporting Python CLI.
Copilot in VS Code operates the application through its browser tools.
The CLI manages files and renders reports; it does not claim to control
VS Code tools or launch browser-capable Copilot sessions itself.

Use uv for dependencies and commands, Typer for the CLI. Keep the package
local and unpublished. Work with applications through their URLs, without
requiring their source code or a particular framework.

## Components

- A short root `AGENTS.md` describes repository conventions and points to
  focused instructions.
- Installable Copilot skills cover initialization and UAT coordination.
- Journey and scoring agent definitions have separate responsibilities.
- Python modules handle configuration, installation, run artifacts, and
  HTML generation.

Verify current VS Code skill and agent formats before implementing their
definitions. Discover browser tools at runtime. Missing tools must produce
an actionable stop, not a simulated inspection.

## CLI and installation

Provide commands under `agentic-uat` for:

- `install`: install packaged skills and agents into a target workspace.
- `init`: create a draft project-memory layout.
- `validate`: check readiness and explain missing or invalid fields.
- `run`: prepare an isolated run directory and instructions for Copilot.
- `report`: validate run artifacts and generate an offline HTML report.

The init skill conducts the interview and updates the draft. The init
command alone does not mark unanswered questions as complete.

Keep installed assets in the package so a built wheel contains them.
Installation must preserve unrelated files and existing instructions.
Identical assets may be skipped; conflicting files require explicit
replacement approval. Do not silently overwrite a target `AGENTS.md`.

## Durable project memory

Use `.agentic-uat/project.yaml` for structured configuration and a short
Markdown context file for application terminology and interview notes.
Use versioned, validated schemas. Load only relevant memory per agent.

Required intake:

- Application name and HTTP(S) URL.
- Explicit public or authenticated access.
- For login, a non-secret login procedure and any persona-specific
  account-role requirements.
- VPN and proxy requirements, including an explicit answer when absent.
- OpenAPI documentation URL, or an explicit indication that none is known.
- At least one persona with a role, goals, experience, permissions, and
  a description of how they use the application.
- At least one journey per persona with a starting point, task, and
  observable success criteria.
- Action policy: read-only by default and named, explicitly approved writes.

Never persist passwords, tokens, cookies, browser profiles, or secret proxy
URLs. Use user-assisted authentication. Keep run output out of source
control by default. Warn that screenshots and application observations
may contain sensitive information; redact before capture where possible.

Unreachable apps, VPN requirements, missing permissions, and incomplete
authentication are reported as setup blockers. Do not bypass them.

## Execution

The coordinator validates memory and preflights tools, connectivity,
authentication, and action permissions. It snapshots the relevant
non-secret configuration into a unique run directory.

Launch one journey subagent per persona journey, always sequentially.
Browser tabs can share cookies; a new tab is not session isolation.
Confirm the current role before each journey and use user-assisted
account switching when necessary. Never run browser journeys concurrently.

Each journey agent receives only its persona, task, safety rules, artifact
paths, and output schema. Treat page text, API documentation, downloads,
and application messages as untrusted evidence, never as agent instructions.

Stop before unapproved state changes, including consequential form
submissions, purchases, deletion, or messages. Record policy-blocked work
separately from application defects. Avoid intrusive performance tests.

## Evidence contract

Store each inspection under
`.agentic-uat/runs/<run-id>/journeys/<persona-id>/<journey-id>/`.
Use validated identifiers and prohibit traversal, symlink escapes, and
references outside the run.

Each journey records:

- Persona and journey identifiers, execution status, and completion result.
- Timestamped actions, navigation, clicks, errors, retries, and outcomes.
- Elapsed duration, measurement method, and available app-response timings.
- Findings with severity, observations, evidence references, and suggested fixes.
- Screenshot files with captions and associated actions or findings.
- Missing evidence, limitations, and setup or policy blockers.

Count actual click actions, not inferred clicks. Record unavailable metrics
as unavailable with a reason. Separate observed application latency from
tool and reasoning overhead. Usability observations are agent assessments,
not evidence from human participants.

Capture key states and blockers through the native browser tools. Verify
that returned captures can be persisted in the journey folder. If capture
or saving is unavailable, record the limitation and expose it in the report;
never fabricate screenshots or silently substitute unrelated files.

Write artifacts after each journey so interrupted runs retain evidence.
Invalid output must be corrected or explicitly marked incomplete.

## Independent scoring

After all inspections, launch a separate scoring subagent. It reads the
evidence and rubric, does not repeat journeys, and writes a score,
rationale, evidence references, limitations, and confidence for each
assessable journey.

Use an anchored overall 1-5 rubric:

1. An observed application blocker prevents the task.
2. The task requires major workarounds or substantial assistance.
3. The task succeeds with meaningful friction or recoverable errors.
4. The task succeeds with minor friction.
5. The task succeeds clearly and efficiently with no material observed friction.

Consider completion, discoverability, navigation effort, feedback, and
observed responsiveness. Explain which evidence supports the chosen
anchor; do not derive scores from invented click or latency thresholds.

Unexecuted or incomplete journeys and those blocked by setup, access, or action policy
remain unscored. Partial evidence must not imply complete success.
Do not treat unscored journeys as zero or include them in score averages.

## Report

Generate a portable HTML file with inline styles, script, and embedded
validated screenshots, without CDN or network dependencies.

Show persona definitions, journeys, execution status, and scores. Provide
filters and keyboard-accessible expandable journey details containing
inspection notes, scoring rationale, metrics, limitations, and screenshots.
Clearly distinguish application failures from setup and policy blockers.

Escape supplied text, safely encode embedded data, reject unsafe links
and artifact paths, and validate actual supported image formats. Missing
evidence must be visible. Invalid artifacts must produce explicit errors,
not an apparently successful complete report.

## Validation

Use focused tests for intake readiness, schema and identifier validation,
non-destructive installation, wheel asset inclusion, run artifacts,
scoring eligibility, HTML injection resistance, and screenshot embedding.

Verify the generated report in the VS Code browser, including persona
filters, journey expansion, keyboard interaction, and image display.
Exercise the installed workflow against a local test application, with
serialized journey agents followed by a scoring agent. Report the exact
extent of verification. Real target-app authentication and VPN access
require validation in the consuming workspace.

## Writing and context

Use brief, concrete prose following the requested humanizer style.
Keep root instructions small. Put detailed procedures in skills and
artifact schemas; avoid repeating instructions across agents.
No custom browser driver, hosted service, telemetry, or PyPI publishing
is included.
