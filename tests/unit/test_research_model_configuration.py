import json
from pathlib import Path

import pytest

from ledgerquant.agents.definitions import definition
from ledgerquant.models.generation import ModelProfile
from ledgerquant.research.agent_cli import parser
from ledgerquant.research.types import digest


ROOT = Path(__file__).parents[2]


def test_explicit_process_profile_default_and_override(monkeypatch):
    monkeypatch.setenv("MODEL_PROFILE_FILE", "/run/config/model-profile.json")
    arguments = ["run", "--config", "registration.json", "--command-key", "test", "--task", "task.json"]
    assert parser().parse_args(arguments).profile == "/run/config/model-profile.json"
    assert parser().parse_args(arguments + ["--profile", "historical.json"]).profile == "historical.json"


def test_unconfigured_cli_still_requires_explicit_model(monkeypatch):
    monkeypatch.delenv("MODEL_PROFILE_FILE", raising=False)
    with pytest.raises(SystemExit):
        parser().parse_args(["run", "--config", "registration.json", "--command-key", "test", "--task", "task.json"])


def test_model_transition_keeps_original_binding_and_changes_only_model_metadata():
    def load(name):
        return ModelProfile.model_validate_json((ROOT / "configs/research" / name).read_text())
    old = load("openai_astra_bootstrap.profile.json")
    new = load("openai_gpt54_mini.profile.json")
    original = json.loads((ROOT / "documents/research/evaluations/agent_loop_bootstrap_20261009/first_run.json").read_text())
    assert digest(definition("research", old)) == original["research_version"]
    assert digest(definition("critic", old)) == original["critic_version"]
    assert new.model == "gpt-5.4-mini"
    changed = {key for key, value in old.model_dump().items() if new.model_dump()[key] != value}
    assert changed == {"model", "input_usd_per_million", "cache_write_usd_per_million", "output_usd_per_million", "price_basis", "knowledge_exposure"}
    assert digest(definition("research", new)) != original["research_version"]


def test_v2_binding_identity_is_preserved_after_v3_transition():
    profile = ModelProfile.model_validate_json((ROOT / "configs/research/openai_gpt54_mini.profile.json").read_text())
    original = json.loads((ROOT / "documents/research/evaluations/mini_requirements_20261009/discovery_run.json").read_text())
    for role in ("research", "critic"):
        assert digest(definition(role, profile, contract_version=2)) == original[f"{role}_version"]
