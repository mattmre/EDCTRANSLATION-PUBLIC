from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import pytest

from edc_translation.llm_live import (
    LIVE_SMOKE_ENV,
    gemini_provider_config_status,
    local_provider_config_status,
    openrouter_provider_config_status,
    smoke_provider,
)


@pytest.mark.parametrize(
    ("provider_id", "status_func"),
    [
        ("local_openai_compat", local_provider_config_status),
        ("openrouter_llm", openrouter_provider_config_status),
        ("google_gemini", gemini_provider_config_status),
    ],
)
def test_live_provider_smoke_is_tiny_and_opt_in(
    provider_id: str,
    status_func: Callable[[], dict[str, Any]],
) -> None:
    if os.environ.get(LIVE_SMOKE_ENV) != "1":
        pytest.skip(f"{LIVE_SMOKE_ENV}=1 is required for live provider smoke tests")

    status = status_func()
    if not status["configured"]:
        pytest.skip(status["reason"])

    result = smoke_provider(
        provider_id,
        source_language="en",
        target_language="fr",
        text="Hello.",
        max_tokens=64,
    )

    assert result["attempted"] is True
    assert result["success"] is True
    assert result["model_id"]
    assert result["latency_ms"] is not None
