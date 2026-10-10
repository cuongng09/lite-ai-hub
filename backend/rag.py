"""
SQLite-vec & FTS5 Hybrid Search Vector Store cho RAG tài liệu (PDF, Docx, TXT).
Tối ưu:
- SQLite WAL mode (Write-Ahead Logging) cho concurrency cao và an toàn.
- FTS5 Full-Text Search kết hợp Cosine Similarity (Hybrid Search BM25 + Vector).
- Lưu trữ embedding_model để kiểm soát tính nhất quán số chiều vector.
- TextSplitter cải tiến: Sliding Window Overlap xuyên suốt giữa các đoạn văn.
- Ngưỡng điểm tối thiểu (min_score) loại bỏ chunk không liên quan.
"""

import os
import re
import json
import uuid
import sqlite3
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


class DocumentParser:
    """Trích xuất nội dung từ PDF, DOCX, TXT thuần Python."""

    @staticmethod
    def extract_text(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return DocumentParser._parse_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            return DocumentParser._parse_docx(file_path)
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

    @staticmethod
    def _parse_pdf(file_path: str) -> str:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        text_pages = []
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text_pages.append(content)
        return "\n\n".join(text_pages)

    @staticmethod
    def _parse_docx(file_path: str) -> str:
        import docx
        doc = docx.Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])


