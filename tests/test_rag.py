import os
import pytest
from pathlib import Path
from backend.rag import TextSplitter, SQLiteVectorStore

def test_text_splitter_sliding_window():
    splitter = TextSplitter(chunk_size=100, chunk_overlap=20)
    text = "Đoạn văn thứ nhất có nội dung khá dài để kiểm tra việc cắt văn bản thành nhiều chunks. Đoạn văn thứ hai tiếp tục bổ sung thông tin chi tiết."
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2
    assert isinstance(chunks, list)
    for c in chunks:
        assert len(c) > 0


def test_text_splitter_always_advances():
    splitter = TextSplitter(chunk_size=30, chunk_overlap=25)
    chunks = splitter.split_text("abc " * 80)
    assert 2 <= len(chunks) <= 200

def test_sqlite_vector_store(tmp_path):
    db_file = tmp_path / "test_rag.db"
    store = SQLiteVectorStore(db_path=str(db_file))
    
    # 1. Thêm tài liệu
    chunks = ["Python là ngôn ngữ lập trình mạnh mẽ", "FastAPI là framework web hiện đại siêu nhanh"]
    dummy_embs = [[0.1] * 128, [0.2] * 128]
    doc_id = store.add_document("test.txt", 1024, chunks, dummy_embs, embedding_model="bge-m3:latest")
    assert doc_id > 0
    
    # 2. Danh sách tài liệu
    docs = store.list_documents()
    assert len(docs) == 1
    assert docs[0]["filename"] == "test.txt"
    assert docs[0]["embedding_model"] == "bge-m3:latest"
    
    # 3. Hybrid search
    results = store.search_similar(
        query_embedding=[0.1] * 128,
        query_text="Python",
        top_k=2,
        min_score=0.2
    )
    assert len(results) >= 1
    assert "Python" in results[0]["content"]
    assert results[0]["score"] > 0.2

    skipped = store.search_similar(
        query_embedding=[0.1] * 128,
        query_text="Python",
        top_k=2,
        min_score=0.01,
        target_model="other-model:latest"
    )
    assert skipped == []

    # 4. Session management với created_at hợp lệ
    sess = store.create_session(title="Phiên test", mode="offline")
    assert sess["id"] is not None
    assert sess["created_at"] is not None
    
    # Lưu tin nhắn
    msg_id = store.add_chat_message(sess["id"], "user", "Xin chào")
    assert msg_id > 0
    messages = store.get_session_messages(sess["id"])
    assert len(messages) == 1
    assert messages[0]["content"] == "Xin chào"
    
    # Xóa session
    assert store.delete_session(sess["id"]) is True
