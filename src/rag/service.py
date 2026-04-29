from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import logging

from src.search import SearchService
from src.api import RemoteAPIClient
from src.indexing.vector_store import ChromaQueryResult

logger = logging.getLogger(__name__)

@dataclass
class RAGResult:
    """Kết quả trả về từ RAGService"""
    query: str
    answer: str
    context: str
    sources: list[ChromaQueryResult]

@dataclass
class RAGService:
    """
    query -> SearchService.search() -> format context -> load prompt -> RemoteAPIClient.generate() -> RAGResult
    """

    search_service: SearchService
    api_client: RemoteAPIClient
    prompt_template_path: str | Path = "configs/prompts/rag_answer_prompt.txt"

    top_k_retrieve: int = 10
    top_k_rerank: int = 5
    use_rerank: bool = True
    
    max_context_length: int = 30000
    max_answer_length: int = 8000
    temperature: float = 0.5

    context_separator: str = "\n---\n"

    _prompt_template: str | None = field(default=None, init=False, repr=False)
    
    def _load_prompt_template(self) -> str:
        """Load prompt template từ file"""
        if self._prompt_template is not None:
            return self._prompt_template

        prompt_path = Path(self.prompt_template_path)

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template file not found: {self.prompt_template_path}")
        
        self._prompt_template = prompt_path.read_text(encoding="utf-8")

        placeholders = ["{query}", "{context}"]
        
        missing_placeholders = [
            pl for pl in placeholders if pl not in self._prompt_template
        ]

        if missing_placeholders:
            raise ValueError(f"Prompt template is missing placeholders: {', '.join(missing_placeholders)}")

        return self._prompt_template
    
    def _format_display(self, result: ChromaQueryResult) -> tuple[str, str]:
        # 1. Format section
        metadata = result.metadata or {}

        hierarchy_order = [
            "diem", "khoan", "dieu", "muc", "chuong", "phan", "chinh", "modau", "van_ban"
        ]

        parts = [
            str(metadata[key]) for key in hierarchy_order if metadata.get(key)
        ]

        # 2. Lấy nội dung
        content = metadata.get("full_text") if metadata.get("full_text") else result.text

        return " ".join(parts) or result.chunk_id, content

    def _format_context(self, docs: list[ChromaQueryResult]) -> str:
        """
        Format retrieved documents thành context cho LLM
        
        Ví dụ:
        [Nguồn 1]
        <Khoản 18 Điều 36>
        <Nội dung>
        """

        context_parts: list[str] = []
        
        for idx, res in enumerate(docs, 1):
            section_display, content = self._format_display(res)
            context_parts.append(
                f"[Nguồn {idx}]\n"
                f"{section_display}\n"
                f"{content}\n"
            )
        
        context = self.context_separator.join(context_parts)

        if len(context) > self.max_context_length:
            context = context[:self.max_context_length] + "\n...[Context truncated]..."
            logger.warning(f"Context truncated to {self.max_context_length} chars")
        
        return context

    def _build_prompt(self, query: str, context: str) -> str:
        template = self._load_prompt_template()

        return template.format(
            query=query,
            context=context
        )

    def answer(
            self, 
            query: str, 
            top_k_retrieve: int | None = None,
            top_k_rerank: int | None = None,
            use_rerank: bool | None = None,
            filter_by_type: list[str] | None = None,
            score_threshold: float | None = None,
    ) -> RAGResult:
        
        metadata_filter = (
            {"section_type": filter_by_type} if filter_by_type else None
        )

        documents = self.search_service.search(
            query=query,
            top_k_retrieve=top_k_retrieve or self.top_k_retrieve,
            top_k_rerank=top_k_rerank or self.top_k_rerank,
            use_rerank=use_rerank if use_rerank is not None else self.use_rerank,
            score_threshold=score_threshold,
            metadata_filter=metadata_filter
        )

        if not documents:
            return RAGResult(
                query=query,
                answer="Xin lỗi, tôi không tìm thấy thông tin liên quan để trả lời câu hỏi của bạn.",
                context="",
                sources=[]
            )

        context = self._format_context(documents)
        prompt = self._build_prompt(query=query, context=context)

        answer = self.api_client.generate(
            prompt=prompt,
            max_length=self.max_answer_length,
            temperature=self.temperature
        )
        return RAGResult(
            query=query,
            answer=answer,
            context=context,
            sources=documents
        )


        