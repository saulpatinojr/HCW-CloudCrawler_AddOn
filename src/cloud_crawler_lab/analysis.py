"""One upload, start to finish, with no web framework in sight: bytes in, a result and its report files out.

    bytes --parse--> JSON --bounds--> request --decision--> DecisionRecord
                                         `-----evidence--> Evidence (the engine's ingest)
    DecisionRecord + Evidence --engine drift--> DriftResult --listing--> a result small enough to keep --bundle-->

The engine does the thinking (`ingest`, `evaluate_decision`, `bundle`); this module only decides what is *kept*.
A decision of 20 claims over 5,000 resources is 100,000 findings, and the engine's own report would be tens of
megabytes. The lab lists the findings that matter (contradicted first, then unknown, then supported), says how many
it left out, and keeps the exact counts in the summary, so what is held for two hours stays small and nothing is
silently dropped.

Nothing is written to disk, and nothing in here logs: the caller logs counts only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cloud_crawler_core import __version__ as ENGINE_VERSION
from cloud_crawler_core.drift import evaluate_decision
from cloud_crawler_core.models import (
    SEVERITY_WEIGHTS,
    DecisionRecord,
    DriftFinding,
    DriftResult,
    Verdict,
)
from cloud_crawler_core.report import NOT_AN_AUDIT, bundle
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cloud_crawler_lab.decisions import DecisionInput, build_decision
from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.evidence import MAX_FILES, EvidenceFile, describe, ingest_files
from cloud_crawler_lab.inputs import check_bounds, parse_document

# The engine answers every claim for every resource it read (a not-applicable answer is a finding too), and each
# finding costs about 3.6 KB while the evaluation runs. Claims times resources is therefore capped so that two
# evaluations at once, the stored results and the process itself stay well inside the lab host's 512 MB: 25,000 is
# about 120 MB for one evaluation (5,000 resources with 5 claims, or 1,250 with 20).
MAX_FINDINGS = 25_000
LISTED_FINDINGS = 1_000
LISTED_CONTRADICTIONS = 1_000
LISTED_RESOURCES_PER_PROPOSAL = 100
# `observed` and `expected` echo what the export held. Past this many characters they are replaced by a marker.
MAX_SHOWN_VALUE = 1_024
MAX_ITEM_BYTES = 8 * 1024 * 1024
NOT_AN_AUDIT_LINE = "Not an audit. See NOT-AN-AUDIT.md in this bundle for what the verdicts do and do not mean."

# Field names of every request model, used to keep free-form keys (tag names, parameter names) out of error paths.
FIELD_NAMES: set[str] = set()


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: list[EvidenceFile] = Field(min_length=1, max_length=MAX_FILES)
    decision: DecisionInput


def _register_field_names(model: type[BaseModel], seen: set[type]) -> None:
    if model in seen:
        return
    seen.add(model)
    for name, info in model.model_fields.items():
        FIELD_NAMES.add(name)
        stack = [info.annotation]
        while stack:
            annotation = stack.pop()
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                _register_field_names(annotation, seen)
            stack.extend(getattr(annotation, "__args__", ()))


_register_field_names(UploadRequest, set())


def _fields(error: ValidationError) -> list[str]:
    """Paths of the fields that failed, built only from the lab's own field names and list positions."""
    paths: set[str] = set()
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        parts: list[str] = []
        for part in item["loc"]:
            if isinstance(part, int):
                parts.append(f"[{part}]")
            elif part in FIELD_NAMES:
                parts.append(f".{part}" if parts else part)
            else:
                break
        paths.add("".join(parts) or "(body)")
    return sorted(paths)[:20]


# Pydantic validates every entry of a mapping before it applies the mapping's own size limit, and writes one error
# per bad entry (about 5 KB each): 250,000 bad entries in a 4 MB decision measured 1.3 GB. So the parts pydantic will
# validate for errors are given a budget first. The evidence content is not in this budget; it is `Any` to pydantic and
# is bounded by `inputs.check_bounds` and the engine's own row limits.
MAX_DECISION_NODES = 20_000
MAX_KEYS = 128
MAX_LIST = 1_000


def _bad_shape(*fields: str) -> ApiError:
    return ApiError(400, "invalid_request", "The request shape is not valid.", {"fields": sorted(fields)})


def check_request_shape(document: Any) -> None:
    if not isinstance(document, dict):
        return  # pydantic says so, in one error
    if len(document) > 2:
        raise _bad_shape("(body)")
    evidence = document.get("evidence")
    if isinstance(evidence, list):
        if len(evidence) > MAX_FILES:
            raise _bad_shape("evidence")
        if any(isinstance(item, dict) and len(item) > 3 for item in evidence):
            raise _bad_shape("evidence")
    nodes = 0
    stack: list[Any] = [document.get("decision")]
    while stack:
        node = stack.pop()
        nodes += 1
        if nodes > MAX_DECISION_NODES:
            raise _bad_shape("decision")
        if isinstance(node, dict):
            if len(node) > MAX_KEYS:
                raise _bad_shape("decision")
            stack.extend(node.values())
        elif isinstance(node, list):
            if len(node) > MAX_LIST:
                raise _bad_shape("decision")
            stack.extend(node)


