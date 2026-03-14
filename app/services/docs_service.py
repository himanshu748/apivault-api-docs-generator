from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import HTTPException

from app.config import Settings
from app.models import (
    DocumentCollectionRequest,
    DocumentCollectionResponse,
    DocumentEndpointRequest,
    DocumentEndpointResponse,
    GenerateReadmeResponse,
    GeneratedDocumentation,
    SearchResponse,
    SearchResult,
    SetupResponse,
    SidebarResponse,
)
from app.services.anthropic_mcp import AnthropicMCPClient, AnthropicMCPError
from app.services.parsing import default_error_codes, infer_method_and_path, title_from_method_path
from app.services.state_store import StateStore


class DocumentationService:
    def __init__(
        self,
        *,
        settings: Settings,
        client: AnthropicMCPClient,
        state_store: StateStore,
    ) -> None:
        self.settings = settings
        self.client = client
        self.state_store = state_store

    def _ensure_environment(self) -> None:
        missing = self.settings.missing_required_env()
        if missing:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Missing required environment variables: "
                    + ", ".join(missing)
                    + ". NOTION_TOKEN must be a Notion MCP OAuth access token, not a direct Notion API key."
                ),
            )

    async def setup(self) -> SetupResponse:
        self._ensure_environment()
        cached_setup = self.state_store.get_setup()
        system_prompt = (
            "You are APIVault. Use the Notion MCP tools to configure a reusable API documentation workspace. "
            "Return strict JSON only, with no markdown fences."
        )
        user_prompt = f"""
Today is 2026-03-10.
Set up the APIVault workspace in Notion under parent page id `{self.settings.notion_parent_page_id}`.

Existing cached setup (may be empty; reuse when possible): {json.dumps(cached_setup, ensure_ascii=True)}

Create or find these resources:
1. A database titled "📖 API Reference"
2. A database titled "🏷️ Services"
3. A hub page titled "📚 API Docs" with an intro and table of contents

Schema requirements:
- "📖 API Reference" properties:
  * Endpoint Title: title
  * Method: select with GET, POST, PUT, DELETE, PATCH
  * Path: rich text
  * Description: rich text
  * Auth Required: checkbox
  * Deprecated: checkbox
  * Version: rich text
  * Service/Tag: relation to the "🏷️ Services" database so the service rollup can work
  * Request Body: rich text
  * Response Schema: rich text
  * Error Codes: rich text
  * Curl Example: rich text
  * Last Updated: last edited time

- "🏷️ Services" properties:
  * Name: title
  * Base URL: url
  * Description: rich text
  * Auth Type: select
  * Endpoint Count: rollup counting related endpoints
  * Owner: rich text
  * Endpoints: relation back to "📖 API Reference"

The "📚 API Docs" hub page should have:
- A short overview of APIVault
- A table of contents block
- Sections for Services, API Reference, and Generated READMEs

Requirements:
- Prefer updating existing resources if they already exist.
- Do not use the direct Notion REST API.
- Return only valid JSON with this shape:
{{
  "api_reference_url": "https://...",
  "services_url": "https://...",
  "hub_page_url": "https://...",
  "notes": ["..."]
}}
""".strip()

        try:
            payload = await self.client.run_json_task(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=3000,
            )
        except AnthropicMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        result = {
            "api_reference_url": payload.get("api_reference_url", ""),
            "services_url": payload.get("services_url", ""),
            "hub_page_url": payload.get("hub_page_url", ""),
            "notes": payload.get("notes", []),
            "auth_notice": (
                "Notion MCP requires user OAuth. APIVault expects NOTION_TOKEN to be a pre-authorized "
                "MCP access token obtained through the Notion MCP OAuth flow."
            ),
        }
        self.state_store.save_setup(result)
        return SetupResponse.model_validate(result)

    async def document_endpoint(
        self, request: DocumentEndpointRequest
    ) -> DocumentEndpointResponse:
        self._ensure_environment()
        cached_setup = self.state_store.get_setup()
        fallback_method, fallback_path = infer_method_and_path(request.code)
        fallback_title = title_from_method_path(fallback_method, fallback_path)
        system_prompt = (
            "You are APIVault, an expert API technical writer. "
            "Use Notion MCP tools when helpful, then return strict JSON only."
        )
        user_prompt = f"""
Today is 2026-03-10.
Generate complete API documentation and store it in Notion for the endpoint below.

Setup context: {json.dumps(cached_setup, ensure_ascii=True)}

Input:
- language: {request.language}
- service: {request.service}
- base_url: {request.base_url}
- raw_input:
{request.code}

Notion tasks:
1. Reuse or create the APIVault setup resources if needed.
2. Upsert a service record in "🏷️ Services" using the service name "{request.service}" and base URL "{request.base_url}".
3. Find an existing endpoint in "📖 API Reference" by matching service + method + path before creating a duplicate.
4. Create or update the endpoint record and fill these properties:
   - Endpoint Title
   - Method
   - Path
   - Description
   - Auth Required
   - Deprecated
   - Version
   - Service/Tag relation
   - Request Body
   - Response Schema
   - Error Codes
   - Curl Example
   - Last Updated
5. Add page content blocks with:
   - Summary
   - Request Parameters table
   - Request Body JSON Schema
   - Request Body Example
   - Response Schema
   - Response Example
   - Error Codes
   - Curl Example
   - Python requests example
   - JavaScript fetch example
   - Assumptions

Content requirements:
- Infer method, path, request params, request body schema, and response schema.
- Description must be plain English in exactly 2 sentences.
- Include realistic sample data.
- Error codes must include 400, 401, 403, 404, 422, and 500.
- If input is ambiguous, make the safest reasonable assumption and list it.
- Use this fallback only if inference is unclear:
  * method: {fallback_method}
  * path: {fallback_path}
  * title: {fallback_title}

Return only valid JSON in this shape:
{{
  "title": "{fallback_title}",
  "summary": "One-sentence summary",
  "description": "Exactly two sentences.",
  "method": "{fallback_method}",
  "path": "{fallback_path}",
  "service": "{request.service}",
  "version": "v1",
  "auth_required": false,
  "deprecated": false,
  "base_url": "{request.base_url}",
  "assumptions": ["..."],
  "request_parameters": [
    {{
      "name": "user_id",
      "type": "string",
      "required": true,
      "description": "User identifier.",
      "location": "path"
    }}
  ],
  "request_body_schema": {{"type": "object", "properties": {{}}, "required": []}},
  "request_body_example": {{}},
  "response_schema": {{"type": "object", "properties": {{}}, "required": []}},
  "response_example": {{}},
  "error_codes": {json.dumps(default_error_codes(), ensure_ascii=True)},
  "curl_example": "curl ...",
  "python_example": "import requests ...",
  "javascript_example": "fetch(...)",
  "request_body_text": "Readable JSON schema text",
  "response_schema_text": "Readable response schema text",
  "error_codes_text": "400 ...",
  "notion_url": "https://..."
}}
""".strip()

        try:
            payload = await self.client.run_json_task(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=5000,
            )
        except AnthropicMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if "error_codes" not in payload or not payload["error_codes"]:
            payload["error_codes"] = default_error_codes()
        payload.setdefault("method", fallback_method)
        payload.setdefault("path", fallback_path)
        payload.setdefault("title", fallback_title)
        payload.setdefault("service", request.service)
        payload.setdefault("base_url", request.base_url)
        payload.setdefault("summary", payload.get("description", fallback_title))
        payload.setdefault("description", payload.get("summary", fallback_title))
        payload.setdefault("request_parameters", [])
        payload.setdefault("request_body_schema", {})
        payload.setdefault("response_schema", {})
        payload.setdefault("assumptions", [])
        payload.setdefault("request_body_text", json.dumps(payload["request_body_schema"], indent=2))
        payload.setdefault(
            "response_schema_text", json.dumps(payload["response_schema"], indent=2)
        )
        payload.setdefault(
            "error_codes_text",
            "\n".join(
                f"{entry['code']}: {entry['meaning']}" for entry in payload["error_codes"]
            ),
        )

        documentation = GeneratedDocumentation.model_validate(payload)
        self.state_store.upsert_doc(documentation.model_dump())
        return DocumentEndpointResponse(
            notion_url=documentation.notion_url,
            method=documentation.method,
            path=documentation.path,
            summary=documentation.summary,
            documentation=documentation,
        )

    async def document_collection(
        self, request: DocumentCollectionRequest
    ) -> DocumentCollectionResponse:
        self._ensure_environment()
        system_prompt = (
            "You split router/controller files into individual endpoints. "
            "Do not use external tools. Return strict JSON only."
        )
        user_prompt = f"""
Analyze this code or natural-language endpoint collection and split it into individual endpoint units.

language: {request.language}
service: {request.service}
base_url: {request.base_url}

Input:
{request.code}

Return only JSON with this shape:
{{
  "items": [
    {{
      "code": "standalone code or description for one endpoint",
      "language": "{request.language}",
      "service": "{request.service}",
      "base_url": "{request.base_url}"
    }}
  ]
}}

If you can only identify one endpoint, return a single item containing the original input.
""".strip()

        try:
            payload = await self.client.run_json_task(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=3000,
                use_notion=False,
            )
        except AnthropicMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        raw_items = payload.get("items") or [
            {
                "code": request.code,
                "language": request.language,
                "service": request.service,
                "base_url": request.base_url,
            }
        ]
        tasks = [
            self.document_endpoint(DocumentEndpointRequest.model_validate(item))
            for item in raw_items
        ]
        results = await asyncio.gather(*tasks)
        return DocumentCollectionResponse(
            service=request.service,
            count=len(results),
            items=results,
        )

    async def generate_readme(self, service: str) -> GenerateReadmeResponse:
        self._ensure_environment()
        cached_setup = self.state_store.get_setup()
        system_prompt = (
            "You are APIVault. Use Notion MCP tools to gather endpoint docs and create a service README page. "
            "Return strict JSON only."
        )
        user_prompt = f"""
Today is 2026-03-10.
Create or update a Notion page titled "📄 {service} — README" for the service "{service}".

Setup context: {json.dumps(cached_setup, ensure_ascii=True)}

Requirements:
- Read all endpoints for the service from "📖 API Reference"
- Place the page under the "📚 API Docs" hub if possible
- Include sections:
  * Overview
  * Authentication guide
  * Quickstart with 3 curl examples
  * Full endpoint reference table
  * Rate limits
  * Changelog placeholder

Return only JSON:
{{
  "service": "{service}",
  "title": "📄 {service} — README",
  "notion_url": "https://...",
  "endpoint_count": 0,
  "overview": "Short overview"
}}
""".strip()

        try:
            payload = await self.client.run_json_task(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=4000,
            )
        except AnthropicMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return GenerateReadmeResponse.model_validate(payload)

    async def search(self, query: str) -> SearchResponse:
        self._ensure_environment()
        if not query.strip():
            return SearchResponse(q=query, results=[])

        cached_setup = self.state_store.get_setup()
        system_prompt = (
            "You are APIVault. Use Notion MCP tools to search the API Reference database. "
            "Return strict JSON only."
        )
        user_prompt = f"""
Search the APIVault "📖 API Reference" database for this query: "{query}".

Setup context: {json.dumps(cached_setup, ensure_ascii=True)}

Return JSON only:
{{
  "results": [
    {{
      "title": "Get Users",
      "method": "GET",
      "path": "/users",
      "description": "Short description",
      "service": "UserService",
      "notion_url": "https://..."
    }}
  ]
}}
""".strip()

        try:
            payload = await self.client.run_json_task(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=2000,
            )
            results = [
                SearchResult.model_validate(item) for item in payload.get("results", [])
            ]
            return SearchResponse(q=query, results=results)
        except (AnthropicMCPError, ValueError):
            cached = self.state_store.search_docs(query)
            return SearchResponse(
                q=query,
                results=[
                    SearchResult(
                        title=item.get("title", ""),
                        method=item.get("method", ""),
                        path=item.get("path", ""),
                        description=item.get("description", ""),
                        service=item.get("service", ""),
                        notion_url=item.get("notion_url"),
                    )
                    for item in cached
                ],
            )

    async def sidebar(self, fresh: bool = False) -> SidebarResponse:
        if not fresh:
            cached = self.state_store.sidebar_from_cache()
            if cached.get("services"):
                return SidebarResponse.model_validate(cached)

        self._ensure_environment()
        cached_setup = self.state_store.get_setup()
        system_prompt = (
            "You are APIVault. Use Notion MCP tools to retrieve service and endpoint navigation data. "
            "Return strict JSON only."
        )
        user_prompt = f"""
Read the APIVault Notion workspace and return sidebar navigation data.

Setup context: {json.dumps(cached_setup, ensure_ascii=True)}

Return JSON only:
{{
  "services": [
    {{
      "name": "UserService",
      "base_url": "https://api.example.com",
      "description": "Service description",
      "auth_type": "Bearer",
      "owner": "Platform Team",
      "notion_url": "https://...",
      "endpoints": [
        {{
          "title": "List Users",
          "method": "GET",
          "path": "/users",
          "description": "Lists users",
          "notion_url": "https://..."
        }}
      ]
    }}
  ],
  "source": "notion"
}}
""".strip()

        try:
            payload = await self.client.run_json_task(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=3000,
            )
            self.state_store.save_sidebar(payload)
            return SidebarResponse.model_validate(payload)
        except (AnthropicMCPError, ValueError):
            return SidebarResponse.model_validate(self.state_store.sidebar_from_cache())
