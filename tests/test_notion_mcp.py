from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.hf_mcp as hf_mcp


class FakeServerParameters:
    def __init__(self, *, command: str, args: list[str], env: dict[str, str]) -> None:
        self.command = command
        self.args = args
        self.env = env


class FakeClientSession:
    def __init__(self, read: object, write: object) -> None:
        self.initialized = False

    async def __aenter__(self) -> "FakeClientSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def initialize(self) -> None:
        self.initialized = True

    async def call_tool(self, tool: str, args: dict) -> SimpleNamespace:
        assert self.initialized is True
        assert tool == "API-get-self"
        assert args == {}
        return SimpleNamespace(
            content=[
                SimpleNamespace(text='{"id":"notion-user","name":"APIVault"}')
            ]
        )


class FakeStdioClient:
    def __init__(self, params: FakeServerParameters) -> None:
        self.params = params

    async def __aenter__(self) -> tuple[object, object]:
        assert self.params.command == "npx"
        assert self.params.args == ["-y", "@notionhq/notion-mcp-server"]
        assert self.params.env["NOTION_TOKEN"] == "ntn_test"
        return object(), object()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_notion_mcp_uses_official_stdio_server(monkeypatch):
    monkeypatch.setattr(hf_mcp, "StdioServerParameters", FakeServerParameters)
    monkeypatch.setattr(hf_mcp, "ClientSession", FakeClientSession)
    monkeypatch.setattr(hf_mcp, "stdio_client", lambda params: FakeStdioClient(params))

    async with hf_mcp.notion_mcp("ntn_test") as session:
        result = await hf_mcp.mcp_call(session, "API-get-self", {})

    assert result == {"id": "notion-user", "name": "APIVault"}
    assert hf_mcp.notion_transport_name() == "mcp-stdio"


@pytest.mark.asyncio
async def test_notion_mcp_requires_token():
    with pytest.raises(hf_mcp.HFMCPError, match="NOTION_TOKEN"):
        async with hf_mcp.notion_mcp(None):
            pass
