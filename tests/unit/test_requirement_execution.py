import json
from decimal import Decimal
from pathlib import Path

from ledgerquant.agents.process_runtime import checklist
from ledgerquant.models.generation import ModelProfile
from ledgerquant.research.process_evaluation import schedule
from ledgerquant.research.types import digest


ROOT = Path(__file__).parents[2] / "configs/research"


def read(name):
    return json.loads((ROOT / name).read_text())


def test_frozen_regression_contracts_and_labels():
    suite = read("contract_requirements_suite.json")
    tasks = schedule(suite)
    assert len(tasks) == 24
    assert all("reference" not in task for task in tasks)
    for case in suite["cases"]:
        answer = checklist(case["proposal"], case["proposal"]["evidence_ids"], contract_version=2)
        assert answer.disposition == case["reference"]["disposition"]
        assert case["reference"]["required_reason"] in answer.reasons


def test_execution_ceiling_covers_every_call_including_probes_and_step_limit():
    manifest = read("mini_requirements.execution.json")
    policy = read("mini_requirements.policy.json")
    suite = read("contract_requirements_suite.json")
    profiles = [ModelProfile.model_validate(read(name)) for name in
                ("openai_gpt54_mini_process.profile.json", "openai_gpt54_mini.profile.json")]
    process_calls = sum({"single": 2, "critic": 3, "checklist": 0}[task["arm"]] for task in schedule(suite))
    counts = [process_calls, 1 + 2 * profiles[1].max_steps_per_agent]
    maximum = sum(count * (Decimal(str(profile.input_usd_per_million)) * (profile.max_request_bytes + 4096)
                  + Decimal(str(profile.output_usd_per_million)) * profile.max_output_tokens)
                  for count, profile in zip(counts, profiles, strict=True))
    assert counts == [manifest["max_process_calls"], manifest["max_discovery_calls"]]
    assert sum(counts) == policy["max_invocations"]
    assert policy["max_runs"] == len(schedule(suite)) + 1
    assert maximum == manifest["worst_case_reserved_micro_usd"] <= policy["max_usd"] * 1_000_000
    assert sum(count * (profile.max_request_bytes + 4096 + profile.max_output_tokens)
               for count, profile in zip(counts, profiles, strict=True)) <= policy["max_reserved_tokens"]
    assert manifest["prior_reserved_micro_usd"] + policy["max_usd"] * 1_000_000 == manifest["combined_reserved_ceiling_micro_usd"]
    assert manifest["combined_reserved_ceiling_micro_usd"] <= manifest["authorization_total_usd"] * 1_000_000
    for key, value in [("policy", policy), ("suite", suite), ("task", read("mini_requirements.task.json")),
                       ("process_profile", profiles[0]), ("discovery_profile", profiles[1])]:
        assert digest(value) == manifest[key + "_sha256"]
