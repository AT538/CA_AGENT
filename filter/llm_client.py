"""
Shared multi-provider LLM calling infrastructure - used by filter.judge
(daily relevance/exam-angle judging) and exam_analysis (PYQ trend analysis),
so both share the same provider registry, key-rotation, and fallback-chain
logic instead of duplicating it.

A "tier_config" dict has: provider, model, fallback_provider, fallback_model,
fallback_provider2, fallback_model2. call_with_fallback() tries them in that
order and returns the first provider that responds (parsed as JSON), or None
if every configured provider failed.
"""

import json
import os

_exhausted_groq_keys: set[int] = set()


def _groq_api_keys() -> list[str]:
    """GROQ_API_KEYS (comma-separated, for rotating across multiple free-tier
    accounts) takes priority; falls back to the single GROQ_API_KEY."""
    keys_csv = os.environ.get("GROQ_API_KEYS")
    if keys_csv:
        return [k.strip() for k in keys_csv.split(",") if k.strip()]
    single = os.environ.get("GROQ_API_KEY")
    return [single] if single else []


def _call_groq(prompt: str, model: str) -> str:
    from groq import Groq, RateLimitError

    keys = _groq_api_keys()
    if not keys:
        raise RuntimeError("no GROQ_API_KEY(s) configured")

    last_error = RuntimeError("no usable groq keys")
    for i, key in enumerate(keys):
        if i in _exhausted_groq_keys:
            continue
        try:
            client = Groq(api_key=key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return resp.choices[0].message.content
        except RateLimitError as e:
            print(f"[warn] groq key #{i + 1}/{len(keys)} rate/quota limited, rotating to next key")
            _exhausted_groq_keys.add(i)
            last_error = e
        except Exception as e:
            last_error = e

    raise last_error


_exhausted_gemini_keys: set[int] = set()


def _gemini_api_keys() -> list[str]:
    """GEMINI_API_KEYS (comma-separated, for rotating across multiple free-tier
    accounts) takes priority; falls back to the single GEMINI_API_KEY."""
    keys_csv = os.environ.get("GEMINI_API_KEYS")
    if keys_csv:
        return [k.strip() for k in keys_csv.split(",") if k.strip()]
    single = os.environ.get("GEMINI_API_KEY")
    return [single] if single else []


def _call_gemini(prompt: str, model: str) -> str:
    import google.generativeai as genai
    from google.api_core.exceptions import ResourceExhausted

    keys = _gemini_api_keys()
    if not keys:
        raise RuntimeError("no GEMINI_API_KEY(s) configured")

    last_error = RuntimeError("no usable gemini keys")
    for i, key in enumerate(keys):
        if i in _exhausted_gemini_keys:
            continue
        try:
            genai.configure(api_key=key)
            gen_model = genai.GenerativeModel(model)
            return gen_model.generate_content(prompt).text
        except ResourceExhausted as e:
            print(f"[warn] gemini key #{i + 1}/{len(keys)} quota exhausted for today, rotating to next key")
            _exhausted_gemini_keys.add(i)
            last_error = e
        except Exception as e:
            last_error = e

    raise last_error


def _call_openrouter(prompt: str, model: str) -> str:
    import httpx
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_ollama(prompt: str, model: str) -> str:
    import httpx
    resp = httpx.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def _call_anthropic(prompt: str, model: str) -> str:
    """Optional paid-tier escape hatch. Requires ANTHROPIC_API_KEY if used."""
    import httpx
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": model, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


_PROVIDERS = {
    "groq": _call_groq,
    "gemini": _call_gemini,
    "openrouter": _call_openrouter,
    "ollama": _call_ollama,
    "anthropic": _call_anthropic,
}


def _parse_json_response(raw: str) -> dict:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


def call_with_fallback(prompt: str, tier_config: dict):
    """Try provider -> fallback_provider -> fallback_provider2 in order.
    Returns the first parsed-JSON response, or None if every configured
    provider failed (caller decides the safe default)."""
    for provider_key, model_key in [
        (tier_config.get("provider"), tier_config.get("model")),
        (tier_config.get("fallback_provider"), tier_config.get("fallback_model")),
        (tier_config.get("fallback_provider2"), tier_config.get("fallback_model2")),
    ]:
        if not provider_key:
            continue
        try:
            raw = _PROVIDERS[provider_key](prompt, model_key)
            return _parse_json_response(raw)
        except Exception as e:
            print(f"[warn] provider {provider_key} failed: {e}")
    return None
