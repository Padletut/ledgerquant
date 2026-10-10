"""Explicit operator and worker commands for the bounded research loop."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine

from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.runtime import Runner
from ledgerquant.capture.settings import database_url_from_environment
from ledgerquant.models.generation import ModelProfile
from ledgerquant.integrations.model_providers.openai import OpenAIResponses
from .access import provision_worker
from .admission import Admission, admit
from .bootstrap import bootstrap, invalidate_evidence
from .imports import load_legacy_bundle
from .registry import Registry


def read(path):
    return json.loads(Path(path).read_text())


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export-legacy")
    export.add_argument("--root", required=True)
    register = commands.add_parser("register")
    register.add_argument("--bundle", help="Required for diagnostic and process-review registrations.")
    for name in ("policy", "campaign"):
        register.add_argument("--" + name, required=True)
    register.add_argument("--workflow", choices=["discovery", "process_review", "idea_exploration"], default="discovery")
    register.add_argument("--contract-version", type=int, choices=[1, 2, 3],
                          help="Defaults to v3 for existing workflows and v1 for idea exploration.")
    worker = commands.add_parser("provision-worker")
    worker.add_argument("--password-file", required=True)
    run = commands.add_parser("run")
    for name in ("config", "command-key", "task"):
        run.add_argument("--" + name, required=True)
    run.add_argument("--process-review", action="store_true")
    suite = commands.add_parser("process-suite")
    for name in ("config", "tasks"):
        suite.add_argument("--" + name, required=True)
    profile_file = os.getenv("MODEL_PROFILE_FILE") or None
    for command in (register, run, suite):
        command.add_argument("--profile", default=profile_file, required=profile_file is None,
                             help="Model profile JSON; defaults to explicitly configured MODEL_PROFILE_FILE.")
    replay = commands.add_parser("replay")
    replay.add_argument("--run-id", required=True)
    admission = commands.add_parser("admit")
    admission.add_argument("--decision", required=True)
    review_correction = commands.add_parser("correct-contract-review")
    review_correction.add_argument("--decision", required=True)
    packet = commands.add_parser("process-packet", help="Export the sealed pre-action packet an assessor may review.")
    packet.add_argument("--run-id", required=True)
    packet.add_argument("--role", choices=["research", "critic"], required=True)
    process_review = commands.add_parser("process-review", help="Read an assessment with exact source excerpts; does not approve it.")
    process_review.add_argument("--assessment-id", required=True)
    process_review.add_argument("--format", choices=["markdown", "json"], default="markdown")
    assessment = commands.add_parser("assess-process", help="Append an operator process assessment of one recorded action.")
    assessment.add_argument("--decision", required=True)
    feedback = commands.add_parser("record-feedback", help="Append typed research feedback derived from recorded sources.")
    feedback.add_argument("--decision", required=True)
    selection = commands.add_parser("select-feedback", help="Show what a feedback policy would supply at a cutoff.")
    selection.add_argument("--policy", required=True)
    selection.add_argument("--cutoff", default=None, help="ISO-8601 UTC cutoff; defaults to now.")
    invalidation = commands.add_parser("invalidate")
    for name in ("evidence-id", "reason", "actor"):
        invalidation.add_argument("--" + name, required=True)
    correction = commands.add_parser("invalidate-process")
    for name in ("suite-sha256", "reason", "actor"):
        correction.add_argument("--" + name, required=True)
    return cli


def main():
    cli = parser()
    args = cli.parse_args()
    if args.command == "register" and args.workflow != "idea_exploration" and not args.bundle:
        cli.error("--bundle is required for diagnostic and process-review registrations")
    if args.command == "register" and args.workflow == "idea_exploration" and args.bundle:
        cli.error("--bundle is not used for idea exploration")
    if args.command == "export-legacy":
        print(json.dumps(load_legacy_bundle(Path(args.root)), sort_keys=True))
        return
    engine = create_engine(database_url_from_environment(), echo=False)
    registry = Registry(engine)
    try:
        if args.command == "register":
            version = args.contract_version or (1 if args.workflow == "idea_exploration" else 3)
            result = bootstrap(registry, read(args.bundle) if args.bundle else None,
                               ModelProfile.model_validate(read(args.profile)),
                               CampaignPolicy.model_validate(read(args.policy)), args.campaign, args.workflow, version)
        elif args.command == "provision-worker":
            provision_worker(engine, Path(args.password_file))
            result = {"worker_role": "ledgerquant_research_worker", "status": "provisioned"}
        elif args.command in {"run", "process-suite"}:
            key_path = os.getenv("OPENAI_API_KEY_FILE")
            key = Path(key_path).read_text().strip() if key_path else os.environ.get("OPENAI_API_KEY", "")
            provider = OpenAIResponses(ModelProfile.model_validate(read(args.profile)), key)
            from ledgerquant.agents.process_runtime import ProcessRunner
            if args.command == "process-suite":
                from .process_evaluation import compact_report
                from .types import digest
                from .registry import BudgetExceeded
                result = []
                for task in read(args.tasks):
                    try:
                        report = ProcessRunner(registry, provider).run(read(args.config), "process-" + digest(task), task)
                    except BudgetExceeded:
                        break
                    result.append(compact_report(task, report))
            else:
                runner = ProcessRunner if args.process_review else Runner
                result = runner(registry, provider).run(read(args.config), args.command_key, read(args.task))
        elif args.command == "replay":
            result = registry.report(args.run_id)
        elif args.command == "admit":
            result = admit(registry, Admission.model_validate(read(args.decision)))
        elif args.command == "correct-contract-review":
            from .review_corrections import ReviewCorrection, correct_review
            result = correct_review(registry, ReviewCorrection.model_validate(read(args.decision)))
        elif args.command == "process-packet":
            from .process_assessment import sealed_packet
            from .types import digest
            with engine.connect() as connection:
                packet = sealed_packet(connection, args.run_id, args.role)
            result = {"packet_sha256": digest(packet), "packet": packet}
        elif args.command == "process-review":
            from sqlalchemy import text
            from .process_review import review_process, render_process_review
            with engine.connect() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                result = review_process(connection, args.assessment_id)
            if args.format == "markdown":
                print(render_process_review(result), end="")
                return
        elif args.command == "assess-process":
            from .process_assessment import ProcessAssessment, assess_process
            result = assess_process(registry, ProcessAssessment.model_validate(read(args.decision)))
        elif args.command == "record-feedback":
            from .feedback import Feedback, record_feedback
            result = record_feedback(registry, Feedback.model_validate(read(args.decision)))
        elif args.command == "select-feedback":
            from datetime import datetime
            from .feedback import FeedbackPolicy, select_feedback
            from .registry import now
            cutoff = datetime.fromisoformat(args.cutoff) if args.cutoff else now()
            with engine.connect() as connection:
                items, manifest = select_feedback(connection, FeedbackPolicy.model_validate(read(args.policy)), cutoff)
            result = {"items": items, "manifest": manifest}
        elif args.command == "invalidate-process":
            from .process_corrections import invalidate_suite
            result = invalidate_suite(registry, args.suite_sha256, args.reason, args.actor)
        else:
            result = invalidate_evidence(registry, args.evidence_id, args.reason, args.actor)
        print(json.dumps(result, sort_keys=True, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
