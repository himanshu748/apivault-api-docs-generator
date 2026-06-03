from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import (
    DocumentCollectionRequest,
    DocumentCollectionResponse,
    DocumentEndpointRequest,
    DocumentEndpointResponse,
    GenerateReadmeRequest,
    GenerateReadmeResponse,
    SearchResponse,
    SetupResponse,
    SidebarResponse,
)
from app.services.hf_mcp import HFMCPClient, mcp_call, notion_transport_name
from app.services.docs_service import DocumentationService
from app.services.state_store import StateStore


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"


state_store = StateStore(settings.state_path)
hf_client = HFMCPClient(settings)
docs_service = DocumentationService(
    settings=settings,
    client=hf_client,
    state_store=state_store,
)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def reject_large_requests(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        try:
            body_size = int(content_length) if content_length else 0
        except ValueError:
            body_size = settings.max_request_body_bytes + 1
        if body_size > settings.max_request_body_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body is too large."},
            )
    return await call_next(request)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    mcp_ok = False
    if settings.notion_token:
        try:
            async with hf_client.notion_ctx() as mcp:
                me = await mcp_call(mcp, "API-get-self", {})
                mcp_ok = notion_transport_name() == "mcp-stdio" and bool(me.get("id"))
        except Exception:
            pass
    return {
        "status": "ok",
        "app": settings.app_name,
        "hf_key": bool(settings.hf_api_key),
        "notion_token": bool(settings.notion_token),
        "parent_page_id": bool(settings.notion_parent_page_id),
        "mcp_connected": mcp_ok,
        "notion_transport": notion_transport_name(),
    }


@app.post("/api/setup", response_model=SetupResponse)
async def setup() -> SetupResponse:
    return await docs_service.setup()


@app.post("/api/document-endpoint", response_model=DocumentEndpointResponse)
async def document_endpoint(
    request: DocumentEndpointRequest,
) -> DocumentEndpointResponse:
    return await docs_service.document_endpoint(request)


@app.post("/api/document-collection", response_model=DocumentCollectionResponse)
async def document_collection(
    request: DocumentCollectionRequest,
) -> DocumentCollectionResponse:
    return await docs_service.document_collection(request)


@app.post("/api/generate-readme", response_model=GenerateReadmeResponse)
async def generate_readme(
    request: GenerateReadmeRequest,
) -> GenerateReadmeResponse:
    return await docs_service.generate_readme(request.service)


@app.get("/api/search", response_model=SearchResponse)
async def search(q: str = Query(default="")) -> SearchResponse:
    return await docs_service.search(q)


@app.get("/api/sidebar", response_model=SidebarResponse)
async def sidebar(fresh: bool = Query(default=False)) -> SidebarResponse:
    return await docs_service.sidebar(fresh=fresh)
