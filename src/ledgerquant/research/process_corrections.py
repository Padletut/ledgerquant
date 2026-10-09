"""Operator invalidation of process contexts without erasing their measurements."""

from sqlalchemy import select

from . import tables as t
from .registry import RegistryError


def invalidate_suite(registry, suite_sha256, reason, actor):
    if not reason.strip() or not actor.strip():
        raise RegistryError("process correction requires actor and reason")
    with registry.engine.connect() as c:
        runs = [dict(row) for row in c.execute(select(t.runs)).mappings()]
    affected = []
    for run in runs:
        task = registry.read(run["task_id"])
        if task.get("suite_sha256") == suite_sha256:
            registry.event(run["id"], "PROCESS_CONTEXT_INVALIDATED", {"suite_sha256": suite_sha256,
                "reason": reason, "actor": actor, "current_support": "INVALID",
                "original_output_retained": True, "task_exposure": "CONSUMED"})
            affected.append(run["id"])
    return {"affected_runs": affected, "status": "INVALIDATED"}
