# agentic-uat

Copilot-native user acceptance testing with serialized browser journeys,
validated evidence, and offline HTML reports. Copilot operates the browser;
the Python CLI prepares artifacts and renders reports.

## Install

```sh
uv sync
uv tool install .
```

For development from this repository checkout, use `uv run agentic-uat ...`
to invoke the local CLI. The `uv tool install .` command installs it for use
from any workspace.

From a target workspace, install the self-contained `.github` skills and
agents, then create and complete project memory:

```sh
agentic-uat install
agentic-uat init
agentic-uat validate
```

Use `/uat-init` in VS Code Copilot to set up project memory. It first explores
the app and any linked repositories or docs. It then asks focused questions
about each persona's scope, typical tasks, success measures, and any unresolved
business terminology. It validates the draft at the end. Project and evidence
JSON schemas are available on demand:
`agentic-uat schema project`, `manifest`, `preflight`, `journey`, `score`,
or `report`.

Intake checks browser reachability first. When the app or its sign-in page
loads, it skips VPN/proxy questions and records that the current connection
works. Network setup is discussed only after an observed connectivity failure.

The target workspace does not need to be a Python project. If the installed
`agentic-uat` command is unavailable, use a known CLI package path:

```sh
uv tool install /path/to/agentic-uat
uv tool run --from /path/to/agentic-uat agentic-uat validate
uv run --project /path/to/agentic-uat agentic-uat validate
```

Replace the placeholder with the actual package path. Do not use
`uv run agentic-uat` from an arbitrary target workspace.

## Prepare and execute

```sh
agentic-uat run
agentic-uat check PATH/TO/RUN
agentic-uat report PATH/TO/RUN --output ./report.html
```

Replace `PATH/TO/RUN` with the run directory printed by `agentic-uat run`.
`run` only creates a run and Copilot handoff; it does not execute browser UAT.
In VS Code, select the Copilot harness, ensure its native browser and task /
subagent tools are enabled, and use `/uat-run` or **UAT Coordinator**. The
coordinator first records its own browser, screenshot, and delegation tools in
`preflight.json`. If any is missing it renders a blocked report and stops
before dispatching journeys. `check --require-preflight` validates that record
and its probe screenshot; the CLI cannot see VS Code tools itself. Preflight
is only a gate, so the report omits it. A blocked run shows a one-line
reason.

The current Copilot chat coordinates native task subagents; it must not create
extra Copilot sessions or chats. Journeys run sequentially with their active
browser tab visible so you can watch. Agents reuse the shared tab, pass its
page ID and URL at handoff, and leave it open afterward. The coordinator
checks the visible viewport against the intended device size; enlarge the
integrated browser pane when needed. Viewport-specific findings identify the
size tested rather than assuming a narrow pane represents a full desktop.

Each journey records actions (one per click), measured timings or why none
were available, ease-of-use and intuitiveness ratings with evidence, success
criteria, blockers, and screenshots. A separate agent scores the saved
evidence. The HTML report focuses on task outcomes and concise application
findings, with supporting screenshots next to the relevant finding; it does
not include the action log or tool-inclusive timings.

The coordinator can write a run's optional `report-content.json` to combine
duplicate findings and edit the stakeholder-facing prose without changing
the original journey evidence. `agentic-uat schema report` describes the
file. `agentic-uat check` validates its source references and requires
every recorded finding to be represented. Supplemental screenshots belong
in the run's `report-evidence/` directory with their capture time. Without
report content, the HTML uses the original findings. Older journey results
remain supported and are marked when criteria were not assessed.

If intake finds write actions, it lists them in a tickbox form with an
`All actions in the app` option. Journeys perform only the approved actions.
An app with no write actions is browsed read-only.
Never store credentials, tokens, cookies, or browser profiles.