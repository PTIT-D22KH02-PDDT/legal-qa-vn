"""
Tools package cho Legal QA Agent.

- `LegalDocumentTools`: wrapper các tool gọi Chroma/DB, trả `ToolOutput`.
- `LLMQueryAnalyzer`: phân tích query bằng LLM (JSON mode).
"""

from .tools import LegalDocumentTools
from .llm_query_analyzer import LLMQueryAnalyzer, QueryAnalysisError

__all__ = [
    "LegalDocumentTools",
    "LLMQueryAnalyzer",
    "QueryAnalysisError",
]
