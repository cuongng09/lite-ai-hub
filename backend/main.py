import os
import re
import json
import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.search import WebSearchEngine
from backend.research import DeepResearchEngine
from backend.ollama_client import OllamaClient
from backend.rag import DocumentParser, TextSplitter, SQLiteVectorStore
from backend.tools import TOOL_DEFINITIONS, ToolExecutor
from backend.skills import SkillRegistry

# Xác định đường dẫn gốc tuyệt đối của dự án
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "rag_knowledge.db"
STATIC_DIR = BASE_DIR / "static"
SKILLS_DIR = BASE_DIR / "skills"

app = FastAPI(
    title="Lite-AI Hub Backend",
    description="Backend AI Local siêu nhẹ, FTS5 Hybrid RAG & Hệ thống Claude Skills / Gemini Gems",
    version="3.0.0"
)

# CORS Middleware chuẩn mực - Không dùng wildcard khi allow_credentials=True
ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "tauri://localhost",
    "http://tauri.localhost"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo các services
search_engine = WebSearchEngine(max_results=5)
ollama_client = OllamaClient()
deep_research_engine = DeepResearchEngine(search_engine, ollama_client)
vector_store = SQLiteVectorStore(db_path=str(DB_PATH))
text_splitter = TextSplitter(chunk_size=1000, chunk_overlap=150)
skill_registry = SkillRegistry(skills_dir=SKILLS_DIR, vector_store=vector_store, ollama_client=ollama_client)
tool_executor = ToolExecutor(search_engine, skill_registry=skill_registry)


class ChatMessage(BaseModel):
    role: str
    content: str


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "Đoạn chat mới"
    mode: Optional[str] = "offline"


class UpdateTitleRequest(BaseModel):
    title: str


class UpdateModeRequest(BaseModel):
    mode: str


class CreateGemRequest(BaseModel):
    name: str
    description: str
    prompt_instruction: str
    attached_doc_ids: Optional[List[int]] = []


class GenerateGemPromptRequest(BaseModel):
    description: str
    model: Optional[str] = "qwen2.5:latest"


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    chat_mode: str = "offline"  # "offline": Kiến thức nền | "online": Thời sự
    model: str = "qwen2.5:latest"
    embedding_model: str = "bge-m3:latest"
    num_ctx: int = 8192
    use_web_search: bool = False
    use_deep_research: bool = False
    use_rag: bool = False
    use_tools: bool = True


def prune_messages_budget(messages: List[ChatMessage], max_chars: int = 14000) -> List[Dict[str, Any]]:
    if not messages:
        return []

    last_msg = messages[-1].model_dump()
    budget = max_chars - len(last_msg.get("content", ""))

    kept = []
    for m in reversed(messages[:-1]):
        content_len = len(m.content or "")
        if budget - content_len >= 0:
            kept.insert(0, m.model_dump())
            budget -= content_len
        else:
            break

    kept.append(last_msg)
    return kept


