---
name: uat-init
description: Use when setting up UAT for a new application or updating its business context, access, personas, journeys, or action policy.
argument-hint: "[application, business-context path, or memory update]"
---

# Initialize UAT project memory

Use this skill to turn an application owner's answers into validated project
memory. Explore first, then ask. Do not ask what the app, its repositories,
or its docs already answer, and do not guess what they cannot.

1. Resolve the CLI ([contract: CLI](../references/uat-contract.md#cli)) and
   run `agentic-uat init`. It creates `.agentic-uat/project.yaml`,
   `.agentic-uat/context.md`, and the `.agentic-uat/business-context/`
   folder, but does not interview anyone.
2. Read both `.agentic-uat/project.yaml` and `.agentic-uat/context.md`.
   Preserve useful existing, non-secret notes in the context file.
3. Get the full current project schema with `agentic-uat schema project`.
   Use that schema when editing `project.yaml`; do not recreate or abbreviate
   its field definitions. Keep versioned project data in
   `.agentic-uat/project.yaml` and application terminology or non-secret
   interview notes in `.agentic-uat/context.md`.
4. Read the business context
   ([contract: Business context](../references/uat-contract.md#business-context)):
   every file in `.agentic-uat/business-context/`, each `context_sources`
   path, and any file or folder the owner named in the request. Add named
   paths to `context_sources`.
5. Check access using [contract: Access](../references/uat-contract.md#access).
   Reuse a shared application page when available. Resolve reachability from
   browser evidence before asking the owner network questions. If sign-in is
   needed, ask the owner to complete it in the shared browser.
6. Explore before asking. Do not change data while exploring, and do not
   trigger downloads or exports
   ([contract: Downloads](../references/uat-contract.md#downloads)).
   - Click through the app's navigation as the named persona. Note the
     workflow steps, terminology, scope selectors and their options (such as
     markets, categories, or channels), existing drafts or records, and any
     constraint messages, disabled controls, or placeholders.
   - Read the repositories, docs, and links the owner supplied. Use READMEs,
     routes, and API specs to find the OpenAPI URL, roles, workflow rules,
     and every state-changing action.
   - If the workspace is the application repository, or the owner supplied
     one, inspect it for development status and deliberate decisions under
     [contract: Codebase inspection](../references/uat-contract.md#codebase-inspection).
   - Write findings to `context.md` before asking anything.
7. Draft personas and journeys from the owner's description and what you
   found. Then resolve the business context in one round of grouped
   `ask_user` forms, grounded in that evidence, offering the options you
   observed. First ask about the persona:
   - which scope to test, such as country, category, or channel, and whether
     to reuse an existing record or create a new one;
   - what the persona does first and next in a typical session, and what they
     must not change;
   - how they judge success, including thresholds and domain rules, so that
     success criteria are observable;
   - the meaning and examples of domain terms that affect decisions or
     success; confirm unresolved meanings rather than guessing;
   - their experience with the app and the domain;
   - personas that are named but not available yet, so they are left out.
   Also ask every open business-context question: whether each feature a
   journey touches is available, in development, planned, or out of scope;
   whether surprising behavior you observed is deliberate; and what the data
   represents. Confirm or correct the drafted journeys in the same round.
   Drop or rewrite journeys that depend on features that are not available.
8. Record each question and its answer in `clarifications`, feature
   availability in `feature_status`, and deliberate behavior in
   `design_decisions`. Do not continue while any question is unanswered;
   `agentic-uat validate` fails on `answer: null`. If the owner does not
   know, record that and how UAT should treat it. Record
   `clarifications: []` only when nothing remained unclear.
9. Set the action policy with one tickbox form, following
   [contract: Action policy](../references/uat-contract.md#action-policy).
   Do not default to read-only when the app has write actions.
10. Ask about anything still missing: the application name, a
    non-secret login procedure and role requirements (never a password or
    token), VPN/proxy setup only after a connectivity failure, and the
    OpenAPI URL only if exploration did not find one. Do not guess a URL.
11. Continue until every required schema field has an answer or observed
    evidence. `access.mode` must match the observed public/login flow.
    Set network fields from the access check, not an unconditional interview.
    For nullable fields, store explicit `null` only when appropriate: no
    login procedure for public access, no VPN/proxy instructions when that
    service is not required, or no known OpenAPI URL. Do not omit required
    keys. Never store credentials, tokens, cookies, or browser profiles.
12. Edit `.agentic-uat/project.yaml` and append or update relevant notes in
    `.agentic-uat/context.md` without replacing unrelated context. Run
    `agentic-uat validate`. If validation reports missing or invalid values,
    ask for the correction and validate again. Do not describe the memory
    as ready until validation succeeds.

If the owner cannot answer a required question, leave the draft incomplete,
explain what is missing, and stop. Do not invent application details. Intake
allows exploration that changes no data, read-only code inspection, and
user-assisted login. It does not run journeys or perform application writes.
