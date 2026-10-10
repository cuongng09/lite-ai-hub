import pytest
from backend.search import WebSearchEngine
from backend.tools import ToolExecutor

def test_web_search_format():
    engine = WebSearchEngine(max_results=3)
    dummy_results = [
        {"title": "Bài viết 1", "href": "https://example.com/1", "body": "Nội dung tóm tắt 1"},
        {"title": "Bài viết 2", "href": "https://example.com/2", "body": "Nội dung tóm tắt 2"}
    ]
    context = engine.format_search_context(dummy_results)
    assert "[1] Bài viết 1" in context
    assert "https://example.com/1" in context
    assert "[2] Bài viết 2" in context

def test_tool_executor_unknown():
    engine = WebSearchEngine()
    executor = ToolExecutor(engine)
    output, meta = executor.execute_tool("unknown_tool", {})
    assert "Không hỗ trợ" in output
    assert meta is None
