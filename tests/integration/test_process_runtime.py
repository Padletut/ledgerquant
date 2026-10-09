from pathlib import Path
from uuid import uuid4
import json

from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.process_runtime import ProcessRunner, checklist
from ledgerquant.models.generation import Generation, ToolCall
from ledgerquant.research.bootstrap import bootstrap
from ledgerquant.research.imports import load_legacy_bundle, LEGACY_IDS
from ledgerquant.research.process_evaluation import schedule, score, compact_report
from ledgerquant.research.types import canonical
from tests.integration.test_research_registry import registered
from tests.integration.test_agent_runtime import Scripted
from tests.unit.test_process_evaluation import suite


class ProcessTransport(Scripted):
    def invoke(self, request):
        if self.count == 0:
            return super().invoke(request)
        self.count += 1
        context = json.loads(request["input"][0]["content"])
        version = 3 if "grounding" in context else 2 if "requirement_rules" in context else 1
        answer = checklist(context["proposal"], LEGACY_IDS, version, context.get("grounding"))
        return Generation("COMPLETED", {"fixture": True}, [],
                          (ToolCall("test", "submit_process_assessment", canonical(answer)),), 100, 100)


def test_three_process_arms_are_real_or_explicitly_deterministic(registered):
    registry, _, profile = registered
    config = bootstrap(registry, load_legacy_bundle(Path(__file__).parents[2]), profile,
        CampaignPolicy(max_runs=3, max_invocations=6, max_reserved_tokens=200000, max_usd=1),
        "process-test-" + uuid4().hex, "process_review")
    reports = []
    for task in schedule(suite())[:3]:
        provider = ProcessTransport(profile, {})
        report = ProcessRunner(registry, provider).run(config, uuid4().hex, task)
        expected_calls = {"single": 2, "critic": 3, "checklist": 0}[task["arm"]]
        assert provider.count == expected_calls
        assert report["events"][-1]["kind"] == "PROCESS_RESULT"
        for invocation in report["invocations"]:
            assert '"reference"' not in canonical(invocation["request"])
            if invocation["request"]["tools"][0]["name"] == "submit_process_assessment":
                context = json.loads(invocation["request"]["input"][0]["content"])
                assert "known_duplicate_hours" not in context
                assert context["known_duplicate_diagnostics"][0]["hours_utc"] == [8, 12, 16]
        reports.append(compact_report(task, report))
    scored = score(suite(), reports)
    assert sum(row["correct"] for row in scored["rows"]) == 3
    assert sum(row["missing_or_failed"] for row in scored["rows"]) == 33

    from ledgerquant.research.process_corrections import invalidate_suite
    invalidate_suite(registry, reports[0]["task"]["suite_sha256"], "fixture context defect", "test_operator")
    replay = registry.report(reports[0]["run_id"])
    assert replay["current_integrity"]["status"] == "INVALID"
    reports[0] = compact_report(reports[0]["task"], replay)
    corrected = score(suite(), reports)
    assert corrected["integrity"] == "INVALID"
    assert corrected["summary"][0]["task_mean_accuracy"] is None


def test_scoped_process_binding_and_schema(registered):
    registry, _, profile = registered
    config = bootstrap(registry, load_legacy_bundle(Path(__file__).parents[2]), profile,
        CampaignPolicy(max_runs=3, max_invocations=6, max_reserved_tokens=200000, max_usd=1),
        "scoped-process-" + uuid4().hex, "process_review", contract_version=2)
    frozen = json.loads((Path(__file__).parents[2] / "configs/research/contract_requirements_suite.json").read_text())
    for task in schedule(frozen)[:3]:
        provider = ProcessTransport(profile, {})
        report = ProcessRunner(registry, provider).run(config, uuid4().hex, task)
        assert report["events"][-1]["kind"] == "PROCESS_RESULT"
        assert report["events"][-1]["detail"]["answer"]["disposition"] == "REVIEW"
        assert all('"reference"' not in canonical(i["request"]) for i in report["invocations"])


def test_grounded_process_freezes_context_and_does_not_duplicate_raw_evidence(registered):
    from ledgerquant.research.grounding import build_context
    from ledgerquant.research.registry import now
    from ledgerquant.research import tables as t
    from tests.unit.test_grounded_proposals import grounded_payload
    registry, _, profile = registered
    config = bootstrap(registry, load_legacy_bundle(Path(__file__).parents[2]), profile,
        CampaignPolicy(max_runs=1, max_invocations=3, max_reserved_tokens=200000, max_usd=1),
        "grounded-process-" + uuid4().hex, "process_review", contract_version=3)
    manifest = registry.read(registry.get(t.snapshots, config["snapshot_id"])["manifest_id"])
    with registry.engine.connect() as c:
        context = build_context(c, manifest, now(), "before-run")
    proposal = grounded_payload(context)
    proposal["evidence_ids"] = list(LEGACY_IDS)
    task = {"arm": "critic", "feedback": "structured", "proposal": proposal}
    report = ProcessRunner(registry, ProcessTransport(profile, {})).run(config, uuid4().hex, task)
    assert report["events"][-1]["detail"]["answer"]["disposition"] == "REVIEW"
    for invocation in report["invocations"][1:]:
        sent = json.loads(invocation["request"]["input"][0]["content"])
        assert "released_evidence" not in sent
        assert sent["grounding"]["facts"] == context["facts"]
