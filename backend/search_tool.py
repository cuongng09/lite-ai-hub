import requests
from typing import List, Dict
from backend.config import SEARXNG_URL

def search_searxng(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """Gửi truy vấn tìm kiếm tới SearXNG local API và trả về danh sách kết quả."""
    url = f"{SEARXNG_URL}/search"
    params = {
        "q": query,
        "format": "json",
        "language": "vi-VN"
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", [])[:max_results]:
            title = item.get("title", "")
            snippet = item.get("content", "")
            source_url = item.get("url", "")
            if snippet:
                results.append({
                    "title": title,
                    "content": snippet,
                    "url": source_url
                })
        return results
    except Exception as e:
        print(f"[SearXNG Error] {e}")
        return []
