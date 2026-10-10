import json
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from backend.rag_engine import ingest_document, query_rag, llm
from backend.search_tool import search_searxng

app = FastAPI(title="Lite-AI Hub Backend")

class ChatRequest(BaseModel):
    message: str
    enable_rag: bool = True
    enable_web: bool = True

def decide_routing(query: str, enable_rag: bool, enable_web: bool) -> str:
    """
    Quyết định nhánh xử lý (Router):
    - 'RAG': Truy xuất tài liệu nội bộ
    - 'WEB': Tra cứu tin tức web qua SearXNG
    - 'DIRECT': Trả lời trực tiếp từ LLM
    """
    if not enable_rag and not enable_web:
        return "DIRECT"

    web_keywords = ["hôm nay", "thời tiết", "tin tức", "giá", "mới nhất", "hiện tại", "năm 202", "tìm kiếm"]
    is_web_query = any(k in query.lower() for k in web_keywords)

    if enable_web and is_web_query:
        return "WEB"
    if enable_rag:
        return "RAG"
    if enable_web:
        return "WEB"
    return "DIRECT"

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """API tải lên tài liệu PDF hoặc TXT."""
    content = await file.read()
    chars_count = ingest_document(content, file.filename)
    return {
        "status": "success",
        "filename": file.filename,
        "processed_characters": chars_count
    }

@app.post("/api/chat")
async def chat_stream(req: ChatRequest):
    """API chat trả về luồng streaming token (SSE - Server Sent Events)."""
    route = decide_routing(req.message, req.enable_rag, req.enable_web)
    citations: List[Dict[str, str]] = []
    context_text = ""

    if route == "RAG":
        context_text, citations = query_rag(req.message, top_k=3)
    elif route == "WEB":
        web_results = search_searxng(req.message, max_results=3)
        if web_results:
            context_parts = []
            for item in web_results:
                context_parts.append(f"[{item['title']}] ({item['url']}): {item['content']}")
                citations.append({
                    "title": item["title"],
                    "content": item["content"],
                    "url": item["url"]
                })
            context_text = "\n\n".join(context_parts)

    system_prompt = (
        "Bạn là trợ lý AI hữu ích, ngắn gọn và chính xác. "
        "Nếu có thông tin ngữ cảnh được cung cấp dưới đây, hãy dựa vào đó để trả lời câu hỏi. "
        "Nếu ngữ cảnh không có thông tin, hãy trả lời bằng hiểu biết của bạn.\n\n"
    )
    if context_text:
        final_prompt = f"{system_prompt}Ngữ cảnh bổ sung:\n{context_text}\n\nCâu hỏi: {req.message}\nTrả lời:"
    else:
        final_prompt = f"{system_prompt}Câu hỏi: {req.message}\nTrả lời:"

    async def event_generator():
        yield f"data: {json.dumps({'type': 'citations', 'citations': citations})}\n\n"

        response_gen = llm.stream_complete(final_prompt)
        for chunk in response_gen:
            delta = chunk.delta
            if delta:
                yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
