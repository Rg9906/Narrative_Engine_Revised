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


class RequestTooLargeError(RuntimeError):
    """The prompt exceeded the backend's per-request or per-minute token allowance.

    Distinct from a dead backend: the backend is fine and a smaller prompt would
    succeed, so callers should shrink the request rather than fail over or give up.
    Groq's free tier reports this as HTTP 413 with code `rate_limit_exceeded` and a
    message of the form "Request too large ... on tokens per minute (TPM): Limit 8000,
    Requested 8984". Retrying it unchanged can never succeed.
    """


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
            # See config/default.yaml: the previous default (llama-3.3-70b-versatile)
            # was decommissioned and 404s.
            "default_model": "openai/gpt-oss-120b",
            "config_model_key": "llm.groq_model",
        },
    }

    # Backends that have hard-failed this process, mapped to why. A dead backend is dead
    # for every LLMProvider instance, not just the one that discovered it: the engine
    # constructs a fresh provider per extraction stage (see LLMExtractionEngine._fetch_json),
    # so without this each of a chapter's ~6 LLM calls independently re-discovered that
    # Gemini was out of quota, burning five exponential-backoff retries (~60s) apiece
    # before failing over. Deliberately class-level and never reset: an exhausted daily
    # quota or a decommissioned model does not recover within one run.
    _dead_backends: Dict[str, str] = {}

    # Separate bookkeeping for rate/quota limits, which are NOT structural failures.
    # A 429 can mean either "you are over your per-minute rate" (recovers in seconds) or
    # "this project's quota is zero" (never recovers), and the response body does not
    # reliably distinguish them. Blacklisting on the first exhausted-retry 429 would let
    # one bad minute -- easily reached, since a chapter issues roughly six sequential
    # calls against a per-minute token budget -- kill the backend for the rest of the run;
    # never blacklisting means a permanently zero-quota project costs ~60s of backoff on
    # every single call. So a backend is retired only after this many *separate* calls
    # have each exhausted their retries.
    _RATE_LIMIT_STRIKES_BEFORE_RETIRING = 2
    _rate_limit_strikes: Dict[str, int] = {}

    # Per-role backend preference used when config supplies none. See the commentary in
    # config/default.yaml: local Ollama is the only backend with guaranteed availability,
    # so it is the floor for the high-volume extraction stages, while a cloud model is an
    # opportunistic upgrade for the editorial prose where model size visibly shows.
    _DEFAULT_ROLE_PREFERENCES = {
        "extraction": ["ollama", "groq", "gemini"],
        "editorial": ["groq", "gemini", "ollama"],
    }

    # Backend order for callers that don't name a role. Preserves the original
    # gemini -> groq -> ollama chain so nothing that predates role routing changes.
    _DEFAULT_PREFERENCE = ["gemini", "groq", "ollama"]

    def __init__(self, config=None, role: Optional[str] = None):
        """
        Args:
            config: project Config, used for model names and role preferences.
            role: which kind of work this provider is for -- "extraction" or "editorial".
                Selects the backend preference order (see _DEFAULT_ROLE_PREFERENCES).
                None keeps the historical global ordering.
        """
        self._config = config
        self._role = role
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
        live_backends = [b for b in backends if b["name"] not in self._dead_backends]
        if not live_backends:
            reasons = "; ".join(f"{name}: {why}" for name, why in self._dead_backends.items())
            raise RuntimeError(f"All LLM backends have hard-failed this run. {reasons}")
        if len(live_backends) < len(backends):
            skipped = [b["name"] for b in backends if b["name"] in self._dead_backends]
            logger.debug(f"Skipping backend(s) already known dead this run: {', '.join(skipped)}")

        # Try each still-live backend in priority order
        for backend_idx, backend in enumerate(live_backends):
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
            max_retries = 5
            initial_delay = 2.0  # seconds
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

                    # A success proves any earlier 429s on this backend were transient
                    # rate limiting rather than an exhausted quota, so the strikes that
                    # would eventually retire it are forgiven.
                    self._rate_limit_strikes.pop(provider_name, None)

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

                    # A request that exceeds the token allowance will never succeed on
                    # retry, and says nothing about the backend's health -- so it neither
                    # retries nor retires anything. It propagates so the caller can send
                    # less. Previously this fell through to the "non-retryable" branch and
                    # retired the backend, which meant one oversized extraction prompt
                    # disabled the LLM for the entire remainder of the chapter run.
                    if status_code == 413:
                        raise RequestTooLargeError(
                            self._describe_http_failure(status_code, error_body)
                        ) from e

                    # Determine if error is rate limit or server error (429 or 5xx)
                    if status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                        # Token-per-minute limits come with the server's own estimate of
                        # when the budget frees up ("Please try again in 34.52s"). Honour it
                        # -- blind exponential backoff under-waits on the early attempts
                        # (burning retries against a window that has not reset) and
                        # over-waits on the late ones.
                        advised = self._advised_retry_delay(error_body, e)
                        sleep_time = initial_delay * (backoff_factor ** attempt)
                        if advised is not None:
                            sleep_time = max(sleep_time, advised)
                            logger.warning(
                                f"Rate limited ({status_code}); backend advises retrying in "
                                f"{advised:.2f}s. Waiting {sleep_time:.2f}s..."
                            )
                        else:
                            logger.warning(
                                f"Transient error {status_code} encountered. Retrying in "
                                f"{sleep_time:.2f}s..."
                            )
                        time.sleep(sleep_time)
                        continue
                    else:
                        # Non-retryable error, or retries exhausted. Either way this
                        # backend is not going to start working later in the same run:
                        # 404 means the configured model no longer exists, 401/403 means
                        # the key is wrong, and a 429 that survived five backoffs means
                        # the quota is genuinely exhausted rather than momentarily tight.
                        reason = self._describe_http_failure(status_code, error_body)
                        if status_code == 429:
                            strikes = self._rate_limit_strikes.get(provider_name, 0) + 1
                            self._rate_limit_strikes[provider_name] = strikes
                            if strikes >= self._RATE_LIMIT_STRIKES_BEFORE_RETIRING:
                                self._dead_backends[provider_name] = reason
                                logger.error(
                                    f"Backend '{provider_name}' (model {model}) retired for this run "
                                    f"after {strikes} rate-limited calls: {reason}. "
                                    f"Attempting next provider..."
                                )
                            else:
                                logger.warning(
                                    f"Backend '{provider_name}' (model {model}) rate-limited "
                                    f"(strike {strikes}/{self._RATE_LIMIT_STRIKES_BEFORE_RETIRING}): "
                                    f"{reason}. Attempting next provider..."
                                )
                        else:
                            self._dead_backends[provider_name] = reason
                            logger.error(
                                f"Backend '{provider_name}' (model {model}) marked dead for this run: "
                                f"{reason}. Attempting next provider..."
                            )
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
            detail = "; ".join(f"{name}: {why}" for name, why in self._dead_backends.items())
            raise RuntimeError(
                f"All LLM providers failed. Last error: {last_error}."
                + (f" Backend status -- {detail}" if detail else "")
            ) from last_error
        else:
            raise RuntimeError("No LLM providers responded successfully.")

    @staticmethod
    def _describe_http_failure(status_code: int, error_body: str) -> str:
        """Turn an HTTP failure into something actionable in a log line.

        A bare "HTTP Error 404: Not Found" is what made the dead-model outage so hard to
        see: it looked like a transient network problem rather than "the model in your
        config no longer exists".
        """
        snippet = (error_body or "").strip().replace("\n", " ")[:200]
        if status_code == 404:
            return f"configured model not found (404) -- it may have been decommissioned. {snippet}"
        if status_code in (401, 403):
            return f"authentication rejected ({status_code}) -- check the API key. {snippet}"
        if status_code == 429:
            return f"quota/rate limit exhausted after retries (429). {snippet}"
        if status_code == 413:
            return f"request exceeded the backend's token allowance (413). {snippet}"
        return f"HTTP {status_code}. {snippet}"

    @staticmethod
    def _advised_retry_delay(error_body: str, error: Exception) -> Optional[float]:
        """Seconds the backend says to wait, from a Retry-After header or its message.

        Groq embeds the figure in prose ("Please try again in 34.5225s") rather than
        always setting a header, so both are checked. Capped so a hostile or malformed
        value cannot stall a run indefinitely.
        """
        import re

        candidates = []

        headers = getattr(error, "headers", None)
        if headers is not None:
            for header in ("retry-after", "Retry-After", "x-ratelimit-reset-tokens"):
                try:
                    raw = headers.get(header)
                except Exception:
                    raw = None
                if raw:
                    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(raw))
                    if match:
                        candidates.append(float(match.group(1)))

        match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*s", error_body or "", re.IGNORECASE)
        if match:
            candidates.append(float(match.group(1)))

        if not candidates:
            return None
        # A small margin, because the window boundary is a moving target.
        return min(max(candidates) + 1.0, 90.0)
