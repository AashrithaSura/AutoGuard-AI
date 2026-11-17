"""Optional LLM transport for the assistant.

Supports any OpenAI-compatible chat-completions endpoint and a local Ollama
server.  No SDK is required, which keeps the capstone installable offline.
The assistant always has a deterministic fallback, so this module is allowed
to fail softly.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_ENABLED,
    LLM_MODEL,
    LLM_TIMEOUT,
    OLLAMA_MODEL,
    OLLAMA_URL,
)


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        ollama_url: str | None = None,
        ollama_model: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else LLM_API_KEY).strip()
        self.base_url = (base_url if base_url is not None else LLM_BASE_URL).rstrip("/")
        self.model = (model if model is not None else LLM_MODEL).strip()
        self.ollama_url = (ollama_url if ollama_url is not None else OLLAMA_URL).rstrip("/")
        self.ollama_model = (ollama_model if ollama_model is not None else OLLAMA_MODEL).strip()
        self.timeout = float(timeout if timeout is not None else LLM_TIMEOUT)
        self.enabled = LLM_ENABLED if enabled is None else enabled

    @property
    def provider(self) -> str:
        if self.ollama_url:
            return "ollama"
        if self.api_key:
            return "openai-compatible"
        return "local"

    @property
    def active_model(self) -> str:
        return self.ollama_model if self.ollama_url else self.model

    @property
    def available(self) -> bool:
        return bool(self.enabled and (self.ollama_url or self.api_key))

    def status(self) -> dict:
        return {
            "available": self.available,
            "provider": self.provider,
            "model": self.active_model if self.available else "",
            "mode": "llm" if self.available else "local",
        }

    def complete(self, system: str, user: str, max_tokens: int = 500) -> LLMResult:
        if not self.available:
            raise LLMError("No LLM is configured. Set AUTOGUARD_LLM_API_KEY or AUTOGUARD_OLLAMA_URL.")
        if self.ollama_url:
            return self._ollama(system, user, max_tokens)
        return self._openai(system, user, max_tokens)

    def _openai(self, system: str, user: str, max_tokens: int) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:
                pass
            raise LLMError(f"LLM request failed with HTTP {exc.code}. {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM returned an unexpected response shape.") from exc
        cleaned = str(text).strip()
        if not cleaned:
            raise LLMError("LLM returned an empty response.")
        return LLMResult(text=cleaned, model=self.model, provider="openai-compatible")

    def _ollama(self, system: str, user: str, max_tokens: int) -> LLMResult:
        payload = {
            "model": self.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }
        request = urllib.request.Request(
            f"{self.ollama_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        try:
            text = body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError("Ollama returned an unexpected response shape.") from exc
        cleaned = str(text).strip()
        if not cleaned:
            raise LLMError("Ollama returned an empty response.")
        return LLMResult(text=cleaned, model=self.ollama_model, provider="ollama")
