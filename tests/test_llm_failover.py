"""Tests for LLMProvider backend retirement.

Context: the engine's entire LLM layer was silently dead. Groq's configured model had
been decommissioned (HTTP 404 "model does not exist") and the Gemini project reported
`quota_limit_value: "0"` (HTTP 429), so every LLM call failed over through dead backends
and every stage degraded to empty output — which the calling code swallows by design.
Two behaviours guard against a repeat:

  * A backend that fails structurally (bad model, bad key) is retired immediately, and
    the reason is reported instead of a bare "HTTP Error 404: Not Found".
  * A backend that is merely rate-limited is NOT retired on the first exhausted retry,
    because a per-minute rate limit recovers while a zero quota does not, and the
    response body does not reliably distinguish them.
"""

import urllib.error

import pytest

from src.utils.llm_provider import LLMProvider


@pytest.fixture(autouse=True)
def _isolate_class_state(monkeypatch):
    """The retirement registries are class-level (deliberately — a dead backend is dead
    for every provider instance in the process). Tests must not leak into each other."""
    monkeypatch.setattr(LLMProvider, "_dead_backends", {})
    monkeypatch.setattr(LLMProvider, "_rate_limit_strikes", {})


def _http_error(code: int, body: bytes = b"{}"):
    return urllib.error.HTTPError(
        url="https://example.invalid", code=code, msg="err", hdrs=None, fp=None
    )


def _provider(monkeypatch, backends, responses):
    """Build a provider with fixed backends and a scripted urlopen.

    `responses` maps backend name -> either an exception to raise or a body to return.
    """
    # TestLLMProvider... in the name keeps _detect_backend from disabling itself under
    # pytest (see LLMProvider._detect_backend).
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "TestLLMProvider::scripted")
    provider = LLMProvider()
    provider._provider = backends[0]["name"]
    provider._available_backends = backends

    attempts = []

    class _Response:
        def __init__(self, body):
            self._body = body
            self.status = 200

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        # Identify the backend from the request URL.
        name = next(b["name"] for b in backends if b["url"] == req.full_url)
        attempts.append(name)
        outcome = responses[name]
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    # Collapse backoff sleeps so the retry loop runs instantly.
    monkeypatch.setattr("time.sleep", lambda *_: None)
    return provider, attempts


OK_BODY = b'{"choices":[{"message":{"content":"done"}}]}'


def _backend(name):
    return {
        "name": name,
        "api_key": "k",
        "url": f"https://{name}.invalid/v1/chat",
        "model": f"{name}-model",
    }


class TestStructuralFailures:
    def test_model_not_found_retires_backend_immediately(self, monkeypatch):
        provider, attempts = _provider(
            monkeypatch,
            [_backend("groq"), _backend("gemini")],
            {"groq": _http_error(404), "gemini": OK_BODY},
        )

        assert provider.chat([{"role": "user", "content": "hi"}]) == "done"
        assert "groq" in LLMProvider._dead_backends
        assert "404" in LLMProvider._dead_backends["groq"]

        # A second call must not re-attempt the retired backend.
        attempts.clear()
        provider.chat([{"role": "user", "content": "hi"}])
        assert attempts == ["gemini"]

    def test_auth_failure_retires_backend(self, monkeypatch):
        provider, _ = _provider(
            monkeypatch,
            [_backend("groq"), _backend("gemini")],
            {"groq": _http_error(401), "gemini": OK_BODY},
        )
        provider.chat([{"role": "user", "content": "hi"}])

        assert "authentication rejected" in LLMProvider._dead_backends["groq"]

    def test_error_names_the_reason_when_everything_is_dead(self, monkeypatch):
        provider, _ = _provider(
            monkeypatch, [_backend("groq")], {"groq": _http_error(404)}
        )

        with pytest.raises(RuntimeError) as excinfo:
            provider.chat([{"role": "user", "content": "hi"}])

        # The old failure mode was an unactionable bare "HTTP Error 404: Not Found".
        assert "model not found" in str(excinfo.value)


