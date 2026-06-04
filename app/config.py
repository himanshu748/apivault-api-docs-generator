from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    _default_cors_origins: ClassVar[tuple[str, ...]] = (
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    )

    app_name: str = "APIVault"
    hf_api_key: str | None = field(default_factory=lambda: os.getenv("HF_API_KEY"))
    hf_model: str = field(
        default_factory=lambda: os.getenv("HF_MODEL", "Qwen/Qwen2.5-72B-Instruct")
    )
    notion_token: str | None = field(
        default_factory=lambda: os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
    )
    notion_parent_page_id: str | None = field(
        default_factory=lambda: os.getenv("NOTION_PARENT_PAGE_ID")
    )
    notion_mcp_url: str = field(
        default_factory=lambda: os.getenv("NOTION_MCP_URL", "https://mcp.notion.com/sse")
    )
    request_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("APIVAULT_TIMEOUT_SECONDS", "120"))
    )
    state_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("APIVAULT_STATE_PATH", ROOT_DIR / "data" / "apivault_state.json")
        )
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", ",".join(Settings._default_cors_origins)).split(",")
            if origin.strip()
        )
    )
    max_request_body_bytes: int = field(
        default_factory=lambda: int(os.getenv("APIVAULT_MAX_BODY_BYTES", "220000"))
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
