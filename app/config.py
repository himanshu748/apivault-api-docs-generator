from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    app_name: str = "APIVault"
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    anthropic_api_url: str = os.getenv(
        "ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages"
    )
    anthropic_version: str = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
    anthropic_mcp_beta: str = os.getenv(
        "ANTHROPIC_MCP_BETA", "mcp-client-2025-04-04"
    )
    notion_token: str | None = os.getenv("NOTION_TOKEN")
    notion_parent_page_id: str | None = os.getenv("NOTION_PARENT_PAGE_ID")
    notion_mcp_url: str = os.getenv("NOTION_MCP_URL", "https://mcp.notion.com/sse")
    request_timeout_seconds: float = float(
        os.getenv("APIVAULT_TIMEOUT_SECONDS", "120")
    )
    state_path: Path = Path(
        os.getenv("APIVAULT_STATE_PATH", ROOT_DIR / "data" / "apivault_state.json")
    )

    def missing_required_env(self) -> list[str]:
        missing = []
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not self.notion_token:
            missing.append("NOTION_TOKEN")
        if not self.notion_parent_page_id:
            missing.append("NOTION_PARENT_PAGE_ID")
        return missing


settings = Settings()
