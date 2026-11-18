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
2. Read `.agentic-uat/project.yaml` and `.agentic-uat/context.md`. Run
   `agentic-uat validate`. If intake is incomplete, stop and use `/uat-init`.
3. Run `agentic-uat run`. It prints the run directory and creates
   `manifest.json`. It does not open a browser.

## Preflight gate

4. List your own tools. Fill `preflight.json` using
   `agentic-uat schema preflight`
   ([contract: Preflight](../references/uat-contract.md#preflight)).
5. If any capability is missing, write `status: blocked`, run
   `agentic-uat check RUN` and `agentic-uat report RUN`, report the missing
   capability, and stop. Do not invoke `UAT Journey` or `UAT Scoring`.
6. Otherwise reveal the application tab
   ([Browser visibility](../references/uat-contract.md#browser-visibility)),
   save the probe screenshot and check
   [Viewport and display size](../references/uat-contract.md#viewport-and-display-size).
   Write `status: ready`, and run
   `agentic-uat check RUN --require-preflight`. Continue only if it passes.

## Journeys

7. For each manifest journey, in order, invoke one `UAT Journey` subagent
   with Copilot's native task tool. Pass a compact brief so it does not
   rediscover what you know:
   - the resolved CLI command, the run path, and the exact `result.json` path
     and journey folder;
   - the persona and journey from the manifest, and `approved_actions`
     verbatim;
   - access notes, domain-term meanings and examples, plus known scope, data,
     and working selectors from `context.md` and earlier journeys' handoffs;
   - the intended and measured viewport sizes and any visible surface
     limitation;
   - the current browser page ID and URL.

   Require browser visibility throughout each journey. Never run journeys in
   parallel.
8. When it returns, run `agentic-uat check RUN`. Fix or report errors before
   the next journey. Add reusable scope, data, or selector facts from its
   handoff to `context.md` and to the next brief.

## Scoring and report

9. Invoke one `UAT Scoring` subagent with the resolved CLI command and the
   run path. It reads saved evidence only.
10. Create `report-content.json` using `agentic-uat schema report` and the
    [stakeholder report contract](../references/uat-contract.md#stakeholder-report).
    Consolidate duplicate issues, keep each observation, impact and
    recommendation brief, and cite all underlying findings. Attach only
    screenshots that visibly support the item. Do not edit journey or score
    artifacts. Run `agentic-uat check RUN`, then `agentic-uat report RUN`.
    The report leaves out preflight; preflight is only a gate.
11. Report which journeys ran, their scores, application defects, and any
    setup, access, policy, or tool blockers. Name artifacts that could not be
    saved.
