#!/usr/bin/env python3
"""probe-mcp: a tiny stdio MCP server with one `echo` tool, for the MCP-matcher probe (M2).

Rendered into throwaway probe projects only (script install: repo/.claude/probe-mcp/, declared in repo/.mcp.json;
plugin install: probe-plugin/mcp/, declared in probe-plugin/.mcp.json). Standard library only, Python 3.8+.

Transport: newline-delimited JSON-RPC 2.0 on stdin and stdout. Handles initialize, ping, tools/list and tools/call;
notifications get no reply. Nothing is logged: the probe's PreToolUse recorder captures the calls.
"""
from __future__ import annotations

import json
import sys
from typing import Optional

SERVER_NAME = "probe-mcp"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
ECHO_TOOL = {
    "name": "echo",
    "description": "Return the given text unchanged.",
    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
}


class RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def initialize(params: dict) -> dict:
    requested = params.get("protocolVersion")
    version = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
    return {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}


def call_tool(params: dict) -> dict:
    if params.get("name") != ECHO_TOOL["name"]:
        raise RpcError(INVALID_PARAMS, f"unknown tool: {params.get('name')!r}")
    arguments = params.get("arguments") or {}
    text = arguments.get("text") if isinstance(arguments, dict) else None
    if not isinstance(text, str):
        raise RpcError(INVALID_PARAMS, "echo needs a string argument 'text'")
    return {"content": [{"type": "text", "text": text}], "isError": False}


HANDLERS = {
    "initialize": initialize,
    "ping": lambda params: {},
    "tools/list": lambda params: {"tools": [ECHO_TOOL]},
    "tools/call": call_tool,
}


def handle(message: object) -> Optional[dict]:
    """Return the reply for one message, or None for a notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": INVALID_REQUEST, "message": "invalid request"}}
    if "id" not in message:
        return None
    params = message.get("params") or {}
    try:
        handler = HANDLERS.get(message["method"])
        if handler is None:
            raise RpcError(METHOD_NOT_FOUND, f"method not found: {message['method']}")
        if not isinstance(params, dict):
            raise RpcError(INVALID_PARAMS, "params must be an object")
        return {"jsonrpc": "2.0", "id": message["id"], "result": handler(params)}
    except RpcError as err:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": err.code, "message": err.message}}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> int:
    for line in stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": PARSE_ERROR, "message": "parse error"}}
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(serve())
