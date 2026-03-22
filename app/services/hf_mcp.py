"""
APIVault — MCP + HuggingFace integration layer.

Architecture:
  HuggingFace InferenceClient  →  structured content generation
  Notion MCP (stdio server)    →  ALL Notion reads & writes via MCP protocol
  httpx fallback               →  when MCP stdio is unavailable
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from huggingface_hub import InferenceClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import Settings
from app.services.parsing import extract_json_payload

log = logging.getLogger("apivault")


class HFMCPError(RuntimeError):
    pass


# ── Notion transport layer (MCP primary, httpx fallback) ─────────────────────

NOTION_API = "https://api.notion.com/v1"
NOTION_VER = "2022-06-28"


class NotionHTTPFallback:
    """Direct Notion REST client — used when MCP stdio is unavailable."""

    def __init__(self, notion_token: str) -> None:
        self._token = notion_token

    def _h(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VER,
            "Content-Type": "application/json",
        }

    async def call_tool(self, tool: str, args: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as c:
            if tool == "API-post-page":
                r = await c.post(f"{NOTION_API}/pages", headers=self._h(), json=args)
            elif tool == "API-post-search":
                r = await c.post(f"{NOTION_API}/search", headers=self._h(), json=args)
            elif tool == "API-get-block-children":
                bid = args.pop("block_id")
                r = await c.get(
                    f"{NOTION_API}/blocks/{bid}/children",
                    headers=self._h(),
                    params=args,
                )
            elif tool == "API-get-self":
                r = await c.get(f"{NOTION_API}/users/me", headers=self._h())
            elif tool == "API-patch-page":
                pid = args.pop("page_id")
                r = await c.patch(
                    f"{NOTION_API}/pages/{pid}", headers=self._h(), json=args
                )
            elif tool == "API-retrieve-a-page":
                pid = args.pop("page_id")
                r = await c.get(f"{NOTION_API}/pages/{pid}", headers=self._h())
            elif tool == "API-post-database":
                r = await c.post(
                    f"{NOTION_API}/databases", headers=self._h(), json=args
                )
            elif tool == "API-post-database-query":
                did = args.pop("database_id")
                r = await c.post(
                    f"{NOTION_API}/databases/{did}/query",
                    headers=self._h(),
                    json=args,
                )
            elif tool == "API-patch-database":
                did = args.pop("database_id")
                r = await c.patch(
                    f"{NOTION_API}/databases/{did}", headers=self._h(), json=args
                )
            else:
                return {"error": f"Unknown tool: {tool}"}
            return r.json()


# ── Block builders ───────────────────────────────────────────────────────────


def _rt(content: str) -> list:
    """Rich-text helper: wrap a plain string for the Notion API."""
    return [{"text": {"content": content}}]


def _heading(text: str, level: int = 2) -> dict:
    k = f"heading_{level}"
    return {"object": "block", "type": k, k: {"rich_text": _rt(text)}}


def _para(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rt(text)},
    }


def _bullet(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rt(text)},
    }


# ── MCP context managers ────────────────────────────────────────────────────


@asynccontextmanager
async def notion_mcp(notion_token: str):
    """Spin up Notion MCP stdio server and yield a ClientSession."""
    params = StdioServerParameters(
        command="npx",
        args=["-y", "@notionhq/notion-mcp-server"],
        env={**os.environ, "NOTION_TOKEN": notion_token},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@asynccontextmanager
def notion_session(notion_token: str):
    return notion_mcp(notion_token)


# ── MCP call helpers ─────────────────────────────────────────────────────────


async def mcp_call(session, tool: str, args: dict) -> dict:
    """Call a Notion MCP tool, returning the parsed JSON result."""
    if isinstance(session, NotionHTTPFallback):
        return await session.call_tool(tool, args)
    result = await session.call_tool(tool, args)
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


async def mcp_create_page(
    session, parent_id: str, title: str, children: list
) -> dict:
    """Create a Notion page via MCP API-post-page tool."""
    return await mcp_call(
        session,
        "API-post-page",
        {
            "parent": {"page_id": parent_id},
            "properties": {"title": {"title": _rt(title)}},
            "children": children[:100],
        },
    )


async def mcp_search(session, query: str = "") -> list:
    """Search Notion via MCP API-post-search tool."""
    result = await mcp_call(
        session, "API-post-search", {"query": query, "page_size": 50}
    )
    return result.get("results", [])


async def mcp_get_children(session, block_id: str) -> list:
    """Read block children via MCP API-get-block-children tool."""
    result = await mcp_call(
        session,
        "API-get-block-children",
        {"block_id": block_id, "page_size": 100},
    )
    return result.get("results", [])


# ── HuggingFace text generation ──────────────────────────────────────────────


async def generate_text(
    model: str,
    api_key: str,
    system: str,
    user_msg: str,
    *,
    max_tokens: int = 4096,
) -> str:
    """Generate text via HuggingFace InferenceClient (streaming)."""
    hf = InferenceClient(model=model, token=api_key)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    out = ""
    for chunk in hf.chat_completion(
        messages=messages, max_tokens=max_tokens, stream=True
    ):
        if chunk.choices:
            d = chunk.choices[0].delta
            if d.content:
                out += d.content
    return out


# ── Public client ────────────────────────────────────────────────────────────


class HFMCPClient:
    """Wraps HuggingFace text generation and Notion MCP operations."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> Any:
        """Use HF to generate text and extract a JSON payload."""
        try:
            raw = await generate_text(
                self.settings.hf_model,
                self.settings.hf_api_key,
                system_prompt,
                user_prompt,
                max_tokens=max_tokens,
            )
            if not raw.strip():
                raise HFMCPError("AI returned no text response.")
            return extract_json_payload(raw)
        except HFMCPError:
            raise
        except ValueError as exc:
            raise HFMCPError(str(exc)) from exc
        except Exception as exc:
            raise HFMCPError(f"HuggingFace API request failed: {exc}") from exc

    def notion_ctx(self):
        """Return a notion_session async context manager."""
        return notion_session(self.settings.notion_token)
