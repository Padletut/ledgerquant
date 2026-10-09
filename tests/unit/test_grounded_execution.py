import json
from decimal import Decimal
from pathlib import Path

from ledgerquant.agents.process_runtime import checklist
from ledgerquant.models.generation import ModelProfile
from ledgerquant.research.process_evaluation import schedule
from ledgerquant.research.types import digest


ROOT = Path(__file__).parents[2]


def read(name):
    return json.loads((ROOT / "configs/research" / name).read_text())


def test_frozen_revision_labels_and_exact_evidence_references():
    suite = read("grounded_revision_suite.json")
    context = json.loads((ROOT / "documents/research/evaluations/grounded_revision_20261009/input_context.json").read_text())
    assert digest(context) == suite["prior_context_sha256"]
    assert len(schedule(suite)) == 18
    for case in suite["cases"]:
        answer = checklist(case["proposal"], case["proposal"]["evidence_ids"], 3, context)
        assert answer.disposition == case["reference"]["disposition"]
        assert case["reference"]["required_reason"] in answer.reasons
    assert all(digest(fact) == key for key, fact in context["facts"].items())


def test_revision_campaign_bound_covers_all_calls_and_preserves_total():
    manifest = read("grounded_revision.execution.json")
    policy = read("grounded_revision.policy.json")
    suite = read("grounded_revision_suite.json")
    profiles = [ModelProfile.model_validate(read(name)) for name in
                ("openai_mini_grounding_process.profile.json", "openai_mini_revision.profile.json")]
    counts = [sum({"single": 2, "critic": 3, "checklist": 0}[task["arm"]] for task in schedule(suite)),
              1 + 2 * profiles[1].max_steps_per_agent]
    maximum = sum(count * (Decimal(str(profile.input_usd_per_million)) * (profile.max_request_bytes + 4096)
                  + Decimal(str(profile.output_usd_per_million)) * profile.max_output_tokens)
                  for count, profile in zip(counts, profiles, strict=True))
    assert maximum == manifest["worst_case_reserved_micro_usd"] <= policy["max_usd"] * 1_000_000
    assert counts == [manifest["max_process_calls"], manifest["max_discovery_calls"]]
    assert sum(counts) == policy["max_invocations"]
    assert len(schedule(suite)) + 1 == policy["max_runs"]
    assert sum(count * (profile.max_request_bytes + 4096 + profile.max_output_tokens)
               for count, profile in zip(counts, profiles, strict=True)) <= policy["max_reserved_tokens"]
    assert manifest["prior_reserved_micro_usd"] + policy["max_usd"] * 1_000_000 == manifest["combined_reserved_ceiling_micro_usd"]
    assert manifest["combined_reserved_ceiling_micro_usd"] <= manifest["authorization_total_usd"] * 1_000_000
    for key, value in [("policy", policy), ("suite", suite), ("task", read("grounded_revision.task.json")),
                       ("process_profile", profiles[0]), ("discovery_profile", profiles[1])]:
        assert digest(value) == manifest[key + "_sha256"]
