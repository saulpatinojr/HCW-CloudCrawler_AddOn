"""The architecture decision a visitor brings, checked and turned into the engine's `DecisionRecord`.

The shape is the App's `DecisionInput` (the `adr_create` tool), so a decision file written for the App uploads
here unchanged, with limits added: every string, list and mapping has a size, a claim's values are plain scalars
(a list or an object inside a comparison is how an unhashable value would reach the engine's set arithmetic), and a
glob may not hold more than a few wildcards. A decision is always recorded as a draft; accepting one is a person's
act, upstream, and never happens in the lab.

Refusals are content-free: they name a claim by its position and a reason from a fixed list, never by what the
visitor wrote, because the engine's own messages quote the offending value.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from cloud_crawler_core.detectors import DETECTORS, get_detector
from cloud_crawler_core.ids import new_id
from cloud_crawler_core.models import (
    Alternative,
    Claim,
    DecisionRecord,
    DecisionScope,
    DecisionStatus,
    EvidenceRequirement,
    Expectation,
    Operator,
    Selector,
    Severity,
    SourceProvenance,
    SourceType,
)
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from cloud_crawler_lab.errors import ApiError

MAX_CLAIMS = 20
MAX_WILDCARDS = 8

Short = Annotated[str, StringConstraints(max_length=256)]
Line = Annotated[str, StringConstraints(max_length=500)]
Paragraph = Annotated[str, StringConstraints(max_length=4000)]
Name = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Scalar = Short | int | float | bool | None
Lines = Annotated[list[Line], Field(max_length=20, default_factory=list)]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectationInput(StrictInput):
    property: Name
    operator: Operator
    value: Scalar | Annotated[list[Scalar], Field(max_length=100)] = None


class SelectorInput(StrictInput):
    resourceTypes: Annotated[list[Name], Field(max_length=30)] = Field(default_factory=list)
    tagSelectors: Annotated[dict[Name, Short], Field(max_length=10)] = Field(default_factory=dict)
    nameGlobs: Annotated[list[Name], Field(max_length=10)] = Field(default_factory=list)
    subscriptionIds: Annotated[list[Name], Field(max_length=20)] = Field(default_factory=list)

    @field_validator("nameGlobs")
    @classmethod
    def _few_wildcards(cls, globs: list[str]) -> list[str]:
        if any(glob.count("*") > MAX_WILDCARDS for glob in globs):
            raise ValueError("too many wildcards")
        return globs


class ClaimInput(StrictInput):
    statement: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    detectorId: Name
    expectation: ExpectationInput
    parameters: Annotated[dict[Name, Scalar], Field(max_length=10)] = Field(default_factory=dict)
    selector: SelectorInput = Field(default_factory=SelectorInput)
    severity: Severity = Severity.HIGH
    required: bool = True
    maxAgeHours: int = Field(default=24, ge=1, le=8760)


class AlternativeInput(StrictInput):
    alternativeId: Name
    title: Line
    description: Paragraph = ""
    pros: Annotated[list[Line], Field(max_length=10)] = Field(default_factory=list)
    cons: Annotated[list[Line], Field(max_length=10)] = Field(default_factory=list)
    selected: bool = False
    rejectionReason: Line | None = None


class ScopeInput(StrictInput):
    tenantId: Name | None = None
    subscriptionIds: Annotated[list[Name], Field(max_length=20)] = Field(default_factory=list)
    resourceGroupNames: Annotated[list[Name], Field(max_length=20)] = Field(default_factory=list)
    tagSelectors: Annotated[dict[Name, Short], Field(max_length=10)] = Field(default_factory=dict)


class DecisionInput(StrictInput):
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    context: Paragraph = ""
    decision: Paragraph = ""
    decisionDrivers: Lines
    consequences: Lines
    constraints: Lines
    assumptions: Lines
    risks: Lines
    openQuestions: Lines
    alternatives: Annotated[list[AlternativeInput], Field(max_length=10)] = Field(default_factory=list)
    claims: Annotated[list[ClaimInput], Field(min_length=1, max_length=MAX_CLAIMS)]
    scope: ScopeInput = Field(default_factory=ScopeInput)
    status: Literal[DecisionStatus.DRAFT, DecisionStatus.PROPOSED] = DecisionStatus.DRAFT
    sourceType: SourceType = SourceType.HUMAN


def _invalid(index: int, reason: str, **more: Any) -> ApiError:
    return ApiError(
        422,
        "invalid_decision",
        "A claim in the decision cannot be evaluated.",
        {"claimIndex": index, "reason": reason, **more},
    )


def build_decision(item: DecisionInput, *, now: datetime) -> DecisionRecord:
    """The draft decision record, claim by claim, each claim proved evaluable by its own detector (as `adr_create`)."""
    decision_id = new_id("decision")
    claims: list[Claim] = []
    requirements: list[EvidenceRequirement] = []
    for index, entry in enumerate(item.claims):
        claim = Claim(
            claimId=new_id("claim"),
            decisionId=decision_id,
            statement=entry.statement,
            detectorId=entry.detectorId,
            # a null parameter is an absent one (the engine would otherwise try `int(None)` on `minimumZones`)
            parameters={name: value for name, value in entry.parameters.items() if value is not None},
            selector=Selector(**entry.selector.model_dump()),
            severity=entry.severity,
            required=entry.required,
            expectation=Expectation(
                property=entry.expectation.property,
                operator=entry.expectation.operator,
                value=entry.expectation.value,
            ),
        )
        try:
            detector = get_detector(claim.detectorId)
        except KeyError:
            raise _invalid(index, "unknown_detector", knownDetectors=sorted(DETECTORS)) from None
        try:
            detector.validate_claim(claim)
        except ValueError:
            # The engine's message quotes the claim's own values; only the detector (a name from our list) is repeated.
            raise _invalid(index, "claim_not_evaluable", detectorId=claim.detectorId) from None
        claims.append(claim)
        requirements.append(EvidenceRequirement(claimId=claim.claimId, maxAgeHours=entry.maxAgeHours))
    return DecisionRecord(
        decisionId=decision_id,
        status=item.status,
        title=item.title,
        context=item.context,
        decisionDrivers=item.decisionDrivers,
        decision=item.decision,
        consequences=item.consequences,
        openQuestions=item.openQuestions,
        constraints=item.constraints,
        assumptions=item.assumptions,
        risks=item.risks,
        alternatives=[Alternative(**alt.model_dump()) for alt in item.alternatives],
        claims=claims,
        scope=DecisionScope(**item.scope.model_dump()),
        evidenceRequirements=requirements,
        provenance=SourceProvenance(sourceType=item.sourceType),
        createdBy=None,
        createdAt=now,
    )
