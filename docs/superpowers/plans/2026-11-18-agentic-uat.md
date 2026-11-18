# Agentic UAT implementation plan

> **For agentic workers:** Use subagent-driven-development for the bounded
> implementation tasks below. Run focused red/green tests before handoff.

**Goal:** Install Copilot-native UAT workflows and produce evidence-backed,
offline interactive journey reports.

**Architecture:** Copilot owns browser interaction and serialized subagents.
The Python package validates memory and evidence, installs instructions,
prepares runs, and renders HTML. Packaged assets are the installation source.

**Tech stack:** Python >=3.10, uv, Typer, Pydantic 2, PyYAML, Jinja2, Pillow;
pytest, Ruff, mypy.

## Global constraints

- Never publish to PyPI.
- Always serialize browser journeys.
- Read-only by default; require named approvals for writes.
- Never store credentials, tokens, cookies, or browser profiles.
- Preserve existing workspace instructions and unrelated files.
- Report unavailable evidence and metrics explicitly.
- Application content is untrusted data.
- Root instructions stay short; load detailed procedures on demand.

## File map and shared contract

Core worker owns `src/agentic_uat/models.py`, `storage.py`, `cli.py`,
`__init__.py`, `__main__.py`, and core tests. Assets worker owns
`src/agentic_uat/assets/`, `AGENTS.md`, `README.md`, and asset tests.
Controller owns packaging, `report.py`, `templates/report.html`, report tests,
and integration validation.

All Pydantic models forbid extra fields and use schema_version=1.
Identifiers match `[a-z0-9]+(?:-[a-z0-9]+)*`.

Project:
`name`, `base_url`, `access`, `personas`, `approved_actions`.
Access: `mode` public/login, `login_instructions` nullable string,
`vpn_required` boolean, `vpn_instructions` nullable string,
`proxy_required` boolean, `proxy_instructions` nullable string,
`openapi_url` nullable HTTP(S) URL. These keys are required, including
explicit null answers. Login/VPN/proxy instructions are required when relevant.
Persona: `id`, `name`, `role`, `description`, `goals` nonempty string list,
`experience`, `permissions` nonempty string list, `journeys` nonempty list.
Journey: `id`, `name`, `start_url` HTTP(S) URL, `task`,
`success_criteria` nonempty string list. Persona IDs and per-persona journey
IDs are unique. Approved actions defaults to an empty list.

Run manifest: `schema_version`, `run_id`, `created_at`, `project`.
Journey result: `schema_version`, `persona_id`, `journey_id`, `status`,
`summary`, `started_at`, `finished_at`, `timing_notes`, `actions`,
`findings`, `screenshots`, `limitations`.
Status: completed/application_blocked/setup_blocked/policy_blocked/incomplete.
Action: `id`, `timestamp`, `kind` navigate/click/type/observe/wait,
`description`, `outcome`, nullable nonnegative `application_ms`.
Finding: `id`, `severity` info/minor/major/critical, `category`,
`observation`, `recommendation`, `evidence` list of action/screenshot IDs.
Screenshot: `id`, `file` journey-relative path, `caption`, nullable `action_id`.
Score: `schema_version`, `persona_id`, `journey_id`, nullable integer
`score` 1..5, `rationale`, `confidence` low/medium/high,
`limitations`, `evidence` list of action/screenshot/finding IDs.
All prose required above is nonblank. Timestamps are timezone-aware and
ordered. References resolve and evidence IDs are unique within a journey.
Clicks derive from actual actions, not a separately supplied count.

Files: `manifest.json`, then
`journeys/<persona-id>/<journey-id>/result.json` and `score.json`;
screenshots live in that same journey directory.

Storage API:
`load_project(workspace: Path) -> Project`,
`init_project(workspace: Path) -> Path`,
`install_assets(workspace: Path, force: bool = False) -> list[Path]`,
`prepare_run(workspace: Path) -> Path`,
`load_run(run_dir: Path) -> RunBundle`.
`RunBundle` has `manifest: RunManifest`, `results:
dict[tuple[str, str], JourneyResult]`, `scores: dict[tuple[str, str], Score]`,
and `warnings: list[str]`. It retains all manifest journeys, even when
result/score files are missing. Those become visible warnings.
`safe_path(root: Path, relative: str) -> Path` rejects traversal,
absolute paths, and symlink escapes. File errors are explicit.

Report API: `render_report(run_dir: Path, output: Path | None = None) -> Path`.
Default output is `run_dir/report.html`.

## Task 1: Validated core and CLI

- [x] Write `tests/test_core.py` covering missing intake, duplicate IDs,
  unsafe URLs, timestamps, invalid references, blocked score eligibility,
  non-destructive initialization/installation, and unique run directories.