class TestRateLimiting:
    def test_single_rate_limited_call_does_not_retire_backend(self, monkeypatch):
        """One bad minute must not kill a working backend for the rest of the run."""
        provider, _ = _provider(
            monkeypatch,
            [_backend("groq"), _backend("gemini")],
            {"groq": _http_error(429), "gemini": OK_BODY},
        )

        provider.chat([{"role": "user", "content": "hi"}])

        assert "groq" not in LLMProvider._dead_backends
        assert LLMProvider._rate_limit_strikes["groq"] == 1

    def test_repeated_rate_limiting_eventually_retires_backend(self, monkeypatch):
        """A permanently zero quota must stop costing a full backoff cycle every call."""
        provider, attempts = _provider(
            monkeypatch,
            [_backend("gemini"), _backend("groq")],
            {"gemini": _http_error(429), "groq": OK_BODY},
        )

        for _ in range(LLMProvider._RATE_LIMIT_STRIKES_BEFORE_RETIRING):
            provider.chat([{"role": "user", "content": "hi"}])

        assert "gemini" in LLMProvider._dead_backends

        attempts.clear()
        provider.chat([{"role": "user", "content": "hi"}])
        assert attempts == ["groq"]

    def test_success_forgives_accumulated_strikes(self, monkeypatch):
        provider, _ = _provider(
            monkeypatch,
            [_backend("groq"), _backend("gemini")],
            {"groq": _http_error(429), "gemini": OK_BODY},
        )
        provider.chat([{"role": "user", "content": "hi"}])
        assert LLMProvider._rate_limit_strikes["groq"] == 1

        # Groq now recovers; its strike should be cleared rather than carried toward
        # retirement.
        provider._available_backends = [_backend("groq")]

        class _Response:
            status = 200

            def read(self):
                return OK_BODY

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Response())
        provider.chat([{"role": "user", "content": "hi"}])

        assert "groq" not in LLMProvider._rate_limit_strikes


class TestRequestTooLarge:
    """Groq's free tier caps requests at 8,000 tokens/minute and rejects anything over
    with HTTP 413. That says the PROMPT is too big, not that the backend is broken, so it
    must neither be retried unchanged (it can never succeed) nor treated as a dead
    backend (which previously disabled the LLM for the rest of the chapter run)."""

    def test_413_raises_a_distinct_error(self, monkeypatch):
        from src.utils.llm_provider import RequestTooLargeError

        provider, _ = _provider(
            monkeypatch, [_backend("groq")], {"groq": _http_error(413)}
        )

        with pytest.raises(RequestTooLargeError):
            provider.chat([{"role": "user", "content": "a very long prompt"}])

    def test_413_does_not_retire_the_backend(self, monkeypatch):
        from src.utils.llm_provider import RequestTooLargeError

        provider, _ = _provider(
            monkeypatch, [_backend("groq")], {"groq": _http_error(413)}
        )

        with pytest.raises(RequestTooLargeError):
            provider.chat([{"role": "user", "content": "too long"}])

        assert "groq" not in LLMProvider._dead_backends
        assert "groq" not in LLMProvider._rate_limit_strikes

    def test_413_is_not_retried(self, monkeypatch):
        """Retrying an oversized request burns the rate-limit window for nothing."""
        from src.utils.llm_provider import RequestTooLargeError

        provider, attempts = _provider(
            monkeypatch, [_backend("groq")], {"groq": _http_error(413)}
        )

        with pytest.raises(RequestTooLargeError):
            provider.chat([{"role": "user", "content": "too long"}])

        assert attempts == ["groq"]


class TestAdvisedRetryDelay:
    """Token-per-minute limits arrive with the server's own estimate of when the budget
    frees up. Blind exponential backoff under-waits early (burning retries against a
    window that has not reset) and over-waits late."""

    def test_parses_the_delay_from_the_message_body(self):
        body = (
            '{"error":{"message":"Rate limit reached ... Please try again in 34.5225s. '
            'Need more tokens?"}}'
        )
        delay = LLMProvider._advised_retry_delay(body, Exception())

        # A margin is added because the window boundary is a moving target.
        assert 35.0 <= delay <= 36.0

    def test_prefers_a_retry_after_header_when_present(self):
        class _WithHeaders(Exception):
            headers = {"retry-after": "12"}

        delay = LLMProvider._advised_retry_delay("", _WithHeaders())
        assert 12.0 <= delay <= 14.0

    def test_returns_none_when_no_hint_is_available(self):
        assert LLMProvider._advised_retry_delay("some other error", Exception()) is None

    def test_caps_an_absurd_advised_delay(self):
        body = "Please try again in 99999s"
        assert LLMProvider._advised_retry_delay(body, Exception()) == 90.0
