from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"setup": {}, "services": {}, "sidebar": {}, "docs": []})

    def load(self) -> dict[str, Any]:
        with self._lock:
            return self._read()

    def get_setup(self) -> dict[str, Any]:
        return self.load().get("setup", {})

    def save_setup(self, setup: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            state["setup"] = setup
            self._write(state)
        return setup

    def save_sidebar(self, sidebar: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            state["sidebar"] = sidebar
            self._write(state)
        return sidebar

    def upsert_doc(self, item: dict[str, Any]) -> None:
        key = f"{item.get('service', '').lower()}::{item.get('method', '').upper()}::{item.get('path', '')}"
        with self._lock:
            state = self._read()
            docs = state.setdefault("docs", [])
            existing_index = next(
                (index for index, value in enumerate(docs) if value.get("_key") == key),
                None,
            )
            record = {**item, "_key": key}
            if existing_index is None:
                docs.append(record)
            else:
                docs[existing_index] = record

            services = state.setdefault("services", {})
            service_name = item.get("service", "")
            service_entry = services.setdefault(
                service_name,
                {
                    "name": service_name,
                    "base_url": item.get("base_url", ""),
                    "description": "",
                    "auth_type": "",
                    "owner": "",
                    "notion_url": None,
                    "endpoints": [],
                },
            )
            service_entry["base_url"] = item.get("base_url", service_entry.get("base_url", ""))
            endpoint_summary = {
                "title": item.get("title", ""),
                "method": item.get("method", ""),
                "path": item.get("path", ""),
                "description": item.get("description", ""),
                "notion_url": item.get("notion_url"),
            }
            endpoint_key = f"{endpoint_summary['method']}::{endpoint_summary['path']}"
            endpoints = {
                f"{entry.get('method')}::{entry.get('path')}": entry
                for entry in service_entry.get("endpoints", [])
            }
            endpoints[endpoint_key] = endpoint_summary
            service_entry["endpoints"] = sorted(
                endpoints.values(), key=lambda value: (value["path"], value["method"])
            )
            self._write(state)

    def search_docs(self, query: str) -> list[dict[str, Any]]:
        lowered = query.lower()
        docs = self.load().get("docs", [])
        results = []
        for item in docs:
            haystack = " ".join(
                [
                    item.get("title", ""),
                    item.get("path", ""),
                    item.get("description", ""),
                    item.get("service", ""),
                ]
            ).lower()
            if lowered in haystack:
                results.append(item)
        return results

    def sidebar_from_cache(self) -> dict[str, Any]:
        cached = self.load()
        sidebar = cached.get("sidebar")
        if sidebar and sidebar.get("services"):
            return sidebar
        services = []
        for service in cached.get("services", {}).values():
            services.append(service)
        return {"services": sorted(services, key=lambda item: item.get("name", "").lower()), "source": "cache"}

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
