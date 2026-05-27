import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.models import ModelConfig


@dataclass(frozen=True)
class LLMResult:
    provider: str
    model: str
    text: str
    json_data: dict[str, Any]
    prompt_hash: str
    used_fallback: bool = False


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def generate_structured(
        self,
        config: ModelConfig | None,
        system_prompt: str,
        user_payload: dict[str, Any],
        fallback: dict[str, Any],
    ) -> LLMResult:
        role = config.role if config else "fallback"
        provider = config.provider if config else "fallback"
        model = config.model_name if config else "fallback"
        prompt_hash = self._prompt_hash(system_prompt, user_payload)

        if not config or not config.enabled:
            return self._fallback_result(provider, model, fallback, prompt_hash)

        try:
            if provider in {"openai", "deepseek", "qwen", "stepfun", "openrouter"}:
                text = self._call_openai_compatible(config, system_prompt, user_payload)
            elif provider == "anthropic":
                text = self._call_anthropic(config, system_prompt, user_payload)
            elif provider == "google":
                text = self._call_gemini(config, system_prompt, user_payload)
            else:
                return self._fallback_result(provider, model, fallback, prompt_hash)
            json_data = self._extract_json(text)
            if not json_data:
                json_data = {**fallback, "raw_text": text, "parse_status": "failed"}
            return LLMResult(provider=provider, model=model, text=text, json_data=json_data, prompt_hash=prompt_hash)
        except Exception as exc:  # noqa: BLE001 - LLM calls must degrade into auditable fallback output
            enriched = {**fallback, "fallback_reason": str(exc), "role": role}
            return self._fallback_result(provider, model, enriched, prompt_hash)

    def _call_openai_compatible(
        self,
        config: ModelConfig,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        key, base_url = self._openai_compatible_credentials(config.provider)
        if not key:
            raise ValueError(f"Missing API key for provider {config.provider}")
        body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=config.timeout_seconds, follow_redirects=True) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _call_anthropic(
        self,
        config: ModelConfig,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        key = self.settings.anthropic_api_key
        if not key:
            raise ValueError("Missing ANTHROPIC_API_KEY")
        body = {
            "model": config.model_name,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}],
        }
        with httpx.Client(timeout=config.timeout_seconds, follow_redirects=True) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        data = response.json()
        chunks = data.get("content", [])
        return "\n".join(chunk.get("text", "") for chunk in chunks if chunk.get("type") == "text")

    def _call_gemini(
        self,
        config: ModelConfig,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        key = self.settings.google_api_key
        if not key:
            raise ValueError("Missing GOOGLE_API_KEY")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{config.model_name}:generateContent"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(user_payload, ensure_ascii=False)}]}],
            "generationConfig": {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_tokens,
                "responseMimeType": "application/json",
            },
        }
        with httpx.Client(timeout=config.timeout_seconds, follow_redirects=True) as client:
            response = client.post(url, params={"key": key}, json=body)
            response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        return "\n".join(part.get("text", "") for part in parts)

    def _openai_compatible_credentials(self, provider: str) -> tuple[str | None, str]:
        if provider == "openai":
            return self.settings.openai_api_key, "https://api.openai.com/v1"
        if provider == "deepseek":
            return self.settings.deepseek_api_key, "https://api.deepseek.com/v1"
        if provider == "qwen":
            return self.settings.qwen_api_key, "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if provider == "stepfun":
            return self.settings.stepfun_api_key, "https://api.stepfun.com/v1"
        if provider == "openrouter":
            return self.settings.openrouter_api_key, "https://openrouter.ai/api/v1"
        return None, ""

    def _extract_json(self, text: str) -> dict[str, Any]:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"items": parsed}
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {"items": parsed}
        except json.JSONDecodeError:
            return {}

    def _fallback_result(
        self,
        provider: str,
        model: str,
        fallback: dict[str, Any],
        prompt_hash: str,
    ) -> LLMResult:
        text = json.dumps(fallback, ensure_ascii=False, indent=2)
        return LLMResult(
            provider=provider,
            model=model,
            text=text,
            json_data=fallback,
            prompt_hash=prompt_hash,
            used_fallback=True,
        )

    def _prompt_hash(self, system_prompt: str, user_payload: dict[str, Any]) -> str:
        payload = system_prompt + "\n" + json.dumps(user_payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

