"""friendly_error_message() categorizes exceptions into clear, actionable text -- shared by
app.py and both CLI entrypoints (2026-09-24). Pure function, no network/API calls."""
import openai
import requests
from selenium.common.exceptions import WebDriverException

import scoutlite_combined as sc


class _FakeResponse:
    """openai's APIStatusError subclasses (AuthenticationError, RateLimitError) read
    response.request internally -- a minimal stand-in, not a real HTTP response."""
    status_code = 401
    request = object()
    headers = {}


def test_runtime_error_passed_through_as_is():
    e = RuntimeError("3 players matched 'Danny Ward' -- won't guess which one")
    assert sc.friendly_error_message(e, "searching") == str(e)


def test_authentication_error_gives_api_key_guidance():
    e = openai.AuthenticationError("invalid key", response=_FakeResponse(), body=None)
    msg = sc.friendly_error_message(e, "generating the brief")
    assert "DEEPSEEK_API_KEY" in msg


def test_rate_limit_error_gives_quota_guidance():
    e = openai.RateLimitError("rate limited", response=_FakeResponse(), body=None)
    msg = sc.friendly_error_message(e, "generating the brief")
    assert "rate limit" in msg.lower() or "quota" in msg.lower()


def test_api_connection_error_gives_network_guidance():
    e = openai.APIConnectionError(request=None)
    msg = sc.friendly_error_message(e, "generating the brief")
    assert "DeepSeek" in msg and "internet connection" in msg


def test_internal_server_error_says_deepseeks_side_not_the_users(monkeypatch):
    fake_response = _FakeResponse()
    fake_response.status_code = 503
    e = openai.InternalServerError("service unavailable", response=fake_response, body=None)
    msg = sc.friendly_error_message(e, "generating the brief")
    assert "DeepSeek" in msg and "servers" in msg


def test_generic_openai_error_mentions_context():
    e = openai.OpenAIError("something else")
    msg = sc.friendly_error_message(e, "generating the brief")
    assert "generating the brief" in msg


def test_webdriver_exception_mentions_fbref_and_context():
    e = WebDriverException("session not created")
    msg = sc.friendly_error_message(e, "fetching Haaland's page")
    assert "FBref" in msg and "fetching Haaland's page" in msg


def test_requests_exception_gives_network_guidance():
    e = requests.ConnectionError("connection refused")
    msg = sc.friendly_error_message(e, "fetching news")
    assert "network" in msg.lower() and "fetching news" in msg


def test_unrecognized_exception_falls_back_to_generic_context_message():
    e = ValueError("some unrelated internal error")
    msg = sc.friendly_error_message(e, "parsing stats")
    assert "parsing stats" in msg
