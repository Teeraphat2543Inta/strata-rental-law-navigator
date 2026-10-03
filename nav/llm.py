"""Minimal Anthropic Messages API client (stdlib only) with on-disk caching for reproducibility."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from . import config

API_URL = "https://api.anthropic.com/v1/messages"


def _key():
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    if not k:
        raise SystemExit("ANTHROPIC_API_KEY is not set. export ANTHROPIC_API_KEY=sk-ant-...")
    return k


def call_tool(system: str, user: str, tool: dict, cache_name: str, max_tokens: int = 16000,
              model: str = None, force: bool = False, _retry: bool = True) -> dict:
    """Force the model to answer through `tool` and return the tool input (a dict).

    Results are cached by (model, prompt hash) under cache/llm/ — this file is also the audit
    record of exactly what the model returned for each document.
    """
    model = model or config.ANTHROPIC_MODEL
    h = hashlib.sha256((model + system + user + json.dumps(tool, sort_keys=True)).encode()).hexdigest()[:16]
    path = config.LLM_CACHE / f"{cache_name}.{h}.json"
    if path.exists() and not force:
        return json.loads(path.read_text())["output"]

    body = {
        "model": model,
        "max_tokens": max_tokens,
        # Sonnet 5.5 / Opus 5.5 reject forced tool_choice and non-default temperature:
        # use auto + an explicit instruction, and retry if the model answers in text.
        "system": system + f"\n\nAlways answer by calling the `{tool['name']}` tool exactly once. "
                           "Do not reply in plain text.",
        "tools": [tool],
        "tool_choice": {"type": "auto"},
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(), method="POST",
        headers={"x-api-key": _key(), "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    resp = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 529) and attempt < 5:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"Anthropic API error {e.code}: {msg}") from None
        except urllib.error.URLError:
            if attempt < 5:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    out = next((c["input"] for c in resp.get("content", []) if c.get("type") == "tool_use"), None)
    if out is None and _retry:
        return call_tool(system + "\n\nYour previous answer did not call the tool. Call it now.",
                         user, tool, cache_name, max_tokens, model, force, _retry=False)
    if out is None:
        raise RuntimeError(f"No tool_use block in response: {json.dumps(resp)[:500]}")
    config.LLM_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model, "cache_name": cache_name,
                                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "usage": resp.get("usage"), "stop_reason": resp.get("stop_reason"),
                                "output": out}, indent=1, ensure_ascii=False))
    return out
