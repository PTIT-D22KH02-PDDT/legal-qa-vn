"""
LLMQueryAnalyzer — phân tích câu hỏi pháp luật bằng LLM structured output.

Chiến lược:
- Ưu tiên `with_structured_output(..., method="function_calling")`.
- Nếu model không hỗ trợ tool/function calling, fallback sang
  `with_structured_output(..., method="json_mode")`.

Mục tiêu: không parse JSON thủ công và vẫn chạy được trên nhiều model Groq.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ..llms import build_llm
from ..schemas import QueryAnalysisResult
from ..utils.llm_prompt_instruction import get_llm_prompt

logger = logging.getLogger(__name__)


class QueryAnalysisError(RuntimeError):
    """Raised khi LLM call hoặc structured parsing fail."""


class LLMQueryAnalyzer:
    """
    LLM-only analyzer, output cố định kiểu `QueryAnalysisResult` nhờ
    `with_structured_output` của LangChain.
    """

    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        model_name: Optional[str] = None,
    ):
        self.llm = llm or build_llm(model=model_name or "llama-3.1-8b-instant")
        # Bind schema 1 lần, tái sử dụng cho mọi lần analyze.
        # Tránh default `json_schema` vì nhiều model Groq không hỗ trợ response_format đó.
        self.structured_llm_fc = self.llm.with_structured_output(
            QueryAnalysisResult,
            method="function_calling",
        )
        self.structured_llm_json = self.llm.with_structured_output(
            QueryAnalysisResult,
            method="json_mode",
        )

    def analyze(self, query: str) -> QueryAnalysisResult:
        """Raises `QueryAnalysisError` nếu LLM call hoặc validation fail."""
        if not query or not query.strip():
            raise QueryAnalysisError("empty query")

        system_prompt, user_prompt = get_llm_prompt(query)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # 1) Ưu tiên function_calling
        try:
            result = self.structured_llm_fc.invoke(messages)
        except Exception as first_err:
            logger.warning(
                "[analyzer] function_calling failed, fallback json_mode: %s",
                first_err,
            )
            # 2) Fallback json_mode
            try:
                result = self.structured_llm_json.invoke(messages)
            except Exception as second_err:
                logger.exception("[analyzer] structured LLM call failed")
                raise QueryAnalysisError(
                    f"analysis failed (function_calling={first_err}; json_mode={second_err})"
                ) from second_err

        # LLM không output original_query → set lại để không bị paraphrase
        result.original_query = query
        return result
