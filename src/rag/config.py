"""Configuration for RAG Pipeline"""

from typing import Optional
from pathlib import Path
import yaml
from pydantic import BaseModel


class RAGConfig(BaseModel):
    """
    Configuration cho RAG Pipeline.
    
    RAG = Retrieval-Augmented Generation
    Kết hợp retrieval (tìm kiếm khoá khác liên quan) 
    + generation (sinh câu trả lời dựa trên context)
    
    Có thể load từ YAML file hoặc khởi tạo trực tiếp.
    """
    
    # Search parameters
    retrieval_top_k: int = 10  # Số documents lấy từ vector search trước khi rerank
    rerank_top_k: int = 5      # Số documents cuối cùng dùng làm context
    use_rerank: bool = True    # Sử dụng reranking hay không
    
    # Context formatting
    context_separator: str = "\n---\n"  # Separator giữa các documents
    max_context_length: int = 3000      # Max length của context
    
    # Generate parameters
    max_answer_length: int = 1000       # Max length của generated answer
    temperature: float = 0.3            # Temperature khi generate
    top_k: int = 30                     # Top-k tokens
    top_p: float = 0.85                 # Top-p nucleus sampling
    
    # Prompt files (loaded from external files)
    system_prompt_file: str = "configs/prompts/system_prompt.txt"
    answer_prompt_file: str = "configs/prompts/answer_prompt.txt"
    
    # API settings
    use_remote_api: bool = False  # Sử dụng remote API
    
    class Config:
        # Allow arbitrary types
        arbitrary_types_allowed = True
    
    @staticmethod
    def from_yaml(yaml_path: str = "configs/rag_config.yaml") -> "RAGConfig":
        """
        Load config từ YAML file.
        
        Args:
            yaml_path: Đường dẫn tới YAML config file
        
        Returns:
            RAGConfig instance
        """
        yaml_file = Path(yaml_path)
        
        if not yaml_file.exists():
            raise FileNotFoundError(f"Config file not found: {yaml_path}")
        
        with open(yaml_file, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f) or {}
        
        return RAGConfig(**config_dict)
    
    def load_prompts(self) -> tuple:
        """
        Load system prompt và answer prompt từ files.
        
        Returns:
            Tuple[system_prompt, answer_prompt]
        
        Raises:
            FileNotFoundError: Nếu prompt files không tồn tại
        """
        system_prompt_path = Path(self.system_prompt_file)
        answer_prompt_path = Path(self.answer_prompt_file)
        
        if not system_prompt_path.exists():
            raise FileNotFoundError(f"System prompt file not found: {self.system_prompt_file}")
        
        if not answer_prompt_path.exists():
            raise FileNotFoundError(f"Answer prompt file not found: {self.answer_prompt_file}")
        
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read().strip()
        
        with open(answer_prompt_path, 'r', encoding='utf-8') as f:
            answer_prompt = f.read().strip()
        
        return system_prompt, answer_prompt
