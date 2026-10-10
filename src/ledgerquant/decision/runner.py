"""One bounded shadow decision per registered opportunity; never dispatches orders."""

import json
from datetime import datetime, timezone

from pydantic import ValidationError

from ledgerquant.models.generation import ModelProfile
from ledgerquant.records import digest
from .shadow import CONTRACT_VERSION, SHADOW_INSTRUCTIONS, SHADOW_TOOL, ShadowDecision, build_context, validate_decision


class ShadowRunner:
    def __init__(self, store, provider):
        self.store = store
        self.provider = provider

    def run(self, opportunity_id):
        opportunity = self.store.opportunity(opportunity_id)
        recorded = self.store.events(opportunity_id)
        if recorded:
            return {"opportunity_id": str(opportunity_id),
                    "status": "RECORDED" if any(e["phase"] == "FINAL" for e in recorded) else "STARTED_UNCERTAIN"}

        config = opportunity["config"]
        profile = ModelProfile.model_validate(config["model_profile"])
        if profile.model_dump(mode="json") != self.provider.profile.model_dump(mode="json"):
            raise ValueError("provider differs from scheduled model profile")
        if config["instructions_sha256"] != digest(SHADOW_INSTRUCTIONS):
            raise ValueError("scheduled instructions differ from running version")
        if config["contract_version"] != CONTRACT_VERSION or config["tool_schema_sha256"] != digest(SHADOW_TOOL):
            raise ValueError("scheduled decision contract differs from running version")

        started_at = datetime.now(timezone.utc)
        delay = (started_at - opportunity["scheduled_at"]).total_seconds()
        if delay < 0:
            raise ValueError("opportunity is not due")
        missed = delay > config["max_start_delay_seconds"]
        rows = [] if missed else self.store.quotes(opportunity["feed_id"], opportunity["symbol"], started_at)
        # The query returns committed rows. Context becomes eligible only after
        # the read completes, even if capture.available_at predates commit.
        decision_at = datetime.now(timezone.utc)
        context = build_context(rows, opportunity["symbol"], decision_at, config["max_quote_age_seconds"])
        if missed:
            context["status"] = "MISSED"

        request = None
        if context["status"] == "READY":
            task = {"context": context, "fixed_horizon_minutes": config["horizon_minutes"],
                    "fixed_expiry_minutes": config["expiry_minutes"]}
            request = self.provider.prepare(SHADOW_INSTRUCTIONS,
                [self.provider.user_message(json.dumps(task, sort_keys=True))], [SHADOW_TOOL])
            # Byte length bounds token count conservatively; use the uncached rate.
            upper_usd = (len(json.dumps(request).encode()) * profile.input_usd_per_million
                         + profile.max_output_tokens * profile.output_usd_per_million) / 1_000_000
            if upper_usd > min(profile.max_run_usd, config["max_usd"]):
                raise ValueError("MODEL_BUDGET_EXCEEDED")

        started = {"context": context, "context_sha256": digest(context),
                   "request": request, "request_sha256": digest(request) if request else None,
                   "model_profile_sha256": digest(config["model_profile"]),
                   "status": context["status"]}
        if not self.store.event(opportunity_id, "STARTED", started):
            return {"opportunity_id": str(opportunity_id), "status": "STARTED_UNCERTAIN"}

        if request is None:
            result = {"status": context["status"], "decision": None, "provider_response": None}
        else:
            generation = None
            try:
                generation = self.provider.invoke(request)
                result = {"status": generation.status, "decision": None,
                          "provider_response": generation.raw,
                          "input_tokens": generation.input_tokens,
                          "output_tokens": generation.output_tokens}
                try:
                    result["returned_model"] = json.loads(generation.raw.get("body", "{}")).get("model")
                except (ValueError, TypeError, AttributeError):
                    result["returned_model"] = None
                if generation.status == "COMPLETED":
                    call = generation.calls[0]
                    if call.name != SHADOW_TOOL["name"]:
                        result["status"] = "WRONG_TOOL"
                    else:
                        decision = ShadowDecision.model_validate(json.loads(call.arguments))
                        result["decision"] = decision.model_dump(mode="json")
                        result["status"] = validate_decision(decision, context,
                            config["horizon_minutes"], config["expiry_minutes"])
                        if result["status"] == "VALID":
                            result["status"] = {"NO_SIGNAL": "NO_SIGNAL", "WAIT": "WAIT"}.get(
                                decision.action, "CANDIDATE")
            except (ValueError, ValidationError, KeyError, IndexError, TypeError):
                result = {"status": "INVALID_MODEL_OUTPUT", "decision": None,
                          "provider_response": generation.raw if generation else None}
            except Exception as exc:
                # The provider may have received the request. Never infer a safe retry.
                result = {"status": "DISPATCH_UNKNOWN", "decision": None,
                          "provider_response": {"error_type": type(exc).__name__}}
        self.store.event(opportunity_id, "FINAL", result)
        return {"opportunity_id": str(opportunity_id), "status": result["status"]}
