"""
Unit tests cho Legal QA Agent
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.agent.llm_query_analyzer import LLMQueryAnalyzer
from src.agent.query_analyzer import QueryAnalyzer
from src.agent.router import ToolRouter
from src.agent.schemas import (
    QueryType, Intent, QueryAnalysisResult, ArticleBlock
)


class TestQueryAnalyzer:
    """Test cases cho QueryAnalyzer (Regex version - fallback)"""
    
    @pytest.fixture
    def analyzer(self):
        return QueryAnalyzer()
    
    def test_detect_specific_article(self, analyzer):
        """Test phát hiện câu hỏi về điều cụ thể"""
        query = "Điều 5 của Luật 102/2017 nói gì?"
        result = analyzer.analyze(query)
        
        assert result.query_type == QueryType.SPECIFIC_LOOKUP
        assert 5 in result.article_numbers
        assert "102/2017" in result.document_names
    
    def test_detect_comparison(self, analyzer):
        """Test phát hiện câu hỏi so sánh"""
        query = "Khác biệt giữa Luật A và Luật B là gì?"
        result = analyzer.analyze(query)
        
        assert result.query_type == QueryType.COMPARATIVE
    
    def test_detect_procedural(self, analyzer):
        """Test phát hiện câu hỏi về quy trình"""
        query = "Quy trình cấp phép là như thế nào?"
        result = analyzer.analyze(query)
        
        assert result.query_type == QueryType.PROCEDURAL
    
    def test_extract_article_numbers(self, analyzer):
        """Test trích xuất số điều"""
        query = "Điều 1, điều 2 và khoản 3 nói gì?"
        result = analyzer.analyze(query)
        
        assert 1 in result.article_numbers
        assert 2 in result.article_numbers
        assert 3 in result.article_numbers
    
    def test_extract_keywords(self, analyzer):
        """Test trích xuất từ khóa"""
        query = "Quy định về bảo hiểm xã hội và bảo hiểm y tế là gì?"
        result = analyzer.analyze(query)
        
        assert len(result.keywords) > 0
        # Should contain 'bảo hiểm'
        assert any('bảo' in kw or 'hiểm' in kw for kw in result.keywords)
    
    def test_confidence_calculation(self, analyzer):
        """Test tính toán độ tin cậy"""
        query1 = "Gì?"
        result1 = analyzer.analyze(query1)
        
        query2 = "Điều 5 của Luật 102/2017 nói gì?"
        result2 = analyzer.analyze(query2)
        
        # Query 2 should have higher confidence
        assert result2.confidence > result1.confidence


class TestToolRouter:
    """Test cases cho ToolRouter"""
    
    @pytest.fixture
    def router(self):
        return ToolRouter()
    
    def test_route_specific_lookup(self, router):
        """Test routing cho SPECIFIC_LOOKUP"""
        analysis = QueryAnalysisResult(
            original_query="Điều 5 là gì?",
            query_type=QueryType.SPECIFIC_LOOKUP,
            intent=Intent.LOOKUP,
            extracted_blocks=[
                ArticleBlock(
                    dieu=5,
                    khoan=None,
                    diem=None,
                    chuong=None,
                    document_name="Luật 102/2017",
                )
            ],
        )
        
        tool_calls = router.route(analysis)
        
        # Should prioritize get_specific_article
        assert len(tool_calls) > 0
        assert tool_calls[0][0] == "get_specific_article"
    
    def test_route_semantic_search(self, router):
        """Test routing cho SEMANTIC_SEARCH"""
        analysis = QueryAnalysisResult(
            original_query="Quy định về bảo hiểm là gì?",
            query_type=QueryType.SEMANTIC_SEARCH,
            intent=Intent.LOOKUP,
            extracted_blocks=[],
        )
        
        tool_calls = router.route(analysis)
        
        # Should use search_legal_documents
        assert len(tool_calls) > 0
        assert tool_calls[0][0] == "search_legal_documents"
    
    def test_route_comparative(self, router):
        """Test routing cho COMPARATIVE"""
        analysis = QueryAnalysisResult(
            original_query="Khác biệt giữa A và B?",
            query_type=QueryType.COMPARATIVE,
            intent=Intent.COMPARE,
            extracted_blocks=[],
        )
        
        tool_calls = router.route(analysis)
        
        # Should include search_legal_documents
        assert any(t[0] == "search_legal_documents" for t in tool_calls)
    
    def test_build_input_search_legal_documents(self, router):
        """Test build input cho search_legal_documents"""
        analysis = QueryAnalysisResult(
            original_query="Bảo hiểm xã hội?",
            query_type=QueryType.SEMANTIC_SEARCH,
            intent=Intent.LOOKUP,
            extracted_blocks=[],
        )
        
        tool_input = router._build_input_search_legal_documents(analysis)
        
        assert "query" in tool_input
        assert "top_k" in tool_input
        assert tool_input["query"] == analysis.original_query
    
    def test_build_input_get_specific_article_no_numbers(self, router):
        """Test build input khi không có article numbers"""
        analysis = QueryAnalysisResult(
            original_query="Gì?",
            query_type=QueryType.SEMANTIC_SEARCH,
            intent=Intent.LOOKUP,
            extracted_blocks=[],
        )
        tool_input = router._build_input_get_specific_article(analysis)
        
        # Should return None nếu không có article numbers
        assert tool_input is None


class TestQueryAnalyzerEdgeCases:
    """Test cases cho edge cases"""
    
    @pytest.fixture
    def analyzer(self):
        return QueryAnalyzer()
    
    def test_empty_query(self, analyzer):
        """Test với query rỗng"""
        result = analyzer.analyze("")
        
        assert result.original_query == ""
        assert result.query_type == QueryType.SEMANTIC_SEARCH
    
    def test_vietnamese_accents(self, analyzer):
        """Test với dấu tiếng Việt"""
        query = "Quy định về bảo hiểm là gì?"
        result = analyzer.analyze(query)
        
        assert len(result.keywords) > 0
    
    def test_multiple_documents(self, analyzer):
        """Test với nhiều tài liệu"""
        query = "So sánh Luật 102/2017, Nghị định 35/2024 và Quyết định 91/2015"
        result = analyzer.analyze(query)
        
        assert len(result.document_names) >= 3
        assert result.query_type == QueryType.COMPARATIVE


def run_tests():
    """Chạy các tests"""
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()
