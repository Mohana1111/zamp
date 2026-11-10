"""
Unified LLM Client for AP Invoicing & Safety Review.

Supports:
- Gemini (via google-genai, model gemini-2.5-flash, supports text + multimodal images)
- Groq (via OpenAI-compatible REST API, model llama-3.3-70b-versatile, text-only)
- Fallback / Rules mode when keys are unavailable.

Principles:
- Strict JSON output
- 1 retry on failure
- 30s timeout
- Provider order: Gemini -> Groq -> None
- No provider names or secrets exposed to business UI
"""

import os
import re
import json
import time
from typing import Optional, Dict, Any, List
from pathlib import Path

# Runtime configuration cache
_AI_CONFIG: Dict[str, Any] = {
    "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
    "groq_api_key": os.getenv("GROQ_API_KEY", "").strip(),
    "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
    "groq_model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
    "enabled": True,
}


def set_ai_api_key(provider: str, api_key: str):
    """Set API key for a provider at runtime."""
    prov = (provider or "").upper().strip()
    key = (api_key or "").strip()
    if "GEMINI" in prov:
        _AI_CONFIG["gemini_api_key"] = key
    elif "GROQ" in prov:
        _AI_CONFIG["groq_api_key"] = key


def set_ai_enabled(enabled: bool):
    """Enable or disable AI review at runtime."""
    _AI_CONFIG["enabled"] = bool(enabled)


def get_ai_config() -> Dict[str, Any]:
    """Internal AI configuration status."""
    return {
        "gemini_configured": bool(_AI_CONFIG.get("gemini_api_key")),
        "groq_configured": bool(_AI_CONFIG.get("groq_api_key")),
        "gemini_model": _AI_CONFIG.get("gemini_model", "gemini-2.5-flash"),
        "groq_model": _AI_CONFIG.get("groq_model", "llama-3.3-70b-versatile"),
        "enabled": _AI_CONFIG.get("enabled", True),
    }


def llm_available() -> bool:
    """Returns True if AI is enabled and at least one LLM key is configured."""
    if not _AI_CONFIG.get("enabled", True):
        return False
    return bool(_AI_CONFIG.get("gemini_api_key") or _AI_CONFIG.get("groq_api_key"))


def get_ai_status() -> Dict[str, Any]:
    """Public AI status endpoint contract (no provider names)."""
    has_key = llm_available()
    return {
        "enabled": _AI_CONFIG.get("enabled", True),
        "mode": "ai" if has_key else "rules",
    }


def _clean_json_text(text: str) -> str:
    """Strips markdown code fences and returns clean json text."""
    if not text:
        return ""
    cleaned = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    return cleaned


def _call_gemini_json(
    system: str,
    user: str,
    images: Optional[List[Any]] = None,
    schema_hint: Optional[str] = None,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Calls Gemini via google-genai client."""
    key = (api_key or _AI_CONFIG.get("gemini_api_key", "")).strip()
    if not key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        model_name = _AI_CONFIG.get("gemini_model", "gemini-2.5-flash")

        contents: List[Any] = []
        if images:
            for img in images:
                if img is not None:
                    contents.append(img)
        contents.append(user)

        cfg_kwargs: Dict[str, Any] = {
            "response_mime_type": "application/json",
            "temperature": float(temperature),
        }
        if system:
            cfg_kwargs["system_instruction"] = system

        config = types.GenerateContentConfig(**cfg_kwargs)

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )

        resp_text = getattr(response, "text", "") or ""
        cleaned = _clean_json_text(resp_text)
        if cleaned:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return None


def _call_groq_json(
    system: str,
    user: str,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Calls Groq API via standard REST JSON completions (text-only)."""
    key = (api_key or _AI_CONFIG.get("groq_api_key", "")).strip()
    if not key:
        return None

    import urllib.request
    import urllib.error

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "ClearPayAP/2.0",
    }

    primary_model = _AI_CONFIG.get("groq_model", "llama-3.3-70b-versatile")
    models = [primary_model, "llama-3.1-8b-instant"]

    for model in models:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system or "You are an expert financial AP reviewer. Respond strictly in valid JSON."},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": float(temperature),
        }
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    resp_body = resp.read().decode("utf-8")
                    parsed = json.loads(resp_body)
                    content = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
                    cleaned = _clean_json_text(content)
                    if cleaned:
                        data = json.loads(cleaned)
                        if isinstance(data, dict):
                            return data
        except Exception:
            continue
    return None


def call_llm_json(
    system: str,
    user: str,
    images: Optional[List[Any]] = None,
    schema_hint: Optional[str] = None,
    temperature: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """
    Unified LLM caller returning parsed JSON or None.
    Provider order: Gemini -> Groq.
    Retries once on transient failure. 30s timeout per call.
    """
    if not _AI_CONFIG.get("enabled", True):
        return None

    gemini_key = _AI_CONFIG.get("gemini_api_key", "").strip()
    groq_key = _AI_CONFIG.get("groq_api_key", "").strip()

    # If images are provided, only vision-capable provider (Gemini) can handle them
    if images and gemini_key:
        for _ in range(2):
            res = _call_gemini_json(system, user, images=images, schema_hint=schema_hint, temperature=temperature)
            if res is not None:
                return res
        return None

    # Priority 1: Gemini
    if gemini_key:
        for _ in range(2):
            res = _call_gemini_json(system, user, images=None, schema_hint=schema_hint, temperature=temperature)
            if res is not None:
                return res

    # Priority 2: Groq
    if groq_key:
        for _ in range(2):
            res = _call_groq_json(system, user, temperature=temperature)
            if res is not None:
                return res

    return None
