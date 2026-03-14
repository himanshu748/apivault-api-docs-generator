from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.services.parsing import extract_json_payload


class AnthropicMCPError(RuntimeError):
    pass


class AnthropicMCPClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run_json_task(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        use_notion: bool = True,
    ) -> Any:
        payload: dict[str, Any] = {
            "model": self.settings.anthropic_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        if use_notion:
            payload["mcp_servers"] = [
                {
                    "type": "url",
                    "url": self.settings.notion_mcp_url,
                    "name": "notion",
                    "authorization_token": self.settings.notion_token,
                }
            ]

        headers = {
            "x-api-key": self.settings.anthropic_api_key or "",
            "anthropic-version": self.settings.anthropic_version,
            "anthropic-beta": self.settings.anthropic_mcp_beta,
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                self.settings.anthropic_api_url,
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            detail = response.text.strip()
            raise AnthropicMCPError(
                f"Anthropic API request failed with {response.status_code}: {detail}"
            )

        body = response.json()
        text = "\n".join(
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        ).strip()
        if body.get("stop_reason") == "max_tokens":
            raise AnthropicMCPError(
                "Claude ran out of tokens before returning a complete JSON response."
            )
        if not text:
            raise AnthropicMCPError("Claude returned no final text response.")

        try:
            return extract_json_payload(text)
        except ValueError as exc:
            raise AnthropicMCPError(str(exc)) from exc
