"""
LLM Configuration và Initialization

Cung cấp helper functions để khởi tạo các LLM models khác nhau
"""

import os
import logging
from typing import Optional, Dict
from langchain_core.language_model import LLM


logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory để tạo LLM instances"""
    
    @staticmethod
    def create_groq_llm(
        model_name: str = "mixtral-8x7b-32768",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        api_key: Optional[str] = None,
    ) -> LLM:
        """
        Tạo Groq LLM instance
        
        Args:
            model_name: Model name từ Groq
            temperature: Temperature (0-1)
            max_tokens: Max tokens để generate
            api_key: Groq API key (mặc định từ GROQ_API_KEY env var)
        
        Returns:
            ChatGroq instance
        """
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            raise ImportError("Please install langchain-groq: pip install langchain-groq")
        
        if not api_key:
            api_key = os.getenv("GROQ_API_KEY")
        
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        
        logger.info(f"[LLM] Creating Groq LLM: {model_name}")
        
        return ChatGroq(
            api_key=api_key,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    
    @staticmethod
    def create_openai_llm(
        model_name: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        api_key: Optional[str] = None,
    ) -> LLM:
        """
        Tạo OpenAI LLM instance
        
        Args:
            model_name: Model name từ OpenAI
            temperature: Temperature (0-1)
            max_tokens: Max tokens để generate
            api_key: OpenAI API key (mặc định từ OPENAI_API_KEY env var)
        
        Returns:
            ChatOpenAI instance
        """
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError("Please install langchain-openai: pip install langchain-openai")
        
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        logger.info(f"[LLM] Creating OpenAI LLM: {model_name}")
        
        return ChatOpenAI(
            api_key=api_key,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    
    @staticmethod
    def create_ollama_llm(
        model_name: str = "llama2",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
    ) -> LLM:
        """
        Tạo Ollama LLM instance (local)
        
        Args:
            model_name: Model name từ Ollama
            base_url: Ollama server URL
            temperature: Temperature (0-1)
        
        Returns:
            OllamaLLM instance
        """
        try:
            from langchain_ollama import OllamaLLM
        except ImportError:
            raise ImportError("Please install langchain-ollama: pip install langchain-ollama")
        
        logger.info(f"[LLM] Creating Ollama LLM: {model_name}")
        
        return OllamaLLM(
            model=model_name,
            base_url=base_url,
            temperature=temperature,
        )
    
    @staticmethod
    def create_fake_llm() -> LLM:
        """
        Tạo Fake LLM instance cho testing
        
        Returns:
            FakeListLLM instance
        """
        from langchain_core.language_model import LLM
        from langchain_core.outputs import Generation, LLMResult
        
        logger.info("[LLM] Creating Fake LLM for testing")
        
        class FakeLLM(LLM):
            """Fake LLM cho testing"""
            
            @property
            def _llm_type(self) -> str:
                return "fake"
            
            def _generate(self, prompts, stop=None, **kwargs):
                return LLMResult(
                    generations=[[Generation(text=f"Fake response for: {prompts[0][:50]}...")]]
                )
        
        return FakeLLM()


class LLMConfig:
    """Configuration cho LLM"""
    
    # Groq models
    GROQ_MODELS = {
        "mixtral": "mixtral-8x7b-32768",
        "llama": "llama-3.3-70b-versatile",
        "gemma": "gemma2-9b-it",
    }
    
    # OpenAI models
    OPENAI_MODELS = {
        "gpt-4": "gpt-4",
        "gpt-4-turbo": "gpt-4-turbo-preview",
        "gpt-3.5": "gpt-3.5-turbo",
    }
    
    # Default configs
    DEFAULT_CONFIGS = {
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    
    @classmethod
    def get_model_info(cls, provider: str = "groq") -> Dict[str, str]:
        """Lấy danh sách models cho provider"""
        if provider.lower() == "groq":
            return cls.GROQ_MODELS
        elif provider.lower() == "openai":
            return cls.OPENAI_MODELS
        else:
            raise ValueError(f"Unknown provider: {provider}")


def create_llm(
    provider: str = "groq",
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs
) -> LLM:
    """
    Helper function để tạo LLM instance
    
    Args:
        provider: "groq", "openai", "ollama", "fake"
        model: Model name (nếu None, dùng default)
        temperature: Temperature
        max_tokens: Max tokens
        **kwargs: Additional arguments
    
    Returns:
        LLM instance
    """
    provider = provider.lower()
    
    if provider == "groq":
        if model is None:
            model = LLMConfig.GROQ_MODELS["mixtral"]
        return LLMFactory.create_groq_llm(
            model_name=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    elif provider == "openai":
        if model is None:
            model = "gpt-4"
        return LLMFactory.create_openai_llm(
            model_name=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    elif provider == "ollama":
        if model is None:
            model = "llama2"
        return LLMFactory.create_ollama_llm(
            model_name=model,
            temperature=temperature,
            **kwargs
        )
    
    elif provider == "fake":
        return LLMFactory.create_fake_llm()
    
    else:
        raise ValueError(f"Unknown provider: {provider}")
