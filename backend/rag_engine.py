import os
import chromadb
from typing import List, Dict, Tuple
from llama_index.core import VectorStoreIndex, Document, StorageContext, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from pypdf import PdfReader
from backend.config import OLLAMA_BASE_URL, LLM_MODEL, EMBED_MODEL, CHROMA_PERSIST_DIR

# 1. Khởi tạo LLM và Embedding model từ Ollama
llm = Ollama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=120.0)
embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_BASE_URL)

Settings.llm = llm
Settings.embed_model = embed_model
Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)

# 2. Khởi tạo ChromaDB Embedded local
chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
chroma_collection = chroma_client.get_or_create_collection("lite_rag_docs")
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Đọc nội dung văn bản từ file PDF hoặc TXT."""
    if filename.lower().endswith(".pdf"):
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "\n".join([page.extract_text() or "" for page in reader.pages])
        return text
    else:
        return file_bytes.decode("utf-8", errors="ignore")

def ingest_document(file_bytes: bytes, filename: str) -> int:
    """Chunking và lưu trữ văn bản vào ChromaDB."""
    text = extract_text_from_file(file_bytes, filename)
    if not text.strip():
        return 0

    doc = Document(text=text, metadata={"source": filename})
    index = VectorStoreIndex.from_documents(
        [doc],
        storage_context=storage_context,
        show_progress=False
    )
    return len(text)

def query_rag(query_str: str, top_k: int = 3) -> Tuple[str, List[Dict[str, str]]]:
    """Tìm kiếm vector gần nhất trong ChromaDB."""
    if chroma_collection.count() == 0:
        return "", []

    index = VectorStoreIndex.from_vector_store(
        vector_store,
        storage_context=storage_context
    )
    retriever = index.as_retriever(similarity_top_k=top_k)
    nodes = retriever.retrieve(query_str)

    context_parts = []
    citations = []

    for node in nodes:
        source_name = node.metadata.get("source", "Tài liệu cục bộ")
        snippet = node.node.get_content().strip()
        context_parts.append(f"[Tài liệu: {source_name}]\n{snippet}")
        citations.append({
            "title": f"Tài liệu: {source_name}",
            "content": snippet[:200] + "...",
            "url": ""
        })

    context_text = "\n\n".join(context_parts)
    return context_text, citations
