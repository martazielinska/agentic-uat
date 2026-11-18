---
name: uat-init
description: Use when setting up UAT for a new application or updating its access, personas, journeys, or action policy.
argument-hint: "[application or memory update]"
---

# Initialize UAT project memory

Use this skill to turn an application owner's answers into validated project
memory. Ask one focused question at a time. Do not guess missing answers.

1. Resolve the CLI using the [shared contract](../references/uat-contract.md).
   Try `agentic-uat --help`; when it works, use the installed command from
   any workspace. If it is unavailable, do not run `uv run agentic-uat` from
   the target workspace. Give the owner the documented install/run options;
   if the package path is unknown, stop and ask them to install the CLI or
   provide its package path. Use the resolved invocation for every command
   below; for one-off use, prefix each `agentic-uat <command>` with the
   selected `uv tool run --from ... agentic-uat` or
   `uv run --project ... agentic-uat`. Run `agentic-uat init` to create both
   `.agentic-uat/project.yaml` and `.agentic-uat/context.md`. It does not
   complete the interview.
2. Read both `.agentic-uat/project.yaml` and `.agentic-uat/context.md`.
   Preserve useful existing, non-secret notes in the context file and ask
   only about missing or unclear fields.
3. Get the full current project schema with `agentic-uat schema project`.
   Use that schema when editing `project.yaml`; do not recreate or abbreviate
   its field definitions. Keep versioned project data in
   `.agentic-uat/project.yaml` and application terminology or non-secret
   interview notes in `.agentic-uat/context.md`.
4. Ask about:
   - Application name and HTTP(S) base URL.
   - Public access or login. For login, ask for a non-secret login procedure
     and any account role requirements; never request a password or token.
   - Whether VPN and proxy access are required. Record an explicit yes/no for
     each; collect instructions only when required. Never record secret proxy
     URLs.
   - A known OpenAPI documentation URL, or an explicit answer that none is
     known. Do not guess a URL.
   - Each persona's name, role, description of how they use the app, at least
     one goal, experience, at least one permission, and at least one journey.
     A journey needs a name, HTTP(S) start URL, task, and observable success
     criteria.
   - The action policy. Default to read-only. Add writes only when the owner
     names and explicitly approves each action.
5. Continue until every required schema field has an answer. `access.mode`,
   `vpn_required`, and `proxy_required` need explicit values; never turn an
   unknown answer into `public`, `false`, or another guess. For nullable
   fields, store explicit `null` only when appropriate: no login procedure
   for public access, no VPN/proxy instructions when that service is not
   required, or no known OpenAPI URL. Do not omit required keys. Keep one
   question per turn, including when asking for clarifications. Never store
   credentials, tokens, cookies, or browser profiles.
6. Edit `.agentic-uat/project.yaml` and append or update relevant notes in
   `.agentic-uat/context.md` without replacing unrelated context. Run
   `agentic-uat validate`. If validation reports missing or invalid values,
   ask for the next correction and validate again. Do not describe the memory
   as ready until validation succeeds.

If the owner cannot answer a required question, leave the draft incomplete,
explain what is missing, and stop. Do not invent application details or
perform browser actions during intake.