def extract_fallback_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Bộ parse dự phòng: Trích xuất tool call khi mô hình in dưới dạng JSON trong content
    thay vì native tool_calls.
    """
    calls = []
    code_blocks = re.findall(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    candidate_strings = code_blocks if code_blocks else [text]

    for candidate in candidate_strings:
        for match in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', candidate):
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    fn_name = data.get("name") or data.get("tool") or data.get("function")
                    args = data.get("arguments") or data.get("parameters") or {}
                    if fn_name in ["web_search", "use_skill", "read_skill_file"]:
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {"query": args} if fn_name == "web_search" else {"name": args}
                        calls.append({
                            "function": {
                                "name": fn_name,
                                "arguments": args
                            }
                        })
                    elif "query" in data and ("search" in str(data.get("action", "")) or "web" in str(data)):
                        calls.append({
                            "function": {
                                "name": "web_search",
                                "arguments": {"query": data["query"]}
                            }
                        })
            except Exception:
                continue
    return calls


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "app": "Lite-AI Hub",
        "version": "3.0.0",
        "skills_count": len(skill_registry.skills_cache)
    }


@app.get("/api/models")
async def get_models():
    """Lấy danh sách các models đang có trong Ollama."""
    models = await ollama_client.list_models()
    return {"models": models}


# --- ENDPOINTS QUẢN LÝ PHIÊN CHAT (SESSIONS & HISTORY) ---

@app.get("/api/sessions")
async def list_sessions():
    """Lấy danh sách tất cả các phiên trò chuyện."""
    sessions = vector_store.list_sessions()
    return {"sessions": sessions}


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    """Tạo một phiên hội thoại mới."""
    session = vector_store.create_session(
        title=req.title or "Đoạn chat mới",
        mode=req.mode or "offline"
    )
    return session


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Lấy danh sách tin nhắn của một phiên hội thoại."""
    messages = vector_store.get_session_messages(session_id)
    return {"session_id": session_id, "messages": messages}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Xóa một phiên hội thoại."""
    success = vector_store.delete_session(session_id)
    return {"success": success}


@app.put("/api/sessions/{session_id}/title")
async def update_session_title(session_id: str, req: UpdateTitleRequest):
    """Đổi tên tiêu đề đoạn chat."""
    success = vector_store.update_session_title(session_id, req.title)
    return {"success": success}


@app.put("/api/sessions/{session_id}/mode")
async def update_session_mode(session_id: str, req: UpdateModeRequest):
    """Cập nhật chế độ của đoạn chat (offline / online)."""
    success = vector_store.update_session_mode(session_id, req.mode)
    return {"success": success}


# --- ENDPOINTS TÀI LIỆU RAG VỚI BATCH EMBEDDINGS ---

@app.get("/api/documents")
async def list_documents():
    """Lấy danh sách tài liệu RAG đã nạp vào SQLite."""
    docs = vector_store.list_documents()
    return {"documents": docs}


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int):
    """Xóa một tài liệu khỏi kho tri thức."""
    success = vector_store.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return {"success": True, "message": f"Đã xóa tài liệu #{doc_id}"}


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    embedding_model: str = Form("bge-m3:latest")
):
    """
    Tải file (PDF, DOCX, TXT) lên, phân đoạn văn bản và
    tạo embeddings theo lô (batch) cực nhanh qua /api/embed.
    """
    filename = file.filename or "unknown_file"
    suffix = Path(filename).suffix

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_path = tmp_file.name

    try:
        raw_text = DocumentParser.extract_text(tmp_path)
        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="Không thể đọc nội dung hoặc file rỗng.")

        chunks = text_splitter.split_text(raw_text)
        if not chunks:
            raise HTTPException(status_code=400, detail="Không tạo được đoạn văn bản từ file.")

        # Tạo embeddings hàng loạt qua /api/embed (Batch size 24)
        embeddings = await ollama_client.get_embeddings_batch(chunks, model=embedding_model, batch_size=24)
        if not embeddings or len(embeddings) != len(chunks):
            raise HTTPException(
                status_code=500,
                detail=f"Lỗi embedding. Vui lòng đảm bảo model '{embedding_model}' đã tải trong Ollama."
            )

        file_size = os.path.getsize(tmp_path)
        doc_id = vector_store.add_document(
            filename=filename,
            file_size=file_size,
            chunks=chunks,
            embeddings=embeddings,
            embedding_model=embedding_model
        )

        return {
            "success": True,
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": len(chunks),
            "embedding_model": embedding_model
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# --- ENDPOINTS HỆ THỐNG SKILLS & GEMINI GEMS ---

@app.get("/api/skills")
async def get_skills():
    """Lấy danh sách tất cả các Skills và Gems hiện có."""
    skill_registry.reload_skills()
    skills_list = []
    for s in skill_registry.skills_cache.values():
        if not s["name"].startswith("system-"):
            skills_list.append({
                "name": s["name"],
                "description": s["description"],
                "is_active": s.get("is_active", True),
                "is_gem": s.get("is_gem", False),
                "attached_doc_ids": s.get("attached_doc_ids", [])
            })
    return {"skills": skills_list}


@app.post("/api/skills")
async def create_gem(req: CreateGemRequest):
    """Tạo một Gem tùy chỉnh (Persona + Hướng dẫn + Tài liệu RAG đính kèm)."""
    clean_name = re.sub(r'[^\w-]', '', req.name.lower().strip().replace(' ', '-'))
    if not clean_name:
        raise HTTPException(status_code=400, detail="Tên Gem không hợp lệ.")

    skill_id = vector_store.upsert_db_skill(
        name=clean_name,
        description=req.description,
        is_active=True,
        is_gem=True,
        prompt_instruction=req.prompt_instruction,
        attached_doc_ids=req.attached_doc_ids
    )
    skill_registry.reload_skills()
    return {"success": True, "id": skill_id, "name": clean_name}


@app.put("/api/skills/{skill_name}/toggle")
async def toggle_skill(skill_name: str, active: bool):
    """Bật hoặc tắt trạng thái kích hoạt của Skill/Gem."""
    success = vector_store.set_skill_active(skill_name, active)
    skill_registry.reload_skills()
    return {"success": success}


@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """Xóa một Gem do người dùng tạo."""
    success = vector_store.delete_db_skill(skill_id)
    skill_registry.reload_skills()
    return {"success": success}


@app.post("/api/skills/generate")
async def generate_gem_prompt(req: GenerateGemPromptRequest):
    """Dùng mô hình LLM hỗ trợ soạn thảo hướng dẫn Gem từ mô tả ý tưởng."""
    prompt = (
        f"Bạn là chuyên gia thiết kế Persona AI và Prompt Engineer. "
        f"Hãy viết một bản hướng dẫn chi tiết, chuyên nghiệp (system instruction) cho trợ lý AI dựa trên ý tưởng sau:\n"
        f"\"{req.description}\"\n\n"
        f"Bản hướng dẫn cần nêu rõ: Vai trò (Persona), Mục tiêu chính, Nguyên tắc ứng xử, Định dạng câu trả lời. "
        f"Trả về trực tiếp nội dung hướng dẫn bằng tiếng Việt, không kèm lời chào."
    )
    tokens = []
    async for ev in ollama_client.stream_chat_events(
        messages=[{"role": "user", "content": prompt}],
        model=req.model or "qwen2.5:latest",
        num_ctx=2048
    ):
        if ev.get("type") == "token":
            tokens.append(ev["token"])

    return {"instruction": "".join(tokens).strip()}


# --- ENDPOINT STREAM CHAT CHÍNH VỚI ĐỊNH TUYẾN SKILLS & DISCONNECT CANCEL ---

@app.post("/api/chat/stream")
async def chat_stream(request: Request, chat_req: ChatRequest):
    """
    Endpoint SSE Streaming thời gian thực hỗ trợ:
    - Định tuyến 3 đường cho Skills (Lệnh tường minh /tên-skill, Tự khớp Semantic, Tool Call)
    - Ngắt sinh tức thì khi Client đóng kết nối (is_disconnected)
    - Lưu tin nhắn vào SQLite sau khi stream thành công
    - FTS5 Hybrid Search kết hợp Cosine Similarity cho RAG
    """
    if not chat_req.messages:
        raise HTTPException(status_code=400, detail="Danh sách tin nhắn trống.")

    raw_last_message = next(
        (m.content for m in reversed(chat_req.messages) if m.role == "user"), ""
    )

    async def sse_event_generator():
        web_sources = []
        rag_sources = []
        context_blocks = []
        full_assistant_response = ""
        active_gem_doc_ids = None

        # -------------------------------------------------------------
        # 1. ĐỊNH TUYẾN SKILLS (3 ĐƯỜNG)
        # -------------------------------------------------------------
        actual_user_message = raw_last_message
        loaded_skill_context = ""

        # Đường 1: Kiểm tra lệnh gõ tường minh /tên-skill
        explicit_skill, remaining_text = skill_registry.extract_explicit_skill_command(raw_last_message)
        if explicit_skill:
            actual_user_message = remaining_text or raw_last_message
            skill_data = skill_registry.skills_cache.get(explicit_skill)
            if skill_data:
                yield f"data: {json.dumps({'type': 'status', 'message': f'🎯 Kích hoạt Skill: {explicit_skill}'}, ensure_ascii=False)}\n\n"
                loaded_skill_context = f"=== CHUYÊN MÔN KỸ NĂNG: {explicit_skill} ===\n{skill_data.get('content', '')}\n=========================================="
                if skill_data.get("attached_doc_ids"):
                    active_gem_doc_ids = skill_data["attached_doc_ids"]

        # Đường 2: Tự khớp ngữ nghĩa (Semantic matching) nếu chưa có lệnh tường minh
        elif not loaded_skill_context and actual_user_message:
            matched_skill = await skill_registry.match_skill_by_semantics(
                actual_user_message,
                threshold=0.55,
                model=chat_req.embedding_model
            )
            if matched_skill:
                skill_data = skill_registry.skills_cache.get(matched_skill)
                if skill_data:
                    yield f"data: {json.dumps({'type': 'status', 'message': f'💡 Tự động khớp Skill: {matched_skill}'}, ensure_ascii=False)}\n\n"
                    loaded_skill_context = f"=== CHUYÊN MÔN KỸ NĂNG: {matched_skill} ===\n{skill_data.get('content', '')}\n=========================================="
                    if skill_data.get("attached_doc_ids"):
                        active_gem_doc_ids = skill_data["attached_doc_ids"]

        is_online = (chat_req.chat_mode == "online") or chat_req.use_web_search or chat_req.use_deep_research

        # -------------------------------------------------------------
        # 2. XỬ LÝ CHẾ ĐỘ THỜI SỰ (ONLINE MODE) VS KIẾN THỨC NỀN
        # -------------------------------------------------------------
        if is_online and actual_user_message:
            if chat_req.use_deep_research:
                research_result = {"sources": [], "context_text": ""}
                async for ev in deep_research_engine.stream_deep_research(actual_user_message, model=chat_req.model):
                    if await request.is_disconnected():
                        return
                    if ev.get("type") == "status":
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    elif ev.get("type") == "result":
                        research_result = ev.get("data", {})
                web_sources = research_result.get("sources", [])
                context_blocks.append(research_result.get("context_text", ""))
            else:
                yield f"data: {json.dumps({'type': 'status', 'message': '🌐 Đang tìm kiếm thông tin thời sự mới nhất năm 2026...'}, ensure_ascii=False)}\n\n"
                web_results = await asyncio.to_thread(search_engine.search, actual_user_message, 5)
                if web_results:
                    web_sources = web_results
                    context_blocks.append(search_engine.format_search_context(web_results))

            # Lấy system prompt từ skill hệ thống system-online
            system_instruction = skill_registry.get_system_skill_content("system-online") or (
                "BẠN ĐANG Ở CHẾ ĐỘ THỜI SỰ (ONLINE MODE). THỜI GIAN HIỆN TẠI LÀ NĂM 2026. "
                "CHỈ ĐƯỢC PHÉP TRẢ LỜI VÀ TỔNG HỢP DỰA TRÊN KẾT QUẢ TÌM KIẾM WEB BÊN DƯỚI. "
                "TUYỆT ĐỐI KHÔNG DÙNG KIẾN THỨC CŨ TRONG BỘ NHỚ HUẤN LUYỆN ĐỂ ĐỐI CHIẾU HOẶC SO SÁNH. "
                "LUÔN TRÍCH DẪN NGUỒN THEO SỐ [1], [2], [3]."
            )
        else:
            # Lấy system prompt từ skill hệ thống system-offline
            system_instruction = skill_registry.get_system_skill_content("system-offline") or (
                "BẠN ĐANG Ở CHẾ ĐỘ KIẾN THỨC NỀN (OFFLINE MODE). "
                "Bạn là trợ lý AI thông minh chuyên về kiến thức nền tảng, tư duy logic, lập trình, toán học và sáng tạo. "
                "Nếu viết mã nguồn, hãy dùng định dạng Markdown ```ngôn_ngữ ... ``` với cú pháp chuẩn."
            )

        # Bổ sung Tầng 1: Tóm tắt các skills đang bật vào system prompt
        skills_summary = skill_registry.get_skills_system_prompt_summary()
        if skills_summary:
            system_instruction += f"\n\n{skills_summary}"

        # -------------------------------------------------------------
        # 3. XỬ LÝ RAG HYBRID SEARCH (FTS5 + COSINE)
        # -------------------------------------------------------------
        if chat_req.use_rag and actual_user_message:
            q_emb = await ollama_client.get_embedding(actual_user_message, model=chat_req.embedding_model)
            if q_emb:
                matched_chunks = await asyncio.to_thread(
                    vector_store.search_similar,
                    query_embedding=q_emb,
                    query_text=actual_user_message,
                    top_k=4,
                    min_score=0.35,
                    target_model=chat_req.embedding_model,
                    doc_ids=active_gem_doc_ids
                )
                if matched_chunks:
                    rag_sources = matched_chunks
                    rag_text_parts = ["--- DỮ LIỆU TÀI LIỆU NỘI BỘ (RAG HYBRID SEARCH) ---"]
                    for c in matched_chunks:
                        rag_text_parts.append(
                            f"[Nguồn: {c['filename']} (Đoạn #{c['chunk_index']}) | Độ khớp: {c['score']:.2f}]\n{c['content']}\n"
                        )
                    rag_text_parts.append("-----------------------------------------------------")
                    context_blocks.append("\n".join(rag_text_parts))

        # Gửi thông tin Sources trước cho Client
        if web_sources or rag_sources:
            yield f"data: {json.dumps({'type': 'sources', 'web': web_sources, 'rag': rag_sources}, ensure_ascii=False)}\n\n"

        # Nếu có Skill context đã nạp sẵn, đưa vào context_blocks
        if loaded_skill_context:
            context_blocks.append(loaded_skill_context)

        # Cắt tỉa lịch sử tin nhắn bảo vệ ngân sách ngữ cảnh
        enriched_messages = prune_messages_budget(chat_req.messages, max_chars=14000)

        if context_blocks:
            combined_context = "\n\n".join(context_blocks)
            enriched_messages[-1]["content"] = (
                f"{combined_context}\n\n"
                f"Dựa vào thông tin trên, hãy trả lời câu hỏi sau:\n{actual_user_message}"
            )

        # -------------------------------------------------------------
        # 4. STREAMING PHẢN HỒI KÈM TOOL CALLING & CANCEL CHECK
        # -------------------------------------------------------------
        tools_to_pass = TOOL_DEFINITIONS if chat_req.use_tools else None

        tool_calls_received = []
        async for event in ollama_client.stream_chat_events(
            messages=enriched_messages,
            model=chat_req.model,
            system=system_instruction,
            tools=tools_to_pass,
            num_ctx=chat_req.num_ctx
        ):
            # Ngắt sinh ngay lập tức nếu client đóng tab hoặc hủy kết nối
            if await request.is_disconnected():
                logger.info("Client ngắt kết nối, dừng stream hoàn toàn.")
                return

            ev_type = event.get("type")
            if ev_type == "token":
                token = event["token"]
                full_assistant_response += token
                yield f"data: {json.dumps({'type': 'content', 'token': token}, ensure_ascii=False)}\n\n"
            elif ev_type == "tool_calls":
                tool_calls_received = event.get("calls", [])
            elif ev_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': event.get('error', 'Lỗi từ Ollama')}, ensure_ascii=False)}\n\n"
                return

        # 5. Fallback Parser kiểm tra JSON tool call nếu native tool calls rỗng
        if not tool_calls_received and full_assistant_response:
            fallback_calls = extract_fallback_tool_calls(full_assistant_response)
            if fallback_calls:
                tool_calls_received = fallback_calls

        # 6. Xử lý các Tool Calls (Gộp tất cả vào 1 assistant message duy nhất + thêm tool_name)
        if tool_calls_received:
            enriched_messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls_received
            })

            for tc in tool_calls_received:
                if await request.is_disconnected():
                    return

                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                fn_args = fn.get("arguments", {})
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except Exception:
                        fn_args = {}

                yield f"data: {json.dumps({'type': 'tool_executing', 'tool': fn_name, 'args': fn_args}, ensure_ascii=False)}\n\n"
                tool_output_str, meta_data = tool_executor.execute_tool(fn_name, fn_args)

                if meta_data and meta_data.get("type") == "sources":
                    found_web = meta_data.get("web", [])
                    web_sources.extend(found_web)
                    yield f"data: {json.dumps({'type': 'sources', 'web': web_sources, 'rag': rag_sources}, ensure_ascii=False)}\n\n"
                elif meta_data and meta_data.get("type") == "skill_loaded":
                    skill_name_val = meta_data.get("skill_name", "")
                    yield f"data: {json.dumps({'type': 'status', 'message': f'📖 Đã nạp Skill: {skill_name_val}'}, ensure_ascii=False)}\n\n"

                enriched_messages.append({
                    "role": "tool",
                    "tool_name": fn_name,
                    "name": fn_name,
                    "content": tool_output_str
                })

            # Lượt thứ 2: Mô hình tổng hợp câu trả lời cuối cùng
            async for event in ollama_client.stream_chat_events(
                messages=enriched_messages,
                model=chat_req.model,
                system=system_instruction,
                num_ctx=chat_req.num_ctx
            ):
                if await request.is_disconnected():
                    return

                if event.get("type") == "token":
                    token = event["token"]
                    full_assistant_response += token
                    yield f"data: {json.dumps({'type': 'content', 'token': token}, ensure_ascii=False)}\n\n"
                elif event.get("type") == "error":
                    yield f"data: {json.dumps({'type': 'error', 'error': event.get('error')}, ensure_ascii=False)}\n\n"
                    return

        # -------------------------------------------------------------
        # 7. LƯU TIN NHẮN SAU KHI STREAM THÀNH CÔNG VÀO SQLITE
        # -------------------------------------------------------------
        if chat_req.session_id and full_assistant_response:
            # Lưu tin nhắn của User
            vector_store.add_chat_message(
                session_id=chat_req.session_id,
                role="user",
                content=raw_last_message
            )
            # Lưu tin nhắn của Assistant
            vector_store.add_chat_message(
                session_id=chat_req.session_id,
                role="assistant",
                content=full_assistant_response,
                artifact=None,
                sources={"web": web_sources, "rag": rag_sources}
            )

        # Báo hiệu hoàn tất
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# --- PHỤC VỤ STATIC WEB UI HIỆN ĐẠI (ZERO RAM FRONTEND) ---
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
