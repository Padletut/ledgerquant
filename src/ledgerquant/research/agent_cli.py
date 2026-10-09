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
    for name in ("bundle", "policy", "campaign"):
        register.add_argument("--" + name, required=True)
    register.add_argument("--workflow", choices=["discovery", "process_review"], default="discovery")
    register.add_argument("--contract-version", type=int, choices=[1, 2, 3], default=3,
                          help="New registrations use v3; v1/v2 remain explicit for historical execution.")
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
    invalidation = commands.add_parser("invalidate")
    for name in ("evidence-id", "reason", "actor"):
        invalidation.add_argument("--" + name, required=True)
    correction = commands.add_parser("invalidate-process")
    for name in ("suite-sha256", "reason", "actor"):
        correction.add_argument("--" + name, required=True)
    return cli


def main():
    args = parser().parse_args()
    if args.command == "export-legacy":
        print(json.dumps(load_legacy_bundle(Path(args.root)), sort_keys=True))
        return
    engine = create_engine(database_url_from_environment(), echo=False)
    registry = Registry(engine)
    try:
        if args.command == "register":
            result = bootstrap(registry, read(args.bundle), ModelProfile.model_validate(read(args.profile)),
                               CampaignPolicy.model_validate(read(args.policy)), args.campaign, args.workflow, args.contract_version)
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
