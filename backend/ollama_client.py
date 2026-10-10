"""
Ollama Client bất đồng bộ siêu nhẹ (Async HTTP), hỗ trợ SSE Streaming, Embeddings và Native Tool Calling (Qwen2.5).
"""

import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

class OllamaClient:
    """Wrapper giao tiếp trực tiếp với Ollama API bằng httpx với Connection Pool persistent."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0, connect=3.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )

    async def list_models(self) -> List[str]:
        """Lấy danh sách model đã tải trong Ollama."""
        try:
            res = await self._client.get("/api/tags", timeout=2.0)
            if res.status_code == 200:
                models = res.json().get("models", [])
                return [m["name"] for m in models]
        except Exception as e:
            logger.warning(f"Không thể kết nối tới Ollama: {e}")
        return []

    async def get_embedding(self, text: str, model: str = "bge-m3:latest") -> List[float]:
        """Tạo embedding vector từ Ollama endpoint với keep_alive giữ model sẵn sàng."""
        batch_res = await self.get_embeddings_batch([text], model=model)
        if batch_res:
            return batch_res[0]
        return []

    async def get_embeddings_batch(
        self,
        texts: List[str],
        model: str = "bge-m3:latest",
        batch_size: int = 24
    ) -> List[List[float]]:
        """
        Tạo embeddings theo lô (batch) thông qua endpoint /api/embed của Ollama.
        Tăng tốc độ nạp RAG gấp nhiều lần so với gọi tuần tự từng chunk.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                # 1. Ưu tiên endpoint /api/embed hỗ trợ batch input danh sách
                payload = {
                    "model": model,
                    "input": batch,
                    "keep_alive": "60m"
                }
                res = await self._client.post("/api/embed", json=payload, timeout=45.0)
                if res.status_code == 200:
                    data = res.json()
                    embs = data.get("embeddings", [])
                    if embs and len(embs) == len(batch):
                        all_embeddings.extend(embs)
                        continue

                # 2. Fallback sang /api/embeddings từng mục nếu Ollama cũ chưa hỗ trợ batch
                for item in batch:
                    item_res = await self._client.post(
                        "/api/embeddings",
                        json={"model": model, "prompt": item, "keep_alive": "60m"},
                        timeout=15.0
                    )
                    if item_res.status_code == 200:
                        all_embeddings.append(item_res.json().get("embedding", []))
                    else:
                        all_embeddings.append([])
            except Exception as e:
                logger.error(f"Lỗi khi lấy batch embeddings ({model}): {e}")
                # Đảm bảo giữ đúng số lượng phần tử
                all_embeddings.extend([[] for _ in range(len(batch))])

        return all_embeddings

    async def stream_chat_events(
        self,
        messages: List[Dict[str, Any]],
        model: str = "qwen2.5:latest",
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        num_ctx: int = 8192
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream câu trả lời hoặc tool calls từ Ollama chat completion (/api/chat).
        - Endpoint /api/chat không nhận trường `system` top-level, bắt buộc chèn {"role": "system"} vào đầu messages.
        - Thiết lập num_ctx mặc định 8192 để tránh cắt context âm thầm.
        Yields:
        - {"type": "token", "token": "..."}
        - {"type": "tool_calls", "calls": [...]}
        - {"type": "error", "error": "..."}
        """
        # Chuẩn bị messages có system prompt ở vị trí đầu tiên
        formatted_messages = []
        has_system = False
        for m in messages:
            if m.get("role") == "system":
                has_system = True
                formatted_messages.append({"role": "system", "content": system if system else m.get("content", "")})
            else:
                formatted_messages.append(dict(m))

        if system and not has_system:
            formatted_messages.insert(0, {"role": "system", "content": system})

        payload = {
            "model": model,
            "messages": formatted_messages,
            "stream": True,
            "keep_alive": "60m",
            "options": {
                "temperature": 0.7,
                "num_ctx": num_ctx
            }
        }
        if tools:
            payload["tools"] = tools

        try:
            async with self._client.stream(
                "POST",
                "/api/chat",
                json=payload
            ) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    try:
                        err_json = json.loads(err_body.decode())
                        err_msg = err_json.get("error", f"HTTP {response.status_code}")
                    except Exception:
                        err_msg = err_body.decode() or f"HTTP {response.status_code}"
                    yield {"type": "error", "error": f"Lỗi Ollama ({response.status_code}): {err_msg}"}
                    return

                accumulated_tool_calls = []

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "error" in data:
                            yield {"type": "error", "error": f"Lỗi từ Ollama: {data['error']}"}
                            return

                        msg = data.get("message", {})
                        
                        # 1. Kiểm tra tool calling
                        tool_calls = msg.get("tool_calls")
                        if tool_calls:
                            accumulated_tool_calls.extend(tool_calls)

                        # 2. Token nội dung
                        content = msg.get("content", "")
                        if content:
                            yield {"type": "token", "token": content}

                        # 3. Khi hoàn tất stream
                        if data.get("done", False):
                            if accumulated_tool_calls:
                                yield {"type": "tool_calls", "calls": accumulated_tool_calls}
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            yield {"type": "error", "error": f"Không thể kết nối đến Ollama: {str(e)}"}

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "qwen2.5:latest",
        system: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Wrapper tương thích ngược trả về chuỗi token đơn thuần."""
        async for ev in self.stream_chat_events(messages=messages, model=model, system=system):
            if ev.get("type") == "token":
                yield ev["token"]
            elif ev.get("type") == "error":
                yield f"\n[Lỗi: {ev['error']}]"
