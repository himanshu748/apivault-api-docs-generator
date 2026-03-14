from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
from app.services.anthropic_mcp import AnthropicMCPClient
from app.services.docs_service import DocumentationService
from app.services.state_store import StateStore


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"


state_store = StateStore(settings.state_path)
anthropic_client = AnthropicMCPClient(settings)
docs_service = DocumentationService(
    settings=settings,
    client=anthropic_client,
    state_store=state_store,
)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


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