def parse_request(document: Any) -> UploadRequest:
    check_request_shape(document)
    try:
        return UploadRequest.model_validate(document)
    except ValidationError as exc:
        raise ApiError(400, "invalid_request", "The request shape is not valid.", {"fields": _fields(exc)}) from None


@dataclass(frozen=True)
class Outcome:
    meta: dict[str, Any]
    files: dict[str, bytes]


def _shown(value: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(value, sort_keys=True, default=str)
    return value if len(text) <= MAX_SHOWN_VALUE else {"truncated": True, "characters": len(text)}


def _claim_table(decision: DecisionRecord, findings: list[DriftFinding]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, int]] = {
        c.claimId: dict.fromkeys((v.value for v in Verdict), 0) for c in decision.claims
    }
    for finding in findings:
        counts[finding.claimId][finding.verdict.value] += 1
    return [
        {
            "claimId": claim.claimId,
            "statement": claim.statement,
            "detectorId": claim.detectorId,
            "severity": claim.severity.value,
            "supported": counts[claim.claimId]["supported"],
            "contradicted": counts[claim.claimId]["contradicted"],
            "unknown": counts[claim.claimId]["unknown"],
            "notApplicable": counts[claim.claimId]["not-applicable"],
        }
        for claim in decision.claims
    ]


def _listing(decision: DecisionRecord, result: DriftResult) -> tuple[DriftResult, dict[str, Any]]:
    """The result as it is kept: findings that matter, capped; values shortened; proposals' resource lists capped."""
    weights = {c.claimId: SEVERITY_WEIGHTS[c.severity] for c in decision.claims}
    rank = {Verdict.CONTRADICTED: 0, Verdict.UNKNOWN: 1, Verdict.SUPPORTED: 2}
    matters = [f for f in result.findings if f.verdict is not Verdict.NOT_APPLICABLE]
    matters.sort(key=lambda f: (rank[f.verdict], -weights.get(f.claimId, 1), f.resourceId or ""))
    listed = [
        f.model_copy(update={"observed": _shown(f.observed), "expected": _shown(f.expected)})
        for f in matters[:LISTED_FINDINGS]
    ]
    contradictions = [
        c.model_copy(update={"observed": _shown(c.observed), "expected": _shown(c.expected)})
        for c in result.contradictions[:LISTED_CONTRADICTIONS]
    ]
    proposals = [
        p.model_copy(update={"impactedResourceIds": p.impactedResourceIds[:LISTED_RESOURCES_PER_PROPOSAL]})
        for p in result.proposals
    ]
    kept = result.model_copy(update={"findings": listed, "contradictions": contradictions, "proposals": proposals})
    disclosure = {
        "findingsTotal": len(result.findings),
        "findingsListed": len(listed),
        "notApplicableNotListed": len(result.findings) - len(matters),
        "findingsLeftOut": len(matters) - len(listed),
        "contradictionsTotal": len(result.contradictions),
        "contradictionsListed": len(contradictions),
        "maxResourcesPerProposal": LISTED_RESOURCES_PER_PROPOSAL,
    }
    return kept, disclosure


def _listing_paragraph(disclosure: dict[str, Any]) -> str:
    return (
        "\n## What is listed\n\n"
        f"The counts above cover all {disclosure['findingsTotal']} findings. This report lists "
        f"{disclosure['findingsListed']} of them: contradicted first, then unknown, then supported. "
        f"{disclosure['notApplicableNotListed']} not-applicable findings are counted, not listed"
        + (
            f", and {disclosure['findingsLeftOut']} more are left out to keep the report small"
            if disclosure["findingsLeftOut"]
            else ""
        )
        + ". A review proposal names at most "
        f"{disclosure['maxResourcesPerProposal']} resources.\n\n{NOT_AN_AUDIT_LINE}\n"
    )


# Characters Markdown or HTML would read, as entities, and every control character (a newline included) as a space.
# A translation table, not a pattern: nothing in this module runs a regular expression over what a visitor sent.
_MARKDOWN_TABLE: dict[int, str] = {
    **dict.fromkeys([*range(0x20), 0x7F], " "),
    **{
        ord(c): e
        for c, e in {
            "|": "&#124;",
            "<": "&lt;",
            ">": "&gt;",
            "`": "&#96;",
            "[": "&#91;",
            "]": "&#93;",
            "\\": "&#92;",
        }.items()
    },
}


