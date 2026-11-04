"""One result contract for all service adapters."""
from datetime import datetime, timezone
from uuid import uuid4

EXIT_CODES = {"verified": 0, "partial": 2, "unavailable": 3, "error": 4}


def result(operation, status, *, data=None, reason=None, source=None, request_id=None,
           complete=False):
    value = {
        "schema": "ios-control-bridge.result.v1",
        "operation": operation,
        "request_id": request_id or str(uuid4()),
        "status": status,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "complete_for_scope": bool(complete),
    }
    if data is not None:
        value["data"] = data
    if reason:
        value["reason"] = reason
    if source:
        value["source"] = source
    return value
