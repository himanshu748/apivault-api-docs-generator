# APIVault Notes

## Project Shape
- FastAPI app with a vanilla HTML/CSS/JS dashboard and a small CLI in `vault.py`.
- Local cache lives at `data/apivault_state.json`; keep it ignored.
- Hugging Face generates documentation JSON; Notion MCP/REST stores pages.

## Commands
- Run tests with `python -m pytest`.
- Check syntax with `python -m compileall app tests vault.py`.
- Check frontend JS with `node --check app/static/app.js`.
- Start locally with `uvicorn app.main:app --reload`.

## Conventions
- The app must import and serve health/static/sidebar/search cache routes without provider secrets or the MCP package installed.
- Generation/write routes should fail with explicit config errors when `HF_API_KEY`, `NOTION_TOKEN`, or `NOTION_PARENT_PAGE_ID` are missing.
- `HF_TOKEN` may be mapped to `HF_API_KEY` at process start for local tests; never commit real provider tokens.
- Notion REST fallback errors should stay sanitized and raise `HFMCPError` instead of returning API error dicts as app data.
- Keep MCP imports lazy/optional so tests and local static routes work in lean environments.
- Do not commit `.env`, `data/apivault_state.json`, caches, logs, or generated output.
