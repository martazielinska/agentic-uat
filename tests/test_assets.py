from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
ASSETS = ROOT / "src" / "agentic_uat" / "assets"
SKILLS = {
    "uat-init": ASSETS / ".github" / "skills" / "uat-init" / "SKILL.md",
    "uat-run": ASSETS / ".github" / "skills" / "uat-run" / "SKILL.md",
}
AGENTS = {
    "uat-coordinator": ASSETS / ".github" / "agents" / "uat-coordinator.agent.md",
    "uat-journey": ASSETS / ".github" / "agents" / "uat-journey.agent.md",
    "uat-scoring": ASSETS / ".github" / "agents" / "uat-scoring.agent.md",
}
CONTRACT = ASSETS / ".github" / "skills" / "references" / "uat-contract.md"
COMMANDS = {"install", "init", "validate", "run", "check", "report", "schema"}
CLI_PREFIX = (
    r"(?:uv\s+run\s+(?:--project\s+\S+\s+)?"
    r"|uv\s+tool\s+run\s+--from\s+\S+\s+)?"
)


def parse_frontmatter(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.DOTALL)
    assert match, f"{path.relative_to(ROOT)} has no YAML frontmatter"
    metadata = yaml.safe_load(match.group(1))
    assert isinstance(metadata, dict)
    return metadata, match.group(2)


def test_packaged_skills_have_discoverable_metadata() -> None:
    for name, path in SKILLS.items():
        metadata, _ = parse_frontmatter(path)
        assert metadata["name"] == name
        assert isinstance(metadata.get("description"), str)
        assert metadata["description"].strip()
        assert "/" not in str(metadata["name"])
        assert ":" not in str(metadata["name"])


def test_packaged_agents_have_copilot_metadata_without_fixed_model() -> None:
    for key, path in AGENTS.items():
        metadata, _ = parse_frontmatter(path)
        assert metadata.get("name")
        assert metadata.get("description")
        assert "model" not in metadata
        assert metadata.get("target") == "github-copilot"
        assert "tools" not in metadata
        if key == "uat-coordinator":
            assert metadata.get("skills") == ["uat-run"]


def test_installed_assets_are_self_contained_github_files() -> None:
    files = sorted(path for path in ASSETS.rglob("*") if path.is_file())
    assert {path for path in files if path in SKILLS.values()} == set(SKILLS.values())
    assert {path for path in files if path in AGENTS.values()} == set(AGENTS.values())
    assert CONTRACT in files
    assert all(path.relative_to(ASSETS).parts[0] == ".github" for path in files)


def test_markdown_references_resolve_inside_packaged_assets() -> None:
    for markdown in ASSETS.rglob("*.md"):
        text = markdown.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("https://", "http://", "#", "mailto:")):
                continue
            relative = target.split("#", 1)[0]
            assert relative, f"Empty link in {markdown.relative_to(ASSETS)}"
            resolved = (markdown.parent / relative).resolve()
            assert resolved.is_relative_to(ASSETS.resolve())
            assert resolved.is_file(), (
                f"Broken link {target!r} in {markdown.relative_to(ASSETS)}"
            )


def test_documented_cli_examples_use_supported_commands() -> None:
    documents = [ROOT / "README.md", *ASSETS.rglob("*.md")]
    for path in documents:
        text = path.read_text(encoding="utf-8")
        examples = re.findall(rf"`{CLI_PREFIX}agentic-uat\s+([a-z][a-z-]*)`", text)
        examples.extend(
            command
            for block in re.findall(r"```[^`]*\n(.*?)```", text, re.DOTALL)
            for line in block.splitlines()
            if (match := re.match(rf"{CLI_PREFIX}agentic-uat\s+([a-z][a-z-]*)", line))
            for command in [match.group(1)]
        )
        for command in examples:
            assert command in COMMANDS, (
                f"Unsupported CLI example in {path.relative_to(ROOT)}: "
                f"agentic-uat {command}"
            )


def test_target_skills_resolve_cli_without_requiring_target_uv_project() -> None:
    for path in SKILLS.values():
        assert "../references/uat-contract.md#cli" in path.read_text(encoding="utf-8")

    contract = CONTRACT.read_text(encoding="utf-8")
    assert "## CLI" in contract
    assert "`agentic-uat --help`" in contract
    normalized = " ".join(contract.lower().split())
    assert "do not run `uv run agentic-uat` from the target workspace" in normalized
    assert "uv tool install /path/to/agentic-uat" in contract
    assert "uv tool run --from /path/to/agentic-uat agentic-uat" in contract
    assert "uv run --project /path/to/agentic-uat agentic-uat" in contract


def test_init_skill_uses_both_durable_memory_files() -> None:
    text = SKILLS["uat-init"].read_text(encoding="utf-8")
    assert ".agentic-uat/project.yaml" in text
    assert ".agentic-uat/context.md" in text
    assert ".agentic-uat/context.yaml" not in text


