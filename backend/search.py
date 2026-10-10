"""
Module Web Search đa nguồn thuần Python.
Hỗ trợ:
- Gói ddgs (duckduckgo_search phiên bản mới)
- Fallback SearXNG tùy chọn (qua SEARXNG_URL)
- Fallback Brave Search API tùy chọn (qua BRAVE_API_KEY)
- Fallback DuckDuckGo HTML scraper đáng tin cậy
- Hoạt động 100% không cần Docker
"""

import os
import re
import urllib.parse
import logging
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class WebSearchEngine:
    """Công cụ tìm kiếm web đa nguồn với cơ chế fallback thông minh."""

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Tìm kiếm web thông minh. Thử lần lượt:
        1. ddgs / duckduckgo_search thư viện chính
        2. SearXNG (nếu cấu hình SEARXNG_URL)
        3. Brave Search API (nếu cấu hình BRAVE_API_KEY)
        4. DuckDuckGo HTML scraper trực tiếp
        """
        limit = max_results or self.max_results
        query = query.strip()
        if not query:
            return []

        # 1. Thử dùng ddgs hoặc duckduckgo_search
        results = self._search_ddgs_library(query, limit)
        if results:
            return results

        # 2. Thử SearXNG nếu có URL cấu hình
        searxng_url = os.getenv("SEARXNG_URL")
        if searxng_url:
            results = self._search_searxng(query, searxng_url, limit)
            if results:
                return results

        # 3. Thử Brave Search API nếu có API key cấu hình
        brave_key = os.getenv("BRAVE_API_KEY")
        if brave_key:
            results = self._search_brave(query, brave_key, limit)
            if results:
                return results

        # 4. Fallback DuckDuckGo HTML Direct Scraper
        results = self._search_ddg_html(query, limit)
        return results

    def _search_ddgs_library(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Tìm kiếm bằng thư viện ddgs / duckduckgo_search."""
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=limit))
                results = []
                for item in raw_results:
                    results.append({
                        "title": item.get("title", "No Title"),
                        "href": item.get("href") or item.get("link", ""),
                        "body": item.get("body") or item.get("snippet", "")
                    })
                return results
        except Exception as e:
            logger.warning(f"ddgs library search gặp lỗi ({e}), chuyển sang nhánh fallback.")
            return []

    def _search_searxng(self, query: str, base_url: str, limit: int) -> List[Dict[str, str]]:
        """Truy vấn SearXNG JSON API."""
        try:
            url = f"{base_url.rstrip('/')}/search"
            params = {"q": query, "format": "json"}
            with httpx.Client(timeout=8.0) as client:
                res = client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    results = []
                    for r in data.get("results", [])[:limit]:
                        results.append({
                            "title": r.get("title", ""),
                            "href": r.get("url", ""),
                            "body": r.get("content", "")
                        })
                    return results
        except Exception as e:
            logger.warning(f"SearXNG fallback thất bại: {e}")
        return []

    def _search_brave(self, query: str, api_key: str, limit: int) -> List[Dict[str, str]]:
        """Truy vấn Brave Search REST API."""
        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
            params = {"q": query, "count": limit}
            with httpx.Client(timeout=8.0) as client:
                res = client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    data = res.json()
                    web_results = data.get("web", {}).get("results", [])
                    results = []
                    for r in web_results[:limit]:
                        results.append({
                            "title": r.get("title", ""),
                            "href": r.get("url", ""),
                            "body": r.get("description", "")
                        })
                    return results
        except Exception as e:
            logger.warning(f"Brave search fallback thất bại: {e}")
        return []

    def _search_ddg_html(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Fallback DuckDuckGo HTML Scraper đáng tin cậy không cần API key."""
        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": query}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://html.duckduckgo.com/"
            }
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                res = client.post(url, data=data, headers=headers)
                if res.status_code == 200:
                    html = res.text
                    # Trích xuất kết quả bằng regex nhẹ
                    results = []
                    # Khối kết quả thường có cấu trúc <a class="result__url" href="..."> và snippet
                    raw_blocks = re.findall(r'<div class="result__body">([\s\S]*?)</div>\s*</div>', html)
                    for block in raw_blocks[:limit]:
                        title_match = re.search(r'<a class="result__snippet[^>]*>([\s\S]*?)</a>', block)
                        url_match = re.search(r'<a class="result__url"[^>]*href="([^"]+)"', block)
                        name_match = re.search(r'<h2[^>]*><a[^>]*>([\s\S]*?)</a>', block)

                        title = re.sub(r'<[^>]+>', '', name_match.group(1)).strip() if name_match else "Kết quả"
                        snippet = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ""
                        raw_href = url_match.group(1).strip() if url_match else ""

                        # Giải mã URL redirect của DuckDuckGo nếu cần
                        if "uddg=" in raw_href:
                            try:
                                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                                href = parsed.get("uddg", [raw_href])[0]
                            except Exception:
                                href = raw_href
                        else:
                            href = raw_href

                        if href and (title or snippet):
                            results.append({
                                "title": title,
                                "href": href,
                                "body": snippet
                            })
                    return results
        except Exception as e:
            logger.error(f"DuckDuckGo HTML fallback thất bại: {e}")
        return []

    def format_search_context(self, results: List[Dict[str, str]]) -> str:
        """Định dạng kết quả tìm kiếm thành context cho LLM prompt."""
        if not results:
            return ""

        context_parts = ["--- KẾT QUẢ TÌM KIẾM WEB (THỜI GIAN THỰC) ---"]
        for idx, item in enumerate(results, start=1):
            title = item.get('title', '').strip()
            href = item.get('href', '').strip()
            body = item.get('body', '').strip()
            context_parts.append(f"[{idx}] {title}\nNguồn: {href}\nNội dung: {body}\n")
        context_parts.append("-------------------------------------------------")
        return "\n".join(context_parts)
