"""The evidence a visitor uploads, handed to the engine's own ingestion (`cloud_crawler_core.ingest.ingest`).

Three kinds are accepted, and the engine (0.1.1 and later) reads all three into resources: `arg-export` (an Azure
Resource Graph export), `tf-state` (a Terraform state file, version 4) and `tf-plan` (the JSON of a plan,
`terraform show -json`). A Terraform document is read through the engine's provider-type table (hashicorp/azurerm
only): a resource type the table knows becomes a row, anything else is counted in a content-free summary and never
read, and a property the document cannot answer (a tag only known after apply, a value Terraform marks sensitive) is
left out so the detector answers `unknown`, never a guess. A plan describes what Terraform would build, not what
exists; the engine never lets a plan row replace a row of another kind. The lab keeps no evidence payload at all once
the result is built: only the fingerprint, the counts and the findings.

Every message that leaves this module names a position or a reason code. The engine's `IngestionError` messages are
content-free by construction (they carry row numbers and limits), and the checks added here follow the same rule.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from cloud_crawler_core.ingest import NORMALISED_KINDS, TERRAFORM_KINDS, ingest
from cloud_crawler_core.models import (
    Evidence,
    EvidenceClass,
    EvidenceKind,
    ScopeKind,
    SourceProvenance,
    SourceType,
    Subject,
)
from cloud_crawler_core.normalize import IngestionError
from pydantic import BaseModel, ConfigDict, Field

from cloud_crawler_lab.errors import ApiError

MAX_FILES = 5
MAX_IDENTIFIER = 2048
# What a detector scans for every claim, resource by resource (`tag_of` reads every tag; zones are listed). Azure allows
# far fewer tags than this on one resource; a row with hundreds of thousands is a way to make the evaluation slow.
MAX_TAGS = 100
MAX_ZONES = 100
FILE_NAME = r"^[\w .()-]{1,120}\.json$"

KINDS: dict[str, EvidenceKind] = {
    "arg-export": EvidenceKind.ARG_EXPORT,
    "tf-state": EvidenceKind.TF_STATE,
    "tf-plan": EvidenceKind.TF_PLAN,
}
# The row fields the engine copies into every finding and proposal; bounded so one row cannot be made huge.
ROW_TEXT_FIELDS = ("id", "name", "type", "location", "resourceGroup", "subscriptionId")


class EvidenceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["arg-export", "tf-state", "tf-plan"]
    content: Any
    name: str | None = Field(default=None, pattern=FILE_NAME)


def _rows_of_export(content: Any) -> list[Any] | None:
    if isinstance(content, list):
        return content
    if isinstance(content, dict) and isinstance(content.get("data"), list):
        return content["data"]
    return None


def _entries(kind: str, content: Any) -> int | None:
    """How many resources a file carries, after proving it has the shape the kind says. None: the engine decides."""
    if kind == "arg-export":
        rows = _rows_of_export(content)
        if rows is None:
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue  # the engine refuses it, naming the row
            if any(isinstance(row.get(field), str) and len(row[field]) > MAX_IDENTIFIER for field in ROW_TEXT_FIELDS):
                raise IngestionError("invalid_request", "a row has an identifier longer than the lab accepts")
            tags, zones = row.get("tags"), row.get("zones")
            if isinstance(tags, dict) and len(tags) > MAX_TAGS:
                raise IngestionError("invalid_request", "a row has more tags than the lab accepts")
            if isinstance(zones, list) and len(zones) > MAX_ZONES:
                raise IngestionError("invalid_request", "a row lists more zones than the lab accepts")
        return len(rows)
    if not isinstance(content, dict):
        raise IngestionError("invalid_request", f"a {kind} document is a JSON object")
    if kind == "tf-state":
        entries = content.get("resources")
        if content.get("version") != 4 or not isinstance(entries, list):
            raise IngestionError("invalid_request", "a Terraform state is version 4 with a resources array")
        return len(entries)
    entries = content.get("resource_changes")
    version = content.get("format_version")
    if not (isinstance(version, str) and version.startswith("1.")) or not isinstance(entries, list):
        raise IngestionError("invalid_request", "a Terraform plan is format_version 1.x with a resource_changes array")
    return len(entries)


def ingest_files(files: list[EvidenceFile], *, max_rows: int, now: datetime) -> list[tuple[Evidence, int | None]]:
    """Ingest every file as unauthenticated, imported evidence. Rows count against one budget across all files."""
    budget = max_rows
    records: list[tuple[Evidence, int | None]] = []
    for index, file in enumerate(files):
        try:
            entries = _entries(file.kind, file.content)
            if entries is not None and entries > budget:
                raise IngestionError("too_many_rows", f"the files have more than {max_rows} rows")
            record = ingest(
                kind=KINDS[file.kind],
                evidence_class=EvidenceClass.IMPORTED,
                payload=file.content,
                subject=Subject(scope=ScopeKind.SUBSCRIPTION),
                provenance=SourceProvenance(sourceType=SourceType.UPLOAD, artifactName=file.name),
                authenticated=False,
                now=now,
                max_rows=budget,
            )
        except IngestionError as exc:
            if exc.code == "too_many_rows":
                raise ApiError(
                    422,
                    "too_many_rows",
                    "The files have more rows than the limit.",
                    {"evidenceIndex": index, "maxRows": max_rows},
                ) from None
            raise ApiError(
                422,
                "ingestion_failed",
                "The evidence could not be read.",
                {"evidenceIndex": index, "reason": str(exc)},
            ) from None
        records.append((record, entries))
        budget -= entries or 0
    return records


def describe(record: Evidence, entries: int | None, name: str | None) -> dict[str, Any]:
    """What the visitor is told about one file: counts and a fingerprint, never the content."""
    read = record.kind in NORMALISED_KINDS
    info: dict[str, Any] = {
        "evidenceId": record.evidenceId,
        "kind": record.kind.value,
        "name": name,
        "resourceCount": len(record.correlations),
        "entryCount": entries,
        "redactedCount": record.redaction.removedCount,
        "confidence": record.confidence,
        "payloadHash": record.payloadHash,
        "readByDetectors": read,
        "note": NOTES[record.kind] if read else NOTE_UNREAD,
    }
    if record.kind in TERRAFORM_KINDS and isinstance(record.payload, dict):
        # The engine's own summary of the document: counts and Terraform type names only, never a value from it.
        info["terraform"] = record.payload.get("terraform")
    return info


NOTE_UNREAD = (
    "Recorded with a fingerprint only. This version of the engine does not read this kind, so claims about it stay "
    "unknown."
)
NOTES: dict[EvidenceKind, str] = {
    EvidenceKind.ARG_EXPORT: "Read into resources; the detectors checked your claims against it.",
    EvidenceKind.TF_STATE: (
        "Read into resources; the detectors checked your claims against it. Only the Azure resource types the engine "
        "maps are read (the rest are counted, not read), and a value the state cannot answer stays unknown."
    ),
    EvidenceKind.TF_PLAN: (
        "Read into the resources Terraform would build; the detectors checked your claims against that plan, not "
        "against what exists. A value that is only known after apply stays unknown."
    ),
}
