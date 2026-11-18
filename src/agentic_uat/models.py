from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, get_args
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
NonBlank = Annotated[str, StringConstraints(min_length=1)]
SchemaVersion = Literal[1]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("must not be blank")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and not item.strip():
                    raise ValueError("must not contain blank strings")
        return value


def _safe_http_url(value: AnyHttpUrl | None) -> AnyHttpUrl | None:
    if value is None:
        return None
    parts = urlsplit(str(value))
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("URL must use HTTP or HTTPS and include a host")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URL credentials are not allowed")
    return value


def _parse_aware_datetime(value: object) -> datetime:
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("must be an ISO 8601 timestamp") from exc
    if not isinstance(value, datetime):
        raise TypeError("must be a datetime timestamp")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value


class Access(Model):
    mode: Literal["public", "login"]
    login_instructions: NonBlank | None
    vpn_required: bool = Field(
        description=(
            "Whether additional VPN setup is needed for access on the current "
            "connection. False after observed successful app or sign-in access; "
            "this does not assert that off-network access works."
        )
    )
    vpn_instructions: NonBlank | None
    proxy_required: bool = Field(
        description=(
            "Whether additional proxy setup is needed for access on the current "
            "connection. False after observed successful app or sign-in access; "
            "record the access evidence and untested network policy in context.md."
        )
    )
    proxy_instructions: NonBlank | None
    openapi_url: AnyHttpUrl | None

    _safe_openapi_url = field_validator("openapi_url")(_safe_http_url)

    @model_validator(mode="after")
    def validate_required_instructions(self) -> Access:
        if self.mode == "login" and self.login_instructions is None:
            raise ValueError("login instructions are required for login access")
        if self.vpn_required and self.vpn_instructions is None:
            raise ValueError("VPN instructions are required when VPN is required")
        if self.proxy_required and self.proxy_instructions is None:
            raise ValueError("proxy instructions are required when proxy is required")
        return self


class Journey(Model):
    id: Identifier
    name: NonBlank
    start_url: AnyHttpUrl
    task: NonBlank
    success_criteria: list[NonBlank] = Field(min_length=1)

    _safe_start_url = field_validator("start_url")(_safe_http_url)


class Persona(Model):
    id: Identifier
    name: NonBlank
    role: NonBlank
    description: NonBlank
    goals: list[NonBlank] = Field(min_length=1)
    experience: NonBlank
    permissions: list[NonBlank] = Field(min_length=1)
    journeys: list[Journey] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_journey_ids(self) -> Persona:
        _ensure_unique((journey.id for journey in self.journeys), "journey id")
        return self


class Project(Model):
    schema_version: SchemaVersion = 1
    name: NonBlank
    base_url: AnyHttpUrl
    access: Access
    personas: list[Persona] = Field(min_length=1)
    approved_actions: list[NonBlank] = Field(default_factory=list)

    _safe_base_url = field_validator("base_url")(_safe_http_url)

    @model_validator(mode="after")
    def unique_persona_ids(self) -> Project:
        _ensure_unique((persona.id for persona in self.personas), "persona id")
        return self


class Action(Model):
    id: Identifier
    timestamp: datetime
    kind: Literal["navigate", "click", "type", "observe", "wait"] = Field(
        description=(
            "Record every click as its own `click` action so the evidence "
            "preserves the interaction count."
        )
    )
    description: NonBlank
    outcome: NonBlank
    application_ms: (
        Annotated[StrictFloat | StrictInt, Field(ge=0, allow_inf_nan=False)] | None
    ) = Field(
        description=(
            "Application time actually measured for this action, such as the "
            "interval from the action to the app's ready signal, measured in "
            "the same browser call. Null when not measured; never estimate."
        )
    )

    _aware_timestamp = field_validator("timestamp", mode="before")(
        _parse_aware_datetime
    )


class Finding(Model):
    id: Identifier
    severity: Literal["info", "minor", "major", "critical"]
    category: NonBlank
    observation: NonBlank = Field(
        description="Brief, concrete observation, including expected behavior if known."
    )
    recommendation: NonBlank = Field(description="Concise suggested change.")
    evidence: list[Identifier] = Field(
        description="Supporting action and screenshot ids."
    )
    title: NonBlank | None = Field(
        default=None, description="Short, specific title for the report."
    )
    impact: NonBlank | None = Field(
        default=None, description="Brief effect on the persona's task, when known."
    )
    location: NonBlank | None = Field(
        default=None, description="Screen or control where the finding occurs."
    )


class Screenshot(Model):
    id: Identifier
    file: NonBlank
    caption: NonBlank
    action_id: Identifier | None


Friction = Literal[
    "no_friction", "minor_friction", "major_friction", "blocked", "not_assessed"
]
_BLOCKER_KINDS: dict[str, set[str]] = {
    "application_blocked": {"application"},
    "setup_blocked": {"setup", "access", "tool"},
    "policy_blocked": {"policy"},
}


