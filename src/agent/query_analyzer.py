"""
Query Analyzer - Phân tích và phân loại câu hỏi từ người dùng
"""

import re
import logging
from typing import List, Set, Tuple
from .schemas import QueryType, Intent, QueryAnalysisResult


logger = logging.getLogger(__name__)


class QueryAnalyzer:
    """
    Phân tích câu hỏi để:
    - Phân loại loại câu hỏi
    - Trích xuất entities (số điều, tên văn bản, v.v.)
    - Xác định intent
    - Gợi ý tools cần sử dụng
    """
    
    # Các pattern để detect loại câu hỏi
    SPECIFIC_ARTICLE_PATTERNS = [
        r'điều\s+(\d+)',                          # "Điều 5"
        r'khoản\s+(\d+)',                         # "Khoản 1"
        r'điểm\s+([a-z])',                        # "Điểm a"
        r'điều\s+(\d+)\s+khoản\s+(\d+)',         # "Điều 5 Khoản 1"
    ]
    
    DOCUMENT_PATTERNS = [
        r'luật\s+([\w\s/\d]+)',                   # "Luật 102/2017"
        r'nghị định\s+([\w\s/\d]+)',             # "Nghị định 123/2017"
        r'quyết định\s+([\w\s/\d]+)',            # "Quyết định 456/2017"
        r'thông tư\s+([\w\s/\d]+)',              # "Thông tư 789/2017"
        r'qh15|qh14|qh13',                        # "QH15", "QH14"
    ]
    
    COMPARISON_KEYWORDS = [
        'khác', 'khác biệt', 'khác nhau', 'so sánh', 'giống', 'giống nhau',
        'giữa', 'và', 'hay', 'hơn', 'ít hơn', 'nhiều hơn'
    ]
    
    PROCEDURAL_KEYWORDS = [
        'quy trình', 'cách', 'làm sao', 'thế nào', 'bước', 'trình tự',
        'yêu cầu', 'điều kiện', 'tiến hành', 'thực hiện', 'áp dụng'
    ]
    
    CONTEXTUAL_KEYWORDS = [
        'hiện hành', 'hủy bỏ', 'bãi bỏ', 'sửa đổi', 'bổ sung', 'thay thế',
        'còn hiệu lực', 'đã hết hiệu lực', 'liên quan', 'mối quan hệ',
        'thay đổi', 'chuyên đề', 'tương tự'
    ]
    
    METADATA_KEYWORDS = [
        'cơ quan nào', 'ban hành', 'năm', 'ngày', 'loại', 'nào', 'cái nào',
        'danh sách', 'có bao nhiêu'
    ]
    
    LOOKUP_KEYWORDS = ['gì', 'là gì', 'cái gì', 'nói gì', 'quy định']
    COMPARE_KEYWORDS = ['khác', 'giống', 'so sánh']
    EXPLAIN_KEYWORDS = ['giải thích', 'tại sao', 'vì sao', 'như thế nào']
    VERIFY_KEYWORDS = ['có phải', 'đúng không', 'có', 'liệu', 'có hay không']
    DEFINE_KEYWORDS = ['định nghĩa', 'là gì']
    
    def __init__(self):
        self.compiled_patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> dict:
        """Compile regex patterns"""
        return {
            'specific_articles': [re.compile(p, re.IGNORECASE) for p in self.SPECIFIC_ARTICLE_PATTERNS],
            'documents': [re.compile(p, re.IGNORECASE) for p in self.DOCUMENT_PATTERNS],
        }
    
    def analyze(self, query: str) -> QueryAnalysisResult:
        """
        Phân tích một câu hỏi 
        Args:
            query: Câu hỏi từ người dùng
        Returns:
            QueryAnalysisResult chứa kết quả phân tích
        """
        query_lower = query.lower()
        # 1. Trích xuất entities
        article_numbers = self._extract_article_numbers(query_lower)
        article_names = self._extract_article_names(query_lower)
        document_types, document_names = self._extract_documents(query_lower)
        keywords = self._extract_keywords(query_lower)
        
        # 2. Phân loại loại câu hỏi
        query_type = self._classify_query_type(
            query_lower, article_numbers, document_types, keywords
        )
        
        # 3. Xác định intent
        intent = self._classify_intent(query_lower, keywords)
        
        # 4. Xác định yêu cầu bổ sung
        requires_metadata_search = query_type == QueryType.METADATA_SEARCH
        requires_relationship_check = query_type == QueryType.CONTEXTUAL
        
        # 5. Tính độ tin cậy
        confidence = self._calculate_confidence(
            article_numbers, document_types, keywords
        )
        
        return QueryAnalysisResult(
            original_query=query,
            query_type=query_type,
            intent=intent,
            article_numbers=article_numbers,
            article_names=article_names,
            document_types=document_types,
            document_names=document_names,
            keywords=keywords,
            requires_metadata_search=requires_metadata_search,
            requires_relationship_check=requires_relationship_check,
            confidence=confidence,
        )
    
    def _extract_article_numbers(self, query: str) -> List[int]:
        """Trích xuất số điều từ câu hỏi"""
        numbers = []
        for pattern in self.compiled_patterns['specific_articles']:
            matches = pattern.findall(query)
            for match in matches:
                if isinstance(match, str) and match.isdigit():
                    numbers.append(int(match))
        return list(set(numbers))  # Remove duplicates
    
    def _extract_article_names(self, query: str) -> List[str]:
        """Trích xuất tên khoản (a, b, c) từ câu hỏi"""
        names = re.findall(r'khoản\s+([a-z]+)', query)
        return list(set(names))
    
    def _extract_documents(self, query: str) -> Tuple[List[str], List[str]]:
        """
        Trích xuất loại và tên tài liệu
        
        Returns:
            (document_types, document_names)
        """
        types = []
        names = []
        
        # Detect loại tài liệu
        doc_type_patterns = {
            'Luật': r'luật\s+',
            'Nghị định': r'nghị định\s+',
            'Quyết định': r'quyết định\s+',
            'Thông tư': r'thông tư\s+',
        }
        
        for doc_type, pattern in doc_type_patterns.items():
            if re.search(pattern, query):
                types.append(doc_type)
        
        # Trích xuất tên tài liệu (ví dụ: "102/2017", "35/2024", v.v.)
        for pattern in self.compiled_patterns['documents']:
            matches = pattern.findall(query)
            names.extend(matches)
        
        return list(set(types)), list(set(names))
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Trích xuất các từ khóa chính từ câu hỏi"""
        # Loại bỏ các từ dừng phổ biến
        stop_words = {
            'các', 'cái', 'cái gì', 'gì', 'nào', 'của', 'cơ', 'à', 'ạ', 'ơi',
            'về', 'từ', 'đến', 'với', 'trong', 'theo', 'là', 'có', 'được',
            'trên', 'dưới', 'trước', 'sau', 'không', 'chưa', 'đã', 'sẽ'
        }
        
        # Split và filter
        words = query.split()
        keywords = [
            w.strip('?,.!;:') for w in words
            if w.strip('?,.!;:') not in stop_words and len(w) > 2
        ]
        return list(set(keywords))[:10]  # Tối đa 10 keywords
    
    def _classify_query_type(
        self, query: str, article_numbers: List[int],
        document_types: List[str], keywords: List[str]
    ) -> QueryType:
        """Phân loại loại câu hỏi"""
        
        # 1. Tìm kiếm điều cụ thể
        if article_numbers or any('điều' in kw or 'khoản' in kw for kw in keywords):
            return QueryType.SPECIFIC_LOOKUP
        
        # 2. So sánh
        if any(kw in query for kw in self.COMPARISON_KEYWORDS):
            return QueryType.COMPARATIVE
        
        # 3. Quy trình
        if any(kw in query for kw in self.PROCEDURAL_KEYWORDS):
            return QueryType.PROCEDURAL
        
        # 4. Bối cảnh pháp lý
        if any(kw in query for kw in self.CONTEXTUAL_KEYWORDS):
            return QueryType.CONTEXTUAL
        
        # 5. Tìm metadata
        if any(kw in query for kw in self.METADATA_KEYWORDS):
            return QueryType.METADATA_SEARCH
        
        # 6. Mặc định: tìm kiếm tổng quát
        return QueryType.SEMANTIC_SEARCH
    
    def _classify_intent(self, query: str, keywords: List[str]) -> Intent:
        """Xác định intent của câu hỏi"""
        
        if any(kw in query for kw in self.DEFINE_KEYWORDS):
            return Intent.DEFINE
        
        if any(kw in query for kw in self.COMPARE_KEYWORDS):
            return Intent.COMPARE
        
        if any(kw in query for kw in self.EXPLAIN_KEYWORDS):
            return Intent.EXPLAIN
        
        if any(kw in query for kw in self.VERIFY_KEYWORDS):
            return Intent.VERIFY
        
        if any(kw in query for kw in ['tính', 'bao nhiêu', 'mấy']):
            return Intent.CALCULATE
        
        return Intent.LOOKUP
    
    def _calculate_confidence(
        self, article_numbers: List[int],
        document_types: List[str], keywords: List[str]
    ) -> float:
        """
        Tính độ tin cậy của phân tích
        Dựa trên số lượng entities được trích xuất
        """
        confidence = 0.5  # Base confidence
        
        if article_numbers:
            confidence += 0.15
        if document_types:
            confidence += 0.15
        if len(keywords) >= 3:
            confidence += 0.2
        
        return min(confidence, 1.0)
