from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    app_name: str = "APIVault"
    hf_api_key: str | None = os.getenv("HF_API_KEY")
    hf_model: str = os.getenv(
        "HF_MODEL", "Qwen/Qwen2.5-72B-Instruct"
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
        if not self.hf_api_key:
            missing.append("HF_API_KEY")
        if not self.notion_token:
            missing.append("NOTION_TOKEN")
        if not self.notion_parent_page_id:
            missing.append("NOTION_PARENT_PAGE_ID")
        return missing


settings = Settings()
