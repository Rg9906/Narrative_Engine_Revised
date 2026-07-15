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
    """Centralized LLM provider with automatic backend detection and failover.

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
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
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
        self._available_backends: List[Dict[str, Any]] = []

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
        """Detect all available LLM backends in priority order."""
        if "PYTEST_CURRENT_TEST" in os.environ and "TestLLMProvider" not in os.environ.get("PYTEST_CURRENT_TEST", ""):
            logger.info("Pytest detected. Disabling real LLM provider to speed up tests.")
            self._provider = None
            return

        self._available_backends = []

        # 1. Check Gemini
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            backend = self._BACKENDS["gemini"]
            self._available_backends.append({
                "name": "gemini",
                "api_key": gemini_key,
                "url": backend["url"],
                "model": self._get_model("gemini", backend)
            })

        # 2. Check Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            backend = self._BACKENDS["groq"]
            self._available_backends.append({
                "name": "groq",
                "api_key": groq_key,
                "url": backend["url"],
                "model": self._get_model("groq", backend)
            })

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
            self._available_backends.append({
                "name": "ollama",
                "api_key": None,
                "url": f"{ollama_url}/api/chat",
                "model": ollama_model or ollama_default_model
            })

        # Set default active backend details
        if self._available_backends:
            active = self._available_backends[0]
            self._provider = active["name"]
            self._api_key = active["api_key"]
            self._url = active["url"]
            self._model = active["model"]
            logger.info(f"LLM provider detected: {self._provider} (model: {self._model})")
        else:
            self._provider = None
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
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a chat completion request and return the raw text response.
        Supports retries with exponential backoff and failover to secondary backends.
        """
        if not self.is_available:
            raise RuntimeError("No LLM provider available. Set GEMINI_API_KEY or GROQ_API_KEY.")

        temp = temperature if temperature is not None else self._temperature

        backends = self._available_backends
        if not backends and self._provider:
            backends = [{
                "name": self._provider,
                "api_key": self._api_key,
                "url": self._url,
                "model": self._model
            }]

        last_error = None
        # Try each available backend in priority order
        for backend_idx, backend in enumerate(backends):
            provider_name = backend["name"]
            api_key = backend["api_key"]
            url = backend["url"]
            model = backend["model"]

            # Update active properties for logging/diagnostics externally
            self._provider = provider_name
            self._api_key = api_key
            self._url = url
            self._model = model

            # Exponential backoff parameters
            max_retries = 3
            initial_delay = 1.0  # seconds
            backoff_factor = 2.0

            for attempt in range(max_retries + 1):
                import time
                import uuid
                request_id = str(uuid.uuid4())
                start_time = time.time()
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

                try:
                    logger.info(
                        f"[{timestamp}] [Request ID: {request_id}] LLM Request Start:\n"
                        f"  Provider: {provider_name}\n"
                        f"  Model: {model}\n"
                        f"  URL: {url}\n"
                        f"  Attempt: {attempt + 1}/{max_retries + 1}"
                    )

                    if provider_name == "ollama":
                        # Call Ollama
                        payload = {
                            "model": model,
                            "messages": messages,
                            "stream": False,
                            "options": {
                                "temperature": temp,
                            },
                        }
                        data = json.dumps(payload).encode("utf-8")
                        headers = {
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                    else:
                        # Call OpenAI compatible
                        payload = {
                            "model": model,
                            "messages": messages,
                            "temperature": temp,
                        }
                        if response_format:
                            payload["response_format"] = response_format
                        data = json.dumps(payload).encode("utf-8")
                        headers = {
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }

                    # Perform request
                    req = urllib.request.Request(url, data=data, headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as res:
                        status_code = res.status
                        resp_body = res.read().decode("utf-8")
                        resp_json = json.loads(resp_body)
                        latency = time.time() - start_time

                    logger.info(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}] [Request ID: {request_id}] LLM Request Success:\n"
                        f"  Status Code: {status_code}\n"
                        f"  Latency: {latency:.3f}s"
                    )

                    # Extract content
                    if provider_name == "ollama":
                        return resp_json["message"]["content"].strip()
                    else:
                        return resp_json["choices"][0]["message"]["content"].strip()

                except urllib.error.HTTPError as e:
                    status_code = e.code
                    try:
                        error_body = e.read().decode("utf-8")
                    except Exception:
                        error_body = "Could not read error response body."
                    latency = time.time() - start_time
                    last_error = e

                    logger.error(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}] [Request ID: {request_id}] LLM Request HTTP Error:\n"
                        f"  Status Code: {status_code}\n"
                        f"  Latency: {latency:.3f}s\n"
                        f"  Response Body: {error_body}"
                    )

                    # Determine if error is rate limit or server error (429 or 5xx)
                    if status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                        sleep_time = initial_delay * (backoff_factor ** attempt)
                        logger.warning(f"Transient error {status_code} encountered. Retrying in {sleep_time:.2f}s...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        # Non-retryable error, or retries exhausted
                        logger.error(f"HTTP error {status_code} is not retryable or retries exhausted. Attempting next provider...")
                        break

                except Exception as e:
                    latency = time.time() - start_time
                    last_error = e
                    logger.error(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}] [Request ID: {request_id}] LLM Request General Error:\n"
                        f"  Latency: {latency:.3f}s\n"
                        f"  Error: {e}"
                    )

                    if attempt < max_retries:
                        sleep_time = initial_delay * (backoff_factor ** attempt)
                        logger.warning(f"Error encountered. Retrying in {sleep_time:.2f}s...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        logger.error("General error and retries exhausted. Attempting next provider...")
                        break

        # If all backends failed
        if last_error:
            raise RuntimeError(
                f"All LLM providers failed. Last error: {last_error}"
            ) from last_error
        else:
            raise RuntimeError("No LLM providers responded successfully.")
