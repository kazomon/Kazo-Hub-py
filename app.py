from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

BASE_URL = "https://jp.pornhub.com"
SEARCH_BASE_URLS = (
    "https://jp.pornhub.com",
    "https://www.pornhub.com",
    "https://de.pornhub.com",
)
USER_AGENT = "SearchResultURLCopier/1.0 (+contact: site-owner@example.com)"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_SEARCH_BYTES = 4 * 1024 * 1024
CACHE_SECONDS = 60 * 60 * 12
FRONTEND_DIR = Path(__file__).parent / "frontend"

app = FastAPI(title="Kazo-Hub API", version="1.0.0")


@app.middleware("http")
async def disable_frontend_asset_caching(request, call_next):
    response = await call_next(request)
    if request.url.path in {"/", "/app.js", "/style.css"}:
        response.headers["Cache-Control"] = "no-store"
    return response


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def first_text(card: Tag, selectors: list[str]) -> str | None:
    for selector in selectors:
        element = card.select_one(selector)
        value = clean_text(element.get_text(" ") if element else None)
        if value:
            return value
    return None


def absolute_url(value: str | None, base_url: str = BASE_URL) -> str | None:
    if not value or value.startswith("data:"):
        return None
    candidate = urljoin(base_url, value)
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return candidate
    return None


def is_allowed_thumbnail_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme == "https"
        and hostname != ""
        and (hostname == "phncdn.com" or hostname.endswith(".phncdn.com"))
    )


def thumbnail_proxy_url(source_url: str | None) -> str | None:
    if not source_url or not is_allowed_thumbnail_url(source_url):
        return None
    return f"/api/thumbnail?{urlencode({'url': source_url})}"


def thumbnail_from_card(card: Tag, base_url: str = BASE_URL) -> str | None:
    image = card.select_one("img")
    candidates = [
        image.get("data-src") if image else None,
        image.get("data-lazy-src") if image else None,
        image.get("data-original") if image else None,
        image.get("src") if image else None,
    ]
    for selector, attribute in (
        ("[data-mediumthumb]", "data-mediumthumb"),
        ("[data-thumb-url]", "data-thumb-url"),
        ("[data-thumb]", "data-thumb"),
    ):
        element = card.select_one(selector)
        candidates.append(element.get(attribute) if element else None)

    for candidate in candidates:
        resolved = absolute_url(candidate, base_url)
        if resolved:
            proxied = thumbnail_proxy_url(resolved)
            if proxied:
                return proxied

    style_element = card.select_one(".phimage, .img, .js-videoThumbImage")
    style = style_element.get("style", "") if style_element else ""
    match = re.search(r"url\((?:['\"])?([^'\")]+)", style, flags=re.IGNORECASE)
    resolved = absolute_url(match.group(1), base_url) if match else None
    return thumbnail_proxy_url(resolved)


def parse_search_results(html: str, base_url: str = BASE_URL) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str | None]] = []
    seen_urls: set[str] = set()

    for card in soup.select("li.videoblock"):
        title_link = None
        for selector in (
            "span.title a[href*='view_video.php']",
            "a.gtm-event-thumb-click[href*='view_video.php']",
        ):
            for link in card.select(selector):
                if clean_text(link.get_text(" ")):
                    title_link = link
                    break
            if title_link:
                break

        if not title_link:
            continue
        title = clean_text(title_link.get_text(" "))
        url = absolute_url(title_link.get("href"), base_url)
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        results.append(
            {
                "title": title,
                "url": url,
                "thumbnailUrl": thumbnail_from_card(card, base_url),
                "duration": first_text(card, [".duration", ".marker-overlays .duration", ".phimage .duration"]),
                "uploader": first_text(card, [".videoUploaderBlock .usernameWrap a", ".videoUploaderBlock a", ".usernameWrap a"]),
                "views": first_text(card, [".videoDetailsBlock .views", ".views"]),
                "added": first_text(card, [".videoDetailsBlock .added", ".added"]),
            }
        )
    return results


@lru_cache(maxsize=1)
def _robots_cache() -> dict[str, bool]:
    return {}


async def search_is_allowed(client: httpx.AsyncClient, base_url: str) -> bool:
    cached = _robots_cache()
    if base_url in cached:
        return cached[base_url]

    try:
        response = await client.get(
            f"{base_url}/robots.txt",
            headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        return False

    allowed = True
    applies = False
    rules: list[tuple[str, str]] = []
    for raw_line in response.text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        directive, value = (part.strip() for part in line.split(":", 1))
        directive = directive.lower()
        if directive == "user-agent":
            applies = value == "*"
        elif applies and directive in {"allow", "disallow"} and value:
            rules.append((directive, value))

    search_url = f"{base_url}/video/search"
    matching = [rule for rule in rules if search_url.startswith(rule[1])]
    if matching:
        matching.sort(key=lambda rule: (-len(rule[1]), 0 if rule[0] == "allow" else 1))
        allowed = matching[0][0] != "disallow"
    cached[base_url] = allowed
    return allowed


async def fetch_search_html(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str | int],
    headers: dict[str, str],
) -> str | None:
    try:
        async with client.stream("GET", url, params=params, headers=headers) as response:
            response.raise_for_status()
            content_length = int(response.headers.get("content-length", "0") or 0)
            if content_length > MAX_SEARCH_BYTES:
                return None

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_SEARCH_BYTES:
                    return None
                chunks.append(chunk)
            return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    except (httpx.HTTPError, ValueError):
        return None


@app.get("/api/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/search")
async def search(
    query: str = Query(min_length=1, max_length=120),
    page: int = Query(default=1, ge=1, le=10),
) -> dict[str, object]:
    query = query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="検索語を入力してください。")

    timeout = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        last_error: Exception | None = None
        for base_url in SEARCH_BASE_URLS:
            if not await search_is_allowed(client, base_url):
                continue
            try:
                html = await fetch_search_html(
                    client,
                    f"{base_url}/video/search",
                    {"search": query, "page": page},
                    headers,
                )
                if html is None:
                    continue
                results = parse_search_results(html, base_url)
                return {"query": query, "page": page, "results": results}
            except httpx.HTTPError as error:
                last_error = error

    raise HTTPException(status_code=502, detail="検索元サイトに接続できませんでした。") from last_error


@app.get("/api/thumbnail")
async def thumbnail(url: str = Query(min_length=1)) -> Response:
    if not is_allowed_thumbnail_url(url):
        raise HTTPException(status_code=400, detail="許可されていない画像URLです。")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=15.0, write=15.0, pool=10.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            upstream = await client.get(
                url,
                headers={"Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"},
            )
            upstream.raise_for_status()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="サムネイルを取得できませんでした。") from error

    content_type = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="画像として扱えない応答です。")
    if len(upstream.content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="サムネイルのサイズが大きすぎます。")

    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={
            "Cache-Control": f"public, max-age={CACHE_SECONDS}, s-maxage={CACHE_SECONDS}",
            "X-Content-Type-Options": "nosniff",
        },
    )


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=3000, reload=True)
