from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import app.services.hf_mcp as hf_mcp
from app.config import Settings


ROOT = Path(__file__).resolve().parents[1]


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


class FakeResponse:
    def __init__(
        self,
        payload: dict | list | None,
        *,
        status_code: int = 200,
        json_error: bool = False,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.notion.com/v1/test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "Notion error body with private details",
                request=request,
                response=response,
            )

    def json(self) -> dict:
        if self.json_error:
            raise ValueError("not json")
        return self.payload


class FakeAsyncClient:
    instances: list["FakeAsyncClient"] = []
    next_response: FakeResponse | None = None

    def __init__(self, *, timeout: int) -> None:
        self.timeout = timeout
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []
        self.instances.append(self)

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(
        self, url: str, *, headers: dict, params: dict | None = None
    ) -> FakeResponse:
        self.calls.append(("get", url, params, None))
        return self.next_response or FakeResponse({"ok": True})

    async def post(
        self, url: str, *, headers: dict, json: dict | None = None
    ) -> FakeResponse:
        self.calls.append(("post", url, None, json))
        return self.next_response or FakeResponse({"ok": True})

    async def patch(
        self, url: str, *, headers: dict, json: dict | None = None
    ) -> FakeResponse:
        self.calls.append(("patch", url, None, json))
        return self.next_response or FakeResponse({"ok": True})


def test_settings_accept_notion_api_key_alias(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.setenv("NOTION_API_KEY", "  ntn_test  ")

    settings = Settings()

    assert settings.notion_token == "ntn_test"


def test_settings_use_hf_token_alias(monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.setenv("HF_TOKEN", "  hf_test  ")

    settings = Settings()

    assert settings.hf_api_key == "hf_test"


def test_settings_treat_blank_required_env_as_missing(monkeypatch):
    monkeypatch.setenv("HF_API_KEY", "  ")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("NOTION_TOKEN", "\t")
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "")

    settings = Settings()

    assert settings.missing_required_env() == [
        "HF_API_KEY",
        "NOTION_TOKEN",
        "NOTION_PARENT_PAGE_ID",
    ]


def test_env_example_keeps_provider_values_blank():
    env_example = (ROOT / ".env.example").read_text()
    values = dict(
        line.split("=", 1)
        for line in env_example.splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    for key in ("HF_API_KEY", "NOTION_TOKEN", "NOTION_API_KEY", "NOTION_PARENT_PAGE_ID", "HF_MODEL"):
        assert values[key] == ""


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


def test_parse_mcp_tool_result_rejects_invalid_json():
    result = SimpleNamespace(content=[SimpleNamespace(text="not json")])

    with pytest.raises(hf_mcp.HFMCPError, match="invalid JSON"):
        hf_mcp.parse_mcp_tool_result(result, "API-get-self")


def test_parse_mcp_tool_result_rejects_non_object_payload():
    result = SimpleNamespace(content=[SimpleNamespace(text="[]")])

    with pytest.raises(hf_mcp.HFMCPError, match="unexpected payload shape"):
        hf_mcp.parse_mcp_tool_result(result, "API-get-self")


def test_parse_mcp_tool_result_rejects_non_text_content():
    result = SimpleNamespace(content=[SimpleNamespace(data={"id": "apivault"})])

    with pytest.raises(hf_mcp.HFMCPError, match="non-text content"):
        hf_mcp.parse_mcp_tool_result(result, "API-get-self")


@pytest.mark.asyncio
async def test_rest_fallback_does_not_mutate_tool_arguments(monkeypatch):
    FakeAsyncClient.instances = []
    FakeAsyncClient.next_response = None
    monkeypatch.setattr(hf_mcp.httpx, "AsyncClient", FakeAsyncClient)
    fallback = hf_mcp.NotionHTTPFallback("ntn_test")
    args = {"block_id": "block_123", "page_size": 25}

    result = await fallback.call_tool("API-get-block-children", args)

    assert result == {"ok": True}
    assert args == {"block_id": "block_123", "page_size": 25}
    client = FakeAsyncClient.instances[0]
    assert client.timeout == 30
    assert client.calls == [
        (
            "get",
            f"{hf_mcp.NOTION_API}/blocks/block_123/children",
            {"page_size": 25},
            None,
        )
    ]


@pytest.mark.asyncio
async def test_rest_fallback_rejects_unknown_tools():
    fallback = hf_mcp.NotionHTTPFallback("ntn_test")

    with pytest.raises(hf_mcp.HFMCPError, match="Unknown Notion tool"):
        await fallback.call_tool("API-delete-everything", {})


@pytest.mark.asyncio
async def test_rest_fallback_requires_tool_arguments():
    fallback = hf_mcp.NotionHTTPFallback("ntn_test")

    with pytest.raises(hf_mcp.HFMCPError, match="block_id"):
        await fallback.call_tool("API-get-block-children", {"page_size": 25})


@pytest.mark.asyncio
async def test_rest_fallback_raises_sanitized_http_errors(monkeypatch):
    FakeAsyncClient.instances = []
    FakeAsyncClient.next_response = FakeResponse({"error": "private"}, status_code=401)
    monkeypatch.setattr(hf_mcp.httpx, "AsyncClient", FakeAsyncClient)
    fallback = hf_mcp.NotionHTTPFallback("ntn_test")

    with pytest.raises(hf_mcp.HFMCPError) as exc_info:
        await fallback.call_tool("API-get-self", {})

    message = str(exc_info.value)
    assert message == "Notion REST request failed with HTTP 401."
    assert "private" not in message
    assert "ntn_test" not in message
    FakeAsyncClient.next_response = None


@pytest.mark.asyncio
async def test_rest_fallback_rejects_invalid_json(monkeypatch):
    FakeAsyncClient.instances = []
    FakeAsyncClient.next_response = FakeResponse(None, json_error=True)
    monkeypatch.setattr(hf_mcp.httpx, "AsyncClient", FakeAsyncClient)
    fallback = hf_mcp.NotionHTTPFallback("ntn_test")

    with pytest.raises(hf_mcp.HFMCPError, match="invalid JSON"):
        await fallback.call_tool("API-get-self", {})

    FakeAsyncClient.next_response = None


@pytest.mark.asyncio
async def test_rest_fallback_rejects_unexpected_payload_shape(monkeypatch):
    FakeAsyncClient.instances = []
    FakeAsyncClient.next_response = FakeResponse([])
    monkeypatch.setattr(hf_mcp.httpx, "AsyncClient", FakeAsyncClient)
    fallback = hf_mcp.NotionHTTPFallback("ntn_test")

    with pytest.raises(hf_mcp.HFMCPError, match="unexpected payload shape"):
        await fallback.call_tool("API-get-self", {})

    FakeAsyncClient.next_response = None
