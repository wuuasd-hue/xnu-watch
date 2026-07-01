"""
models.py — The 6-model roster and the low-level call functions.

All 6 models are called through OpenRouter's unified /chat/completions API.
Each roster entry carries its own env-var key name, so each of the 6 models
uses a SEPARATE OpenRouter API key/account (spreads free-tier rate limits
across 6 keys instead of hammering one).

SECURITY NOTE: API keys are read from environment variables ONLY (populated
by GitHub Actions from repo Secrets). Never hardcode keys in this file — if
you paste a real key into source, treat it as compromised and rotate it
immediately, since it will end up in git history even after later edits.
"""

import json
import os
import time

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# The 6-model roster — all open-weight models, routed through OpenRouter's
# FREE tier. The ":free" suffix is mandatory: without it OpenRouter routes
# the same model ID to its paid backend and bills your credits (this is
# exactly what caused the earlier 402 Payment Required errors).
# Each model uses its own API key (env var below) so free-tier rate limits
# (20 req/min, ~50-1000 req/day) are spread across 6 separate OpenRouter
# keys instead of shared on one.
#
# NOTE: OpenRouter's free-model catalog changes over time (models get added/
# retired). If one of these starts returning 404, check openrouter.ai/models
# (filter: price = free) for a current replacement — call_model() already
# skips failed models gracefully rather than crashing the whole run.
ROSTER = [
    {"id": "llama-3.3-70b",     "model": "meta-llama/llama-3.3-70b-instruct:free",      "key_env": "OPENROUTER_API_KEY_1"},
    {"id": "llama-4-scout",     "model": "meta-llama/llama-4-scout:free",               "key_env": "OPENROUTER_API_KEY_2"},
    {"id": "deepseek-r1",       "model": "deepseek/deepseek-r1-distill-llama-70b:free", "key_env": "OPENROUTER_API_KEY_3"},
    {"id": "qwen3-235b",        "model": "qwen/qwen3-235b-a22b:free",                   "key_env": "OPENROUTER_API_KEY_4"},
    {"id": "qwen3-coder",       "model": "qwen/qwen3-coder:free",                       "key_env": "OPENROUTER_API_KEY_5"},
    {"id": "deepseek-v3",       "model": "deepseek/deepseek-chat-v3-0324:free",         "key_env": "OPENROUTER_API_KEY_6"},
]


def _post(api_key: str, model: str, prompt: str, max_tokens: int = 900) -> str | None:
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                # OpenRouter uses these for its free-tier leaderboard/attribution;
                # harmless to include, not required.
                "HTTP-Referer": "https://github.com/xnu-watch",
                "X-Title": "xnu-watch",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
            timeout=90,
        )
        if resp.status_code == 429:
            print(f"[RATE LIMIT] {model} -> backing off 15s")
            time.sleep(15)
            return None
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices")
        if not choices:
            print(f"[ERROR] {model} returned no choices: {data}")
            return None
        return choices[0]["message"]["content"]
    except Exception as e:
        print(f"[ERROR] call to {model} failed: {e}")
        return None


def call_model(model_entry: dict, prompt: str) -> str | None:
    """Dispatch a prompt to OpenRouter using this roster entry's own key."""
    api_key = os.environ.get(model_entry["key_env"], "")
    if not api_key:
        print(f"[WARN] {model_entry['key_env']} missing, skipping {model_entry['id']}")
        return None
    return _post(api_key, model_entry["model"], prompt)


def parse_json_response(raw: str | None) -> dict | None:
    """Extract a JSON object from a model's raw text response. Models
    sometimes wrap JSON in markdown fences or add stray prose — this strips
    that and finds the outermost {...} block."""
    if not raw:
        return None
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    # Find the first { and matching last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        print(f"[ERROR] no JSON object found in response: {text[:200]}")
        return None
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON parse failed: {e} — raw: {candidate[:200]}")
        return None
