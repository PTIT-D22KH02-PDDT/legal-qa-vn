"""
LLM-based Query Analyzer for Vietnamese Legal QA
Sử dụng LLM (Groq) thay vì regex để phân tích câu hỏi pháp luật
"""
import json
import logging
from .llm_prompt_instruction import get_llm_prompt
from .schemas import (
    QueryAnalysisResult,
    ArticleBlock,
    QueryType,
    Intent,
)
from .llms import LLMGroq

logger = logging.getLogger(__name__)


class LLMQueryAnalyzer:
    """
    Analyzer sử dụng LLM để phân tích câu hỏi pháp luật
    
    Tính năng:
    - Phân loại query type (SPECIFIC_LOOKUP, SEMANTIC_SEARCH, ...)
    - Xác định intent (LOOKUP, COMPARE, EXPLAIN, ...)
    - Trích xuất entities (Điều, Khoản, Điểm, Chương)
    - Trả về structured JSON
    - Fallback to regex nếu LLM fail
    """
    def __init__(
        self,
        llm=None,
        fallback_analyzer=None,
        api_key=None,
    ):
        """
        Initialize LLMQueryAnalyzer
        
        Args:
            llm: LangChain LLM instance (default: Groq)
            fallback_analyzer: Regex analyzer để fallback
            api_key: API key for Groq LLM
        """
        if llm is None:
            self.llm = LLMGroq(api_key=api_key)
        else:
            self.llm = llm
        
        self.fallback_analyzer = fallback_analyzer
    def analyze(self, query: str) -> QueryAnalysisResult:
        """
        Phân tích query sử dụng LLM
        Args:
            query: User's query string
        Returns:
            QueryAnalysisResult với structured entities
        """
        try:
            # Lấy prompt từ llm_prompt_instruction
            system_prompt, user_prompt = get_llm_prompt(query)
            
            # Call LLM
            response_text = self._call_llm(system_prompt, user_prompt)
            
            # Parse JSON response
            parsed = self._parse_json(response_text)
            
            # Validate & convert to QueryAnalysisResult
            result = self._validate_and_convert(parsed, query)
            
            logger.debug(f"Query analyzed: {query[:50]}... → {result.query_type}")
            return result
        
        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}")
            if self.fallback_analyzer:
                return self.fallback_analyzer.analyze(query)
            raise
    
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Gọi LLM với prompts
        Args:
            system_prompt: System instruction
            user_prompt: User prompt với query
        Returns:
            LLM response text
        """
        # Pass model_name để dùng config model (llama-3.1-8b-instant)
        response = self.llm.ask(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            model_name="llama-3.1-8b-instant",  # Use fast model for query analysis
            temperature=0.0  # Deterministic for entity extraction
        )
        return response
    
    def _parse_json(self, response_text: str) -> dict:
        """
        Parse JSON từ LLM response
        Args:
            response_text: Raw response từ LLM
        Returns:
            Parsed JSON dict
        Raises:
            ValueError: Nếu parse fail
        """
        try:
            # Thử parse trực tiếp
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Thử extract JSON block
            import re
            match = re.search(r'\{[\s\S]*\}', response_text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            
            raise ValueError(f"Could not parse JSON from response: {response_text[:200]}")
    
    def _validate_and_convert(self, parsed_dict: dict, original_query: str) -> QueryAnalysisResult:
        """
        Validate parsed JSON và convert sang QueryAnalysisResult
        Args:
            parsed_dict: Parsed JSON từ LLM
            original_query: Original query string
        Returns:
            QueryAnalysisResult
        Raises:
            ValueError: Nếu validation fail
        """
        try:
            # Parse article blocks
            article_blocks = []
            for block in parsed_dict.get("extracted_blocks", []):
                article_block = ArticleBlock(
                    dieu=block.get("dieu"),
                    khoan=block.get("khoan"),
                    diem=block.get("diem"),
                    chuong=block.get("chuong"),
                    document_name=block.get("document_name"),
                )
                article_blocks.append(article_block)
            
            # Create QueryAnalysisResult
            result = QueryAnalysisResult(
                original_query=original_query,
                query_type=QueryType(parsed_dict.get("query_type", "semantic")),
                intent=Intent(parsed_dict.get("intent", "lookup")),
                extracted_blocks=article_blocks,
                keywords=parsed_dict.get("keywords", []),
                confidence=float(parsed_dict.get("confidence", 0.5)),
                reasoning=parsed_dict.get("reasoning", ""),
                requires_metadata_search=parsed_dict.get("requires_metadata_search", False),
                requires_relationship_check=parsed_dict.get("requires_relationship_check", False),
            )
            
            return result
        
        except Exception as e:
            raise ValueError(f"Failed to validate response: {e}, response was: {parsed_dict}")
