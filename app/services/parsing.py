from __future__ import annotations

import json
import re
from typing import Any


JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

ROUTE_PATTERNS = (
    re.compile(
        r"@\w+\.(get|post|put|delete|patch)\(\s*(?:path\s*=\s*)?[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:app|router)\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:app|router)\.route\(\s*[\"']([^\"']+)[\"']\s*,\s*methods\s*=\s*\[([^\]]+)\]",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:GET|POST|PUT|DELETE|PATCH)\s+(/[\w\-/{}/:]+)",
        re.IGNORECASE,
    ),
)


def extract_json_payload(text: str) -> Any:
    candidates = []
    candidates.extend(match.group(1).strip() for match in JSON_FENCE_RE.finditer(text))
    candidates.append(text.strip())
    candidates.extend(_scan_balanced_json(text))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("Claude response did not contain valid JSON.")


def infer_method_and_path(code: str) -> tuple[str, str]:
    for pattern in ROUTE_PATTERNS:
        match = pattern.search(code)
        if not match:
            continue
        if pattern is ROUTE_PATTERNS[2]:
            methods = re.findall(r"[\"']([A-Z]+)[\"']", match.group(2).upper())
            method = methods[0] if methods else "GET"
            return method, normalize_path(match.group(1))
        if pattern is ROUTE_PATTERNS[3]:
            leading = re.search(r"\b(GET|POST|PUT|DELETE|PATCH)\b", match.group(0), re.I)
            method = leading.group(1).upper() if leading else "GET"
            return method, normalize_path(match.group(1))
        return match.group(1).upper(), normalize_path(match.group(2))

    natural_language = re.search(
        r"\b(GET|POST|PUT|DELETE|PATCH)\b[^/\n]*?(/[\w\-/{}/:]+)", code, re.IGNORECASE
    )
    if natural_language:
        return natural_language.group(1).upper(), normalize_path(natural_language.group(2))

    return "POST", "/undocumented-endpoint"


def normalize_path(path: str) -> str:
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized.lstrip("/")
    return normalized


def title_from_method_path(method: str, path: str) -> str:
    fragments = [fragment for fragment in path.split("/") if fragment]
    if not fragments:
        return f"{method} Root"
    humanized = " ".join(fragment.strip("{}:").replace("-", " ").title() for fragment in fragments)
    return f"{method} {humanized}"


def default_error_codes() -> list[dict[str, Any]]:
    return [
        {"code": 400, "meaning": "The request payload or parameters are invalid."},
        {"code": 401, "meaning": "Authentication credentials are missing or invalid."},
        {"code": 403, "meaning": "The caller is authenticated but not allowed to access this resource."},
        {"code": 404, "meaning": "The requested resource could not be found."},
        {"code": 422, "meaning": "Validation failed for the submitted data."},
        {"code": 500, "meaning": "The server encountered an unexpected error."},
    ]


def _scan_balanced_json(text: str) -> list[str]:
    snippets: list[str] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth = 0
            in_string = False
            escape = False
            for index in range(start, len(text)):
                char = text[index]
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == opener:
                    depth += 1
                elif char == closer:
                    depth -= 1
                    if depth == 0:
                        snippets.append(text[start : index + 1].strip())
                        break
            start = text.find(opener, start + 1)
    return snippets
