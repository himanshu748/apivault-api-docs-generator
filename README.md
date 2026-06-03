# APIVault

APIVault is a local FastAPI app that turns raw route code or plain-English API descriptions into full API documentation and stores the results in Notion through HuggingFace's MCP client. The UI is a vanilla HTML/CSS/JS dashboard with live search, a documentation preview, and a source-vs-generated toggle.

## What it does

- `POST /api/setup` creates or reuses the APIVault Notion workspace:
  - `📖 API Reference` database
  - `🏷️ Services` database
  - `📚 API Docs` hub page
- `POST /api/document-endpoint` documents a single endpoint, stores it in Notion, and returns the generated content plus the Notion URL.
- `POST /api/document-collection` splits a router/controller file into multiple endpoints and documents them in parallel.
- `POST /api/generate-readme` creates a `📄 [Service] — README` page from the endpoints already stored in Notion.
- `GET /api/search?q=...` searches the API reference for the dashboard.
- `GET /api/sidebar` feeds the left-side navigation tree.
- `vault.py` reads a local file and posts it to `/api/document-collection`.

## Important auth note

APIVault prefers the Notion MCP package when it is installed. In lean local environments it can fall back to supported direct Notion REST calls, so the app can still import and serve the dashboard without the MCP dependency. `NOTION_TOKEN` is still expected to be a Notion MCP OAuth access token for the hosted MCP path.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the example env file and set your values:

```bash
cp .env.example .env
```

4. Start the FastAPI app:

```bash
uvicorn app.main:app --reload
```

5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Health, static pages, cached sidebar, and cached search work without provider secrets. Generation and write endpoints return explicit configuration errors until `HF_API_KEY`, `NOTION_TOKEN`, and `NOTION_PARENT_PAGE_ID` are configured. `/api/health` reports `notion_transport` so MCP stdio and REST fallback are not confused.

Optional environment:

- `CORS_ORIGINS`: comma-separated browser origins allowed to call the API. Defaults to local Uvicorn origins.
- `APIVAULT_MAX_BODY_BYTES`: request size guard for write endpoints. Defaults to `220000`.

## Verify

```bash
python -m pytest
python -m compileall app tests vault.py
node --check app/static/app.js
```

## CLI usage

```bash
python vault.py \
  --file routes/users.py \
  --service UserService \
  --base-url https://api.example.com
```

## Notes

- The default Notion MCP transport is `https://mcp.notion.com/sse` because that is what this project targets, but `NOTION_MCP_URL` is configurable.
- The app keeps a local JSON cache in `data/apivault_state.json` to make the sidebar and search feel responsive, but Notion remains the source of truth.
- Keep `.env`, `data/apivault_state.json`, caches, and generated output out of git.
