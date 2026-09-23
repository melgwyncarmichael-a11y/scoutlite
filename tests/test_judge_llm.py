"""judge_llm.review()'s fail-soft path: on any error it must still warn (2026-09-24 fix -- a
bare except used to swallow this completely, making a broken fact-checker indistinguishable
from a clean pass), not just return an empty result silently. No live API call needed."""
import pytest

import judge_llm


def test_review_fails_soft_and_warns_on_api_error(monkeypatch):
    def _broken_client():
        raise ConnectionError("DeepSeek unreachable")

    monkeypatch.setattr(judge_llm, "get_deepseek_client", _broken_client)
    with pytest.warns(RuntimeWarning, match="judge_llm.review\\(\\) failed"):
        result = judge_llm.review("news text", "fit text", {}, None, None, None, None)
    assert result == {"findings": [], "has_major": False}


def test_review_fails_soft_and_warns_on_malformed_json(monkeypatch):
    class _FakeMessage:
        content = "not valid json at all"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _FakeResponse()

    monkeypatch.setattr(judge_llm, "get_deepseek_client", lambda: _FakeClient())
    with pytest.warns(RuntimeWarning, match="judge_llm.review\\(\\) failed"):
        result = judge_llm.review("news text", "fit text", {}, None, None, None, None)
    assert result == {"findings": [], "has_major": False}
