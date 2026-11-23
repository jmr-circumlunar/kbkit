"""Stdio MCP tools and their JSON contracts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from inspect import signature

from . import __version__
from .application import ApplicationService
from .audit import AUDIT_CATEGORIES, AUDIT_DISPOSITIONS
from .paging import MAX_PAYLOAD_BYTES, json_size
from .profile import QueryError
from .selector import SelectorError
from .transaction import PendingTransactionError, TransactionError


SUPPORTED_PROTOCOLS = ("2025-11-25", "2025-06-18")
STRING = {"type": "string"}
INTEGER = {"type": "integer"}
BOOLEAN = {"type": "boolean"}
STRINGS = {"type": "array", "items": STRING, "minItems": 1, "maxItems": 50}
TEXT_FILTER = {"anyOf": [STRING, STRINGS]}
LINES = {"type": "array", "items": INTEGER, "minItems": 2, "maxItems": 2}
WINDOW = {"limit": INTEGER, "offset": INTEGER, "max_bytes": INTEGER}


def obj(properties, *required):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


SELECTOR = obj({"path": STRING, "heading_path": STRINGS, "block_id": STRING,
                "line_range": {"anyOf": [STRING, LINES]}})
OPERATIONS = {"type": "array", "minItems": 1, "maxItems": 50, "items": obj({
    "operation": {"type": "string", "enum": ["create", "append", "replace", "insert", "delete", "move", "rename", "set_prop"]},
    "path": STRING, "selector": SELECTOR, "content": STRING, "expected_hash": STRING,
    "position": {"type": "string", "enum": ["start", "end"]},
    "template": STRING, "variables": {"type": "object", "additionalProperties": STRING},
    "destination": STRING, "property": STRING, "value": STRING,
}, "operation")}


@dataclass(frozen=True)
class Tool:
    method: str
    description: str
    schema: dict


TOOLS = {
    "kb_status": Tool("status", "Inspect the vault profile, lifecycle counts and knowledge freshness.", obj(WINDOW)),
    "kb_index": Tool("index", "Verify Markdown content hashes and synchronize the derived index.", obj({})),
    "kb_sync": Tool("sync", "Check for external Markdown edits and incrementally update the local index.", obj({})),
    "kb_search": Tool("search", "Search Markdown blocks with metadata filters and bounded results.", obj({
        **WINDOW, "query": STRING, "include_inactive": BOOLEAN, "include_excluded": BOOLEAN, "max_chars": INTEGER, "select": STRING,
        "path": TEXT_FILTER, "kind": TEXT_FILTER, "state": TEXT_FILTER,
        "tags": {**TEXT_FILTER, "description": "A document must contain all requested tags."},
        "symbols": {**TEXT_FILTER, "description": "A block must match all requested identifiers."},
        "exclude": TEXT_FILTER, "budget_chars": INTEGER,
    })),
    "kb_read": Tool("read", "Read text by path, heading, block ID or source lines.", obj({
        "path": STRING, "heading": STRINGS, "block_id": STRING, "lines": LINES, "max_bytes": INTEGER,
    })),
    "kb_outline": Tool("outline", "List headings with their title paths and source line ranges.", obj({"path": STRING, **WINDOW}, "path")),
    "kb_facet": Tool("facet", "Count documents by path, kind, state or tags.", obj({"dimension": STRING, "path": TEXT_FILTER, **WINDOW})),
    "kb_graph": Tool("graph", "List one collection of wikilink graph data.", obj({"collection": STRING, "path": STRING, **WINDOW})),
    "kb_lint": Tool("lint", "List deterministic vault findings without applying changes.", obj(WINDOW)),
    "kb_check": Tool("check", "Check configured vault gates and return the blocking findings.", obj(WINDOW)),
    "kb_audit_record": Tool("record_audit", "Archive Agent-supplied review results with a stable run UUID.", obj({
        "run_id": STRING, "reviewer": STRING, "scope": STRINGS,
        "findings": {"type": "array", "maxItems": 1000, "items": obj({
            "path": STRING, "category": {"type": "string", "enum": AUDIT_CATEGORIES}, "message": STRING,
            "disposition": {"type": "string", "enum": AUDIT_DISPOSITIONS}, "transaction_id": STRING,
        }, "path", "category", "message", "disposition")},
    }, "run_id", "reviewer", "scope", "findings")),
    "kb_audit_report": Tool("audit_report", "Read a saved review receipt and optionally filter to pending findings.", obj({
        **WINDOW, "run_id": STRING, "disposition": {"type": "string", "enum": AUDIT_DISPOSITIONS},
    }, "run_id")),
    "kb_maintain": Tool("maintain", "Refresh the index and code-bound knowledge, then record findings and authorized mechanical fixes.", obj({
        **WINDOW, "collection": STRING,
        "auto_apply": {"type": "string", "enum": ["none", "safe"], "description": "Set safe only for an authorized run."},
    })),
    "kb_maintenance_report": Tool("maintenance_report", "Read a page of a previously saved maintenance report.",
                                  obj({"run_id": STRING, "collection": STRING, **WINDOW}, "run_id")),
    "kb_proposals": Tool("proposals", "List executable maintenance proposals and their statuses.", obj({"status": STRING, **WINDOW})),
    "kb_proposal_apply": Tool("apply_proposal", "Apply an approved low-risk proposal.", obj({"proposal_id": STRING}, "proposal_id")),
    "kb_write_plan": Tool("plan_operations", "Preview a batch of Markdown writes without changing the vault.",
                          obj({"operations": OPERATIONS, **WINDOW}, "operations")),
    "kb_write_apply": Tool("apply_operations", "Apply a batch. Provide the preview plan_hash and reuse the same UUID request_id for safe retries.",
                           obj({"operations": OPERATIONS, "plan_hash": STRING, "request_id": STRING}, "operations")),
    "kb_write_status": Tool("write_status", "Check a transaction by its transaction ID or write request ID.",
                            obj({"transaction_id": STRING}, "transaction_id")),
    "kb_restore": Tool("restore", "Restore a deleted note if its original path is still free.", obj({"entry_id": STRING}, "entry_id")),
}


def _validate(value, schema, name):
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                _validate(value, option, name)
                return
            except ValueError:
                continue
        raise ValueError(f"{name} does not match an accepted type")
    kind = schema["type"]
    expected = {"string": str, "object": dict, "array": list, "integer": int, "boolean": bool}[kind]
    if type(value) is not expected:
        raise ValueError(f"{name} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{name} must be one of: {', '.join(schema['enum'])}")
    if kind == "object":
        allowed = schema.get("properties", {})
        additional = schema.get("additionalProperties")
        unknown = [] if additional else sorted(set(value) - allowed.keys())
        missing = sorted(set(schema.get("required", ())) - value.keys())
        if unknown or missing:
            raise ValueError(f"{name}: unknown fields {unknown}, missing fields {missing}; allowed fields: {', '.join(allowed)}")
        for key, item in value.items():
            _validate(item, allowed.get(key, additional), key)
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 200):
            raise ValueError(f"{name} has an unsupported number of items")
        for item in value:
            _validate(item, schema["items"], name)
    elif kind == "string":
        value.encode("utf-8")


# Leave room for the JSON-RPC envelope and the escaped request ID.
RESULT_BUDGET = MAX_PAYLOAD_BYTES - 2048


OUTPUT_MODES = ("text", "structured")


def _result(payload, is_error, output):
    if output == "structured":
        return {"isError": is_error, "structuredContent": payload, "content": []}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {"isError": is_error, "content": [{"type": "text", "text": text}]}


def _failure(code, message, hint, *, retryable=False, details=None):
    return ({"code": code, "message": str(message)[:1000], "severity": "error",
             "hint": hint, "retryable": retryable, "details": details or {}}, True)


def _tool_payload(name, arguments, service, output):
    tool = TOOLS[name]
    if service is None:
        return _failure("KB_VAULT_NOT_CONFIGURED", "No vault is configured.",
                        "Set KBKIT_VAULT to the vault directory in the Agent MCP configuration and reconnect.")
    try:
        _validate(arguments, tool.schema, "arguments")
    except (UnicodeError, ValueError) as exc:
        return _failure("KB_ARGUMENT_INVALID", exc, "Call tools/list and use the advertised inputSchema.")
    try:
        action = getattr(service, tool.method)
        if "max_bytes" in tool.schema["properties"]:
            requested = arguments.get("max_bytes")
            if requested is None:
                size_parameter = signature(action).parameters.get("max_bytes")
                requested = size_parameter.default if size_parameter is not None else 36_000
            if requested <= MAX_PAYLOAD_BYTES:
                available = RESULT_BUDGET - 256
                # JSON inside a text block may add one escape per serialized byte.
                budget = available // 2 if output == "text" else available
                arguments = {**arguments, "max_bytes": min(requested, budget)}
        payload = action(**arguments)
    except QueryError as exc:
        code = "KB_QUERY_ENUM_INVALID" if exc.allowed is not None else "KB_QUERY_INVALID"
        hint = "Choose a value from details.allowed." if exc.allowed is not None else "Retry with literal words or a quoted phrase."
        return _failure(code, exc, hint, details={"field": exc.field, "allowed": (exc.allowed or [])[:200]})
    except SelectorError as exc:
        return _failure("KB_SELECTOR_INVALID", exc, "Verify the vault-relative path, then use kb_outline or kb_search to locate the selection.")
    except PendingTransactionError as exc:
        return _failure("KB_WRITE_PENDING", exc, "Inspect kb_write_status, then use kbc recover with the transaction ID.",
                        retryable=True, details={"transaction_id": exc.transaction_id})
    except TransactionError as exc:
        return _failure("KB_WRITE_CONFLICT", exc, "Inspect the current note and use kb_write_plan again before retrying the write.")
    except FileNotFoundError as exc:
        return _failure("KB_NOT_FOUND", exc, "Check the path, proposal or report ID and confirm it is in the active vault.")
    except UnicodeError as exc:
        return _failure("KB_ENCODING_INVALID", exc, "Save the affected note as UTF-8 and retry.")
    except (ValueError, KeyError) as exc:
        return _failure("KB_VALIDATION_FAILED", exc, "Check the field values against tools/list and inspect the vault with kb_status.")
    except (OSError, sqlite3.Error) as exc:
        return _failure("KB_IO_ERROR", exc, "Check vault and index permissions, then try kbc doctor --vault PATH.", retryable=True)
    return payload, False


def _call(name, arguments, service, output):
    payload, is_error = _tool_payload(name, arguments, service, output)
    result = _result(payload, is_error, output)
    if json_size(result) <= RESULT_BUDGET:
        return result
    if is_error:
        return _result({**payload, "details": {}}, True, output)
    if name in {"kb_write_apply", "kb_write_status"}:
        summary = {key: payload[key] for key in ("transaction_id", "state", "index_dirty") if key in payload}
        return _result({**summary, "hint": "Use the CLI write status command to read the full receipt."}, False, output)
    payload, is_error = _failure("KB_RESPONSE_TOO_LARGE", "The result exceeds the response budget.",
                                 "Request a smaller max_bytes or limit for this tool.")
    return _result(payload, is_error, output)


def _protocol_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: object, service: ApplicationService | None = None, *, output: str = "text") -> dict | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _protocol_error(None, -32600, "invalid request")
    if "id" not in message:
        return None
    method = message["method"]
    request_id = message["id"]
    if type(request_id) not in {int, str}:
        return _protocol_error(None, -32600, "invalid request ID")
    if isinstance(request_id, int) and request_id.bit_length() > 256:
        return _protocol_error(None, -32600, "request ID is too long")
    if isinstance(request_id, str):
        try:
            if len(request_id.encode("utf-8")) > 256:
                return _protocol_error(None, -32600, "request ID is too long")
        except UnicodeEncodeError:
            return _protocol_error(None, -32600, "invalid request ID")
    params = message.get("params", {})
    if not isinstance(params, dict):
        return _protocol_error(request_id, -32602, "params must be an object")
    if method == "ping":
        result = {}
    elif method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        result = {"protocolVersion": version, "capabilities": {"tools": {}},
                  "serverInfo": {"name": "kbkit", "version": __version__}}
    elif method == "tools/list":
        result = {"tools": [{"name": name, "description": tool.description, "inputSchema": tool.schema}
                            for name, tool in TOOLS.items()]}
    elif method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in TOOLS:
            return _protocol_error(request_id, -32602, "unknown tool; call tools/list")
        result = _call(name, params.get("arguments", {}), service, output)
    else:
        return _protocol_error(request_id, -32601, "method not found")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
