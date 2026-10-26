from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.evidence import MAX_FILES, MAX_IDENTIFIER, EvidenceFile, describe, ingest_files

from ..conftest import load_sample

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def files(*items):
    return [EvidenceFile.model_validate(item) for item in items]


def arg(content, name="e.json"):
    return {"kind": "arg-export", "content": content, "name": name}


def rows(n, prefix="r"):
    return [
        {"id": f"/subscriptions/00000000-0000-0000-0000-000000000001/{prefix}{i}", "name": f"{prefix}{i}", "type": "t"}
        for i in range(n)
    ]


def refused(items, **kwargs) -> ApiError:
    with pytest.raises(ApiError) as caught:
        ingest_files(files(*items), max_rows=kwargs.get("max_rows", 5000), now=NOW)
    return caught.value


def test_a_resource_graph_export_is_ingested_as_unauthenticated_imported_evidence():
    [(record, entries)] = ingest_files(files(arg(load_sample("sample-resource-graph.json"))), max_rows=5000, now=NOW)
    assert entries == 13 and len(record.correlations) == 13
    assert record.evidenceClass.value == "imported" and record.kind.value == "arg-export"
    assert record.confidence == 0.74, "an upload is never above the unauthenticated cap"
    assert record.provenance.sourceType.value == "upload" and record.provenance.artifactName == "e.json"
    assert record.payloadHash.startswith("sha256:") and record.retrievedAt == NOW
    info = describe(record, entries, "e.json")
    assert info["readByDetectors"] is True and info["resourceCount"] == 13 and "content" not in info
    assert set(info) == {
        "evidenceId",
        "kind",
        "name",
        "resourceCount",
        "entryCount",
        "redactedCount",
        "confidence",
        "payloadHash",
        "readByDetectors",
        "note",
    }


def test_secrets_in_an_export_are_redacted_and_counted():
    export = rows(1)
    export[0]["properties"] = {"connectionString": "Server=sentinel", "keep": "yes"}
    [(record, _)] = ingest_files(files(arg(export)), max_rows=10, now=NOW)
    assert record.redaction.removedCount == 1
    assert "sentinel" not in str(record.payload) and "yes" in str(record.payload)


def test_terraform_state_and_plan_are_recorded_but_not_read_by_this_engine():
    state = {"version": 4, "resources": [{"type": "azurerm_x", "instances": []}] * 3}
    plan = {"format_version": "1.2", "resource_changes": [{"address": "a"}] * 2}
    records = ingest_files(
        files({"kind": "tf-state", "content": state}, {"kind": "tf-plan", "content": plan}), max_rows=10, now=NOW
    )
    [(state_record, state_entries), (plan_record, plan_entries)] = records
    assert (state_entries, plan_entries) == (3, 2)
    assert state_record.correlations == [] and plan_record.correlations == []
    for record, entries in records:
        info = describe(record, entries, None)
        assert info["readByDetectors"] is False and info["resourceCount"] == 0
        assert "does not read Terraform" in info["note"]


@pytest.mark.parametrize(
    "kind, content",
    [
        ("tf-state", []),
        ("tf-state", {"version": 3, "resources": []}),
        ("tf-state", {"version": 4}),
        ("tf-state", {"version": 4, "resources": "no"}),
        ("tf-plan", {"format_version": "2.0", "resource_changes": []}),
        ("tf-plan", {"format_version": 1, "resource_changes": []}),
        ("tf-plan", {"format_version": "1.0"}),
        ("tf-plan", "a string"),
        ("arg-export", {"nope": 1}),
        ("arg-export", "a string"),
        ("arg-export", None),
        ("arg-export", [1, 2]),
        ("arg-export", [{"name": "no id"}]),
    ],
)
def test_content_that_is_not_the_kind_it_claims_is_refused_with_a_reason_and_a_position(kind, content):
    error = refused([{"kind": kind, "content": content}])
    assert (error.status, error.code) == (422, "ingestion_failed")
    assert error.details["evidenceIndex"] == 0 and isinstance(error.details["reason"], str)


def test_the_position_names_the_file_that_failed():
    error = refused([arg(rows(1)), {"kind": "tf-state", "content": {"version": 9}}])
    assert error.details["evidenceIndex"] == 1


def test_rows_count_against_one_budget_across_all_files():
    assert refused([arg(rows(3)), arg(rows(3, "q"))], max_rows=5).code == "too_many_rows"
    error = refused([arg(rows(6))], max_rows=5)
    assert (error.status, error.code, error.details) == (422, "too_many_rows", {"evidenceIndex": 0, "maxRows": 5})
    ingest_files(files(arg(rows(3)), arg(rows(2, "q"))), max_rows=5, now=NOW)
    state = {"version": 4, "resources": [{}] * 6}
    assert refused([{"kind": "tf-state", "content": state}], max_rows=5).code == "too_many_rows"


def test_an_identifier_longer_than_any_resource_id_is_refused():
    long_id = [{"id": "/" + "a" * MAX_IDENTIFIER, "name": "n", "type": "t"}]
    assert refused([arg(long_id)]).code == "ingestion_failed"
    ok = [{"id": "/" + "a" * (MAX_IDENTIFIER - 1), "name": "n", "type": "t"}]
    ingest_files(files(arg(ok)), max_rows=10, now=NOW)


def test_the_request_holds_at_most_a_few_files_with_plain_names_and_known_kinds():
    EvidenceFile.model_validate(arg(rows(1), "Export (1).json"))
    for bad in (
        {"kind": "azqr-report", "content": {}},
        {"kind": "arg-export", "content": [], "name": "../x.json"},
        {"kind": "arg-export", "content": [], "name": "x.csv"},
        {"kind": "arg-export", "content": [], "name": "x" * 130 + ".json"},
        {"kind": "arg-export", "content": [], "extra": 1},
        {"content": []},
    ):
        with pytest.raises(ValidationError):
            EvidenceFile.model_validate(bad)
    assert MAX_FILES == 5
