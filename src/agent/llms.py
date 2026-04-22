"""
Khởi tạo LLM từ các provider khác nhau
"""
import os
import logging
from typing import Optional, Any, List, Dict
from groq import Groq
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, ConfigDict
logger = logging.getLogger(__name__)
class LLMFactory:
    """Factory để tạo LLM instances từ các provider"""
    @staticmethod
    def create_llm(
        provider: str = "groq",
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        timeout: int = 30,
        base_url: Optional[str] = None,
    ):
        """
        Tạo LLM instance từ provider
        Args:
            provider: "groq", "openai", "ollama"
            api_key: API key (nếu None, lấy từ env)
            model_name: Model name
            temperature: Temperature (0-1)
            timeout: Timeout (giây)
            base_url: Base URL (cho ollama)
        Returns:
            LLM instance (Groq, OpenAI, hoặc Ollama client)
        """
        provider = provider.lower()
        
        if provider == "groq":
            return LLMFactory._create_groq(api_key, model_name, temperature, timeout)
        
        elif provider == "openai":
            # return LLMFactory._create_openai(api_key, model_name, temperature, timeout)
            return None
        
        elif provider == "ollama":
            # return LLMFactory._create_ollama(model_name, base_url, temperature)
            return None        
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    @staticmethod
    def _create_groq(api_key: Optional[str]):
        """Tạo Groq LLM instance"""
        if not api_key:
            api_key = os.getenv("GROQ_API_KEY")
        
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment")
        
        
        # Groq không nhận model, temperature trong __init__, chỉ api_key
        return Groq(api_key=api_key)
    
    @staticmethod
    def ask_groq(llm : Groq, user_prompt: str, system_prompt: Optional[str] = None, model_name: Optional[str] = None,
                 temperature: float = 0.0, timeout: int = 30):
        """Gửi prompt đến Groq và nhận response"""
        if not model_name:
            model_name = "llama-3.1-8b-instant"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        
        response = llm.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=1000,
            timeout=timeout
        )
        
        return response.choices[0].message.content

    # @staticmethod
    # def _create_openai(api_key: Optional[str], model_name: Optional[str],
    #                    temperature: float, timeout: int):
    #     """Tạo OpenAI LLM instance"""
    #     try:
    #         from openai import OpenAI
    #     except ImportError:
    #         raise ImportError("Please install openai: pip install openai")
        
    #     if not api_key:
    #         api_key = os.getenv("OPENAI_API_KEY")
        
    #     if not api_key:
    #         raise ValueError("OPENAI_API_KEY not found in environment")
        
    #     if not model_name:
    #         model_name = "gpt-3.5-turbo"
        
    #     logger.info(f"[LLM] Creating OpenAI LLM: {model_name}")
        
    #     return OpenAI(
    #         api_key=api_key,
    #         timeout=timeout,
    #     )
    
    # @staticmethod
    # def _create_ollama(model_name: Optional[str], base_url: Optional[str],
    #                    temperature: float):
    #     """Tạo Ollama LLM instance"""
    #     try:
    #         from ollama import Client
    #     except ImportError:
    #         raise ImportError("Please install ollama: pip install ollama")
        
    #     if not base_url:
    #         base_url = "http://localhost:11434"
        
    #     if not model_name:
    #         model_name = "mistral"
        
    #     logger.info(f"[LLM] Creating Ollama LLM: {model_name} at {base_url}")
        
    #     return Client(host=base_url)


