from __future__ import annotations

import httpx

from vault import summarize_http_failure


def test_summarize_http_failure_omits_response_body() -> None:
    response = httpx.Response(
        500,
        text="provider failed with sk-live-secret and /private/local/path",
    )

    message = summarize_http_failure(response)

    assert message == f"HTTP 500 server_error; response body omitted ({len(response.text)} bytes)"
    assert "sk-live-secret" not in message
    assert "/private/local/path" not in message
