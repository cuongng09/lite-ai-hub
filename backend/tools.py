"""
Module định nghĩa và thực thi Function Calling (Tools) cho Ollama Qwen2.5.
Hỗ trợ:
- Web Search tức thì cho tìm kiếm thông tin thời gian thực
- use_skill(name): Nạp nội dung chi tiết của một Skill (Claude Skills / Gemini Gems)
- read_skill_file(skill_name, relative_path): Đọc tệp tham khảo trong thư mục references/
"""

import json
import logging
from typing import Dict, Any, List, Tuple, Optional
from backend.search import WebSearchEngine

logger = logging.getLogger(__name__)

# Định nghĩa Tool Schemas chuẩn OpenAI / Ollama
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Tìm kiếm thông tin trên internet khi người dùng hỏi về tin tức thời sự, sự kiện gần đây, dữ liệu thời gian thực năm 2026, giá cả, thời tiết hoặc công nghệ mới.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Từ khóa hoặc câu truy vấn tìm kiếm tiếng Việt hoặc tiếng Anh ngắn gọn, súc tích"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": "Nạp toàn bộ hướng dẫn chuyên môn chi tiết của một Kỹ năng (Skill) từ hệ thống khi người dùng yêu cầu tác vụ tương ứng.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Tên định danh của skill (ví dụ: 'web-ui-designer', 'diagram-mermaid', 'code-review-vi', 'doc-summarizer', 'viet-writer', 'deep-research-report')"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": "Đọc tệp tài liệu tham khảo bổ trợ trong thư mục references/ của một skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Tên skill chứa tệp tài liệu"
                    },
                    "relative_path": {
                        "type": "string",
                        "description": "Đường dẫn tương đối của tệp trong thư mục references/"
                    }
                },
                "required": ["skill_name", "relative_path"]
            }
        }
    }
]


class ToolExecutor:
    """Bộ thực thi các công cụ được gọi bởi mô hình LLM."""

    def __init__(self, search_engine: WebSearchEngine, skill_registry: Optional[Any] = None):
        self.search_engine = search_engine
        self.skill_registry = skill_registry

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Thực thi tool theo tên và đối số.
        Trả về tuple: (kết quả text gửi lại cho LLM, sources/meta metadata nếu có)
        """
        try:
            if name == "web_search":
                query = arguments.get("query", "")
                if not query:
                    return "Truy vấn tìm kiếm rỗng.", None
                
                results = self.search_engine.search(query, max_results=5)
                if not results:
                    return f"Không tìm thấy kết quả phù hợp cho: '{query}'", None
                context = self.search_engine.format_search_context(results)
                return context, {"type": "sources", "web": results}

            elif name == "use_skill":
                skill_name = arguments.get("name", "")
                if not self.skill_registry:
                    return "Hệ thống Skill chưa được khởi tạo.", None
                content = self.skill_registry.use_skill(skill_name)
                return content, {"type": "skill_loaded", "skill_name": skill_name}

            elif name == "read_skill_file":
                skill_name = arguments.get("skill_name", "")
                rel_path = arguments.get("relative_path", "")
                if not self.skill_registry:
                    return "Hệ thống Skill chưa được khởi tạo.", None
                content = self.skill_registry.read_skill_file(skill_name, rel_path)
                return content, None

            else:
                return f"Không hỗ trợ tool: {name}", None

        except Exception as e:
            logger.error(f"Lỗi khi thực thi tool {name}: {e}")
            return f"Lỗi thực thi tool {name}: {str(e)}", None
