"""
Configuration cho API client
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class APIConfig:
    """Configuration từ .env"""
    
    embed_api_url: str = os.getenv("HOST_NAME", "http://localhost:8000") + "/embed"
    rerank_api_url: str = os.getenv("HOST_NAME", "http://localhost:8000") + "/rerank"
    generate_api_url: str = os.getenv("HOST_NAME", "http://localhost:8000") + "/generate"
    api_timeout: int = int(os.getenv("API_TIMEOUT", "120"))
    
    def __post_init__(self):
        """Validate config"""
        if not self.embed_api_url:
            raise ValueError("EMBED_API_URL not set in .env")
        if not self.rerank_api_url:
            raise ValueError("RERANK_API_URL not set in .env")
        if not self.generate_api_url:
            raise ValueError("GENERATE_API_URL not set in .env")
        if self.api_timeout <= 0:
            raise ValueError("API_TIMEOUT must be positive")
    
    @classmethod
    def from_env(cls):
        """Load config từ .env"""
        return cls()
