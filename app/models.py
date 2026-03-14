from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentEndpointRequest(BaseModel):
    code: str = Field(min_length=1)
    language: str = Field(default="python", min_length=1)
    service: str = Field(min_length=1)
    base_url: str = Field(min_length=1)


class DocumentCollectionRequest(DocumentEndpointRequest):
    pass


class GenerateReadmeRequest(BaseModel):
    service: str = Field(min_length=1)


class EndpointParameter(BaseModel):
    name: str
    type: str
    required: bool
    description: str
    location: str = "query"


class ErrorCodeDoc(BaseModel):
    code: int
    meaning: str


class GeneratedDocumentation(BaseModel):
    title: str
    summary: str
    description: str
    method: str
    path: str
    service: str
    version: str = "v1"
    auth_required: bool = False
    deprecated: bool = False
    base_url: str
    assumptions: list[str] = Field(default_factory=list)
    request_parameters: list[EndpointParameter] = Field(default_factory=list)
    request_body_schema: dict[str, Any] = Field(default_factory=dict)
    request_body_example: Any = None
    response_schema: dict[str, Any] = Field(default_factory=dict)
    response_example: Any = None
    error_codes: list[ErrorCodeDoc] = Field(default_factory=list)
    curl_example: str = ""
    python_example: str = ""
    javascript_example: str = ""
    request_body_text: str = ""
    response_schema_text: str = ""
    error_codes_text: str = ""
    notion_url: str | None = None


class DocumentEndpointResponse(BaseModel):
    notion_url: str | None = None
    method: str
    path: str
    summary: str
    documentation: GeneratedDocumentation


class DocumentCollectionResponse(BaseModel):
    service: str
    count: int
    items: list[DocumentEndpointResponse] = Field(default_factory=list)


class SetupResponse(BaseModel):
    api_reference_url: str
    services_url: str
    hub_page_url: str
    notes: list[str] = Field(default_factory=list)
    auth_notice: str


class GenerateReadmeResponse(BaseModel):
    service: str
    title: str
    notion_url: str | None = None
    endpoint_count: int = 0
    overview: str = ""


class SearchResult(BaseModel):
    title: str
    method: str
    path: str
    description: str
    service: str
    notion_url: str | None = None


class SearchResponse(BaseModel):
    q: str
    results: list[SearchResult] = Field(default_factory=list)


class SidebarEndpoint(BaseModel):
    title: str
    method: str
    path: str
    description: str
    notion_url: str | None = None


class SidebarService(BaseModel):
    name: str
    base_url: str = ""
    description: str = ""
    auth_type: str = ""
    owner: str = ""
    notion_url: str | None = None
    endpoints: list[SidebarEndpoint] = Field(default_factory=list)


class SidebarResponse(BaseModel):
    services: list[SidebarService] = Field(default_factory=list)
    source: str = "cache"
