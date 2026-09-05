"""Verify the configured Copilot provider without printing credentials."""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402


def main() -> int:
    if not settings.LLM_API_KEY.strip():
        print("NOT_CONFIGURED")
        return 1
    models_response = httpx.get(
        f"{settings.LLM_BASE_URL.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        timeout=20,
    )
    if models_response.is_success:
        model_ids = sorted(
            item["id"] for item in models_response.json().get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        print("AVAILABLE_MODELS=" + ",".join(model_ids))
    models = list(dict.fromkeys([settings.LLM_MODEL, settings.LLM_FALLBACK_MODEL]))
    for model in models:
        response = httpx.post(
            f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            json={
                "model": model,
                "temperature": 0,
                "max_tokens": 20,
                "messages": [{"role": "user", "content": "Reply with OK."}],
            },
            timeout=20,
        )
        print(f"HTTP {response.status_code}; model={model}")
        if response.is_success:
            print(f"COPILOT_PROVIDER_CONNECTED model={model}")
            return 0
        try:
            payload = response.json()
            print(str(payload.get("error", {}))[:1000])
        except ValueError:
            print(response.text[:500])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
