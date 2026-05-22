"""Shared structured error payloads for EDC_TRANSLATION surfaces."""

from __future__ import annotations

from typing import Any

AUTO_ROUTE_UNAVAILABLE = "auto_route_unavailable"


def auto_route_unavailable_message(
    source_language: str,
    target_language: str,
    diagnostics: dict[str, object],
) -> str:
    """Build the stable human-readable message for failed auto routing."""

    detail = "; ".join(
        f"{candidate['id']}: {candidate['reason']}"
        for candidate in diagnostics.get("candidates", [])
        if isinstance(candidate, dict)
    )
    if not detail:
        detail = "no candidate engines configured"
    return (
        "No auto-routeable translation engine for "
        f"{source_language}->{target_language}: {detail}"
    )


def auto_route_error_payload(
    message: str,
    diagnostics: dict[str, object],
) -> dict[str, Any]:
    """Return the stable API/CLI/MCP error payload for failed auto routing."""

    return {
        "error": {
            "code": AUTO_ROUTE_UNAVAILABLE,
            "message": message,
            "routing_diagnostics": diagnostics,
        }
    }
