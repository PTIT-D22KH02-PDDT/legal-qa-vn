"""Search module - Unified vector search + re-ranking pipeline."""

from .pipeline import SearchPipeline
from .config import PipelineConfig
from .retrieval import RetrievalService, RetrieveQuestionRequest, RetrieveResult
from .rerank import CrossEncoderReranker, RankedResult

__all__ = [
    "SearchPipeline",
    "PipelineConfig",
    "RetrievalService",
    "RetrieveQuestionRequest",
    "RetrieveResult",
    "CrossEncoderReranker",
    "RankedResult",
]
