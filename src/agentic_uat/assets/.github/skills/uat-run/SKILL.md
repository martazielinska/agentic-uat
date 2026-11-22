---
name: uat-run
description: Use when asked to inspect application journeys, collect findings, or score an existing agentic-uat project with Copilot in VS Code.
argument-hint: "[project or run path]"
---

# Run UAT

You coordinate. The CLI writes and validates files; Copilot's browser tools
do the journeys. Rules referenced below live in the
[artifact contract](../references/uat-contract.md).
Remain in the current chat and follow
[Orchestration](../references/uat-contract.md#orchestration); do not launch
another coordinator session or chat.

## Prepare

1. Resolve the CLI ([contract: CLI](../references/uat-contract.md#cli)).
2. Read `.agentic-uat/project.yaml`, `.agentic-uat/context.md`, and the
   [business context](../references/uat-contract.md#business-context). Run
   `agentic-uat validate`. If intake is incomplete or the project memory is
   legacy schema version 1, stop and use `/uat-init`.
3. Business-context gate: before starting, check each journey's task,
   terms, and success criteria against the context, `feature_status`,
   `design_decisions`, and `clarifications`. If something a user would know
   is still unclear to you, ask the owner with `ask_user`, record the
   answer in `project.yaml`, and validate again. Do not start a run with an
   open question or a journey that depends on an unavailable feature.
4. Run `agentic-uat run`. It prints the run directory, creates
   `manifest.json`, and creates each journey folder. It does not open a
   browser.

## Preflight gate

5. List your own tools. Fill `preflight.json` using
   `agentic-uat schema preflight`
   ([contract: Preflight](../references/uat-contract.md#preflight)).
6. If any capability is missing, write `status: blocked`, run
   `agentic-uat check RUN` and `agentic-uat report RUN`, report the missing
   capability, and stop. Do not invoke `UAT Journey` or `UAT Scoring`.
7. Otherwise reveal the application tab
   ([Browser visibility](../references/uat-contract.md#browser-visibility)),
   save the probe screenshot and check
   [Viewport and display size](../references/uat-contract.md#viewport-and-display-size).
   Write `status: ready`, and run
   `agentic-uat check RUN --require-preflight`. Continue only if it passes.

## Journeys

8. For each manifest journey, in order, invoke one `UAT Journey` subagent
   with Copilot's native task tool. Pass a compact brief so it does not
   rediscover what you know:
   - the resolved CLI command, the run path, and the exact `result.json` path
     and journey folder;
   - the persona and journey from the manifest, and `approved_actions`
     verbatim;
   - access notes, domain-term meanings and examples, plus known scope, data,
     and working selectors from `context.md` and earlier journeys' handoffs;
   - features that are not available and design decisions, so that they
     are not reported as defects;
   - the intended and measured viewport sizes and any visible surface
     limitation;
   - the current browser page ID and URL.

   Brief only what the persona could know or what was observed in the
   browser. Never pass routes, selectors, API calls, or behavior taken from
   source code
   ([contract: Codebase inspection](../references/uat-contract.md#codebase-inspection)).
   Require browser visibility throughout each journey. Never run journeys in
   parallel.
9. When it returns, run `agentic-uat check RUN`. Fix or report errors before
   the next journey. Add reusable scope, data, or selector facts from its
   handoff to `context.md` and to the next brief. If it returns a business
   question, ask the owner before the next journey.

## Finding review, scoring, and report

10. Review every recorded finding under
    [contract: Finding review](../references/uat-contract.md#finding-review)
    before scoring. Ask the owner when it is unclear whether behavior is
    deliberate or still in development.
11. Invoke one `UAT Scoring` subagent with the resolved CLI command, the run
    path, and the findings excluded in review with their basis. It reads
    saved evidence only.
12. Create `report-content.json` using `agentic-uat schema report` and the
    [stakeholder report contract](../references/uat-contract.md#stakeholder-report).
    Consolidate duplicate issues, keep each observation, impact and
    recommendation brief, and cite all underlying findings. List each
    excluded finding in `excluded`. Attach only screenshots that visibly
    support the item. Do not edit journey or score artifacts. Run
    `agentic-uat check RUN`, then `agentic-uat report RUN`.
    The report leaves out preflight; preflight is only a gate.
13. Report which journeys ran, their scores, application defects, findings
    excluded as by design or not yet available, and any setup, access,
    policy, or tool blockers. Name artifacts that could not be saved.