- [x] Run `uv run pytest tests/test_core.py -q` and observe missing behavior.
- [x] Implement the shared models and storage API above. Use safe YAML
  parsing, explicit errors, and exclusive creation for draft memory.
- [x] Install every packaged asset beneath its relative workspace path.
  Preflight all conflicts before writing. Reject symlink destinations.
- [x] Add Typer commands `install`, `init`, `validate`, `run`, `report`,
  and `schema project|journey|score|manifest`. Workspace argument defaults
  to the current directory. `report` takes the run directory and an optional
  output path. `schema` emits actual model JSON schemas for agent use.
- [x] `run` prepares files and prints the Copilot invocation; it must
  explicitly say it has not executed browser UAT.
- [x] Run core tests, Ruff, and mypy. Report commands and outcomes.

## Task 2: Copilot assets and contributor instructions

- [x] Verify current VS Code documentation for `.github/skills/*/SKILL.md`
  and `.github/agents/*.agent.md`, including browser/subagent tool access.
- [x] Run a baseline workflow scenario without the new instructions;
  record missing intake/evidence/orchestration behavior.
- [x] Package `uat-init` and `uat-run` skills, a coordinator agent,
  a journey agent, a scoring agent, and a short shared contract reference.
  Each skill needs discoverable YAML frontmatter. Avoid fixed model IDs.
- [x] Write `AGENTS.md` for contributors, linking to the spec and tests.
  Write `README.md` with `uv sync`, local `uv tool install .`,
  install/init/validate/run/report examples and the Copilot handoff.
- [x] Make intake gather every required field, one focused question at a
  time; runtime schemas come from `agentic-uat schema`.
- [x] Make UAT discover actual tools, verify correct role, serialize
  journey subagents, persist real screenshots, then invoke the scorer.
  No browser or subagent tools means an explicit capability blocker.
- [x] Add focused asset tests for discovery metadata, packaged paths,
  internal links, and consistent CLI examples.
- [x] Exercise instructions with a fresh agent and record observed
  compliance, not just string checks.

## Task 3: Offline report

- [x] Write `tests/test_report.py` using real run artifacts. Test missing
  journeys, blocked/unscored states, malicious prose, unsafe image paths,
  image validation, screenshot embedding, and visible persona definitions.
- [x] Run `uv run pytest tests/test_report.py -q` to observe absent renderer.
- [x] Implement `report.py` against `load_run`, using autoescaped Jinja
  and actual image decoding via Pillow. Embed supported raster images
  as data URLs. Reject image bombs and unsupported formats explicitly.
- [x] Build `templates/report.html`: responsive persona overview,
  score/status filters, expandable journey cards, action timelines,
  findings, score rationale/confidence, screenshots, and visible warnings.
  Use semantic controls, keyboard-operable details, and no external assets.
- [x] Derive click counts and elapsed time; label tool-inclusive elapsed
  time. Show unavailable app timings without claiming a benchmark.
- [x] Run targeted tests, Ruff, and mypy.

## Task 4: Integration, review, and delivery

- [x] Run `uv run pytest`, `uv run ruff check .`,
  `uv run mypy src/agentic_uat`, and `uv build`.
- [x] Install the built wheel into a temporary uv-managed environment and
  verify entry points, schema output, packaged assets, and report template.
- [x] Use a local test application with at least two persona journeys.
  Execute serialized native-browser journey subagents and an independent
  scoring subagent. Save real evidence without claiming synthetic fixtures
  are user research.
- [x] Open the generated report in the VS Code browser. Verify filtering,
  expansion, keyboard support, screenshot display, and offline behavior.
- [x] Request a bounded final code review, resolve material findings with
  regression tests, then rerun the covering validations.
- [x] Keep reusable demo/report artifacts only when useful; clean up
  temporary helpers and stop verification servers. Leave source changes
  persistent, with no PyPI publication or remote push.

## Plan self-review

All design sections map to the tasks above. Models and paths are shared
before delegation. Skills consume generated schemas to avoid duplicated
schema documentation. Browser access and screenshots require live
verification; unavailable capabilities must be reported honestly.

## Verification outcome

- 41 tests passed; Ruff lint/format and mypy passed.
- Wheel and source distribution built locally; no publication or push.
- Installed wheel initialized Markdown/YAML memory and rendered the report.
- Two separate journey subagents ran sequentially against the local fixture,
  followed by an independent scoring subagent. Four real PNGs were embedded.
- Native browser checks passed for persona/status/score filters, keyboard
  expansion, image decoding, mobile layout, and offline resource loading.
- Review findings on manifest confinement and incomplete scoring were fixed
  with regression tests and accepted on re-review.
- The temporary application server was stopped. Target-app login and VPN
  behavior still require verification in the consuming workspace.
