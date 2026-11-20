# agentic-uat

Copilot-native user acceptance testing for web applications. Copilot runs
browser journeys and collects evidence; the CLI validates artifacts and
generates a self-contained HTML report.

## Install

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/),
Git, Python 3.10 or later, and VS Code with Copilot.

```sh
uv tool install 'git+https://github.com/martazielinska/agentic-uat.git'
```

If `agentic-uat` is not on your PATH, run `uv tool update-shell` and restart
your terminal.

In the root of the workspace you want to test, install the Copilot skills and
agents:

```sh
agentic-uat install
```

The target workspace does not need to be a Python project. Installation
preserves existing instructions and reports conflicting asset files instead
of overwriting them.

## Run UAT

1. Open the target workspace in VS Code and use `/uat-init` in Copilot chat.
   It explores the application, asks about personas and journeys, and creates
   and validates project memory.
2. Use `/uat-run` or **UAT Coordinator** in the same chat. Enable Copilot's
   browser, screenshot, and native task/subagent tools. Journeys run
   sequentially with the browser visible, and the report is written to
   `.agentic-uat/runs/<run-id>/report.html`.

The CLI command `agentic-uat run` only prepares a run; it does not execute
browser UAT. Use `agentic-uat --help` for other commands. Approve any
state-changing actions during intake; never store credentials, tokens,
cookies, or browser profiles.
