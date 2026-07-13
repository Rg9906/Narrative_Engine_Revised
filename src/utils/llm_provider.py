"""
LLM Provider — System-wide LLM abstraction layer.

Provides a unified interface to call LLM chat completions across multiple
backends. The provider auto-detects available API keys and routes requests
to the first available backend in priority order:

    1. Gemini  (env: GEMINI_API_KEY)
    2. Groq    (env: GROQ_API_KEY)
    3. Ollama  (auto-detected at localhost:11434, or env: OLLAMA_MODEL / OLLAMA_API_URL)

All backends use the OpenAI-compatible messages format. Zero external
dependencies — uses only stdlib `urllib.request` and `json`.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("NarrativeEngine.Utils.LLMProvider")


class LLMProvider:
    """Centralized LLM provider with automatic backend detection.

    Usage::

        llm = LLMProvider()
        if llm.is_available:
            response_text = llm.chat([
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ])
    """

    # Backend configuration defaults
    _BACKENDS = {
        "gemini": {
            "env_key": "GEMINI_API_KEY",
            "url": "https://generativelanguage.googleapis.com/v1beta/chat/completions",
            "default_model": "gemini-2.0-flash",
            "config_model_key": "llm.gemini_model",
        },
        "groq": {
            "env_key": "GROQ_API_KEY",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "default_model": "llama-3.3-70b-versatile",
            "config_model_key": "llm.groq_model",
        },
    }

    def __init__(self, config=None):
        self._config = config
        self._provider: Optional[str] = None
        self._api_key: Optional[str] = None
        self._url: Optional[str] = None
        self._model: Optional[str] = None
        self._temperature: float = 0.2

        # Load temperature from config if available
        if config and hasattr(config, "get"):
            temp = config.get("llm.temperature")
            if temp is not None:
                try:
                    self._temperature = float(temp)
                except (ValueError, TypeError):
                    pass

        self._detect_backend()

    def _detect_backend(self) -> None:
        """Detect the first available LLM backend in priority order."""
        # 1. Check Gemini
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            backend = self._BACKENDS["gemini"]
            self._provider = "gemini"
            self._api_key = gemini_key
            self._url = backend["url"]
            self._model = self._get_model("gemini", backend)
            logger.info(f"LLM provider detected: Gemini (model: {self._model})")
            return

        # 2. Check Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            backend = self._BACKENDS["groq"]
            self._provider = "groq"
            self._api_key = groq_key
            self._url = backend["url"]
            self._model = self._get_model("groq", backend)
            logger.info(f"LLM provider detected: Groq (model: {self._model})")
            return

        # 3. Check Ollama (local)
        ollama_model = os.environ.get("OLLAMA_MODEL")
        ollama_url = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
        ollama_default_model = "llama3"
        if self._config and hasattr(self._config, "get"):
            ollama_default_model = self._config.get("llm.ollama_model", "llama3") or "llama3"
            configured_url = self._config.get("llm.ollama_url")
            if configured_url:
                ollama_url = configured_url

        if ollama_model or os.environ.get("OLLAMA_API_URL") or self._check_ollama_alive(ollama_url):
            self._provider = "ollama"
            self._api_key = None
            self._url = f"{ollama_url}/api/chat"
            self._model = ollama_model or ollama_default_model
            logger.info(f"LLM provider detected: Ollama (model: {self._model}, url: {ollama_url})")
            return

        logger.info("No LLM provider detected. LLM critique will be skipped.")

    def _get_model(self, provider_name: str, backend: Dict[str, Any]) -> str:
        """Resolve model name from config → env → default."""
        # Check config first
        if self._config and hasattr(self._config, "get"):
            config_model = self._config.get(backend["config_model_key"])
            if config_model:
                return config_model
        return backend["default_model"]

    @staticmethod
    def _check_ollama_alive(url: str) -> bool:
        """Check if local Ollama server is responding."""
        try:
            with urllib.request.urlopen(url, timeout=1.5) as res:
                return res.status == 200
        except Exception:
            return False

    @property
    def provider_name(self) -> str:
        """Return the active provider name, or 'none'."""
        return self._provider or "none"

    @property
    def is_available(self) -> bool:
        """Whether any LLM backend was detected."""
        return self._provider is not None

    @property
    def model(self) -> Optional[str]:
        """The active model name."""
        return self._model

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> str:
        """Send a chat completion request and return the raw text response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Override the default temperature for this call.

        Returns:
            The assistant's response text.

        Raises:
            RuntimeError: If no LLM provider is available.
            Exception: If the API request fails.
        """
        if not self.is_available:
            raise RuntimeError("No LLM provider available. Set GEMINI_API_KEY or GROQ_API_KEY.")

        temp = temperature if temperature is not None else self._temperature

        if self._provider == "ollama":
            return self._call_ollama(messages, temp)
        else:
            return self._call_openai_compatible(messages, temp)

    def _call_openai_compatible(self, messages: List[Dict[str, str]], temperature: float) -> str:
        """Call an OpenAI-compatible API (Gemini, Groq)."""
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        req = urllib.request.Request(self._url, data=data, headers=headers)

        logger.info(f"Calling {self._provider} API (model: {self._model})...")
        with urllib.request.urlopen(req, timeout=30) as res:
            response_json = json.loads(res.read().decode("utf-8"))

        # Standard OpenAI-compatible response format
        return response_json["choices"][0]["message"]["content"].strip()

    def _call_ollama(self, messages: List[Dict[str, str]], temperature: float) -> str:
        """Call the local Ollama API."""
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
        )

        logger.info(f"Calling Ollama API (model: {self._model})...")
        with urllib.request.urlopen(req, timeout=60) as res:
            response_json = json.loads(res.read().decode("utf-8"))

        return response_json["message"]["content"].strip()
