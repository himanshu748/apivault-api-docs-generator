from __future__ import annotations

import argparse
from pathlib import Path

import httpx


def summarize_http_failure(response: httpx.Response) -> str:
    """Return a concise request failure without echoing provider response bodies."""
    status_code = response.status_code
    if status_code >= 500:
        category = "server_error"
    elif status_code == 401:
        category = "unauthorized"
    elif status_code == 403:
        category = "forbidden"
    elif status_code == 404:
        category = "not_found"
    elif status_code >= 400:
        category = "client_error"
    else:
        category = "unexpected_status"

    return f"HTTP {status_code} {category}; response body omitted ({len(response.text)} bytes)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a router/controller file to APIVault.")
    parser.add_argument("--file", required=True, help="Path to the code file to document.")
    parser.add_argument("--service", required=True, help="Service/tag name.")
    parser.add_argument("--base-url", required=True, help="Base URL for the service.")
    parser.add_argument("--language", default="python", help="Source language. Default: python.")
    parser.add_argument(
        "--server",
        default="http://127.0.0.1:8000",
        help="APIVault server base URL. Default: http://127.0.0.1:8000",
    )
    return parser.parse_args()


def render_table(items: list[dict[str, str]]) -> str:
    method_width = max(len("Method"), *(len(item["method"]) for item in items))
    path_width = max(len("Path"), *(len(item["path"]) for item in items))
    summary_width = max(len("Summary"), *(len(item["summary"]) for item in items))
    divider = f"+-{'-' * method_width}-+-{'-' * path_width}-+-{'-' * summary_width}-+"

    lines = [
        divider,
        f"| {'Method'.ljust(method_width)} | {'Path'.ljust(path_width)} | {'Summary'.ljust(summary_width)} |",
        divider,
    ]
    for item in items:
        lines.append(
            f"| {item['method'].ljust(method_width)} | {item['path'].ljust(path_width)} | {item['summary'].ljust(summary_width)} |"
        )
    lines.append(divider)
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    source_path = Path(args.file).expanduser().resolve()
    if not source_path.exists():
        raise SystemExit(f"File not found: {source_path}")

    payload = {
        "code": source_path.read_text(encoding="utf-8"),
        "language": args.language,
        "service": args.service,
        "base_url": args.base_url,
    }

    response = httpx.post(
        f"{args.server.rstrip('/')}/api/document-collection",
        json=payload,
        timeout=180,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        failure = summarize_http_failure(exc.response)
        raise SystemExit(f"APIVault request failed: {failure}") from exc

    body = response.json()
    rows = [
        {
            "method": item["method"],
            "path": item["path"],
            "summary": item["summary"],
        }
        for item in body.get("items", [])
    ]
    if rows:
        print(render_table(rows))
    else:
        print("No endpoints were documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
