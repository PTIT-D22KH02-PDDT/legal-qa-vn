from dataclasses import dataclass
import logging
from pathlib import Path

from src.api import RemoteAPIClient
from src.indexing.vector_store import ChromaQueryResult
from src.search import SearchService

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    query: str
    answer: str
    context: str
    sources: list[ChromaQueryResult]


@dataclass
class RAGService:
    search_service: SearchService
    api_client: RemoteAPIClient
    prompt_template_path: str | Path = "configs/prompts/rag_answer_prompt.txt"

    top_k_retrieve: int = 10
    top_k_rerank: int = 5
    use_rerank: bool = True

    max_context_length: int = 8000
    max_answer_length: int = 2000
    temperature: float = 0.1

    context_separator: str = "\n---\n"

    def _load_prompt_template(self) -> str:
        prompt_path = Path(self.prompt_template_path)

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template file not found: {self.prompt_template_path}")

        prompt_template = prompt_path.read_text(encoding="utf-8")
        placeholders = ["{query}", "{context}"]
        missing_placeholders = [
            placeholder
            for placeholder in placeholders
            if placeholder not in prompt_template
        ]

        if missing_placeholders:
            raise ValueError(f"Prompt template is missing placeholders: {', '.join(missing_placeholders)}")

        return prompt_template

    def _format_display(self, result: ChromaQueryResult) -> tuple[str, str]:
        metadata = result.metadata or {}

        hierarchy_order = [
            "diem", "khoan", "dieu", "muc", "chuong", "phan", "chinh", "modau", "so_hieu"
        ]

        parts = [
            str(metadata[key]) for key in hierarchy_order if metadata.get(key)
        ]

        content = metadata.get("full_text") if metadata.get("full_text") else result.text

        return " ".join(parts) or result.chunk_id, content

    def _format_context(self, docs: list[ChromaQueryResult]) -> str:
        context_parts: list[str] = []

        for idx, res in enumerate(docs, 1):
            section_display, content = self._format_display(res)
            context_parts.append(
                f"[Nguon {idx}]\n"
                f"{section_display}\n"
                f"{content}\n"
            )

        context = self.context_separator.join(context_parts)

        if len(context) > self.max_context_length:
            context = context[:self.max_context_length] + "\n...[Context truncated]..."
            logger.warning("Context truncated to %s chars", self.max_context_length)

        return context

    def _build_prompt(self, query: str, context: str) -> str:
        template = self._load_prompt_template()

        return template.format(
            query=query,
            context=context,
        )

    def answer(
        self,
        query: str,
        top_k_retrieve: int | None = None,
        top_k_rerank: int | None = None,
        use_rerank: bool | None = None,
        filter_by_type: list[str] | None = None,
        distance_threshold: float | None = None,
    ) -> RAGResult:
        metadata_filter = (
            {"section_type": filter_by_type} if filter_by_type else None
        )

        documents = self.search_service.search(
            query=query,
            top_k_retrieve=top_k_retrieve or self.top_k_retrieve,
            top_k_rerank=top_k_rerank or self.top_k_rerank,
            use_rerank=use_rerank if use_rerank is not None else self.use_rerank,
            distance_threshold=distance_threshold,
            metadata_filter=metadata_filter,
        )

        if not documents:
            return RAGResult(
                query=query,
                answer="Xin loi, toi khong tim thay thong tin lien quan de tra loi cau hoi cua ban.",
                context="",
                sources=[],
            )

        context = self._format_context(documents)
        prompt = self._build_prompt(query, context)
        logger.info("Context length: %d chars. Starting generation with LLM...", len(context))
        answer = self.api_client.generate(
            prompt=prompt,
            max_length=self.max_answer_length,
            temperature=self.temperature,
        )
        return RAGResult(
            query=query,
            answer=answer,
            context=context,
            sources=documents,
        )