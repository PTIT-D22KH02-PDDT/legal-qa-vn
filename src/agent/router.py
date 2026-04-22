"""
Router - Logic định tuyến tool selection dựa trên query analysis
"""

import logging
from typing import List, Tuple, Dict, Any
from .schemas import QueryAnalysisResult, QueryType, Intent


logger = logging.getLogger(__name__)


class ToolRouter:
    """
    Xác định tool nào cần sử dụng dựa trên kết quả phân tích query
    Workflow:
    1. Nhận QueryAnalysisResult từ QueryAnalyzer
    2. Xác định primary tool (tool chính)
    3. Xác định secondary tools (tools bổ sung nếu cần)
    4. Return danh sách tools theo thứ tự ưu tiên
    """
    # Mapping giữa QueryType và tools
    QUERY_TYPE_TO_TOOLS = {
        QueryType.SEMANTIC_SEARCH: ["search_legal_documents"],
        QueryType.SPECIFIC_LOOKUP: ["get_specific_article", "search_legal_documents"],
        QueryType.COMPARATIVE: ["search_legal_documents", "find_related_documents"],
        QueryType.PROCEDURAL: ["search_legal_documents"],
        QueryType.CONTEXTUAL: ["find_related_documents", "search_legal_documents"],
        QueryType.METADATA_SEARCH: ["search_document_metadata", "search_legal_documents"],
    }
    
    # Mapping giữa Intent và tools
    INTENT_TO_TOOLS = {
        Intent.LOOKUP: ["search_legal_documents", "get_specific_article"],
        Intent.COMPARE: ["search_legal_documents", "find_related_documents"],
        Intent.EXPLAIN: ["search_legal_documents", "find_cross_references"],
        Intent.VERIFY: ["search_legal_documents", "get_specific_article"],
        Intent.CALCULATE: [],  # Không cần search, dùng LLM để tính
        Intent.DEFINE: ["search_legal_documents", "get_specific_article"],
    }
    
    def __init__(self):
        pass
    
    def route(self, analysis: QueryAnalysisResult) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Route query đến tools phù hợp
        Args:
            analysis: QueryAnalysisResult từ QueryAnalyzer
        Returns:
            List các tuple (tool_name, tool_input) theo thứ tự ưu tiên
        """
        logger.info(f"[Router] Routing query: type={analysis.query_type}, intent={analysis.intent}")
        
        # 1. Xác định tools dựa trên QueryType
        tools_by_type = self.QUERY_TYPE_TO_TOOLS.get(analysis.query_type, [])
        
        # 2. Xác định tools dựa trên Intent
        tools_by_intent = self.INTENT_TO_TOOLS.get(analysis.intent, [])
        
        # 3. Merge và loại bỏ duplicate
        selected_tools = self._merge_and_prioritize(tools_by_type, tools_by_intent)
        
        # 4. Build tool inputs dựa trên analysis result
        tool_calls = self._build_tool_inputs(analysis, selected_tools)
        
        logger.info(f"[Router] Selected tools: {[t[0] for t in tool_calls]}")
        return tool_calls
    def _merge_and_prioritize(
        self, tools_by_type: List[str], tools_by_intent: List[str]
    ) -> List[str]:
        """
        Merge tools từ QueryType và Intent, xóa duplicate, và sắp xếp theo ưu tiên
        Priority order:
        1. Tools từ QueryType (thường là primary)
        2. Tools từ Intent (bổ sung)
        """
        # Preserve order while removing duplicates
        seen = set()
        merged = []
        
        for tool in tools_by_type + tools_by_intent:
            if tool not in seen:
                merged.append(tool)
                seen.add(tool)
        
        return merged
    
    def _build_tool_inputs(
        self, analysis: QueryAnalysisResult, selected_tools: List[str]
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Build input parameters cho từng tool dựa trên analysis result
        
        Nếu có multiple extracted_blocks, có thể gọi cùng một tool multiple times
        (1 lần cho mỗi block)
         
        Returns:
            List các tuple (tool_name, tool_input)
        """
        tool_inputs = []
        
        for tool_name in selected_tools:
            if tool_name == "get_specific_article" and len(analysis.extracted_blocks) > 0:
                # Gọi get_specific_article cho mỗi block
                for block in analysis.extracted_blocks:
                    tool_input = self._build_input_get_specific_article_for_block(block)
                    if tool_input is not None:
                        tool_inputs.append((tool_name, tool_input))
            else:
                tool_input = self._build_input_for_tool(tool_name, analysis)
                if tool_input is not None:
                    tool_inputs.append((tool_name, tool_input))
        
        return tool_inputs
    
    def _build_input_for_tool(
        self, tool_name: str, analysis: QueryAnalysisResult
    ) -> Dict[str, Any]:
        """
        Build input cho một tool cụ thể
        """
        if tool_name == "search_legal_documents":
            return self._build_input_search_legal_documents(analysis)
        
        elif tool_name == "search_document_metadata":
            return self._build_input_search_document_metadata(analysis)
        
        elif tool_name == "get_specific_article":
            return self._build_input_get_specific_article(analysis)
        
        elif tool_name == "find_related_documents":
            return self._build_input_find_related_documents(analysis)
        
        elif tool_name == "find_cross_references":
            return self._build_input_find_cross_references(analysis)
        
        return None
    
    def _build_input_search_legal_documents(
        self, analysis: QueryAnalysisResult
    ) -> Dict[str, Any]:
        """Build input cho search_legal_documents"""
        return {
            "query": analysis.original_query,
            "top_k": 5,
            "filter_by_type": ["dieu", "khoan", "diem"],
        }
    
    def _build_input_search_document_metadata(
        self, analysis: QueryAnalysisResult
    ) -> Dict[str, Any]:
        """Build input cho search_document_metadata"""
        # Ưu tiên lấy loại văn bản từ document_types (nếu có)
        doc_type = None
        if analysis.document_types:
            doc_type = analysis.document_types[0]
        
        # Fallback: lấy document_name từ block đầu tiên
        doc_name = None
        if not doc_type and analysis.extracted_blocks:
            doc_name = analysis.extracted_blocks[0].document_name
        
        # Nếu không có gì, skip tool này
        if not doc_type and not doc_name:
            return None
        
        return {
            "doc_type": doc_type,
            "org_unit": None,
        }
    
    def _build_input_get_specific_article(
        self, analysis: QueryAnalysisResult
    ) -> Dict[str, Any]:
        """Build input cho get_specific_article (deprecated - sử dụng _build_input_get_specific_article_for_block)"""
        return None
    
    def _build_input_get_specific_article_for_block(self, block) -> Dict[str, Any]:
        """Build input cho get_specific_article cho 1 block cụ thể"""
        # Chỉ gọi nếu có dieu trong block
        if block.dieu is None:
            return None
        
        return {
            "article_block": block,
        }
    
    def _build_input_find_related_documents(
        self, analysis: QueryAnalysisResult
    ) -> Dict[str, Any]:
        """Build input cho find_related_documents"""
        # Lấy document_name từ block đầu tiên
        doc_name = None
        if analysis.extracted_blocks:
            doc_name = analysis.extracted_blocks[0].document_name
        
        return {
            "doc_id": doc_name,
            "relation_type": None,
        }
    
    def _build_input_find_cross_references(
        self, analysis: QueryAnalysisResult
    ) -> Dict[str, Any]:
        """Build input cho find_cross_references"""
        # Lấy block đầu tiên
        if not analysis.extracted_blocks or analysis.extracted_blocks[0].dieu is None:
            return None
        
        block = analysis.extracted_blocks[0]
        return {
            "article_block": block,
        }
    
    def should_skip_semantic_search(self, analysis: QueryAnalysisResult) -> bool:
        """
        Xác định có cần skip semantic search không
        (Nếu đã có specific lookup, không cần search chung)
        """
        return (
            analysis.query_type == QueryType.SPECIFIC_LOOKUP and
            len(analysis.extracted_blocks) > 0
        )
    
    def get_tool_explanation(self, tool_name: str) -> str:
        """Lấy giải thích về tool"""
        explanations = {
            "search_legal_documents": "Tìm kiếm tài liệu bằng vector similarity",
            "search_document_metadata": "Tìm kiếm metadata của tài liệu",
            "get_specific_article": "Lấy nội dung điều khoản cụ thể",
            "find_related_documents": "Tìm tài liệu liên quan (sửa đổi, bổ sung, v.v.)",
            "find_cross_references": "Tìm các tham chiếu chéo",
        }
        return explanations.get(tool_name, "Tool không xác định")
