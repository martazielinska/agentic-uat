# UAT artifact contract

The CLI models are authoritative. Load full JSON Schema output when writing
artifacts; do not copy schema definitions into agent instructions:

```sh
agentic-uat schema project
agentic-uat schema manifest
agentic-uat schema journey
agentic-uat schema score
```

## Resolve the CLI

From this repository checkout, development commands may use `uv run
agentic-uat ...`. Do not assume a target application is a Python or uv
project. First try `agentic-uat --help`; if the installed tool is on PATH,
use `agentic-uat ...` anywhere.

If it is not installed, and the package source path is known, choose one:

```sh
uv tool install /path/to/agentic-uat
uv tool run --from /path/to/agentic-uat agentic-uat validate
uv run --project /path/to/agentic-uat agentic-uat validate
```

The install makes the command available across workspaces. The other forms
run it against the CLI package without depending on the target project's
Python configuration. Replace `/path/to/agentic-uat` with the actual package
path. If that path is unknown and the command is unavailable, stop and ask
the owner to install the CLI or provide its location. Do not run
`uv run agentic-uat` from an arbitrary target workspace.

`agentic-uat init` creates a draft, `validate` checks project memory, and
`run` prepares a run directory and Copilot handoff only. The Copilot agent
executes browser work. `report` validates the run and renders its report.

Project memory is `.agentic-uat/project.yaml` plus optional
`.agentic-uat/context.md`. Run data is stored as:

```text
.agentic-uat/runs/<run-id>/
├── manifest.json
└── journeys/<persona-id>/<journey-id>/
    ├── result.json
    ├── score.json
    └── <real screenshot files>
```

The `journey` schema is the complete `JourneyResult` for `result.json`; the
`score` schema is for `score.json`. Use the exact files in each
`journeys/<persona-id>/<journey-id>/` directory. The manifest retains every
planned journey, including journeys with no result. Journey evidence and
scores are separate artifacts. Screenshots are journey-relative files
referenced by the result. Do not invent fields, evidence, timestamps, images,
or scores; use the live schema and validate artifacts with the CLI.

Only `completed` and `application_blocked` journeys are eligible for numeric
scores. `incomplete` journeys must never receive numeric scores. Unexecuted
journeys and those blocked by setup, access, or action policy remain unscored.
Numeric scores also require actual saved evidence; an eligible status alone
does not justify a score.

`screenshotPage` may only return a view, not a file. If it cannot save to a
path, discover `runPlaywrightCode` and check its actual signature. Where
available, use `page.screenshot({path: <absolute path inside journey folder>,
fullPage: true})` only to persist the genuine capture. Use `readPage` and
native interaction tools for page actions. Verify the PNG is readable before
referencing its journey-relative path.

Browser use is read-only by default. Only exact, named actions in the
project's approved-actions list permit writes. Never persist credentials,
tokens, cookies, or browser profiles. Run one journey at a time, then score
the saved evidence in a separate pass.
