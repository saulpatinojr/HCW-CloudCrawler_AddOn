"""Acceptance: the lab's answers on the sample estate are the App's answers (website proposal, section 21).

The golden files are the App's own (`HCW-CloudCrawler_App`, tests/acceptance/golden), copied unchanged: the same
decision against the same export must give the same verdict for every resource, whichever edition runs it. Here the
run goes through the lab's upload route, so the whole path is covered: envelope, decision builder, the engine's ingest
and drift code, the listing, the bundle and the owner-token read.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from ..conftest import make_body

GOLDEN = Path(__file__).with_name("golden")


def golden(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def read(client, created):
    headers = {"x-owner-token": created.json()["ownerToken"]}
    return client.get(f"/api/uploads/{created.json()['uploadId']}", headers=headers).json()


def name_of(finding) -> str:
    return finding["resourceId"].rsplit("/", 1)[-1]


def test_zone_redundancy_matches_the_apps_golden_verdicts(client):
    created = client.post("/api/uploads", json=make_body())
    assert created.status_code == 201
    expected = golden("zone-redundancy.verdicts.json")
    detail = read(client, created)
    listed = {name_of(f): f["verdict"] for f in detail["findings"]}
    assert listed == {name: verdict for name, verdict in expected.items() if verdict != "not-applicable"}
    assert detail["summary"]["notApplicable"] == Counter(expected.values())["not-applicable"]
    # the figures the App's own acceptance test pins
    assert detail["summary"] == {
        "supported": 3,
        "contradicted": 2,
        "unknown": 0,
        "notApplicable": 8,
        "score": 60.0,
        "coverage": 1.0,
    }
    assert len(detail["contradictions"]) == 2
    [proposal] = detail["proposals"]
    assert proposal["kind"] == "contradiction" and proposal["status"] == "open"
    sql = next(f for f in detail["findings"] if name_of(f) == "hcw-sample-sql-01")
    assert sql["verdict"] == "contradicted"
    assert sql["observed"] == {"zoneRedundant": False, "reading": False} and sql["expected"] == {"zoneRedundant": True}
    assert sql["evidenceIds"] == [detail["evidence"][0]["evidenceId"]]
    assert detail["evidence"][0]["confidence"] == 0.74, "an upload is unauthenticated evidence"


def test_the_wave_one_baseline_matches_the_apps_golden_verdicts(client):
    from ..conftest import load_sample

    created = client.post("/api/uploads", json=make_body(decision=load_sample("decision-wave-one.json")))
    assert created.status_code == 201
    detail = read(client, created)
    by_detector = {c["claimId"]: c["detectorId"] for c in detail["claims"]}
    listed: dict[str, dict[str, str]] = {}
    for finding in detail["findings"]:
        listed.setdefault(by_detector[finding["claimId"]], {})[name_of(finding)] = finding["verdict"]
    expected = golden("wave-one.verdicts.json")
    assert set(listed) == set(expected)
    for detector, verdicts in expected.items():
        assert listed[detector] == {n: v for n, v in verdicts.items() if v != "not-applicable"}, detector
    claims = {c["detectorId"]: c for c in detail["claims"]}
    for detector, verdicts in expected.items():
        counts = Counter(verdicts.values())
        row = claims[detector]
        assert (row["supported"], row["contradicted"], row["notApplicable"]) == (
            counts["supported"],
            counts["contradicted"],
            counts["not-applicable"],
        ), detector
    assert detail["listing"]["findingsTotal"] == 6 * 13 and detail["listing"]["findingsLeftOut"] == 0


def test_the_starter_decision_runs_against_the_sample_export(client):
    from ..conftest import load_sample

    created = client.post("/api/uploads", json=make_body(decision=load_sample("decision-starter.json")))
    assert created.status_code == 201
    summary = created.json()["summary"]
    assert summary["contradicted"] > 0 and summary["supported"] > 0 and summary["score"] is not None
    # every claim is stated back to the visitor with its own counts, so the pane can show them without the findings
    claims = created.json()["claims"]
    assert [c["detectorId"] for c in claims] == [
        "public-access-disabled",
        "private-endpoint-present",
        "managed-identity",
        "tag-required",
    ]
    assert sum(c["contradicted"] for c in claims) == summary["contradicted"]


@pytest.mark.parametrize("sample", ["decision-zone-redundancy.json", "decision-wave-one.json", "decision-starter.json"])
def test_every_sample_decision_is_a_valid_upload_with_the_sample_export(client, sample):
    from ..conftest import load_sample

    r = client.post("/api/uploads", json=make_body(decision=load_sample(sample)))
    assert r.status_code == 201, r.text
    assert r.json()["decision"]["status"] == "draft"
