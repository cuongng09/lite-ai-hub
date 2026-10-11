import re
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
from backend.search import WebSearchEngine
from backend.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class DeepResearchEngine:
    def __init__(self, search_engine: WebSearchEngine, ollama_client: Optional[OllamaClient] = None):
        self.search_engine = search_engine
        self.ollama_client = ollama_client

    async def generate_sub_queries(self, topic: str, model: str = "qwen2.5:latest") -> List[str]:
        topic_clean = topic.strip()
        if self.ollama_client:
            prompt = (
                f"Hãy phân rã câu hỏi/chủ đề sau thành 3 câu truy vấn tìm kiếm ngắn gọn, độc lập, bao quát các khía cạnh khác nhau:\n"
                f"Chủ đề: \"{topic_clean}\"\n\n"
                f"Chỉ trả về JSON array gồm 3 chuỗi. Ví dụ: [\"truy vấn 1\", \"truy vấn 2\", \"truy vấn 3\"]."
            )
            try:
                tokens = []
                async for ev in self.ollama_client.stream_chat_events(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    num_ctx=2048
                ):
                    if ev.get("type") == "token":
                        tokens.append(ev["token"])

                full_text = "".join(tokens).strip()
                match = re.search(r'\[[\s\S]*?\]', full_text)
                if match:
                    queries = json.loads(match.group(0))
                    if isinstance(queries, list) and queries:
                        return [str(q).strip() for q in queries[:3] if str(q).strip()]
            except Exception as e:
                logger.warning(f"Lỗi phân rã LLM sub-queries ({e}), dùng fallback.")

        return [
            f"{topic_clean} mới nhất năm 2026",
            f"{topic_clean} phân tích chi tiết dữ liệu",
            f"{topic_clean} đánh giá so sánh"
        ]

    async def fetch_page_content(self, url: str, max_chars: int = 1500) -> str:
        if not url or not url.startswith("http"):
            return ""

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml"
        }
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    html = res.text
                    cleaned = re.sub(r'<(script|style|nav|header|footer|noscript|svg)[^>]*>[\s\S]*?</\1>', ' ', html, flags=re.IGNORECASE)
                    paragraphs = re.findall(r'<p[^>]*>([\s\S]*?)</p>', cleaned, flags=re.IGNORECASE)
                    if paragraphs:
                        text_parts = [
                            re.sub(r'<[^>]+>', '', p).strip()
                            for p in paragraphs
                            if len(re.sub(r'<[^>]+>', '', p).strip()) > 30
                        ]
                        full_extracted = " ".join(text_parts)
                    else:
                        full_extracted = re.sub(r'<[^>]+>', ' ', cleaned)

                    full_extracted = re.sub(r'\s+', ' ', full_extracted).strip()
                    return full_extracted[:max_chars]
        except Exception as e:
            logger.debug(f"Không thể đọc trang web {url}: {e}")
        return ""

    async def stream_deep_research(self, topic: str, model: str = "qwen2.5:latest") -> AsyncGenerator[Dict[str, Any], None]:
        yield {"type": "status", "message": "🔍 Bước 1/4: Đang phân tích và phân rã các khía cạnh nghiên cứu..."}
        sub_queries = await self.generate_sub_queries(topic, model=model)

        yield {"type": "status", "message": f"🌐 Bước 2/4: Đang tìm kiếm song song {len(sub_queries)} hướng thông tin năm 2026..."}
        tasks = [
            asyncio.to_thread(self.search_engine.search, q, 3)
            for q in sub_queries
        ]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        all_sources: List[Dict[str, Any]] = []
        seen_links = set()

        for res in results_nested:
            if isinstance(res, list):
                for item in res:
                    href = item.get("href", "")
                    if href and href not in seen_links:
                        seen_links.add(href)
                        all_sources.append(dict(item))

        if len(all_sources) < 4:
            extra_query = f"{topic} tin tức tài liệu mới nhất"
            extra_res = await asyncio.to_thread(self.search_engine.search, extra_query, 4)
            for item in extra_res:
                href = item.get("href", "")
                if href and href not in seen_links:
                    seen_links.add(href)
                    all_sources.append(dict(item))

        final_sources = all_sources[:5]
        yield {"type": "status", "message": f"📄 Bước 3/4: Đã tìm thấy {len(all_sources)} nguồn. Đang trích xuất nội dung từ {len(final_sources)} trang uy tín..."}

        fetch_tasks = [
            self.fetch_page_content(s.get("href", ""))
            for s in final_sources
        ]
        pages_content = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for s, content in zip(final_sources, pages_content):
            if isinstance(content, str) and content.strip():
                s["deep_content"] = content.strip()
            else:
                s["deep_content"] = s.get("body", "")

        yield {"type": "status", "message": f"📊 Bước 4/4: Đã trích xuất {len(final_sources)} tài liệu. Đang tổng hợp báo cáo chi tiết..."}

        context_lines = [f"=== BÁO CÁO NGHIÊN CỨU SÂU (DEEP RESEARCH 2026): {topic} ==="]
        for idx, s in enumerate(final_sources, start=1):
            s["citation_id"] = idx
            title = s.get("title", "")
            href = s.get("href", "")
            content_snippet = s.get("deep_content") or s.get("body", "")
            context_lines.append(
                f"[{idx}] {title}\n"
                f"Nguồn: {href}\n"
                f"Nội dung trích xuất: {content_snippet}\n"
            )
        context_lines.append("================================================================")

        yield {
            "type": "result",
            "data": {
                "topic": topic,
                "sources": final_sources,
                "context_text": "\n".join(context_lines)
            }
        }

    async def execute_deep_research(self, topic: str, model: str = "qwen2.5:latest") -> Dict[str, Any]:
        result = None
        async for ev in self.stream_deep_research(topic, model=model):
            if ev.get("type") == "result":
                result = ev.get("data")
        return result or {"topic": topic, "sources": [], "context_text": ""}
