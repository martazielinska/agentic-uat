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

Use `/uat-init` in VS Code Copilot to interview for missing information and
validate the draft. Project and evidence JSON schemas are available on demand:
`agentic-uat schema project`, `manifest`, `journey`, or `score`.

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
agentic-uat report PATH/TO/RUN --output ./report.html
```

Replace `PATH/TO/RUN` with the run directory printed by `agentic-uat run`.
`run` only creates a run and Copilot handoff; it does not execute browser UAT.
In VS Code, select the Copilot harness, ensure its native browser and task /
subagent tools are enabled, and use `/uat-run` or **UAT Coordinator**. The
coordinator checks live tool availability and screenshot persistence, then
runs one journey at a time and scores saved evidence separately. Missing
browser, delegation, or evidence-saving capability is reported as a blocker.

Journeys are read-only unless an exact write action is named and approved.
Never store credentials, tokens, cookies, or browser profiles.