def test_init_checks_reachability_before_asking_network_questions() -> None:
    init = " ".join(SKILLS["uat-init"].read_text(encoding="utf-8").split())
    contract = " ".join(CONTRACT.read_text(encoding="utf-8").split())
    assert "../references/uat-contract.md#access" in init
    assert init.index("Check access") < init.index("Ask about")
    assert "If the app or its sign-in page loads" in contract
    assert "do not ask about VPN or proxy" in contract
    assert "Ask about VPN/proxy only after an observed connectivity failure" in contract
    assert "do not perform browser actions during intake" not in init.lower()


def test_scoring_agent_and_contract_exclude_incomplete_numeric_scores() -> None:
    for path in (AGENTS["uat-scoring"], CONTRACT):
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert (
            "Only `completed` and `application_blocked` journeys are eligible "
            "for numeric scores."
        ) in text, path
        assert ("`incomplete` journeys must never receive numeric scores.") in text, (
            path
        )


def test_coordinator_hands_cli_to_subagents_and_never_writes_their_artifacts() -> None:
    run = " ".join(SKILLS["uat-run"].read_text(encoding="utf-8").split())
    assert run.count("resolved CLI command") == 2
    coordinator = " ".join(
        AGENTS["uat-coordinator"].read_text(encoding="utf-8").split()
    )
    assert "never create or edit them yourself" in coordinator


def test_uat_uses_subagents_without_creating_copilot_sessions() -> None:
    contract = " ".join(CONTRACT.read_text(encoding="utf-8").split())
    assert "## Orchestration" in contract
    assert "current Copilot chat" in contract
    assert "Do not create extra Copilot sessions or chats" in contract
    assert "`create_session`" in contract
    for path in (SKILLS["uat-run"], AGENTS["uat-coordinator"]):
        assert "#orchestration" in path.read_text(encoding="utf-8")


def test_browser_visibility_is_required_for_journey_handoffs() -> None:
    contract = " ".join(CONTRACT.read_text(encoding="utf-8").split())
    assert "## Browser visibility" in contract
    assert "await page.bringToFront();" in contract
    assert "Keep the active journey tab visible" in contract
    assert "Do not close or hide" in contract
    assert "report the tool limitation" in contract
    for path in (SKILLS["uat-run"], AGENTS["uat-journey"]):
        assert "#browser-visibility" in path.read_text(encoding="utf-8")


def test_viewport_guidance_is_passed_to_journeys() -> None:
    contract = " ".join(CONTRACT.read_text(encoding="utf-8").split())
    assert "ask the owner to enlarge the integrated browser pane" in contract
    assert "do not infer visible coverage from reported dimensions alone" in contract
    assert "do not generalize to device sizes that were not tested" in contract
    for path in (SKILLS["uat-run"], AGENTS["uat-journey"]):
        assert "#viewport-and-display-size" in path.read_text(encoding="utf-8")
    assert "measured viewport sizes" in " ".join(
        SKILLS["uat-run"].read_text(encoding="utf-8").split()
    )


def test_business_terminology_is_clarified_and_passed_to_journeys() -> None:
    init = " ".join(SKILLS["uat-init"].read_text(encoding="utf-8").split())
    run = " ".join(SKILLS["uat-run"].read_text(encoding="utf-8").split())
    journey = " ".join(AGENTS["uat-journey"].read_text(encoding="utf-8").split())
    assert "confirm unresolved meanings rather than guessing" in init
    assert "domain-term meanings and examples" in run
    assert "ask the coordinator to clarify it with the owner; do not guess" in journey


def test_journeys_act_capture_and_time_in_one_browser_call() -> None:
    contract = " ".join(CONTRACT.read_text(encoding="utf-8").split())
    journey = AGENTS["uat-journey"].read_text(encoding="utf-8")
    assert "new Date().toISOString()" in contract
    assert "Never run `date` in a shell, query the session store" in contract
    assert "Do not use `fullPage: true`" in contract
    assert "fullPage: true });" not in contract
    assert "Do not check each file separately" in contract
    for anchor in ("#act-capture-and-time-in-one-call", "#browser-efficiency"):
        assert anchor in journey


def test_scoring_uses_recorded_text_when_screenshots_are_cropped() -> None:
    for path in (AGENTS["uat-scoring"], CONTRACT):
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert "action outcomes" in text, path
        assert "cropped" in text, path


def test_init_explores_then_asks_persona_and_tickbox_action_policy() -> None:
    init = " ".join(SKILLS["uat-init"].read_text(encoding="utf-8").split())
    contract = " ".join(CONTRACT.read_text(encoding="utf-8").split())
    assert init.index("Explore before asking") < init.index("ask about the persona")
    assert "Default to read-only" not in init
    assert "../references/uat-contract.md#action-policy" in init
    assert "multi-select form" in contract
    assert "`All actions in the app`" in contract
    assert "Do not default to read-only when the app writes" in contract
