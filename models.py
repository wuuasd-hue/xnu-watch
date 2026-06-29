"""
models.py — The 6-model roster and the low-level call functions.

Each entry: provider, model id on that provider, and a short human label
used in logs/blackboard transcripts.
"""

import json
import os
import time

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"

# The 6-model roster. "id" is used as the key everywhere (blackboard, logs).
ROSTER = [
    {"id": "llama-3.3-70b",     "provider": "groq",     "model": "llama-3.3-70b-versatile"},
    {"id": "llama-4-scout",     "provider": "groq",     "model": "meta-llama/llama-4-scout-17b-16e-instruct"},
    {"id": "deepseek-r1",       "provider": "groq",     "model": "deepseek-r1-distill-llama-70b"},
    {"id": "qwen3-32b",         "provider": "groq",     "model": "qwen/qwen3-32b"},
    {"id": "qwen2.5-coder-32b", "provider": "together",  "model": "Qwen/Qwen2.5-Coder-32B-Instruct"},
    {"id": "deepseek-v3",       "provider": "together",  "model": "deepseek-ai/DeepSeek-V3"},
]


def _post(url: str, api_key: str, model: str, prompt: str, max_tokens: int = 900) -> str | None:
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[ERROR] call to {model} failed: {e}")
        return None


def call_model(model_entry: dict, prompt: str) -> str | None:
    """Dispatch a prompt to the right provider for this roster entry."""
    if model_entry["provider"] == "groq":
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            print(f"[WARN] GROQ_API_KEY missing, skipping {model_entry['id']}")
            return None
        return _post(GROQ_URL, api_key, model_entry["model"], prompt)
    elif model_entry["provider"] == "together":
        api_key = os.environ.get("TOGETHER_API_KEY", "")
        if not api_key:
            print(f"[WARN] TOGETHER_API_KEY missing, skipping {model_entry['id']}")
            return None
        return _post(TOGETHER_URL, api_key, model_entry["model"], prompt)
    else:
        raise ValueError(f"Unknown provider: {model_entry['provider']}")


def parse_json_response(content: str | None) -> dict | None:
    """Extract a JSON object from a model's raw text response, tolerating
    markdown fences and stray prose around the JSON."""
    if not content:
        return None
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) >= 2:
            content = parts[1]
            if content.startswith("json"):
                content = content[4:]
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            return json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError):
            print(f"[WARN] could not parse JSON from response: {content[:200]}")
            return None
