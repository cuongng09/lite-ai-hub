import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:latest")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3:latest")
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
