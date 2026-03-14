from app.services.parsing import extract_json_payload, infer_method_and_path, title_from_method_path


def test_extract_json_payload_from_fenced_block() -> None:
    text = """
    Here is your result:
    ```json
    {"method":"GET","path":"/users"}
    ```
    """
    payload = extract_json_payload(text)
    assert payload == {"method": "GET", "path": "/users"}


def test_extract_json_payload_from_surrounding_text() -> None:
    text = 'Claude says {"items":[{"code":"router.get(\\"/users\\")"}]} done.'
    payload = extract_json_payload(text)
    assert payload["items"][0]["code"] == 'router.get("/users")'


def test_infer_method_and_path_fastapi_decorator() -> None:
    code = '@router.post("/users/{user_id}")\nasync def update_user(user_id: str):\n    return {}'
    method, path = infer_method_and_path(code)
    assert method == "POST"
    assert path == "/users/{user_id}"


def test_infer_method_and_path_from_plain_text() -> None:
    method, path = infer_method_and_path("Create an endpoint: DELETE /users/{id}")
    assert method == "DELETE"
    assert path == "/users/{id}"


def test_title_from_method_path() -> None:
    assert title_from_method_path("GET", "/users/{id}") == "GET Users Id"
