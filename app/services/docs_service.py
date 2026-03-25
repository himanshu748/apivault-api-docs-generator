from __future__ import annotations

import asyncio
import json
import logging
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
from app.services.hf_mcp import (
    HFMCPClient,
    HFMCPError,
    _bullet,
    _heading,
    _para,
    _rt,
    mcp_call,
    mcp_create_page,
    mcp_search,
)
from app.services.parsing import (
    default_error_codes,
    infer_method_and_path,
    title_from_method_path,
)
from app.services.state_store import StateStore

log = logging.getLogger("apivault")


class DocumentationService:
    def __init__(
        self,
        *,
        settings: Settings,
        client: HFMCPClient,
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

    # ── setup ────────────────────────────────────────────────────────────────

    async def setup(self) -> SetupResponse:
        self._ensure_environment()
        cached_setup = self.state_store.get_setup()
        parent_id = self.settings.notion_parent_page_id

        # Step 1: HF generates workspace structure JSON
        system_prompt = (
            "You are APIVault. Generate a workspace setup plan as strict JSON only, "
            "with no markdown fences."
        )
        user_prompt = f"""
Today is 2026-03-10.
Generate a workspace setup plan for APIVault API documentation under parent page id `{parent_id}`.

Existing cached setup (may be empty; reuse when possible): {json.dumps(cached_setup, ensure_ascii=True)}

Return only valid JSON:
{{
  "overview": "Short overview of the APIVault workspace",
  "api_ref_title": "📖 API Reference",
  "services_title": "🏷️ Services",
  "hub_title": "📚 API Docs",
  "sections": ["Services", "API Reference", "Generated READMEs"],
  "notes": ["any setup notes"]
}}
""".strip()

        try:
            payload = await self.client.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1000,
            )
        except HFMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        # Step 2: MCP creates Notion pages
        try:
            async with self.client.notion_ctx() as mcp:
                # Create Services page
                svc_blocks = [
                    _heading("Services Registry"),
                    _para("API services will be documented as sub-pages."),
                    _heading("Fields", 3),
                    _bullet("Name"), _bullet("Base URL"), _bullet("Description"),
                    _bullet("Auth Type (Bearer/API Key/OAuth/None)"), _bullet("Owner"),
                ]
                services_page = await mcp_create_page(
                    mcp, parent_id,
                    payload.get("services_title", "🏷️ Services"), svc_blocks,
                )

                # Create API Reference page
                ref_blocks = [
                    _heading("API Reference"),
                    _para("Endpoint documentation will be added as sub-pages."),
                    _heading("Fields", 3),
                    _bullet("Method (GET/POST/PUT/DELETE/PATCH)"),
                    _bullet("Path"), _bullet("Description"),
                    _bullet("Auth Required"), _bullet("Request Body"),
                    _bullet("Response Schema"), _bullet("Error Codes"),
                ]
                api_ref_page = await mcp_create_page(
                    mcp, parent_id,
                    payload.get("api_ref_title", "📖 API Reference"), ref_blocks,
                )

                # Create hub page
                overview = payload.get("overview", "APIVault API Documentation Workspace")
                sections = payload.get("sections", ["Services", "API Reference", "READMEs"])
                hub_blocks = [
                    _heading("Welcome to APIVault"), _para(overview),
                    _heading("Table of Contents"),
                ]
                for section in sections:
                    hub_blocks.append(_bullet(section))
                hub_blocks.append(_heading("Resources"))
                hub_blocks.append(_bullet(f"API Reference: {api_ref_page.get('url', 'N/A')}"))
                hub_blocks.append(_bullet(f"Services: {services_page.get('url', 'N/A')}"))

                hub_page = await mcp_create_page(
                    mcp, parent_id,
                    payload.get("hub_title", "📚 API Docs"), hub_blocks,
                )

        except (HFMCPError, HTTPException):
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Notion MCP error: {exc}"
            ) from exc

        result = {
            "api_reference_url": api_ref_page.get("url", ""),
            "services_url": services_page.get("url", ""),
            "hub_page_url": hub_page.get("url", ""),
            "notes": payload.get("notes", []),
            "auth_notice": (
                "Notion MCP requires user OAuth. APIVault expects NOTION_TOKEN to be a pre-authorized "
                "MCP access token obtained through the Notion MCP OAuth flow."
            ),
        }
        self.state_store.save_setup(result)
        return SetupResponse.model_validate(result)

    # ── document-endpoint ────────────────────────────────────────────────────

    async def document_endpoint(
        self, request: DocumentEndpointRequest
    ) -> DocumentEndpointResponse:
        self._ensure_environment()
        cached_setup = self.state_store.get_setup()
        fallback_method, fallback_path = infer_method_and_path(request.code)
        fallback_title = title_from_method_path(fallback_method, fallback_path)

        # Step 1: HF generates documentation JSON
        system_prompt = (
            "You are APIVault, an expert API technical writer. "
            "Generate complete API documentation as strict JSON only, with no markdown fences."
        )
        user_prompt = f"""
Today is 2026-03-10.
Generate complete API documentation for the endpoint below.

Setup context: {json.dumps(cached_setup, ensure_ascii=True)}

Input:
- language: {request.language}
- service: {request.service}
- base_url: {request.base_url}
- raw_input:
{request.code}

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
  "error_codes_text": "400 ..."
}}
""".strip()

        try:
            payload = await self.client.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=5000,
            )
        except HFMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        # Apply defaults
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
        payload.setdefault(
            "request_body_text",
            json.dumps(payload["request_body_schema"], indent=2),
        )
        payload.setdefault(
            "response_schema_text",
            json.dumps(payload["response_schema"], indent=2),
        )
        payload.setdefault(
            "error_codes_text",
            "\n".join(
                f"{entry['code']}: {entry['meaning']}"
                for entry in payload["error_codes"]
            ),
        )

        # Step 2: MCP writes documentation to Notion
        notion_url = None
        try:
            async with self.client.notion_ctx() as mcp:
                blocks = [
                    _heading("Summary"),
                    _para(payload.get("summary", "")),
                    _heading("Description"),
                    _para(payload.get("description", "")),
                ]

                # Request Parameters
                params = payload.get("request_parameters", [])
                if params:
                    blocks.append(_heading("Request Parameters"))
                    for p in params:
                        loc = p.get("location", "query")
                        req = "required" if p.get("required") else "optional"
                        blocks.append(
                            _bullet(
                                f'{p.get("name", "")} ({p.get("type", "string")}, '
                                f"{loc}, {req}): {p.get('description', '')}"
                            )
                        )

                # Request Body
                if payload.get("request_body_schema"):
                    blocks.append(_heading("Request Body Schema"))
                    blocks.append(_para(payload.get("request_body_text", "")))
                if payload.get("request_body_example"):
                    blocks.append(_heading("Request Body Example"))
                    blocks.append(
                        _para(
                            json.dumps(
                                payload["request_body_example"], indent=2
                            )
                        )
                    )

                # Response
                if payload.get("response_schema"):
                    blocks.append(_heading("Response Schema"))
                    blocks.append(
                        _para(payload.get("response_schema_text", ""))
                    )
                if payload.get("response_example"):
                    blocks.append(_heading("Response Example"))
                    blocks.append(
                        _para(
                            json.dumps(
                                payload["response_example"], indent=2
                            )
                        )
                    )

                # Error Codes
                blocks.append(_heading("Error Codes"))
                for err in payload.get("error_codes", []):
                    blocks.append(
                        _bullet(
                            f'{err.get("code", "")}: {err.get("meaning", "")}'
                        )
                    )

                # Code Examples
                if payload.get("curl_example"):
                    blocks.append(_heading("cURL Example"))
                    blocks.append(_para(payload["curl_example"]))
                if payload.get("python_example"):
                    blocks.append(_heading("Python Example"))
                    blocks.append(_para(payload["python_example"]))
                if payload.get("javascript_example"):
                    blocks.append(_heading("JavaScript Example"))
                    blocks.append(_para(payload["javascript_example"]))

                # Assumptions
                if payload.get("assumptions"):
                    blocks.append(_heading("Assumptions"))
                    for assumption in payload["assumptions"]:
                        blocks.append(_bullet(assumption))

                parent_id = self.settings.notion_parent_page_id
                title = payload.get("title", fallback_title)
                page = await mcp_create_page(mcp, parent_id, title, blocks)
                notion_url = page.get("url")
        except Exception as exc:
            log.warning("Notion write failed: %s", exc)

        payload["notion_url"] = notion_url
        documentation = GeneratedDocumentation.model_validate(payload)
        self.state_store.upsert_doc(documentation.model_dump())
        return DocumentEndpointResponse(
            notion_url=documentation.notion_url,
            method=documentation.method,
            path=documentation.path,
            summary=documentation.summary,
            documentation=documentation,
        )

    # ── document-collection ──────────────────────────────────────────────────

    async def document_collection(
        self, request: DocumentCollectionRequest
    ) -> DocumentCollectionResponse:
        self._ensure_environment()

        # Step 1: HF splits collection into individual endpoints
        system_prompt = (
            "You split router/controller files into individual endpoints. "
            "Return strict JSON only, with no markdown fences."
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
            payload = await self.client.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=3000,
            )
        except HFMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        raw_items = payload.get("items") or [
            {
                "code": request.code,
                "language": request.language,
                "service": request.service,
                "base_url": request.base_url,
            }
        ]

        # Step 2: Document each endpoint (HF generates JSON + MCP writes pages)
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

    # ── generate-readme ──────────────────────────────────────────────────────

    async def generate_readme(self, service: str) -> GenerateReadmeResponse:
        self._ensure_environment()

        # Step 1: HF generates README content
        system_prompt = (
            "You are APIVault. Generate a service README as strict JSON only, "
            "with no markdown fences."
        )
        user_prompt = f"""
Today is 2026-03-10.
Generate a comprehensive README for the service "{service}".

Include sections:
- Overview
- Authentication guide
- Quickstart with 3 curl examples
- Full endpoint reference table
- Rate limits
- Changelog placeholder

Return only JSON:
{{
  "service": "{service}",
  "title": "📄 {service} — README",
  "overview": "Short overview",
  "auth_guide": "Authentication description",
  "quickstart_examples": ["curl ...", "curl ...", "curl ..."],
  "endpoints": [
    {{"method": "GET", "path": "/example", "description": "Example endpoint"}}
  ],
  "rate_limits": "Rate limit description",
  "changelog": "Changelog placeholder"
}}
""".strip()

        try:
            payload = await self.client.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=4000,
            )
        except HFMCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        # Step 2: MCP writes README page to Notion
        notion_url = None
        try:
            async with self.client.notion_ctx() as mcp:
                blocks = [
                    _heading("Overview"),
                    _para(payload.get("overview", "")),
                    _heading("Authentication"),
                    _para(payload.get("auth_guide", "")),
                    _heading("Quickstart"),
                ]
                for example in payload.get("quickstart_examples", []):
                    blocks.append(_para(example))

                blocks.append(_heading("Endpoint Reference"))
                for ep in payload.get("endpoints", []):
                    blocks.append(
                        _bullet(
                            f'{ep.get("method", "GET")} {ep.get("path", "/")} '
                            f'— {ep.get("description", "")}'
                        )
                    )

                blocks.append(_heading("Rate Limits"))
                blocks.append(
                    _para(
                        payload.get(
                            "rate_limits", "See service documentation."
                        )
                    )
                )
                blocks.append(_heading("Changelog"))
                blocks.append(
                    _para(
                        payload.get(
                            "changelog", "No changes recorded yet."
                        )
                    )
                )

                parent_id = self.settings.notion_parent_page_id
                title = payload.get("title", f"📄 {service} — README")
                page = await mcp_create_page(mcp, parent_id, title, blocks)
                notion_url = page.get("url")
        except Exception:
            log.warning("Notion write failed for README", exc_info=True)

        return GenerateReadmeResponse(
            service=service,
            title=payload.get("title", f"📄 {service} — README"),
            notion_url=notion_url,
            endpoint_count=len(payload.get("endpoints", [])),
            overview=payload.get("overview", ""),
        )

    # ── search ───────────────────────────────────────────────────────────────

    async def search(self, query: str) -> SearchResponse:
        self._ensure_environment()
        if not query.strip():
            return SearchResponse(q=query, results=[])

        # Use MCP API-post-search directly
        try:
            async with self.client.notion_ctx() as mcp:
                pages = await mcp_search(mcp, query)
                results = []
                for page in pages:
                    props = page.get("properties", {})

                    # Extract title
                    title = ""
                    for prop in props.values():
                        if prop.get("type") == "title":
                            title = "".join(
                                t.get("plain_text", "")
                                for t in prop.get("title", [])
                            )
                            break

                    # Extract Method
                    method = ""
                    method_prop = props.get("Method", {})
                    if method_prop.get("select"):
                        method = method_prop["select"].get("name", "")

                    # Extract Path
                    path = "".join(
                        t.get("plain_text", "")
                        for t in props.get("Path", {}).get("rich_text", [])
                    )

                    # Extract Description
                    description = "".join(
                        t.get("plain_text", "")
                        for t in props.get("Description", {}).get(
                            "rich_text", []
                        )
                    )

                    if title or method or path:
                        results.append(
                            SearchResult(
                                title=title,
                                method=method,
                                path=path,
                                description=description,
                                service="",
                                notion_url=page.get("url"),
                            )
                        )
                return SearchResponse(q=query, results=results)
        except Exception:
            # Fall back to local cache
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

    # ── sidebar ──────────────────────────────────────────────────────────────

    async def sidebar(self, fresh: bool = False) -> SidebarResponse:
        if not fresh:
            cached = self.state_store.sidebar_from_cache()
            if cached.get("services"):
                return SidebarResponse.model_validate(cached)

        self._ensure_environment()

        # Use MCP to read workspace structure
        try:
            async with self.client.notion_ctx() as mcp:
                pages = await mcp_search(mcp, "")
                services_map: dict[str, dict] = {}

                for page in pages:
                    props = page.get("properties", {})

                    # Detect service pages (has "Base URL" property)
                    if "Base URL" in props:
                        name = ""
                        for prop in props.values():
                            if prop.get("type") == "title":
                                name = "".join(
                                    t.get("plain_text", "")
                                    for t in prop.get("title", [])
                                )
                                break
                        if not name:
                            continue

                        base_url = ""
                        if props["Base URL"].get("url"):
                            base_url = props["Base URL"]["url"] or ""

                        description = "".join(
                            t.get("plain_text", "")
                            for t in props.get("Description", {}).get(
                                "rich_text", []
                            )
                        )

                        auth_type = ""
                        auth_prop = props.get("Auth Type", {})
                        if auth_prop.get("select"):
                            auth_type = auth_prop["select"].get("name", "")

                        owner = "".join(
                            t.get("plain_text", "")
                            for t in props.get("Owner", {}).get(
                                "rich_text", []
                            )
                        )

                        services_map[name] = {
                            "name": name,
                            "base_url": base_url,
                            "description": description,
                            "auth_type": auth_type,
                            "owner": owner,
                            "notion_url": page.get("url"),
                            "endpoints": [],
                        }

                sidebar_data = {
                    "services": sorted(
                        services_map.values(),
                        key=lambda s: s.get("name", "").lower(),
                    ),
                    "source": "notion",
                }
                self.state_store.save_sidebar(sidebar_data)
                return SidebarResponse.model_validate(sidebar_data)
        except Exception:
            return SidebarResponse.model_validate(
                self.state_store.sidebar_from_cache()
            )