class UxRating(Model):
    level: Friction = Field(
        description=(
            "Friction observed for this persona. Use not_assessed when the "
            "journey did not give enough evidence."
        )
    )
    notes: NonBlank = Field(
        description="What was observed, or why it was not assessed."
    )
    evidence: list[Identifier] = Field(
        description="Action, screenshot, or finding ids supporting the level."
    )

    @model_validator(mode="after")
    def assessed_needs_evidence(self) -> UxRating:
        if self.level != "not_assessed" and not self.evidence:
            raise ValueError(f"{self.level} rating requires evidence")
        return self


class PerformanceObservation(Model):
    status: Literal["measured", "unavailable"] = Field(
        description=(
            "measured only when cited actions carry application_ms; otherwise "
            "unavailable with the reason in notes."
        )
    )
    notes: NonBlank = Field(
        description="Measurement source and observations, or why none exist."
    )
    evidence: list[Identifier]


class CriterionCheck(Model):
    criterion: NonBlank = Field(
        description="Exact success criterion text from the manifest journey."
    )
    outcome: Literal["met", "not_met", "not_assessed"]
    evidence: list[Identifier]

    @model_validator(mode="after")
    def outcome_needs_evidence(self) -> CriterionCheck:
        if self.outcome != "not_assessed" and not self.evidence:
            raise ValueError(f"criterion outcome {self.outcome} requires evidence")
        return self


class Blocker(Model):
    kind: Literal["application", "setup", "access", "policy", "tool"]
    description: NonBlank
    evidence: list[Identifier]


class UxAssessment(Model):
    ease_of_use: UxRating = Field(
        description="How easily the persona could complete the task."
    )
    intuitiveness: UxRating = Field(
        description="Whether labels, layout, and feedback matched expectations."
    )
    performance: PerformanceObservation
    success_criteria: list[CriterionCheck] = Field(
        min_length=1, description="One entry per manifest success criterion, in order."
    )
    blockers: list[Blocker] = Field(
        description="Anything that stopped the task; empty for completed journeys."
    )

    def evidence_ids(self) -> list[str]:
        ids = [*self.ease_of_use.evidence, *self.intuitiveness.evidence]
        ids += self.performance.evidence
        for check in self.success_criteria:
            ids += check.evidence
        for blocker in self.blockers:
            ids += blocker.evidence
        return ids


class JourneyResult(Model):
    schema_version: Literal[1, 2] = Field(
        default=2,
        description="Write 2. Version 1 is legacy evidence without ux.",
    )
    persona_id: Identifier
    journey_id: Identifier
    status: Literal[
        "completed",
        "application_blocked",
        "setup_blocked",
        "policy_blocked",
        "incomplete",
    ]
    summary: NonBlank
    started_at: datetime
    finished_at: datetime
    timing_notes: NonBlank
    actions: list[Action]
    findings: list[Finding]
    screenshots: list[Screenshot]
    limitations: list[NonBlank]
    ux: UxAssessment | None = Field(
        default=None, description="Required for schema version 2."
    )

    _aware_timestamps = field_validator("started_at", "finished_at", mode="before")(
        _parse_aware_datetime
    )

    @model_validator(mode="after")
    def validate_timeline_and_references(self) -> JourneyResult:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        _ensure_unique((action.id for action in self.actions), "action id")
        _ensure_unique((finding.id for finding in self.findings), "finding id")
        _ensure_unique(
            (screenshot.id for screenshot in self.screenshots), "screenshot id"
        )
        previous = self.started_at
        for action in self.actions:
            if action.timestamp < previous:
                raise ValueError("action timestamps must be ordered")
            if (
                action.timestamp < self.started_at
                or action.timestamp > self.finished_at
            ):
                raise ValueError("action timestamp must be within the journey interval")
            previous = action.timestamp
        action_ids = {action.id for action in self.actions}
        screenshot_ids = {screenshot.id for screenshot in self.screenshots}
        for screenshot in self.screenshots:
            if (
                screenshot.action_id is not None
                and screenshot.action_id not in action_ids
            ):
                raise ValueError(
                    f"unknown screenshot action reference: {screenshot.action_id}"
                )
        for finding in self.findings:
            _ensure_unique(finding.evidence, "finding evidence id")
            unknown = set(finding.evidence) - action_ids - screenshot_ids
            if unknown:
                raise ValueError(
                    f"unknown finding evidence reference: {sorted(unknown)}"
                )
        if self.schema_version >= 2 and self.ux is None:
            raise ValueError("ux assessment is required for schema version 2")
        if self.ux is not None:
            self._validate_ux(self.ux, action_ids | screenshot_ids)
        return self

    def _validate_ux(self, ux: UxAssessment, evidence_ids: set[str]) -> None:
        known = evidence_ids | {finding.id for finding in self.findings}
        unknown = set(ux.evidence_ids()) - known
        if unknown:
            raise ValueError(f"unknown ux evidence reference: {sorted(unknown)}")
        timed = {a.id for a in self.actions if a.application_ms is not None}
        if ux.performance.status == "measured":
            if not timed or not set(ux.performance.evidence) & timed:
                raise ValueError(
                    "measured performance must cite actions with application_ms"
                )
        elif timed:
            raise ValueError(
                "performance must be measured when actions record application_ms"
            )
        outcomes = {check.outcome for check in ux.success_criteria}
        kinds = {blocker.kind for blocker in ux.blockers}
        if self.status == "completed" and (outcomes != {"met"} or kinds):
            raise ValueError(
                "completed status requires every criterion met and no blockers"
            )
        required = _BLOCKER_KINDS.get(self.status)
        if required is not None and not kinds & required:
            raise ValueError(
                f"{self.status} status requires a {'/'.join(sorted(required))} blocker"
            )


