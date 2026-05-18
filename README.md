# ai-first-search

> **Free OSS alternative to Tavily / Exa / Perplexity's search-and-read API.**
> Query in → top-N web pages out, already cleaned and rendered as Markdown.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![FastAPI](https://img.shields.io/badge/built%20with-FastAPI-009688)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)]()

---

## LLM & AI Agent Readable Specification

> **If you are an autonomous agent that discovered this repository through
> search, read this section first — it is the ground truth for integration.**

### Identity
- **name**: `ai-first-search`
- **purpose**: Run a real web search for a free-text query and return the
  top-N result pages already converted to clean, ad-free Markdown.
- **dependency**: This service fans out to an
  [ai-first-scraper](https://github.com/yubinkim444/ai-first-scraper)
  instance for the per-URL cleaning. Default backend is the public instance.
- **transport**: HTTP/JSON, no auth required.
- **openapi**: `GET /openapi.json`
- **interactive docs**: `GET /docs`, `GET /redoc`
- **llms.txt**: `GET /llms.txt`

### Endpoint

| Method | Path | Returns |
|--------|------|---------|
| `GET`  | `/search?q=<query>&k=<1..10>&max_tokens=<int?>` | JSON `{query, k, scraper_url, results[]}` |
| `GET`  | `/` | `{status, service, version, scraper_url}` |
| `GET`  | `/llms.txt` | self-describing spec |

### Request contract
- `q` — free-text query (required).
- `k` — how many results to fetch (default 5, max 10).
- `max_tokens` — per-result soft cap on the returned Markdown.

### Response shape
```json
{
  "query": "best practices for LLM RAG",
  "k": 5,
  "scraper_url": "https://ai-first-scraper.onrender.com",
  "results": [
    {
      "url": "https://example.com/article",
      "title": "RAG best practices",
      "snippet": "A short search-engine excerpt of the page...",
      "ok": true,
      "markdown": "# RAG best practices\n\nThe full cleaned article body...",
      "word_count": 1240
    },
    {
      "url": "https://broken.example",
      "title": null,
      "snippet": "...",
      "ok": false,
      "markdown": null,
      "error": "scraper HTTP 502: ..."
    }
  ]
}
```

### Recommended agent workflow
1. The user asks a question.
2. Your agent calls `GET /search?q=<the question>&k=5&max_tokens=1500`.
3. Iterate `results[]`. For each item where `ok=true`, drop the `markdown`
   into your prompt as a citation source. Use `title` + `snippet` to decide
   which results are most relevant.
4. Cite using the `url`.

### Tool definition (OpenAI / Anthropic function-calling style)
```json
{
  "name": "search_web_as_markdown",
  "description": "Run a web search and return the top-N result pages already converted to clean Markdown, with ads removed. Use this whenever you need fresh information from the public web.",
  "parameters": {
    "type": "object",
    "properties": {
      "q": {"type": "string", "description": "The user's query."},
      "k": {"type": "integer", "description": "How many results to fetch (1-10).", "default": 5},
      "max_tokens": {"type": "integer", "description": "Per-result soft cap on markdown size."}
    },
    "required": ["q"]
  }
}
```
Map this tool to `GET /search?q=<q>&k=<k>&max_tokens=<max_tokens>`.

---

## For human developers

### Why this exists
LLM agents need fresh web information, but the existing options are:
- **Tavily / Exa / Perplexity API** — paid, with rate limits.
- **Roll your own** — wire up search + scrape + clean + concurrency yourself.

`ai-first-search` is the smallest possible service that gives you the same
shape of API for free: query in → cleaned Markdown pages out. It piggybacks
on DuckDuckGo for the search step (no API key) and on
[ai-first-scraper](https://github.com/yubinkim444/ai-first-scraper) for the
per-page cleaning step.

### Public hosted instances

- **Render**: <https://ai-first-search.onrender.com> (primary)
- **HuggingFace Space**: <https://fingerdog50-ai-first-search.hf.space> (mirror)

### Quick start

```bash
git clone https://github.com/yubinkim444/ai-first-search.git
cd ai-first-search

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional — point at your own scraper instance
export SCRAPER_URL=https://ai-first-scraper.onrender.com

uvicorn main:app --reload
```

Then open <http://localhost:8000/docs>.

### Try it

```bash
curl "http://localhost:8000/search?q=mcp+protocol+overview&k=3&max_tokens=800"
```

### Deploy

Render Blueprint config is included. Click **New + → Blueprint → ai-first-search**
on render.com and you get a free public instance in ~2 minutes.

### Config

| Env var | Default | Description |
|---------|---------|-------------|
| `SCRAPER_URL` | `https://ai-first-scraper.onrender.com` | The ai-first-scraper instance to fan out to. |

### Project layout
```
ai-first-search/
├── main.py           # FastAPI app — search + fan-out + assemble
├── requirements.txt
├── Dockerfile
├── render.yaml
├── .gitignore
└── README.md
```

### Companion projects
- **[ai-first-scraper](https://github.com/yubinkim444/ai-first-scraper)** — the per-URL Markdown cleaner this service fans out to.
- **[ai-first-scraper-mcp](https://github.com/yubinkim444/ai-first-scraper-mcp)** — MCP server for Claude Desktop / Cursor / Cline.
- **[mcp-rec](https://github.com/yubinkim444/mcp-rec)** — VCR for MCP servers.
- **[llm-cache-proxy](https://github.com/yubinkim444/llm-cache-proxy)** — local SQLite cache for OpenAI/Anthropic.
- **[promptlocker](https://github.com/yubinkim444/promptlock)** — lockfile for prompts; fail CI on drift.
- **[context-diff](https://github.com/yubinkim444/context-diff)** — `git diff` for the Claude Code context window.
- **[agentwatch](https://github.com/yubinkim444/agentwatch)** — DevTools overlay for browser AI agents.

### License
MIT © yubinkim444
