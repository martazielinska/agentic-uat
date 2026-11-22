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

1. Optionally add business context first (see below).
2. Open the target workspace in VS Code and use `/uat-init` in Copilot chat.
   It reads the business context, explores the application, inspects the
   application code when available, asks about anything still unclear, and
   creates and validates project memory.
3. Use `/uat-run` or **UAT Coordinator** in the same chat. Enable Copilot's
   browser, screenshot, and native task/subagent tools. Journeys run
   sequentially with the browser visible, and the report is written to
   `.agentic-uat/runs/<run-id>/report.html`.

The CLI command `agentic-uat run` only prepares a run; it does not execute
browser UAT. Use `agentic-uat --help` for other commands. Approve any
state-changing actions during intake; never store credentials, tokens,
cookies, or browser profiles.

Journeys never use the browser's native downloads, so no save prompts appear
and nothing is written to your Downloads folder. Files the app exports are
captured in the page and, when they are evidence, saved under
`.agentic-uat/runs/<run-id>/journeys/<persona>/<journey>/outputs/`.

## Business context

Give Copilot what your users know but an agent cannot infer from the
screens. Put non-secret files in `.agentic-uat/business-context/`, which
`agentic-uat init` creates with a short guide. Any format Copilot can read
works, such as Markdown, text, Word, or PDF. Useful content includes:

- the business process, user roles, and domain terms, codes, or
  abbreviations with examples;
- targets, thresholds, and rules users apply to judge success;
- feature availability: available, in development, planned, or out of
  scope;
- deliberate design decisions that may look like defects;
- test data, scopes, or records to use or avoid.

To use files or folders elsewhere, name them when you start `/uat-init`
(for example, `/uat-init docs/product/`) or list them under
`context_sources` in `.agentic-uat/project.yaml`. Paths are relative to the
workspace or absolute, and `agentic-uat validate` checks that they exist.

After reading the context and exploring the app, `/uat-init` asks about
anything still unclear. It records the answers in `project.yaml` as
`clarifications`, `feature_status`, and `design_decisions`. UAT cannot
start while any question is unanswered: `agentic-uat validate` and
`agentic-uat run` fail. Features that are not available are not evaluated.
Findings that contradict a confirmed design decision are left out of the
report.

When Copilot runs from the application repository, or you supply one, it
may read the code to check development status and deliberate choices, and
asks you when the code is ambiguous. Code never guides how journeys use
the app; journeys work only from what the UI shows.

Project memory created before business-context intake (schema version 1)
must be updated with `/uat-init` before the next run.
