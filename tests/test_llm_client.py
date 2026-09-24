"""get_deepseek_client()'s singleton behavior and explicit timeout (2026-09-25 -- the SDK's own
default is a 600s read timeout, checked directly against the installed openai package; a
genuine hang would otherwise leave a user waiting up to 10 minutes before anything surfaces)."""
import llm_client


def test_client_is_a_reused_singleton(monkeypatch):
    monkeypatch.setattr(llm_client, "_client", None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    c1 = llm_client.get_deepseek_client()
    c2 = llm_client.get_deepseek_client()
    assert c1 is c2


def test_client_uses_explicit_shorter_timeout(monkeypatch):
    monkeypatch.setattr(llm_client, "_client", None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = llm_client.get_deepseek_client()
    # openai's own default is 600s -- confirm we're not silently back on that default.
    assert client.timeout == llm_client.REQUEST_TIMEOUT_SECONDS
    assert client.timeout < 600
