"""
Configuration loader cho reranking pipeline.
"""
from pathlib import Path
from typing import Any, Dict, Optional
from src.core.config import BaseConfig


class RerankerConfig(BaseConfig):
    """Configuration class cho reranking pipeline."""
    
    def _get_root_dir(self) -> Path:
        """Lấy root directory (3 levels up từ rerank/config.py)."""
        return Path(__file__).resolve().parents[3]
    
    def _get_default_config_path(self) -> Path:
        """Lấy default config path."""
        return self.root_dir / "configs" / "rerank_config.yaml"
    
    def get_reranker_params(self) -> Dict[str, Any]:
        """Lấy reranker parameters."""
        reranker_config = self.config.get('reranker', {})
        model_dir = reranker_config.get('model_dir')
        
        if model_dir is None:
            model_dir = str(self.root_dir / "models" / "mmarco-mMiniLMv2-L12-H384-v1")
        else:
            model_path = Path(model_dir)
            if not model_path.is_absolute():
                model_dir = str(self.root_dir / model_dir)
            else:
                model_dir = str(model_path)
        
        return {
            'model_dir': model_dir,
            'device': reranker_config.get('device', 'cpu'),
            'batch_size': reranker_config.get('batch_size', 32),
            'normalize_scores': reranker_config.get('normalize_scores', True),
            'max_length': reranker_config.get('max_length', 512),
        }
    
    @staticmethod
    def get_default_config() -> 'RerankerConfig':
        """Lấy default configuration."""
        return RerankerConfig()
