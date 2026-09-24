#!/usr/bin/env python3
"""Shared DeepSeek (OpenAI-compatible) client factory. A single, lazily-created client reused
across every synthesis and judge call, instead of a fresh OpenAI(...) instantiation -- and its
own connection pool -- on every single call (found in a dependency/architecture audit,
2026-09-21: scoutlite_combined.py and judge_llm.py each built their own client per call, up to
several times per brief once the judge loop's revision passes are counted).

Lazy on purpose: importing this module must not require DEEPSEEK_API_KEY to already be set --
only actually calling get_deepseek_client() does -- so modules that import scoutlite_combined
or judge_llm for their other functions (parsing, prompt-building, tests) don't need the key
just to import.
"""
import os

from openai import OpenAI

_client: OpenAI | None = None

# The SDK's own default is a 600s read timeout (checked directly, 2026-09-25) -- if DeepSeek
# ever genuinely hangs rather than erroring, a user would stare at a static spinner for up to
# 10 minutes before anything happens, even though the error message once it fires is already
# clear (friendly_error_message's APITimeoutError case). 90s is generous headroom over how long
# a real synthesis+judge call actually takes (seconds, based on live testing this session) while
# failing fast enough that a genuine hang surfaces in a reasonable time. The SDK still retries
# transient errors (timeouts, connection errors, 5xx) twice by default before raising.
REQUEST_TIMEOUT_SECONDS = 90.0


def get_deepseek_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    return _client
