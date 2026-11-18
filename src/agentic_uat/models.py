from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
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
    vpn_required: bool
    vpn_instructions: NonBlank | None
    proxy_required: bool
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
    kind: Literal["navigate", "click", "type", "observe", "wait"]
    description: NonBlank
    outcome: NonBlank
    application_ms: (
        Annotated[StrictFloat | StrictInt, Field(ge=0, allow_inf_nan=False)] | None
    )

    _aware_timestamp = field_validator("timestamp", mode="before")(
        _parse_aware_datetime
    )


class Finding(Model):
    id: Identifier
    severity: Literal["info", "minor", "major", "critical"]
    category: NonBlank
    observation: NonBlank
    recommendation: NonBlank
    evidence: list[Identifier]


class Screenshot(Model):
    id: Identifier
    file: NonBlank
    caption: NonBlank
    action_id: Identifier | None


class JourneyResult(Model):
    schema_version: SchemaVersion = 1
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
        return self


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


class RunManifest(Model):
    schema_version: SchemaVersion = 1
    run_id: Identifier
    created_at: datetime
    project: Project

    _aware_created_at = field_validator("created_at", mode="before")(
        _parse_aware_datetime
    )


@dataclass(frozen=True)
class RunBundle:
    manifest: RunManifest
    results: dict[tuple[str, str], JourneyResult]
    scores: dict[tuple[str, str], Score]
    warnings: list[str]


def _ensure_unique(values: Iterable[str], label: str) -> None:
    sequence = list(values)
    if len(sequence) != len(set(sequence)):
        raise ValueError(f"{label} values must be unique")
