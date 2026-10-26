from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cloud_crawler_lab.decisions import MAX_CLAIMS, DecisionInput, build_decision
from cloud_crawler_lab.errors import ApiError

from ..conftest import load_sample, one_claim_decision

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def build(raw):
    return build_decision(DecisionInput.model_validate(raw), now=NOW)


@pytest.mark.parametrize("name", ["decision-zone-redundancy.json", "decision-wave-one.json", "decision-starter.json"])
def test_the_sample_decisions_build_into_draft_records(name):
    record = build(load_sample(name))
    assert record.status.value == "draft" and record.version == 1 and record.createdBy is None
    assert record.decisionId.startswith("dec_") and record.createdAt == NOW
    assert record.provenance.sourceType.value == "human"
    assert all(c.decisionId == record.decisionId and c.claimId.startswith("clm_") for c in record.claims)
    assert [r.claimId for r in record.evidenceRequirements] == [c.claimId for c in record.claims]


def test_a_proposed_decision_stays_proposed_and_an_accepted_one_is_not_a_thing_the_lab_does():
    assert build({**one_claim_decision(), "status": "proposed"}).status.value == "proposed"
    with pytest.raises(ValidationError):
        DecisionInput.model_validate({**one_claim_decision(), "status": "accepted"})


def test_ids_are_minted_here_never_taken_from_the_visitor():
    with pytest.raises(ValidationError):
        DecisionInput.model_validate({**one_claim_decision(), "decisionId": "dec_mine"})
    with pytest.raises(ValidationError):
        DecisionInput.model_validate({**one_claim_decision(), "actorId": "someone"})
    assert build(one_claim_decision()).decisionId != build(one_claim_decision()).decisionId


def test_unknown_detector_names_the_claim_by_position_and_lists_the_known_ones():
    with pytest.raises(ApiError) as caught:
        build(one_claim_decision(detectorId="sentinel-detector-name"))
    error = caught.value
    assert (error.status, error.code) == (422, "invalid_decision")
    assert error.details["claimIndex"] == 0 and error.details["reason"] == "unknown_detector"
    assert "zone-redundancy" in error.details["knownDetectors"]
    assert "sentinel" not in str(error.details) + error.message


def test_a_claim_its_detector_cannot_evaluate_is_refused_without_quoting_its_values():
    bad = one_claim_detector = one_claim_decision(
        detectorId="zone-redundancy",
        expectation={"property": "zoneRedundant", "operator": "gte", "value": "sentinel-value"},
    )
    with pytest.raises(ApiError) as caught:
        build(bad)
    error = caught.value
    assert error.details == {"claimIndex": 0, "reason": "claim_not_evaluable", "detectorId": "zone-redundancy"}
    assert "sentinel" not in str(error.details) + error.message
    second = {"title": "t", "claims": [one_claim_decision()["claims"][0], one_claim_detector["claims"][0]]}
    with pytest.raises(ApiError) as caught:
        build(second)
    assert caught.value.details["claimIndex"] == 1


def test_detector_parameters_are_checked_by_the_detector():
    with pytest.raises(ApiError) as caught:
        build(
            one_claim_decision(
                detectorId="tag-required", expectation={"property": "tag", "operator": "exists"}, parameters={}
            )
        )
    assert caught.value.details["reason"] == "claim_not_evaluable"


@pytest.mark.parametrize(
    "mutation",
    [
        {"title": ""},
        {"title": "t" * 201},
        {"context": "c" * 4001},
        {"claims": []},
        {"claims": None},
        {"risks": ["r"] * 21},
        {"risks": ["r" * 501]},
        {"unknownField": 1},
        {"alternatives": [{"alternativeId": "a", "title": "t", "costEstimates": []}]},
        {"scope": {"subscriptionIds": ["s"] * 21}},
        {"scope": {"tagSelectors": {f"k{i}": "v" for i in range(11)}}},
    ],
)
def test_every_field_has_a_size_and_extra_fields_are_refused(mutation):
    with pytest.raises(ValidationError):
        DecisionInput.model_validate({**one_claim_decision(), **mutation})


def test_the_number_of_claims_is_bounded():
    claims = one_claim_decision()["claims"] * (MAX_CLAIMS + 1)
    with pytest.raises(ValidationError):
        DecisionInput.model_validate({"title": "t", "claims": claims})
    DecisionInput.model_validate({"title": "t", "claims": claims[:MAX_CLAIMS]})


@pytest.mark.parametrize(
    "claim",
    [
        {"statement": ""},
        {"statement": "s" * 501},
        {"maxAgeHours": 0},
        {"maxAgeHours": 9000},
        {"severity": "catastrophic"},
        {"parameters": {f"p{i}": 1 for i in range(11)}},
        {"parameters": {"p": {"nested": "object"}}},
        {"parameters": {"p": ["a list"]}},
        {"expectation": {"property": "p", "operator": "in", "value": [{"an": "object"}]}},
        {"expectation": {"property": "p", "operator": "in", "value": [["nested"]]}},
        {"expectation": {"property": "p", "operator": "in", "value": ["v"] * 101}},
        {"expectation": {"property": "p", "operator": "eq", "value": {"an": "object"}}},
        {"expectation": {"property": "p", "operator": "matches", "value": "x"}},
        {"selector": {"nameGlobs": ["*" * 9]}},
        {"selector": {"nameGlobs": ["a"] * 11}},
        {"selector": {"resourceTypes": ["t"] * 31}},
        {"selector": {"resourceTypes": ["t" * 129]}},
        {"selector": {"regex": ".*"}},
    ],
)
def test_claims_hold_scalars_and_bounded_collections_only(claim):
    with pytest.raises(ValidationError):
        DecisionInput.model_validate(one_claim_decision(**claim))


def test_values_the_engine_compares_are_plain_scalars_so_it_never_hashes_a_container():
    build(
        one_claim_decision(
            expectation={
                "property": "location",
                "operator": "in",
                "value": ["centralus", "eastus2", 3, 1.5, True, None],
            }
        )
    )
    build(one_claim_decision(selector={"nameGlobs": ["hcw-*-prod-*"], "tagSelectors": {"env": "prod"}}))
