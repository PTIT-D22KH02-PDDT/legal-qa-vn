from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from ..graph.state import AgentState
from ..tools.llm_query_analyzer import LLMQueryAnalyzer, QueryAnalysisError
from src.indexing.parsing.extract_metadata import Extractor
logger = logging.getLogger(__name__)


def build_analyze_node(llm) -> Callable[[AgentState], Dict[str, Any]]:
    analyzer = LLMQueryAnalyzer(llm=llm)

    def analyze_query(state: AgentState) -> Dict[str, Any]:
        query = state.get("query") or state.get("original_query", "")
        logger.info("[analyze] query=%r", query[:120])

        if not query:
            return {"errors": ["analyze_query: empty query"]}

        try:
            analysis = analyzer.analyze(query)
            logger.info(
                "[analyze] in_scope=%s specific=%s blocks=%d intent=%s",
                analysis.in_scope, analysis.is_specific,
                len(analysis.extracted_blocks), analysis.intent,
            )
            
            # Normalize so_hieu in all blocks (01/2019/NQ-HĐTP → 01_2019_nq_hdtp)
            for block in analysis.extracted_blocks:
                if block.so_hieu:
                    logger.info("[analyze] Normalizing so_hieu: %r", block.so_hieu)
                    extractor=Extractor()
                    block.so_hieu = extractor._extract_so_hieu(block.so_hieu)
            
            # Log detailed block info
            for idx, block in enumerate(analysis.extracted_blocks):
                logger.info(
                    "[analyze] block[%d] dieu=%s khoan=%s diem=%s "
                    "document_name=%r so_hieu=%r",
                    idx, block.dieu, block.khoan, block.diem,
                    block.document_name, block.so_hieu
                )
            return {
                "analysis": analysis,
                "original_query": state.get("original_query") or query,
                "rewrite_count": state.get("rewrite_count", 0),
            }
        except QueryAnalysisError as e:
            logger.warning("[analyze] failed: %s", e)
            return {
                "analysis": None,
                "original_query": state.get("original_query") or query,
                "errors": [f"analyze_query: {e}"],
            }

    return analyze_query
