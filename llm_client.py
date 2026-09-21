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


def get_deepseek_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    return _client
