"""
Configuration loader cho retrieval pipeline.
"""
from pathlib import Path
from typing import Any, Dict, Optional, List
from src.core.config import BaseConfig


class RetrievalConfig(BaseConfig):
    """Configuration class cho retrieval pipeline."""
    
    def _get_root_dir(self) -> Path:
        """Get root directory (3 levels up từ search/retrieval/config.py)."""
        return Path(__file__).resolve().parents[3]
    
    def _get_default_config_path(self) -> Path:
        """Get default config path."""
        return self.root_dir / "configs" / "retrieval_config.yaml"
    
    def get_retrieval_params(self) -> Dict[str, Any]:
        """Get retrieval-specific parameters."""
        retrieval_config = self.config.get('retrieval', {})
        
        return {
            'default_top_k': retrieval_config.get('default_top_k', 5),
            'score_threshold': retrieval_config.get('score_threshold', None),
            'default_filter_types': retrieval_config.get('default_filter_types', None),
        }
    
    @staticmethod
    def get_default_config() -> 'RetrievalConfig':
        """Get default configuration."""
        return RetrievalConfig()