def markdown_text(value: str) -> str:
    """Text that can sit in a Markdown table cell or heading without becoming Markdown or HTML. The report is
    downloaded and opened elsewhere, and a resource name, a tag value or a decision title is whatever its author typed:
    a newline then `# heading`, an image whose address is a tracking beacon, a `<script>`. Control characters (newlines
    included) become spaces, so one finding stays one table row."""
    return value.translate(_MARKDOWN_TABLE)


def _markdown_value(value: Any) -> Any:
    if isinstance(value, str):
        return markdown_text(value)
    if isinstance(value, list):
        return [_markdown_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _markdown_value(v) for k, v in value.items()}
    return value


def _for_markdown(decision: DecisionRecord, kept: DriftResult) -> tuple[DecisionRecord, DriftResult]:
    """Copies of the decision and the kept result with every free-text field made safe for the Markdown report. The JSON
    report keeps the originals: JSON quotes what it carries."""
    findings = [
        f.model_copy(
            update={
                "resourceId": markdown_text(f.resourceId) if f.resourceId else None,
                "observed": _markdown_value(f.observed),
                "expected": _markdown_value(f.expected),
                "unknownReason": markdown_text(f.unknownReason) if f.unknownReason else None,
            }
        )
        for f in kept.findings
    ]
    proposals = [
        p.model_copy(
            update={
                "title": markdown_text(p.title),
                "rationale": markdown_text(p.rationale),
                "impactedResourceIds": [markdown_text(i) for i in p.impactedResourceIds],
                "recommendedActions": [
                    a.model_copy(update={"action": markdown_text(a.action)}) for a in p.recommendedActions
                ],
            }
        )
        for p in kept.proposals
    ]
    return (
        decision.model_copy(update={"title": markdown_text(decision.title)}),
        kept.model_copy(update={"findings": findings, "proposals": proposals}),
    )


def _files(decision: DecisionRecord, kept: DriftResult, disclosure: dict[str, Any]) -> dict[str, bytes]:
    texts = bundle(decision, kept)
    texts["report.md"] = bundle(*_for_markdown(decision, kept))["report.md"]
    report = json.loads(texts["report.json"])
    report["lab"] = {"edition": "lab", "callsAzure": False, "notAnAudit": NOT_AN_AUDIT_LINE, "listing": disclosure}
    texts["report.json"] = json.dumps(report, indent=2, sort_keys=True) + "\n"
    texts["report.md"] = texts["report.md"].rstrip("\n") + "\n" + _listing_paragraph(disclosure)
    return {name: text.encode("utf-8") for name, text in sorted(texts.items())}


def process_upload(body: bytes, *, max_rows: int, now: datetime | None = None) -> Outcome:
    """Everything between the verified, size-capped body and a result ready to store. Raises ApiError, nothing else
    the visitor could learn from; the caller turns any other exception into a plain 500."""
    now = now or datetime.now(UTC)
    document = parse_document(body)
    check_bounds(document)
    request = parse_request(document)
    del document  # the request holds what it needs; every copy of the upload that is not needed is let go early
    decision = build_decision(request.decision, now=now)
    records = ingest_files(request.evidence, max_rows=max_rows, now=now)
    for file in request.evidence:
        file.content = None
    read = sum(len(record.correlations) for record, _ in records)
    if len(decision.claims) * read > MAX_FINDINGS:
        raise ApiError(
            422,
            "too_many_findings",
            "Claims times resources is more than the lab evaluates at once; use fewer of either.",
            {"claims": len(decision.claims), "resources": read, "maxFindings": MAX_FINDINGS},
        )
    result = evaluate_decision(decision, [record for record, _ in records], now=now)
    kept, disclosure = _listing(decision, result)
    files = _files(decision, kept, disclosure)
    if sum(len(data) for data in files.values()) > MAX_ITEM_BYTES:
        raise ApiError(
            422, "result_too_large", "The result is larger than the lab keeps.", {"maxBytes": MAX_ITEM_BYTES}
        )
    meta = {
        "engine": {"name": "cloud-crawler-core", "version": ENGINE_VERSION, "callsAzure": False},
        "notAnAudit": {"line": NOT_AN_AUDIT_LINE, "text": NOT_AN_AUDIT, "file": "NOT-AN-AUDIT.md"},
        "summary": result.summary.model_dump(mode="json"),
        "decision": {
            "decisionId": decision.decisionId,
            "title": decision.title,
            "status": decision.status.value,
            "version": decision.version,
            "claimCount": len(decision.claims),
        },
        "evidence": [
            describe(record, entries, file.name)
            for (record, entries), file in zip(records, request.evidence, strict=True)
        ],
        "claims": _claim_table(decision, result.findings),
        "listing": disclosure,
        "proposalCount": len(result.proposals),
        "files": sorted(files),
    }
    return Outcome(meta=meta, files=files)
