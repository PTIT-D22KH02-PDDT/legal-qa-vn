"""
Entry point cho Legal QA Agent.
1. Boot infrastructure: RemoteAPIClient, RemoteEmbeddingModel, ChromaStore, LLM.
2. Build LangGraph rồi gọi graph.invoke().

Cách chạy:
    python -m src.agent.runner                  # interactive mặc định
    python -m src.agent.runner --interactive    # hội thoại liên tục
    python -m src.agent.runner --file <path>    # chạy câu hỏi từ file
    python -m src.agent.runner --examples       # chạy bộ câu hỏi mẫu
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.api.remote_client import RemoteAPIClient
from src.indexing.embedding.remote_embedding import RemoteEmbeddingModel
from src.indexing.vector_store import ChromaStore, ChromaConfig
from src.search.search import SearchService
from system.database.db_respository import get_session

from .graph.builder import build_default_graph
from .llms import build_llm
from .tools import LegalDocumentTools

load_dotenv()

# Fix Windows console UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)

EXAMPLE_QUERIES: List[str] = [
    "Việc mua bán tài sản thế cấp, cầm cố được quy định như thế nào trong pháp luật Việt Nam?",
    "Giao dịch dân sự vô hiệu do vi phạm điều cấm của luật thì hậu quả pháp lý là gì?",
]


class LegalQARunner:
    def __init__(
        self,
        checkpointer_kind: str = "memory",
        enable_logging: bool = True,
    ):
        if enable_logging:
            logging.basicConfig(level=logging.INFO)

        logger.info("[runner] Initializing with REMOTE embedding...")

        # 1. Remote API client (dùng chung cho embed + generate)
        self.api_client = RemoteAPIClient()

        # 2. Embedding & Vector Store
        self.embedding_model = RemoteEmbeddingModel(self.api_client)
        self.chroma_store = ChromaStore(
            config=ChromaConfig(
                collection_name="legal_documents",
                persist_directory="chroma_db",
                is_persist=True,
                distance_metric="ip"
            )
        )
        self.search_service = SearchService(
            chroma_store=self.chroma_store,
            embedding_model=self.embedding_model,
        )

        # 3. LLM (Groq hoặc Remote, theo AGENT_LLM_PROVIDER trong .env)
        self.llm = build_llm(api_client=self.api_client)

        # 4. Tools provider + graph
        self.db_session = get_session()
        self.tools_provider = LegalDocumentTools(
            chroma_store=self.chroma_store,
            embedding_model=self.embedding_model,
            llm=self.llm,
            retrieval_service=self.search_service,
            db_session=self.db_session
        )
        self.graph = build_default_graph(
            llm=self.llm,
            tools_provider=self.tools_provider,
            checkpointer_kind=checkpointer_kind,
        )

        logger.info("[runner] Ready (Remote Mode).")

    def query(self, question: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Chạy 1 câu hỏi qua graph.

        Returns:
            {"answer": str, "sources": list[str], "state": dict}
        """
        thread_id = thread_id or str(uuid.uuid4())
        logger.info("[query] %r thread=%s", question[:120], thread_id)

        final_state = self.graph.invoke(
            {"query": question, "original_query": question, "rewrite_count": 0},
            config={"configurable": {"thread_id": thread_id}},
        )

        answer = final_state.get("final_answer") or ""
        sources = final_state.get("sources") or []

        if answer:
            logger.info("[answer] %s", answer[:200])

        print(f"\nAgent: {answer}")
        if sources:
            print(f"[Nguồn] {', '.join(sources)}")

        return {"answer": answer, "sources": sources, "state": final_state}

    def interactive_mode(self) -> None:
        """CLI hội thoại liên tục."""
        thread_id = str(uuid.uuid4())
        print("\n" + "=" * 60)
        print("Legal QA Agent — Chế độ tương tác")
        print("=" * 60)
        print("Nhập câu hỏi (hoặc 'exit'/'quit' để thoát):\n")

        while True:
            try:
                question = input("Bạn: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nTạm biệt!")
                return
            if not question:
                continue
            if question.lower() in {"exit", "quit", "thoát"}:
                print("Tạm biệt!")
                return
            try:
                self.query(question, thread_id=thread_id)
            except Exception as e:
                logger.exception("query failed")
                print(f"Lỗi: {e}\n")

    def run_examples(self, n: int = 3) -> None:
        """Chạy n câu hỏi trong EXAMPLE_QUERIES."""
        print("\n" + "=" * 60)
        print("Running Example Queries")
        print("=" * 60)
        for q in EXAMPLE_QUERIES[:n]:
            print(f"\n{'=' * 60}\nQuery: {q}\n{'=' * 60}")
            try:
                self.query(q)
            except Exception as e:
                logger.exception("example failed")
                print(f"Lỗi: {e}")


def main() -> None:
    args = sys.argv[1:]
    runner = LegalQARunner(enable_logging=True)

    if "--file" in args:
        idx = args.index("--file")
        filepath = args[idx + 1]
        print(f"Reading query from {filepath}...")
        with open(filepath, "r", encoding="utf-8") as f:
            runner.query(f.read().strip())
    elif "--examples" in args:
        runner.run_examples(n=3)
    else:
        runner.interactive_mode()


if __name__ == "__main__":
    main()