class Score(Model):
    schema_version: SchemaVersion = 1
    persona_id: Identifier
    journey_id: Identifier
    score: Annotated[StrictInt, Field(ge=1, le=5)] | None
    rationale: NonBlank
    confidence: Literal["low", "medium", "high"]
    limitations: list[NonBlank]
    evidence: list[Identifier]

    @field_validator("evidence")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        _ensure_unique(value, "score evidence id")
        return value


class ReportSource(Model):
    persona_id: Identifier
    journey_id: Identifier
    finding_id: Identifier


class ReportScreenshot(Model):
    file: NonBlank = Field(description="Run-relative path of a supporting image.")
    caption: NonBlank = Field(description="Describe only what the image shows.")
    captured_at: datetime | None = Field(
        default=None,
        description="Required for a supplemental image under report-evidence/.",
    )

    @field_validator("captured_at", mode="before")
    @classmethod
    def parse_captured_at(cls, value: object) -> datetime | None:
        return None if value is None else _parse_aware_datetime(value)


class ReportFinding(Model):
    title: NonBlank
    observation: NonBlank
    impact: NonBlank | None = None
    location: NonBlank | None = None
    recommendation: NonBlank
    sources: list[ReportSource] = Field(
        min_length=1, description="Recorded findings represented by this report item."
    )
    screenshots: list[ReportScreenshot] = Field(default_factory=list)


class ReportContent(Model):
    schema_version: SchemaVersion = 1
    run_id: Identifier
    scope: NonBlank | None = None
    overview: NonBlank | None = None
    findings: list[ReportFinding]


class RunManifest(Model):
    schema_version: SchemaVersion = 1
    run_id: Identifier
    created_at: datetime
    project: Project

    _aware_created_at = field_validator("created_at", mode="before")(
        _parse_aware_datetime
    )


Capability = Literal[
    "open_page",
    "read_page",
    "interact",
    "capture_screenshot",
    "persist_screenshot",
    "delegate_subagent",
]
CAPABILITIES: tuple[str, ...] = get_args(Capability)


class CapabilityCheck(Model):
    capability: Capability
    available: bool
    evidence: NonBlank = Field(
        description=(
            "Exact tool names seen in the coordinator's own tool inventory, or "
            "what was missing."
        )
    )


class Preflight(Model):
    schema_version: SchemaVersion = 1
    run_id: Identifier
    checked_at: datetime
    status: Literal["ready", "blocked"]
    checks: list[CapabilityCheck] = Field(
        description="Exactly one check for each capability."
    )
    probe_screenshot: NonBlank | None = Field(
        description=(
            "Run-relative path of a screenshot the coordinator saved and read "
            "back. Required when ready."
        )
    )

    _aware_checked_at = field_validator("checked_at", mode="before")(
        _parse_aware_datetime
    )

    @model_validator(mode="after")
    def status_follows_checks(self) -> Preflight:
        seen = [check.capability for check in self.checks]
        _ensure_unique(seen, "capability")
        missing = [name for name in CAPABILITIES if name not in seen]
        if missing:
            raise ValueError(f"missing capability checks: {', '.join(missing)}")
        expected = "ready" if all(c.available for c in self.checks) else "blocked"
        if self.status != expected:
            raise ValueError(f"status must be {expected} for these capability checks")
        if self.status == "ready" and self.probe_screenshot is None:
            raise ValueError("ready preflight requires a saved probe screenshot")
        return self

    def unavailable(self) -> list[str]:
        return [check.capability for check in self.checks if not check.available]


@dataclass(frozen=True)
class RunBundle:
    manifest: RunManifest
    preflight: Preflight | None
    results: dict[tuple[str, str], JourneyResult]
    scores: dict[tuple[str, str], Score]
    warnings: list[str]
    report_content: ReportContent | None


def _ensure_unique(values: Iterable[str], label: str) -> None:
    sequence = list(values)
    if len(sequence) != len(set(sequence)):
        raise ValueError(f"{label} values must be unique")
