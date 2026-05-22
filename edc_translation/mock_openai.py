"""Small OpenAI-compatible endpoint for local stack smoke tests."""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field


MODEL_ID = "mock-translation-smoke"

app = FastAPI(title="EDC_TRANSLATION Local OpenAI-Compatible Smoke Endpoint")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage] = Field(default_factory=list)
    max_tokens: int = 64
    temperature: float = 0


@app.get("/healthz")
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "created": now,
                "owned_by": "edc_translation_local",
            }
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(payload: ChatCompletionRequest) -> dict[str, Any]:
    user_text = next(
        (
            message.content
            for message in reversed(payload.messages)
            if message.role == "user"
        ),
        "",
    )
    translated = _deterministic_translation(user_text)
    return {
        "id": f"chatcmpl-edc-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": translated},
                "finish_reason": "stop",
            }
        ],
    }


def _deterministic_translation(prompt: str) -> str:
    if "Translate this sentence." in prompt:
        return "Traduisez cette phrase."
    if "Hello" in prompt:
        return "Bonjour."
    return "Traduction locale de validation."
