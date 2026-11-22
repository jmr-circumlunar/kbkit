"""Stdio MCP tools and their JSON contracts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from . import __version__
from .application import ApplicationService
from .paging import MAX_PAYLOAD_BYTES, json_size
from .profile import QueryError
from .selector import SelectorError
from .transaction import TransactionError


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


SELECTOR = obj({"path": STRING, "heading_path": TEXT_FILTER, "block_id": STRING,
                "line_range": {"anyOf": [STRING, LINES]}})
OPERATIONS = {"type": "array", "minItems": 1, "maxItems": 50, "items": obj({
    "operation": {"type": "string", "enum": ["create", "append", "delete", "move", "rename", "set_prop"]},
    "path": STRING, "selector": SELECTOR, "content": STRING, "expected_hash": STRING,
    "destination": STRING, "property": STRING, "value": STRING,
}, "operation")}


@dataclass(frozen=True)
class Tool:
    method: str
    description: str
    schema: dict


TOOLS = {
    "kb_status": Tool("status", "Inspect the vault profile, lifecycle counts and knowledge freshness.", obj(WINDOW)),
    "kb_index": Tool("index", "Synchronize the derived index with Markdown content.", obj({})),
    "kb_search": Tool("search", "Search Markdown blocks with metadata filters and bounded results.", obj({
        **WINDOW, "query": STRING, "include_inactive": BOOLEAN, "include_excluded": BOOLEAN, "max_chars": INTEGER, "select": STRING,
        "path": TEXT_FILTER, "kind": TEXT_FILTER, "state": TEXT_FILTER, "tags": TEXT_FILTER,
        "symbols": TEXT_FILTER, "exclude": TEXT_FILTER, "budget_chars": INTEGER,
    })),
    "kb_read": Tool("read", "Read text by path, heading, block ID or source lines.", obj({
        "path": STRING, "heading": STRINGS, "block_id": STRING, "lines": LINES, "max_bytes": INTEGER,
    })),
    "kb_outline": Tool("outline", "List headings with their title paths and source line ranges.", obj({"path": STRING, **WINDOW}, "path")),
    "kb_facet": Tool("facet", "Count documents by path, kind, state or tags.", obj({"dimension": STRING, "path": TEXT_FILTER, **WINDOW})),
    "kb_graph": Tool("graph", "List one collection of wikilink graph data.", obj({"collection": STRING, "path": STRING, **WINDOW})),
    "kb_lint": Tool("lint", "List deterministic vault findings without applying changes.", obj(WINDOW)),
    "kb_maintain": Tool("maintain", "Refresh code-bound knowledge and the index, then record governance findings.", obj({**WINDOW, "collection": STRING})),
    "kb_maintenance_report": Tool("maintenance_report", "Read a page of a previously saved maintenance report.",
                                  obj({"run_id": STRING, "collection": STRING, **WINDOW}, "run_id")),
    "kb_proposals": Tool("proposals", "List executable maintenance proposals and their statuses.", obj({"status": STRING, **WINDOW})),
    "kb_proposal_apply": Tool("apply_proposal", "Apply an approved low-risk proposal.", obj({"proposal_id": STRING}, "proposal_id")),
    "kb_write_plan": Tool("plan_operations", "Preview a batch of Markdown writes without changing the vault.",
                          obj({"operations": OPERATIONS}, "operations")),
    "kb_write_apply": Tool("apply_operations", "Apply a batch with an optional plan_hash from the preview.",
                           obj({"operations": OPERATIONS, "plan_hash": STRING}, "operations")),
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
        allowed = schema["properties"]
        unknown = sorted(set(value) - allowed.keys())
        missing = sorted(set(schema.get("required", ())) - value.keys())
        if unknown or missing:
            raise ValueError(f"{name}: unknown fields {unknown}, missing fields {missing}; allowed fields: {', '.join(allowed)}")
        for key, item in value.items():
            _validate(item, allowed[key], key)
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 200):
            raise ValueError(f"{name} has an unsupported number of items")
        for item in value:
            _validate(item, schema["items"], name)
    elif kind == "string":
        value.encode("utf-8")


def _result(payload, is_error=False):
    return {"isError": is_error, "structuredContent": payload,
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]}


def _failure(code, message, hint, *, retryable=False, details=None):
    return _result({"code": code, "message": str(message)[:1000], "severity": "error",
                    "hint": hint, "retryable": retryable, "details": details or {}}, True)


def _call(name, arguments, service):
    tool = TOOLS[name]
    if service is None:
        return _failure("KB_VAULT_NOT_CONFIGURED", "No vault is configured.",
                        "Set KBKIT_VAULT to the vault directory in the Agent MCP configuration and reconnect.")
    try:
        _validate(arguments, tool.schema, "arguments")
    except (UnicodeError, ValueError) as exc:
        return _failure("KB_ARGUMENT_INVALID", exc, "Call tools/list and use the advertised inputSchema.")
    try:
        payload = getattr(service, tool.method)(**arguments)
    except QueryError as exc:
        code = "KB_QUERY_ENUM_INVALID" if exc.allowed is not None else "KB_QUERY_INVALID"
        hint = "Choose a value from details.allowed." if exc.allowed is not None else "Retry with literal words or a quoted phrase."
        return _failure(code, exc, hint, details={"field": exc.field, "allowed": (exc.allowed or [])[:200]})
    except SelectorError as exc:
        return _failure("KB_SELECTOR_INVALID", exc, "Verify the vault-relative path, then use kb_outline or kb_search to locate the selection.")
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
    if json_size(payload) > MAX_PAYLOAD_BYTES:
        return _failure("KB_RESPONSE_TOO_LARGE", "The result exceeds the response budget.",
                        "Use a smaller limit or split the operation preview into smaller batches.")
    return _result(payload)


def _protocol_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: object, service: ApplicationService | None = None) -> dict | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _protocol_error(None, -32600, "invalid request")
    if "id" not in message:
        return None
    method = message["method"]
    request_id = message["id"]
    if type(request_id) not in {int, str}:
        return _protocol_error(None, -32600, "invalid request ID")
    if isinstance(request_id, str):
        try:
            request_id.encode("utf-8")
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
        result = _call(name, params.get("arguments", {}), service)
    else:
        return _protocol_error(request_id, -32601, "method not found")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