class TextSplitter:
    """
    Chia văn bản thành các đoạn (chunks) sử dụng Sliding Window Overlap
    xuyên suốt giữa các đoạn văn để bảo toàn ngữ cảnh hoàn hảo cho bge-m3.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []

        # Chuẩn hóa khoảng trắng nhưng giữ cấu trúc ngắt dòng
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + self.chunk_size

            if end < text_length:
                # Tìm điểm ngắt tự nhiên gần nhất (kết thúc đoạn, kết thúc câu, hoặc dấu cách)
                natural_break = -1
                search_window = text[max(start, end - 150): min(text_length, end + 50)]
                offset = max(start, end - 150)

                for delimiter in ["\n\n", ".\n", ". ", "!\n", "?\n", "\n", " "]:
                    idx = search_window.rfind(delimiter)
                    if idx != -1:
                        natural_break = offset + idx + len(delimiter)
                        break

                if natural_break > start:
                    end = natural_break

            chunk_content = text[start:end].strip()
            if chunk_content:
                chunks.append(chunk_content)

            # Bước nhảy tiếp theo có overlap liên tục
            start = end - self.chunk_overlap
            if start < 0 or start >= text_length:
                break

        return chunks


class SQLiteVectorStore:
    """
    Vector Store tích hợp trong SQLite với FTS5 Hybrid Search và WAL Mode.
    Lưu trữ embedding vector dưới dạng BLOB (Float32), FTS5 full-text indexing,
    và lọc theo ngưỡng điểm tương đồng tối thiểu.
    """

    def __init__(self, db_path: str = "rag_knowledge.db"):
        self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Bảng documents lưu thông tin tài liệu kèm embedding_model
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    chunk_count INTEGER DEFAULT 0,
                    embedding_model TEXT DEFAULT 'bge-m3:latest',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            try:
                cursor.execute("ALTER TABLE documents ADD COLUMN embedding_model TEXT DEFAULT 'bge-m3:latest';")
            except Exception:
                pass


            # Bảng chunks lưu vector embedding BLOB
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    FOREIGN KEY (doc_id) REFERENCES documents (id) ON DELETE CASCADE
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);")

            # Bảng ảo FTS5 cho Full-Text Keyword Search
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                        content,
                        chunk_id UNINDEXED,
                        doc_id UNINDEXED,
                        tokenize = 'unicode61'
                    );
                """)
            except Exception as e:
                logger.warning(f"Không thể khởi tạo FTS5 ảo: {e}")

            # Bảng chat_sessions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    mode TEXT DEFAULT 'offline',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            try:
                cursor.execute("ALTER TABLE chat_sessions ADD COLUMN mode TEXT DEFAULT 'offline';")
            except Exception:
                pass


            # Bảng chat_messages
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    artifact_json TEXT DEFAULT NULL,
                    sources_json TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);")

            # Bảng skills (quản lý hệ thống Skill & Gemini Gems)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    is_active INTEGER DEFAULT 1,
                    is_gem INTEGER DEFAULT 0,
                    prompt_instruction TEXT,
                    attached_doc_ids TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    def add_document(
        self,
        filename: str,
        file_size: int,
        chunks: List[str],
        embeddings: List[List[float]],
        embedding_model: str = "bge-m3:latest"
    ) -> int:
        """Lưu tài liệu, chunks, embeddings và chỉ mục FTS5 vào SQLite."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO documents (filename, file_size, chunk_count, embedding_model)
                VALUES (?, ?, ?, ?);
                """,
                (filename, file_size, len(chunks), embedding_model)
            )
            doc_id = cursor.lastrowid

            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                emb_array = np.array(emb, dtype=np.float32)
                cursor.execute(
                    """
                    INSERT INTO chunks (doc_id, chunk_index, content, embedding)
                    VALUES (?, ?, ?, ?);
                    """,
                    (doc_id, idx, chunk, emb_array.tobytes())
                )
                chunk_id = cursor.lastrowid

                # Nạp đồng thời vào FTS5
                try:
                    cursor.execute(
                        "INSERT INTO chunks_fts (content, chunk_id, doc_id) VALUES (?, ?, ?);",
                        (chunk, str(chunk_id), str(doc_id))
                    )
                except Exception:
                    pass

            conn.commit()
            return doc_id

    def list_documents(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các tài liệu hiện có trong CSDL."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, filename, file_size, chunk_count, embedding_model, created_at FROM documents ORDER BY id DESC;"
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "filename": row[1],
                    "file_size": row[2],
                    "chunk_count": row[3],
                    "embedding_model": row[4],
                    "created_at": row[5]
                }
                for row in rows
            ]

    def delete_document(self, doc_id: int) -> bool:
        """Xóa tài liệu và toàn bộ chunks & FTS5 index liên quan."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM chunks_fts WHERE doc_id = ?;", (str(doc_id),))
            except Exception:
                pass
            cursor.execute("DELETE FROM documents WHERE id = ?;", (doc_id,))
            conn.commit()
            return cursor.rowcount > 0

    def search_similar(
        self,
        query_embedding: List[float],
        query_text: str = "",
        top_k: int = 4,
        min_score: float = 0.35,
        target_model: str = "bge-m3:latest",
        doc_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm lai (Hybrid Search): Kết hợp Vector Cosine Similarity (70%) + FTS5 Keyword Search (30%).
        Loại bỏ các kết quả có điểm dưới ngưỡng min_score.
        """
        if not query_embedding:
            return []

        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Truy vấn Vector Chunks
            sql = """
                SELECT c.id, c.doc_id, d.filename, d.embedding_model, c.chunk_index, c.content, c.embedding
                FROM chunks c
                JOIN documents d ON c.doc_id = d.id
            """
            params = []
            if doc_ids:
                placeholders = ",".join("?" * len(doc_ids))
                sql += f" WHERE c.doc_id IN ({placeholders})"
                params.extend(doc_ids)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            if not rows:
                return []

            fts_scores: Dict[int, float] = {}
            if query_text.strip():
                clean_q = re.sub(r'[^\w\s]', ' ', query_text).strip()
                tokens = clean_q.split()
                if tokens:
                    fts_query = " OR ".join(f'"{t}"' for t in tokens[:6])
                    try:
                        cursor.execute(
                            """
                            SELECT chunk_id, rank
                            FROM chunks_fts
                            WHERE chunks_fts MATCH ?
                            ORDER BY rank
                            LIMIT 20;
                            """,
                            (fts_query,)
                        )
                        for cid_raw, rank_val in cursor.fetchall():
                            cid = int(cid_raw)
                            raw_rank = abs(float(rank_val))
                            fts_scores[cid] = raw_rank / (1.0 + raw_rank)
                    except Exception as e:
                        logger.debug(f"Lỗi truy vấn FTS5: {e}")


        # 3. Tính toán điểm kết hợp và lọc ngưỡng
        scored_results = []
        for row in rows:
            chunk_id, d_id, filename, doc_emb_model, chunk_index, content, emb_bytes = row

            if doc_emb_model and doc_emb_model != target_model:
                logger.warning(
                    f"Cảnh báo: Tài liệu '{filename}' được nhúng bằng '{doc_emb_model}', nhưng truy vấn dùng '{target_model}'."
                )

            chunk_vec = np.frombuffer(emb_bytes, dtype=np.float32)
            chunk_norm = np.linalg.norm(chunk_vec)
            if chunk_norm == 0 or len(chunk_vec) != len(q_vec):
                continue

            # Cosine similarity
            cos_sim = float(np.dot(q_vec, chunk_vec) / (q_norm * chunk_norm))

            # Kết hợp với điểm FTS5 nếu có
            fts_sim = fts_scores.get(chunk_id, 0.0)
            if fts_sim > 0:
                final_score = (0.7 * cos_sim) + (0.3 * fts_sim)
            else:
                final_score = cos_sim

            # Lọc theo ngưỡng tối thiểu
            if final_score >= min_score:
                scored_results.append({
                    "chunk_id": chunk_id,
                    "doc_id": d_id,
                    "filename": filename,
                    "chunk_index": chunk_index,
                    "content": content,
                    "score": round(final_score, 4),
                    "vector_score": round(cos_sim, 4),
                    "fts_score": round(fts_sim, 4)
                })

        # Sắp xếp giảm dần theo điểm cuối cùng
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:top_k]

    # --- QUẢN LÝ LỊCH SỬ CHAT SESSIONS & MESSAGES (PERSISTENT SQLite) ---

    def create_session(self, title: str = "Đoạn chat mới", mode: str = "offline") -> Dict[str, Any]:
        """Tạo một phiên hội thoại mới và lưu vào SQLite với created_at chuẩn ISO."""
        session_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chat_sessions (id, title, mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (session_id, title, mode, now_iso, now_iso)
            )
            conn.commit()
        return {
            "id": session_id,
            "title": title,
            "mode": mode,
            "created_at": now_iso,
            "updated_at": now_iso
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các phiên trò chuyện, sắp xếp theo thời gian mới nhất."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.title, s.mode, s.created_at, s.updated_at,
                       COUNT(m.id) as message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON s.id = m.session_id
                GROUP BY s.id
                ORDER BY s.updated_at DESC;
            """)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "mode": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "message_count": row[5]
                }
                for row in rows
            ]

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Lấy toàn bộ tin nhắn thuộc về một session cụ thể."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, role, content, artifact_json, sources_json, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id ASC;
            """, (session_id,))
            rows = cursor.fetchall()
            messages = []
            for row in rows:
                sources = None
                if row[4]:
                    try:
                        sources = json.loads(row[4])
                    except Exception:
                        pass

                messages.append({
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "sources": sources or {"web": [], "rag": []},
                    "created_at": row[5]
                })
            return messages

    def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        artifact: Optional[Dict[str, Any]] = None,
        sources: Optional[Dict[str, Any]] = None
    ) -> int:
        """Lưu một tin nhắn mới vào session và cập nhật updated_at của session."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Đảm bảo session tồn tại nếu chưa có
            cursor.execute("SELECT id FROM chat_sessions WHERE id = ?;", (session_id,))
            if not cursor.fetchone():
                cursor.execute(
                    """
                    INSERT INTO chat_sessions (id, title, mode, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (session_id, content[:35] + ("..." if len(content) > 35 else ""), "offline", now_iso, now_iso)
                )

            art_json = json.dumps(artifact, ensure_ascii=False) if artifact else None
            src_json = json.dumps(sources, ensure_ascii=False) if sources else None

            cursor.execute("""
                INSERT INTO chat_messages (session_id, role, content, artifact_json, sources_json)
                VALUES (?, ?, ?, ?, ?);
            """, (session_id, role, content, art_json, src_json))
            msg_id = cursor.lastrowid

            cursor.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?;",
                (now_iso, session_id)
            )
            conn.commit()
            return msg_id

    def delete_session(self, session_id: str) -> bool:
        """Xóa hoàn toàn một phiên hội thoại và tin nhắn liên quan."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_sessions WHERE id = ?;", (session_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_session_title(self, session_id: str, title: str) -> bool:
        """Cập nhật tiêu đề phiên trò chuyện."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?;",
                (title, now_iso, session_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_session_mode(self, session_id: str, mode: str) -> bool:
        """Cập nhật chế độ phiên trò chuyện (offline / online)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE chat_sessions SET mode = ?, updated_at = ? WHERE id = ?;",
                (mode, now_iso, session_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    # --- QUẢN LÝ SKILLS & GEMS TRONG SQLITE ---

    def list_db_skills(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các skill và gems từ CSDL."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, description, is_active, is_gem, prompt_instruction, attached_doc_ids, created_at, updated_at FROM skills ORDER BY is_gem ASC, name ASC;"
            )
            rows = cursor.fetchall()
            skills = []
            for r in rows:
                doc_ids = []
                if r[6]:
                    try:
                        doc_ids = json.loads(r[6])
                    except Exception:
                        pass
                skills.append({
                    "id": r[0],
                    "name": r[1],
                    "description": r[2] or "",
                    "is_active": bool(r[3]),
                    "is_gem": bool(r[4]),
                    "prompt_instruction": r[5] or "",
                    "attached_doc_ids": doc_ids,
                    "created_at": r[7],
                    "updated_at": r[8]
                })
            return skills

    def upsert_db_skill(
        self,
        name: str,
        description: str,
        is_active: bool = True,
        is_gem: bool = False,
        prompt_instruction: str = "",
        attached_doc_ids: Optional[List[int]] = None
    ) -> str:
        """Tạo hoặc cập nhật skill/gem trong SQLite."""
        skill_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        doc_json = json.dumps(attached_doc_ids or [])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM skills WHERE name = ?;", (name,))
            existing = cursor.fetchone()
            if existing:
                s_id = existing[0]
                cursor.execute("""
                    UPDATE skills
                    SET description = ?, is_active = ?, is_gem = ?, prompt_instruction = ?, attached_doc_ids = ?, updated_at = ?
                    WHERE id = ?;
                """, (description, 1 if is_active else 0, 1 if is_gem else 0, prompt_instruction, doc_json, now_iso, s_id))
                conn.commit()
                return s_id
            else:
                cursor.execute("""
                    INSERT INTO skills (id, name, description, is_active, is_gem, prompt_instruction, attached_doc_ids, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (skill_id, name, description, 1 if is_active else 0, 1 if is_gem else 0, prompt_instruction, doc_json, now_iso, now_iso))
                conn.commit()
                return skill_id

    def set_skill_active(self, skill_name_or_id: str, is_active: bool) -> bool:
        """Bật/tắt trạng thái hoạt động của skill."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skills SET is_active = ?, updated_at = ? WHERE id = ? OR name = ?;",
                (1 if is_active else 0, now_iso, skill_name_or_id, skill_name_or_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_db_skill(self, skill_id: str) -> bool:
        """Xóa một skill (thường là Gem do người dùng tạo)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM skills WHERE id = ?;", (skill_id,))
            conn.commit()
            return cursor.rowcount > 0
