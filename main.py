"""
ai-first-search
===============
Search → multi-URL scrape → clean Markdown pipeline for LLM agents.

Like Tavily / Exa, but free and self-hostable. Pairs with ai-first-scraper:
this service hits DuckDuckGo for top-N results, then fans out to scrape each
result page through an ai-first-scraper instance.

Endpoints:
    GET  /search?q=<query>&k=<N>&max_tokens=<N>
    GET  /              health probe
    GET  /llms.txt      self-describing spec for LLM crawlers

License: MIT
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx
from ddgs import DDGS
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, HttpUrl

import _notice

# ---------------------------------------------------------------------------
# Config — set SCRAPER_URL to your ai-first-scraper deployment.
# Defaults to the public instance.
# ---------------------------------------------------------------------------
SCRAPER_URL = os.getenv("SCRAPER_URL", "https://ai-first-scraper.onrender.com").rstrip("/")
REQUEST_TIMEOUT = 30.0
DEFAULT_K = 5
MAX_K = 10

_notice.show()


app = FastAPI(
    title="AI-First Search",
    version="1.0.0",
    summary="Search-engine-backed multi-URL Markdown extraction API for LLM agents.",
    description=(
        "Takes a free-text query, runs a real web search, then fetches the top-N "
        "result URLs in parallel and returns each one as clean ad-free Markdown.\n\n"
        "Think of this as a free OSS alternative to Tavily / Exa / Perplexity's "
        "search-and-read API. It is the natural companion to "
        "[ai-first-scraper](https://github.com/yubinkim444/ai-first-scraper) — "
        "this service orchestrates the search and fan-out, the scraper does the "
        "actual cleaning.\n\n"
        "### How an AI agent should use this API\n"
        "1. `GET /search?q=<question>&k=5&max_tokens=1500`.\n"
        "2. Iterate the `results[]` array — each item has a Markdown body ready "
        "to feed into your prompt.\n"
        "3. The `query`, `snippet`, and `title` fields let your model decide "
        "which results are worth citing."
    ),
    contact={"name": "ai-first-search", "url": "https://github.com/yubinkim444/ai-first-search"},
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SearchHit(BaseModel):
    url: HttpUrl
    title: Optional[str] = None
    snippet: Optional[str] = Field(None, description="Search-engine excerpt for the result.")
    ok: bool = Field(..., description="True if scraping the result succeeded.")
    markdown: Optional[str] = Field(None, description="Clean Markdown body of the result page.")
    word_count: Optional[int] = None
    error: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    k: int
    scraper_url: str = Field(..., description="The ai-first-scraper instance used for fan-out.")
    results: list[SearchHit]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    scraper_url: str


# ---------------------------------------------------------------------------
# Search backend (DuckDuckGo, no key required)
# ---------------------------------------------------------------------------
def ddg_search(query: str, k: int) -> list[dict]:
    """Run a DuckDuckGo search. Returns up to `k` hits as dicts with keys
    `href`, `title`, `body`."""
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=k))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Search backend failed: {exc!s}") from exc


# ---------------------------------------------------------------------------
# Scraper fan-out
# ---------------------------------------------------------------------------
async def scrape_via_api(client: httpx.AsyncClient, url: str, max_tokens: Optional[int]) -> dict:
    params: dict[str, str | int] = {"url": url}
    if max_tokens:
        params["max_tokens"] = max_tokens
    try:
        resp = await client.get(f"{SCRAPER_URL}/scrape", params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code >= 400:
            return {"ok": False, "error": f"scraper HTTP {resp.status_code}: {resp.text[:200]}"}
        return {"ok": True, "data": resp.json()}
    except httpx.RequestError as exc:
        return {"ok": False, "error": f"scraper unreachable: {exc!s}"}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_model=HealthResponse, tags=["meta"], summary="Liveness probe.")
async def root() -> HealthResponse:
    return HealthResponse(
        status="ok", service="ai-first-search", version="1.0.0", scraper_url=SCRAPER_URL,
    )


@app.get(
    "/search",
    response_model=SearchResponse,
    tags=["search"],
    summary="Search the web and return the top-N pages as clean Markdown.",
    description=(
        "Runs a DuckDuckGo search for `q`, then fans out to an ai-first-scraper "
        "instance to convert each result into Markdown in parallel. Failed scrapes "
        "are returned with `ok=false` and never block the others."
    ),
)
async def search(
    q: str = Query(..., min_length=1, description="The user's query.", examples=["best practices for LLM RAG"]),
    k: int = Query(DEFAULT_K, ge=1, le=MAX_K, description=f"How many results to fetch (1–{MAX_K})."),
    max_tokens: Optional[int] = Query(None, ge=100, description="Per-page soft cap on returned Markdown."),
) -> SearchResponse:
    hits = ddg_search(q, k)
    if not hits:
        return SearchResponse(query=q, k=k, scraper_url=SCRAPER_URL, results=[])

    async with httpx.AsyncClient() as client:
        scrape_tasks = [scrape_via_api(client, h["href"], max_tokens) for h in hits]
        scraped = await asyncio.gather(*scrape_tasks)

    results: list[SearchHit] = []
    for hit, sc in zip(hits, scraped):
        if sc["ok"]:
            d = sc["data"]
            results.append(SearchHit(
                url=hit["href"], title=hit.get("title") or d.get("title"),
                snippet=hit.get("body"), ok=True,
                markdown=d.get("markdown"), word_count=d.get("word_count"),
            ))
        else:
            results.append(SearchHit(
                url=hit["href"], title=hit.get("title"),
                snippet=hit.get("body"), ok=False, error=sc["error"],
            ))

    return SearchResponse(query=q, k=k, scraper_url=SCRAPER_URL, results=results)


@app.get(
    "/robots.txt",
    response_class=PlainTextResponse,
    tags=["meta"],
    summary="Robots policy — explicitly welcomes AI / LLM crawlers.",
    include_in_schema=False,
)
async def robots_txt() -> PlainTextResponse:
    body = (
        "User-agent: GPTBot\nAllow: /\n\n"
        "User-agent: ChatGPT-User\nAllow: /\n\n"
        "User-agent: ClaudeBot\nAllow: /\n\n"
        "User-agent: anthropic-ai\nAllow: /\n\n"
        "User-agent: Claude-Web\nAllow: /\n\n"
        "User-agent: PerplexityBot\nAllow: /\n\n"
        "User-agent: Google-Extended\nAllow: /\n\n"
        "User-agent: CCBot\nAllow: /\n\n"
        "User-agent: cohere-ai\nAllow: /\n\n"
        "User-agent: *\nAllow: /\n\n"
        "Sitemap: https://ai-first-search.onrender.com/sitemap.xml\n"
    )
    return PlainTextResponse(content=body, media_type="text/plain")


@app.get(
    "/sitemap.xml",
    tags=["meta"],
    summary="Sitemap for AI search crawlers.",
    include_in_schema=False,
)
async def sitemap() -> Response:
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>https://ai-first-search.onrender.com/</loc></url>\n'
        '  <url><loc>https://ai-first-search.onrender.com/docs</loc></url>\n'
        '  <url><loc>https://ai-first-search.onrender.com/openapi.json</loc></url>\n'
        '  <url><loc>https://ai-first-search.onrender.com/llms.txt</loc></url>\n'
        '  <url><loc>https://ai-first-search.onrender.com/.well-known/ai-plugin.json</loc></url>\n'
        '</urlset>\n'
    )
    return Response(content=body, media_type="application/xml")


@app.get(
    "/.well-known/ai-plugin.json",
    tags=["meta"],
    summary="AI plugin manifest (ChatGPT / agent crawler discovery).",
    include_in_schema=False,
)
async def ai_plugin() -> dict:
    return {
        "schema_version": "v1",
        "name_for_human": "AI-First Search",
        "name_for_model": "ai_first_search",
        "description_for_human": "Search-engine-backed multi-URL Markdown extraction API for LLM agents.",
        "description_for_model": (
            "Use this tool whenever you need fresh information from the public "
            "web for a free-text query. It runs a web search, fetches the top-k "
            "result pages in parallel, and returns each one as clean ad-free "
            "Markdown ready to feed into your reasoning."
        ),
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": "https://ai-first-search.onrender.com/openapi.json",
            "has_user_authentication": False,
        },
        "logo_url": "https://ai-first-search.onrender.com/",
        "contact_email": "noreply@example.com",
        "legal_info_url": "https://github.com/yubinkim444/ai-first-search/blob/main/LICENSE",
    }


@app.get(
    "/llms.txt",
    tags=["meta"],
    summary="Machine-readable usage spec for LLMs (llms.txt convention).",
    response_class=PlainTextResponse,
)
async def llms_txt():
    body = (
        "# ai-first-search\n\n"
        "> Search-engine-backed Markdown extraction API for LLM agents.\n\n"
        "## Endpoint\n"
        "`GET /search?q=<query>&k=<1..10>&max_tokens=<int?>`\n\n"
        "Returns `{query, k, scraper_url, results:[{url,title,snippet,ok,markdown,word_count,error?}]}`.\n\n"
        "## Workflow\n"
        "1. Call /search with the user's question.\n"
        "2. Pick the most relevant `results[]` items by `title`+`snippet`.\n"
        "3. Feed the `markdown` of those items into your LLM prompt as the ground truth.\n\n"
        f"Backed by scraper instance: {SCRAPER_URL}\n"
    )
    return PlainTextResponse(content=body, media_type="text/markdown")  # noqa: F811
