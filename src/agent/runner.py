"""
Entry point cho Legal QA Agent.

Một file duy nhất chịu 2 việc:
1. Boot infrastructure: ChromaStore, embedding, LLM, SearchPipeline.
2. Build LangGraph (xem `src/agent/graph/`) rồi gọi `graph.invoke()`.
Không còn lớp wrapper `LegalQAAgent` vì graph đã tự chứa toàn bộ logic
(analyze → plan → execute → grade → rewrite → generate → validate).
Cách chạy:
    python -m src.agent.runner                  # chạy ví dụ (interactive mặc định)
    python -m src.agent.runner --interactive    # hội thoại liên tục
    python -m src.agent.runner --examples       # chạy bộ câu hỏi mẫu
    python -m src.agent.runner --no-config      # bỏ qua YAML, dùng mặc định hard-code
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Any, Dict, List, Optional

from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
from src.indexing.vector_store import ChromaConfig, ChromaStore
from src.search.config import PipelineConfig
from src.search.pipeline import SearchPipeline

from .config import get_agent_config
from .graph import build_default_graph
from .llms import build_llm
from .tools import LegalDocumentTools

logger = logging.getLogger(__name__)

EXAMPLE_QUERIES: List[str] = [
    "Việc mua bán tài sản thế cấp, cầm cố được quy định như thế nào trong pháp luật Việt Nam?",
]

class LegalQARunner:
    def __init__(
        self,
        use_config: bool = True,
        llm_model: Optional[str] = None,
        chroma_db_dir: Optional[str] = None,
        embedding_model_dir: Optional[str] = None,
        checkpointer_kind: str = "memory",
        enable_logging: bool = True,
    ):
        self.enable_logging = enable_logging
        if enable_logging:
            logging.basicConfig(level=logging.INFO)

        logger.info("[runner] Initializing...")

        # 1. Load config (hoặc fallback hard-code)
        collection_name = "legal_documents"
        is_persist = True
        distance_metric = "ip"
        llm_params: Dict[str, Any] = {}

        if use_config:
            agent_config = get_agent_config()
            pipeline_config = PipelineConfig.get_default_config()

            llm_provider = agent_config.get_query_analyzer_params().get("llm_provider", "groq")
            llm_params = agent_config.get_llm_provider_params(llm_provider)
            llm_model = llm_model or llm_params.get("model_name")

            vs_params = pipeline_config.get_vector_store_params()
            chroma_db_dir = chroma_db_dir or vs_params.get("persist_directory")
            collection_name = vs_params.get("collection_name", collection_name)
            is_persist = vs_params.get("is_persist", True)
            distance_metric = vs_params.get("distance_metric", "ip")

            embedding_model_dir = embedding_model_dir or pipeline_config.get_embedding_model_dir()
        else:
            llm_model = llm_model or "llama-3.1-8b-instant"
            chroma_db_dir = chroma_db_dir or "chroma_db"
            embedding_model_dir = embedding_model_dir or "models/vietnamese-embedding"

        logger.info("  LLM=%s  Chroma=%s  Embedding=%s",
                    llm_model, chroma_db_dir, embedding_model_dir)

        # 2. Infrastructure
        self.chroma_store = ChromaStore(config=ChromaConfig(
            collection_name=collection_name,
            persist_directory=chroma_db_dir,
            is_persist=is_persist,
            distance_metric=distance_metric,
        ))
        self.embedding_model = OnnxEmbeddingModel(model_dir=str(embedding_model_dir))
        self.search_pipeline = SearchPipeline(
            chroma_store=self.chroma_store,
            embedding_model=self.embedding_model,
        )

        # 3. LLM (ChatOpenAI trỏ Groq endpoint)
        api_key = llm_params.get("api_key") or os.getenv("GROQ_API_KEY")
        temperature = llm_params.get("temperature", 0.0) if use_config else 0.0
        self.llm = build_llm(
            model=llm_model,
            temperature=temperature,
            api_key=api_key,
        )

        # 4. Tools provider + graph
        self.tools_provider = LegalDocumentTools(
            chroma_store=self.chroma_store,
            embedding_model=self.embedding_model,
            retrieval_service=self.search_pipeline,
        )
        self.graph = build_default_graph(
            llm=self.llm,
            tools_provider=self.tools_provider,
            checkpointer_kind=checkpointer_kind,
        )

        logger.info("[runner] Ready.")

    def query(self, question: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Chạy 1 câu hỏi qua graph. Trả về dict gồm các field cốt lõi
        để caller tuỳ ý hiển thị / log.

        Returns:
            {
                "answer": str,
                "sources": list[str],
                "validation": Optional[ValidationResult],
                "state": dict  # full final state (debug)
            }
        """
        thread_id = thread_id or str(uuid.uuid4())
        logger.info("[query] %r thread=%s", question[:120], thread_id)

        final_state = self.graph.invoke(
            {"query": question, "original_query": question, "rewrite_count": 0},
            config={"configurable": {"thread_id": thread_id}},
        )

        answer = final_state.get("final_answer") or ""
        sources = final_state.get("sources") or []
        validation = final_state.get("validation")

        if answer:
            logger.info("[answer] %s", answer[:200])
        if sources:
            logger.info("[sources] %s", ", ".join(sources))

        return {
            "answer": answer,
            "sources": sources,
            "validation": validation,
            "state": final_state,
        }

    # ------------------------------------------------------------------
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
                result = self.query(question, thread_id=thread_id)
                print(f"\nAgent: {result['answer']}")
                if result["sources"]:
                    print(f"[Nguồn] {', '.join(result['sources'])}")
                print()
            except Exception as e:
                logger.exception("query failed")
                print(f"Lỗi: {e}\n")

    # ------------------------------------------------------------------
    def run_examples(self, n: int = 3) -> None:
        """Chạy `n` câu hỏi trong EXAMPLE_QUERIES."""
        print("\n" + "=" * 60)
        print("Running Example Queries")
        print("=" * 60)
        for q in EXAMPLE_QUERIES[:n]:
            print(f"\n{'=' * 60}\nQuery: {q}\n{'=' * 60}")
            try:
                result = self.query(q)
                print(f"\nAnswer: {result['answer']}")
                if result["sources"]:
                    print(f"Sources: {', '.join(result['sources'])}")
            except Exception as e:
                logger.exception("example failed")
                print(f"Lỗi: {e}")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main() -> None:
    args = sys.argv[1:]
    use_config = "--no-config" not in args

    runner = LegalQARunner(use_config=use_config, enable_logging=True)

    if "--examples" in args:
        runner.run_examples(n=3)
    else:
        # mặc định: interactive
        runner.interactive_mode()


if __name__ == "__main__":
    main()
