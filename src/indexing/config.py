"""
Configuration loader cho indexing pipeline.
"""
from pathlib import Path
from typing import Any, Dict, Optional
from src.core.config import BaseConfig


class IndexingConfig(BaseConfig):
    """Configuration class cho indexing pipeline."""
    
    def _get_root_dir(self) -> Path:
        """Get root directory (2 levels up từ indexing/config.py)."""
        return Path(__file__).resolve().parents[2]
    
    def _get_default_config_path(self) -> Path:
        """Get default config path."""
        return self.root_dir / "configs" / "indexing_config.yaml"
    
    def get_chunker_params(self) -> Dict[str, Any]:
        """Get chunker parameters."""
        chunking_config = self.config.get('chunking', {})
        params = chunking_config.get('params', {})
        if not isinstance(params, dict):
            raise ValueError("Chunker params should be a dictionary")
        return {
            'strategy': chunking_config.get('strategy', 'fixed_size'),
            **params
        }
    
    @staticmethod
    def get_default_config() -> 'IndexingConfig':
        """Get default configuration."""
        return IndexingConfig()
