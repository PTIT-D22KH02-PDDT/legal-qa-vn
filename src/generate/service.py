"""
Generate Service - sử dụng LLM để sinh văn bản
"""

import logging
from typing import Optional

from src.api.remote_client import RemoteAPIClient

logger = logging.getLogger(__name__)


class GenerateService:
    """
    Service để generate text từ LLM model.
    
    Có thể sử dụng remote API (qua ngrok) hoặc local model.
    """
    
    def __init__(self, api_client: Optional[RemoteAPIClient] = None):
        """
        Args:
            api_client: RemoteAPIClient instance. Nếu None, dùng local model (future enhancement)
        """
        self.api_client = api_client
        
        if self.api_client:
            logger.info("GenerateService initialized with remote API")
        else:
            logger.info("GenerateService initialized (local model not implemented yet)")
    
    def generate(
        self,
        prompt: str,
        max_length: int = 200,
        temperature: float = 0.7,
        top_k: int = 50,
        top_p: float = 0.95,
    ) -> str:
        """
        Generate text từ prompt.
        
        Args:
            prompt: Input prompt
            max_length: Maximum length của generated text
            temperature: Sampling temperature (0.0 - 2.0)
                - Gần 0: Deterministic, lặp lại
                - ~1.0: Balanced
                - > 1.0: Creative, random
            top_k: Keep top-k tokens
            top_p: Nucleus sampling threshold
        
        Returns:
            Generated text
        
        Raises:
            RuntimeError: Nếu không có API client và local model không available
            APIError: Nếu gọi remote API thất bại
        """
        if not self.api_client:
            raise RuntimeError("No API client configured. Local model generation not implemented yet.")
        
        if not prompt or len(prompt.strip()) == 0:
            raise ValueError("prompt must not be empty")
        
        if max_length <= 0:
            raise ValueError("max_length must be positive")
        
        if not (0.0 <= temperature <= 2.0):
            logger.warning(f"temperature {temperature} outside recommended range [0.0, 2.0]")
        
        logger.debug(f"Generating with prompt: {prompt[:50]}...")
        
        try:
            answer = self.api_client.generate(
                prompt=prompt,
                max_length=max_length,
                temperature=temperature
            )
            
            logger.debug(f"Generated text length: {len(answer)}")
            return answer
        
        except Exception as e:
            logger.error(f"Failed to generate: {str(e)}")
            raise
    
    def generate_answer(
        self,
        query: str,
        context: str,
        max_length: int = 256,
        temperature: float = 0.5,
    ) -> str:
        """
        Generate answer từ query + context (common pattern trong RAG).
        
        Args:
            query: User question
            context: Retrieved context/documents
            max_length: Maximum length
            temperature: Sampling temperature
        
        Returns:
            Generated answer
        """
        # Format prompt theo RAG pattern
        prompt = self._format_rag_prompt(query, context)
        
        return self.generate(
            prompt=prompt,
            max_length=max_length,
            temperature=temperature
        )
    
    def generate_summary(
        self,
        text: str,
        max_length: int = 150,
        temperature: float = 0.3,
    ) -> str:
        """
        Generate summary of text.
        
        Args:
            text: Text to summarize
            max_length: Maximum summary length
            temperature: Low temperature for consistent summaries
        
        Returns:
            Summary
        """
        prompt = f"Vui lòng tóm tắt đoạn text sau:\n{text}\n\nTóm tắt:"
        
        return self.generate(
            prompt=prompt,
            max_length=max_length,
            temperature=temperature
        )
    
    def generate_question(
        self,
        text: str,
        max_length: int = 100,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate question từ text.
        
        Args:
            text: Text to generate question from
            max_length: Maximum question length
            temperature: Sampling temperature
        
        Returns:
            Generated question
        """
        prompt = f"Tạo một câu hỏi từ đoạn text sau:\n{text}\n\nCâu hỏi:"
        
        return self.generate(
            prompt=prompt,
            max_length=max_length,
            temperature=temperature
        )
    
    @staticmethod
    def _format_rag_prompt(query: str, context: str) -> str:
        """
        Format prompt cho RAG (Retrieval-Augmented Generation) pattern.
        
        Args:
            query: User query
            context: Retrieved context
        
        Returns:
            Formatted prompt
        """
        prompt = f"""Dựa trên thông tin sau, vui lòng trả lời câu hỏi.

Thông tin:
{context}

Câu hỏi: {query}

Trả lời:"""
        return prompt
    
    def health_check(self) -> bool:
        """
        Check nếu API server available.
        
        Returns:
            True nếu khỏe, False otherwise
        """
        if not self.api_client:
            return False
        
        return self.api_client.health_check()
