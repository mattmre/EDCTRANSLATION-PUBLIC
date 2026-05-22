"""HTTP wrapper for the EDC_TRANSLATION MCP-style tool surface."""

from __future__ import annotations

import argparse
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from edc_translation.auth import Principal
from edc_translation.auth_middleware import (
    PrincipalAuthMiddleware,
    current_principal,
    require_route_scope,
)
from edc_translation.mcp import call_tool, list_tools


class ToolCallRequest(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="EDC_TRANSLATION MCP HTTP", version="0.1.0")
app.add_middleware(PrincipalAuthMiddleware)


@app.get("/healthz")
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/mcp/tools")
def http_list_tools(
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    return list_tools()


@app.post("/mcp/call")
def http_call_tool(
    payload: ToolCallRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    return call_tool(payload.name, payload.arguments, principal=principal)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edc-translation-mcp-http")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--reload", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    uvicorn.run(
        "edc_translation.mcp_http:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
