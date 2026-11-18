"""Minimal stdio MCP contract probe used by E2 tests."""

from __future__ import annotations

import sqlite3

from .application import ApplicationService


WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "operation": {"enum": ["create", "append", "delete", "move", "rename"]},
                    "path": {"type": "string", "description": "Vault-relative Markdown path."},
                    "selector": {"type": "object"},
                    "content": {"type": "string"},
                    "expected_hash": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["operation"],
                "anyOf": [{"required": ["path"]}, {"required": ["selector"]}],
                "if": {"properties": {"operation": {"const": "create"}}},
                "then": {"required": ["content"]},
            },
        },
    },
    "required": ["operations"],
}


def handle(message: dict, service: ApplicationService | None = None) -> dict:
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "kbkit", "version": "0.1.0"}}
    elif method == "tools/list":
        result = {"tools": [
            {"name": "kb_status", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
            {"name": "kb_index", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
            {"name": "kb_search", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
            {"name": "kb_read", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "kb_maintain", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
            {"name": "kb_proposals", "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}}}},
            {"name": "kb_write_plan", "inputSchema": WRITE_SCHEMA},
            {"name": "kb_write_apply", "inputSchema": WRITE_SCHEMA},
        ]}
    elif method == "tools/call":
        if service is None:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": "vault service is not configured"}}
        params = message.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            if name == "kb_status":
                payload = service.status()
            elif name == "kb_index":
                payload = service.index()
            elif name == "kb_search":
                if not isinstance(arguments.get("query"), str) or not arguments["query"].strip():
                    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "query must be a non-empty string"}}
                payload = service.search(arguments["query"])
            elif name == "kb_read":
                if not isinstance(arguments.get("path"), str) or not arguments["path"].strip():
                    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "path must be a non-empty string"}}
                payload = service.read(arguments["path"])
            elif name == "kb_maintain":
                payload = service.maintain()
            elif name == "kb_proposals":
                payload = service.proposals(arguments.get("status"))
            elif name == "kb_write_plan":
                if not isinstance(arguments.get("operations"), list):
                    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "operations must be an array"}}
                payload = service.plan_operations(arguments["operations"])
            elif name == "kb_write_apply":
                if not isinstance(arguments.get("operations"), list):
                    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "operations must be an array"}}
                payload = service.apply_operations(arguments["operations"])
            elif name == "kb_graph":
                payload = service.graph()
            elif name == "kb_lint":
                payload = service.lint()
            else:
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "unknown tool"}}
        except (KeyError, ValueError) as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}}
        except (OSError, sqlite3.Error) as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}
        result = {"content": [{"type": "text", "text": str(payload)}]}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
