"""
Hệ thống Skill & Gemini Gems (Claude Skills + Gemini Gems).
Kiến trúc:
1. Thư mục skills/<tên>/SKILL.md với YAML frontmatter (name, description), references/
2. Lớp SkillRegistry quét thư mục, parse frontmatter, đồng bộ SQLite bảng skills.
3. Nạp 3 tầng:
   - Tầng 1: Tóm tắt name + description nhúng vào system prompt.
   - Tầng 2: Tool use_skill(name) trả thân SKILL.md về cho mô hình.
   - Tầng 3: Tool read_skill_file(skill, path) đọc references/ (chặn path traversal).
4. Định tuyến 3 đường:
   - Lệnh tường minh /tên-skill
   - Tự khớp ngữ nghĩa embedding (bge-m3)
   - Tool call use_skill
5. Quản lý Gemini Gems: Persona + Hướng dẫn + RAG Doc IDs đính kèm.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from backend.rag import SQLiteVectorStore
from backend.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Quản lý, nạp và định tuyến hệ thống Skill & Gemini Gems."""

    AUTO_INJECT_MAX_CHARS = 3500
    AUTO_MATCH_MAX_SKILL_CHARS = 12000
    TOOL_SKILL_MAX_CHARS = 16000
    SHORT_QUERY_CHARS = 12

    def __init__(
        self,
        skills_dir: Path,
        vector_store: SQLiteVectorStore,
        ollama_client: Optional[OllamaClient] = None
    ):
        self.skills_dir = Path(skills_dir)
        self.vector_store = vector_store
        self.ollama_client = ollama_client
        self.skills_cache: Dict[str, Dict[str, Any]] = {}
        self.description_embeddings: Dict[str, List[float]] = {}
        self._disk_mtime: float = 0.0
        self._init_skills_dir()
        self.reload_skills()

    def _init_skills_dir(self):
        """Khởi tạo thư mục skills nếu chưa có."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def parse_skill_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Parse file SKILL.md với định dạng YAML frontmatter."""
        try:
            content = file_path.read_text(encoding="utf-8")
            match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
            if not match:
                # Không có frontmatter chuẩn -> dùng tên thư mục
                name = file_path.parent.name
                return {
                    "name": name,
                    "description": f"Skill {name}",
                    "content": content.strip(),
                    "file_path": str(file_path),
                    "dir_path": str(file_path.parent)
                }

            frontmatter_text = match.group(1)
            body_content = match.group(2).strip()

            metadata = {}
            for line in frontmatter_text.splitlines():
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    k, v = line.split(":", 1)
                    metadata[k.strip()] = v.strip().strip('"').strip("'")

            name = metadata.get("name", file_path.parent.name)
            description = metadata.get("description", f"Skill {name}")

            return {
                "name": name,
                "description": description,
                "content": body_content,
                "file_path": str(file_path),
                "dir_path": str(file_path.parent)
            }
        except Exception as e:
            logger.error(f"Lỗi khi đọc file skill {file_path}: {e}")
            return None

    def reload_skills(self):
        """Quét thư mục skills/ và đồng bộ với SQLite bảng skills."""
        self.skills_cache.clear()
        disk_skill_names = set()

        if self.skills_dir.exists():
            for skill_folder in self.skills_dir.iterdir():
                if skill_folder.is_dir():
                    skill_md = skill_folder / "SKILL.md"
                    if skill_md.exists():
                        parsed = self.parse_skill_file(skill_md)
                        if parsed:
                            name = parsed["name"]
                            disk_skill_names.add(name)
                            # Đảm bảo có bản ghi trong SQLite
                            self.vector_store.upsert_db_skill(
                                name=name,
                                description=parsed["description"],
                                is_active=True,
                                is_gem=False,
                                update_active=False,
                                update_instruction=False
                            )
                            self.skills_cache[name] = parsed

        # Nạp các Gems do người dùng tạo từ SQLite
        db_skills = self.vector_store.list_db_skills()
        for s in db_skills:
            name = s["name"]
            if s.get("is_gem"):
                self.skills_cache[name] = {
                    "name": name,
                    "description": s["description"],
                    "content": s.get("prompt_instruction", ""),
                    "is_gem": True,
                    "is_active": s.get("is_active", True),
                    "attached_doc_ids": s.get("attached_doc_ids", []),
                    "file_path": None,
                    "dir_path": None
                }
            elif name in self.skills_cache:
                self.skills_cache[name]["is_active"] = s.get("is_active", True)

        self._disk_mtime = self._latest_disk_mtime()
        logger.info(f"Đã nạp {len(self.skills_cache)} skills và gems vào hệ thống.")

    def _latest_disk_mtime(self) -> float:
        if not self.skills_dir.exists():
            return 0.0
        latest = 0.0
        for skill_folder in self.skills_dir.iterdir():
            skill_md = skill_folder / "SKILL.md"
            if skill_md.is_file():
                latest = max(latest, skill_md.stat().st_mtime)
        return latest

    def reload_if_stale(self):
        """Chỉ quét lại đĩa khi SKILL.md thay đổi — tránh upsert SQLite mỗi lần GET."""
        if self._latest_disk_mtime() != self._disk_mtime:
            self.reload_skills()

    def get_active_skills(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các skill và gems đang được bật."""
        return [
            s for s in self.skills_cache.values()
            if s.get("is_active", True) and not s["name"].startswith("system-")
        ]

    def get_system_skill_content(self, skill_name: str) -> Optional[str]:
        """Lấy nội dung skill hệ thống (ví dụ system-online hoặc system-offline)."""
        skill = self.skills_cache.get(skill_name)
        if skill:
            return skill.get("content", "")
        return None

    def get_skills_system_prompt_summary(self) -> str:
        """
        Tầng 1: Tạo danh sách ngắn gọn (name: description) của các skill đang bật
        để nhúng vào system prompt.
        """
        active = self.get_active_skills()
        if not active:
            return ""

        lines = ["\n--- DANH SÁCH SKILLS KHẢ DỤNG ---"]
        lines.append("Bạn có quyền truy cập vào các kỹ năng chuyên môn bên dưới. Khi cần nội dung chi tiết của kỹ năng nào, hãy gọi tool `use_skill(name)`:")
        for s in active:
            lines.append(f"- **{s['name']}**: {s['description']}")
        lines.append("---------------------------------\n")
        return "\n".join(lines)

    def use_skill(self, name: str) -> str:
        """
        Tầng 2: Trả về thân nội dung của file SKILL.md khi mô hình gọi tool.
        """
        clean_name = name.strip().lstrip("/")
        skill = self.skills_cache.get(clean_name)
        if not skill:
            return f"Không tìm thấy skill '{clean_name}'. Vui lòng kiểm tra lại danh sách skills khả dụng."

        return self.format_skill_context(
            clean_name,
            skill.get("content", ""),
            max_chars=self.TOOL_SKILL_MAX_CHARS
        )

    def format_skill_context(
        self,
        name: str,
        content: str,
        max_chars: Optional[int] = None
    ) -> str:
        body = content or ""
        note = ""
        if max_chars and len(body) > max_chars:
            body = body[:max_chars].rstrip()
            note = (
                "\n[Đã rút gọn. Gọi tool `use_skill` hoặc `read_skill_file` "
                "nếu cần phần hướng dẫn / references đầy đủ.]\n"
            )
        return (
            f"=== CHUYÊN MÔN KỸ NĂNG: {name} ===\n"
            f"{body}{note}\n"
            f"=========================================="
        )

    def read_skill_file(self, skill_name: str, relative_path: str) -> str:
        """
        Tầng 3: Đọc file trong thư mục references/ của skill với bảo vệ chống Path Traversal.
        """
        clean_name = skill_name.strip().lstrip("/")
        skill = self.skills_cache.get(clean_name)
        if not skill or not skill.get("dir_path"):
            return f"Skill '{clean_name}' không có tài liệu tham khảo đính kèm."

        base_dir = Path(skill["dir_path"]).resolve()
        target_path = (base_dir / "references" / relative_path).resolve()

        # Kiểm tra chống Path Traversal
        try:
            target_path.relative_to(base_dir)
        except ValueError:
            return "Từ chối truy cập: Đường dẫn tệp vi phạm bảo mật (Path Traversal)."

        if not target_path.exists() or not target_path.is_file():
            return f"Không tìm thấy tệp tài liệu: {relative_path}"

        try:
            return target_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return f"Lỗi đọc tệp: {str(e)}"

    def extract_explicit_skill_command(self, text: str) -> Tuple[Optional[str], str]:
        """
        Đường 1: Kiểm tra lệnh gõ tường minh /tên-skill ở đầu câu của người dùng.
        Trả về: (skill_name_hoặc_None, cleaned_text)
        """
        match = re.match(r'^\/([\w-]+)\s*(.*)$', text.strip())
        if match:
            cmd = match.group(1).lower()
            remaining_prompt = match.group(2).strip()
            if cmd in self.skills_cache:
                return cmd, remaining_prompt
        return None, text

    async def match_skill_by_semantics(
        self,
        query: str,
        threshold: float = 0.68,
        model: str = "bge-m3:latest",
        query_embedding: Optional[List[float]] = None
    ) -> Optional[str]:
        """
        Đường 2: Tự khớp ngữ nghĩa qua embedding description.
        Bỏ qua câu ngắn và skill quá lớn (tránh nạp last30days/docx vào context).
        """
        if not self.ollama_client or not query.strip():
            return None
        if len(query.strip()) < self.SHORT_QUERY_CHARS:
            return None

        active_skills = [
            s for s in self.get_active_skills()
            if len(s.get("content") or "") <= self.AUTO_MATCH_MAX_SKILL_CHARS
        ]
        if not active_skills:
            return None

        try:
            q_emb = query_embedding or await self.ollama_client.get_embedding(query, model=model)
            if not q_emb:
                return None

            q_vec = np.array(q_emb, dtype=np.float32)
            q_norm = np.linalg.norm(q_vec)
            if q_norm == 0:
                return None

            missing = [
                s for s in active_skills
                if s["name"] not in self.description_embeddings
            ]
            if missing:
                texts = [f"{s['name']}: {s.get('description', '')}" for s in missing]
                embs = await self.ollama_client.get_embeddings_batch(texts, model=model)
                for s, emb in zip(missing, embs):
                    if emb:
                        self.description_embeddings[s["name"]] = emb

            best_skill = None
            best_score = -1.0
            dim = int(q_vec.shape[0])

            for s in active_skills:
                d_emb = self.description_embeddings.get(s["name"])
                if not d_emb or len(d_emb) != dim:
                    continue
                d_vec = np.array(d_emb, dtype=np.float32)
                d_norm = np.linalg.norm(d_vec)
                if d_norm <= 0:
                    continue
                sim = float(np.dot(q_vec, d_vec) / (q_norm * d_norm))
                if sim > best_score:
                    best_score = sim
                    best_skill = s["name"]

            if best_score >= threshold and best_skill:
                logger.info(f"Khớp ngữ nghĩa tự động với Skill '{best_skill}' (độ tương đồng: {best_score:.3f})")
                return best_skill
        except Exception as e:
            logger.debug(f"Lỗi khi khớp ngữ nghĩa skill: {e}")

        return None