class LLMGroq(BaseChatModel):
    """
    LangChain-compatible Groq LLM wrapper - hỗ trợ tool calling via LangChain agents
    Extends BaseChatModel để hỗ trợ create_tool_calling_agent
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    api_key: Optional[str] = None
    model_name: str = "llama-3.1-8b-instant"
    temperature: float = 0.0
    max_tokens: int = 1000
    groq_client: Optional[Any] = Field(default=None, exclude=True)
    tools: Optional[List[Any]] = Field(default=None, exclude=True)
    
    def __init__(self, api_key: Optional[str] = None, model_name: str = "llama-3.1-8b-instant", **kwargs):
        """Khởi tạo LLMGroq"""
        super().__init__(
            api_key=api_key or os.getenv("GROQ_API_KEY"),
            model_name=model_name,
            **kwargs
        )
    
    def model_post_init(self, __context: Any) -> None:
        """Initialize Groq client after Pydantic validation"""
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment or arguments")
        self.groq_client = Groq(api_key=self.api_key)
    
    def bind_tools(self, tools, **kwargs):
        """
        Bind tools to LLM for LangChain agent support.
        
        Args:
            tools: List of tools from LangChain
            **kwargs: Additional arguments
        
        Returns:
            self (for chaining)
        """
        # Store tools for reference
        self.tools = tools
        logger.debug(f"[LLMGroq] Bound {len(tools)} tools")
        return self
    
    @property
    def _llm_type(self) -> str:
        """Return type of LLM"""
        return "groq"
    
    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        """Generate response from Groq"""
        # Convert LangChain messages to Groq format
        groq_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                groq_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                groq_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                groq_messages.append({"role": "system", "content": msg.content})
            else:
                groq_messages.append({"role": "user", "content": str(msg.content)})
        
        # Call Groq API
        response = self.groq_client.chat.completions.create(
            model=self.model_name,
            messages=groq_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop=stop,
        )
        
        # Convert response to LangChain format
        content = response.choices[0].message.content
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )
    
    def ask(self, user_prompt: str, system_prompt: Optional[str] = None,
            model_name: Optional[str] = None, temperature: Optional[float] = None, timeout: int = 30) -> str:
        """
        Simple interface for asking questions (backward compatibility)
        
        Args:
            user_prompt: User's question
            system_prompt: System instruction
            model_name: Override model name (default: self.model_name)
            temperature: Optional temperature override
            timeout: Timeout (not used with Groq API)
        
        Returns:
            Response text
        """
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=user_prompt))
        
        # Use provided model_name or fall back to instance model_name
        old_model = self.model_name
        if model_name:
            self.model_name = model_name
        
        # Use LangChain's invoke if available, fallback to _generate
        old_temp = self.temperature
        if temperature is not None:
            self.temperature = temperature
        
        result = self._generate(messages)
        # Restore old values
        if temperature is not None:
            self.temperature = old_temp
        if model_name:
            self.model_name = old_model
        
        return result.generations[0].message.content


# Backward compatibility wrapper
class LLMGroqLegacy: 
    """Legacy wrapper - chỉ dùng nếu cần custom ask() behavior"""
    def __init__(self, api_key: Optional[str] = None):
        self.llm = LLMFactory._create_groq(api_key)
    
    def ask(self, user_prompt: str, system_prompt: Optional[str] = None,
            model_name: Optional[str] = "llama-3.1-8b-instant", temperature: float = 0.0,
            timeout: int = 30) -> str:
        """Gửi prompt đến Groq và nhận response"""
        if model_name is None:
            model_name = "llama-3.1-8b-instant"
        return LLMFactory.ask_groq(
            llm=self.llm,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            model_name=model_name,
            temperature=temperature,
            timeout=timeout
        )

def test_groq():
    """Test LLMGroq wrapper"""
    print("[TEST] Testing LLMGroq wrapper...")
    
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment")
        
        llm = LLMGroq(api_key=api_key)
        response = llm.ask(
            user_prompt="What is the capital of France?",
            system_prompt="You are a helpful assistant that answers questions.",
            model_name="llama-3.1-8b-instant",
            temperature=0.0,
            timeout=30
        )
        print("✓ Response received:")
        print(f"  {response}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


def test_groq_llm():
    """Test hàm LLMFactory với Groq"""
    print("[TEST] Testing LLMFactory with Groq...")
    
    try:
        # Tạo LLM instance
        llm = LLMFactory.create_llm(provider="groq")
        print("✓ LLM instance created successfully")
        
        # Test gửi message đơn giản
        print("\n[TEST] Sending test message to Groq...")
        response = llm.chat.completions.create(
             model="llama-3.1-8b-instant",
             messages=[
                {"role": "system", "content": "Extract product review information from the text."},
                {
                    "role": "user",
                    "content": "I bought the UltraSound Headphones last week and I'm really impressed! The noise cancellation is amazing and the battery lasts all day. Sound quality is crisp and clear. I'd give it 4.5 out of 5 stars.",
                },
            ],
            temperature=0.0,
            max_tokens=50
        )
        
        print("✓ Response received:")
        print(f"  {response.choices[0].message.content}")
        print(response)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_groq()
