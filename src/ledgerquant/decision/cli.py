"""Operator commands for the non-trading shadow Executor."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine

from ledgerquant.capture.settings import database_url_from_environment
from ledgerquant.integrations.model_providers.openai import OpenAIResponses
from ledgerquant.models.generation import ModelProfile
from ledgerquant.records import digest
from .runner import ShadowRunner
from .shadow import CONTRACT_VERSION, SHADOW_INSTRUCTIONS, SHADOW_TOOL
from .store import ShadowStore
from .access import provision_shadow_worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    provision = commands.add_parser("provision-worker")
    provision.add_argument("--password-file", required=True)
    schedule = commands.add_parser("schedule")
    schedule.add_argument("--feed-id", required=True)
    schedule.add_argument("--symbol", required=True)
    schedule.add_argument("--at", required=True, help="Future ISO-8601 time with UTC offset")
    schedule.add_argument("--profile", required=True)
    run = commands.add_parser("run")
    run.add_argument("--id", required=True)
    show = commands.add_parser("show")
    show.add_argument("--id", required=True)
    args = parser.parse_args()

    store = ShadowStore(create_engine(database_url_from_environment(), pool_pre_ping=True))
    if args.command == "provision-worker":
        provision_shadow_worker(store.engine, Path(args.password_file))
        print(json.dumps({"role": "ledgerquant_shadow_worker", "status": "provisioned"}))
    elif args.command == "schedule":
        at = datetime.fromisoformat(args.at)
        profile = ModelProfile.model_validate_json(Path(args.profile).read_text())
        config = {
            "contract_version": CONTRACT_VERSION,
            "model_profile": profile.model_dump(mode="json"),
            "instructions_sha256": digest(SHADOW_INSTRUCTIONS),
            "tool_schema_sha256": digest(SHADOW_TOOL),
            "max_start_delay_seconds": 120,
            "max_quote_age_seconds": 10,
            "horizon_minutes": 60,
            "expiry_minutes": 5,
            "max_usd": 1,
        }
        result = store.schedule(args.feed_id, args.symbol, at, config)
        print(json.dumps({"opportunity_id": str(result["id"]),
                          "scheduled_at": result["scheduled_at"].isoformat(),
                          "config_sha256": result["config_sha256"]}))
    elif args.command == "run":
        opportunity_id = UUID(args.id)
        config = store.opportunity(opportunity_id)["config"]
        profile = ModelProfile.model_validate(config["model_profile"])
        key_path = os.getenv("OPENAI_API_KEY_FILE")
        key = Path(key_path).read_text().strip() if key_path else os.environ.get("OPENAI_API_KEY", "")
        provider = OpenAIResponses(profile, key)
        print(json.dumps(ShadowRunner(store, provider).run(opportunity_id)))
    else:
        opportunity_id = UUID(args.id)
        events = store.events(opportunity_id)
        print(json.dumps({"opportunity_id": str(opportunity_id), "events": events},
                         default=str, sort_keys=True))


if __name__ == "__main__":
    main()
