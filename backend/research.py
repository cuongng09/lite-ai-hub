"""
Deep Web Research Engine (Perplexity style).
Nâng cấp:
1. Phân rã câu hỏi động bằng LLM (hoặc quy tắc ngữ nghĩa nếu offline).
2. Tìm kiếm đồng thời đa nguồn.
3. Tải nội dung trang web chính (deep page fetcher) và trích xuất nội dung thực tế thay vì chỉ lấy snippet ngắn.
4. Vòng lặp phản hồi: "Đánh giá thông tin thiếu gì -> tìm kiếm bổ sung".
"""

import re
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
import httpx
from backend.search import WebSearchEngine
from backend.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class DeepResearchEngine:
    """Công cụ nghiên cứu sâu đa nguồn Perplexity-style."""

    def __init__(self, search_engine: WebSearchEngine, ollama_client: Optional[OllamaClient] = None):
        self.search_engine = search_engine
        self.ollama_client = ollama_client

    async def generate_sub_queries(self, topic: str, model: str = "qwen2.5:latest") -> List[str]:
        """
        Phân rã câu hỏi thành 2-3 truy vấn con đa chiều bằng LLM.
        Fallback sang quy tắc trích xuất từ khóa nếu LLM không phản hồi.
        """
        topic_clean = topic.strip()
        if self.ollama_client:
            prompt = (
                f"Hãy phân rã câu hỏi/chủ đề sau thành 3 câu truy vấn tìm kiếm Google ngắn gọn, độc lập, "
                f"bao quát các khía cạnh khác nhau (tổng quan, chi tiết kỹ thuật/sự kiện, số liệu mới nhất 2026):\n"
                f"Chủ đề: \"{topic_clean}\"\n\n"
                f"Chỉ trả về JSON array của 3 chuỗi, ví dụ: [\"truy vấn 1\", \"truy vấn 2\", \"truy vấn 3\"]. Không kèm lời giải thích."
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
                # Tìm JSON array
                match = re.search(r'\[[\s\S]*?\]', full_text)
                if match:
                    queries = json.loads(match.group(0))
                    if isinstance(queries, list) and queries:
                        return [str(q).strip() for q in queries[:3] if str(q).strip()]
            except Exception as e:
                logger.warning(f"Phân rã LLM sub-queries không thành công ({e}), dùng quy tắc fallback.")

        # Fallback theo quy tắc từ khóa
        return [
            f"{topic_clean} mới nhất năm 2026",
            f"{topic_clean} phân tích chi tiết dữ liệu",
            f"{topic_clean} đánh giá so sánh"
        ]

    async def fetch_page_content(self, url: str, max_chars: int = 1500) -> str:
        """
        Tải nội dung HTML của trang web và trích xuất đoạn văn bản chính,
        loại bỏ quảng cáo, scripts, css, menus.
        """
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
                    # Loại bỏ thẻ script, style, nav, header, footer, noscript
                    cleaned = re.sub(r'<(script|style|nav|header|footer|noscript|svg)[^>]*>[\s\S]*?</\1>', ' ', html, flags=re.IGNORECASE)
                    
                    # Trích xuất văn bản trong thẻ p hoặc article
                    paragraphs = re.findall(r'<p[^>]*>([\s\S]*?)</p>', cleaned, flags=re.IGNORECASE)
                    if paragraphs:
                        text_parts = []
                        for p in paragraphs:
                            p_clean = re.sub(r'<[^>]+>', '', p).strip()
                            if len(p_clean) > 30:  # Bỏ qua các đoạn quá ngắn
                                text_parts.append(p_clean)
                        full_extracted = " ".join(text_parts)
                    else:
                        full_extracted = re.sub(r'<[^>]+>', ' ', cleaned)

                    # Chuẩn hóa khoảng trắng
                    full_extracted = re.sub(r'\s+', ' ', full_extracted).strip()
                    return full_extracted[:max_chars]
        except Exception as e:
            logger.debug(f"Không thể đọc trang web {url}: {e}")
        return ""

    async def execute_deep_research(self, topic: str, model: str = "qwen2.5:latest") -> Dict[str, Any]:
        """
        Nghiên cứu sâu chủ đề với vòng lặp phản hồi:
        1. Phân rã câu hỏi thành các sub-queries
        2. Tìm kiếm song song
        3. Tải nội dung trang web chính cho các bài viết hàng đầu
        4. Vòng lặp: Nếu thiếu nguồn, tìm kiếm bổ sung 1 lượt
        """
        sub_queries = await self.generate_sub_queries(topic, model=model)

        # Lượt 1: Tìm kiếm song song các sub-queries
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

        # Lượt 2 (Vòng lặp đánh giá): Nếu chưa đủ 4 nguồn chất lượng, tìm kiếm bổ sung
        if len(all_sources) < 4:
            extra_query = f"{topic} tin tức tài liệu mới nhất"
            extra_res = await asyncio.to_thread(self.search_engine.search, extra_query, 4)
            for item in extra_res:
                href = item.get("href", "")
                if href and href not in seen_links:
                    seen_links.add(href)
                    all_sources.append(dict(item))

        # Chọn top 5 nguồn nổi bật nhất
        final_sources = all_sources[:5]

        # Đọc nội dung sâu từ các URL
        fetch_tasks = [
            self.fetch_page_content(s.get("href", ""))
            for s in final_sources
        ]
        pages_content = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for s, content in zip(final_sources, pages_content):
            if isinstance(content, str) and content.strip():
                # Ghi đè body bằng nội dung trang chi tiết nếu có
                s["deep_content"] = content.strip()
            else:
                s["deep_content"] = s.get("body", "")

        # Đánh số citation và dựng context có cấu trúc
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

        return {
            "topic": topic,
            "sources": final_sources,
            "context_text": "\n".join(context_lines)
        }
