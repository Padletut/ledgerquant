"""Human review exports must preserve the claim, exact sources and integrity limits."""

from copy import deepcopy

import pytest

from ledgerquant.research.process_review import render_process_review
from ledgerquant.research.registry import RegistryError
from ledgerquant.research.types import digest


def bundle():
    draft = {"title": "Scope review", "diagnostic": {"hours_utc": [12]},
             "data_requirements": [{"reason": "Costs apply only to a future economic test."}]}
    packet = {"run_id": "recorded-run", "role": "research", "action_time": "2026-10-09T12:00:00Z",
              "draft": {"sha256": digest(draft), **draft}, "critique": None,
              "grounding_context_sha256": None, "grounding_context": None,
              "tool_results": [], "recorded_contract_review": None,
              "test_basis": {"context_invalidated": False}, "task": {},
              "agent_definition": {"research_contract_version": 1}, "current_service_checks": {}}
    assessment = {"run_id": packet["run_id"], "role": "research", "packet_sha256": digest(packet),
                  "assessor": "original_assessor", "assessor_outcome_exposure": "EXPOSED",
                  "review_state": "PROPOSED", "reviewer": None, "reason": "Check cost scope.",
                  "findings": [{"code": "REQUIREMENT_SCOPE_CONFUSION", "status": "SUPPORTED",
                                "responsible_component": "research", "severity": "material",
                                "explanation": "Current and future requirements conflict.",
                                "applicability": "Binding current requirements.",
                                "references": ["draft.data_requirements[0].reason"]}],
                  "critic_delta": [], "limitations": ["Assessor has seen later outcomes."]}
    return {"version": "process_review/1", "assessment_id": digest(assessment), "assessment": assessment,
            "packet_sha256": digest(packet), "packet": packet, "recorded_at": "2026-10-10T00:00:00Z",
            "source_state": {"state": "SUSPENDED", "reasons": ["NOT_REVIEWED"]},
            "current_packet_sha256": digest(packet)}


def test_review_shows_claim_exact_cited_text_and_no_implied_approval():
    source = bundle()
    before = deepcopy(source)
    rendered = render_process_review(source, source_link="source.json")
    assert "Costs apply only to a future economic test." in rendered
    assert "draft.data_requirements[0].reason" in rendered
    assert "Current and future requirements conflict." in rendered
    assert "SUPPORTED" in rendered and "UNRESOLVED" in rendered
    assert "EXPOSED" in rendered and "PROPOSED" in rendered
    assert "[Complete source packet and assessment](source.json)" in rendered
    assert source == before


@pytest.mark.parametrize("section", ["packet", "assessment"])
def test_modified_source_is_rejected(section):
    source = bundle()
    source[section]["unexpected_change"] = True
    with pytest.raises(RegistryError, match="REVIEW_SOURCE_HASH_MISMATCH"):
        render_process_review(source)


def test_hash_reference_expands_to_its_source_and_unknown_reference_fails():
    source = bundle()
    finding = source["assessment"]["findings"][0]
    finding["references"] = [source["packet"]["draft"]["sha256"]]
    source["assessment_id"] = digest(source["assessment"])
    assert "Costs apply only to a future economic test." in render_process_review(source)
    finding["references"] = ["operator_decision.reason"]
    source["assessment_id"] = digest(source["assessment"])
    with pytest.raises(RegistryError, match="REFERENCE_OUTSIDE_PACKET"):
        render_process_review(source)


def test_stale_or_superseded_review_is_visibly_marked():
    source = bundle()
    source["current_packet_sha256"] = "0" * 64
    source["source_state"]["reasons"].append("SUPERSEDED")
    rendered = render_process_review(source)
    assert "SOURCE CHANGED" in rendered and "SUPERSEDED" in rendered
    assert "Obtain a current packet" in rendered


def test_unrelated_later_outcome_is_never_rendered():
    source = bundle()
    original = render_process_review(source)
    source["later_outcome"] = {"profit": "LATER_OUTCOME_SENTINEL"}
    assert render_process_review(source) == original


def test_source_markdown_stays_inside_a_literal_quotation():
    source = bundle()
    source["packet"]["draft"]["data_requirements"][0]["reason"] = "```\n# Untrusted heading"
    source["packet_sha256"] = digest(source["packet"])
    source["current_packet_sha256"] = source["packet_sha256"]
    source["assessment"]["packet_sha256"] = source["packet_sha256"]
    source["assessment_id"] = digest(source["assessment"])
    rendered = render_process_review(source)
    assert "> \\`\\`\\`\n> \\# Untrusted heading" in rendered
    assert "\n# Untrusted heading" not in rendered


def test_reviewed_export_records_the_decision_and_reviewer_without_prompting_for_initial_review():
    source = bundle()
    source["assessment"].update(review_state="REVIEWED", reviewer="human_reviewer",
                                supersedes="prior-assessment")
    source["assessment"]["findings"][0]["status"] = "NOT_SUPPORTED"
    source["assessment_id"] = digest(source["assessment"])
    source["source_state"] = {"state": "CURRENT", "reasons": []}
    before = deepcopy(source)
    rendered = render_process_review(source)
    assert "**Reviewed finding:** `NOT_SUPPORTED`" in rendered
    assert "human\\_reviewer" in rendered and "prior-assessment" in rendered
    assert "Assessor's proposed label" not in rendered
    assert "No decision has been selected for you" not in rendered
    assert "Costs apply only to a future economic test." in rendered
    assert source == before
