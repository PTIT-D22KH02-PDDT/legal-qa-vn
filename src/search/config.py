"""
Configuration loader cho search pipeline.
"""
from pathlib import Path
from typing import Any, Dict, Optional
from src.core.config import BaseConfig


class PipelineConfig(BaseConfig):
    """Configuration class cho search pipeline."""
    
    def _get_root_dir(self) -> Path:
        """Lấy root directory (2 levels up từ search/config.py)."""
        return Path(__file__).resolve().parents[2]
    
    def _get_default_config_path(self) -> Path:
        """Lấy default config path."""
        root_dir = self._get_root_dir()
        return root_dir / "configs" / "search_config.yaml"
    
    def get_retrieval_params(self) -> Dict[str, Any]:
        """Lấy retrieval parameters."""
        pipeline_config = self.config.get('pipeline', {})
        retrieval_config = pipeline_config.get('retrieval', {})
        
        return {
            'default_top_k': retrieval_config.get('default_top_k', 10),
            'score_threshold': retrieval_config.get('score_threshold'),
            'default_filter_types': retrieval_config.get('default_filter_types'),
        }
    
    def get_rerank_params(self) -> Dict[str, Any]:
        """Lấy rerank parameters."""
        pipeline_config = self.config.get('pipeline', {})
        rerank_config = pipeline_config.get('rerank', {})
        
        return {
            'enabled': rerank_config.get('enabled', True),
            'top_k': rerank_config.get('top_k', 5),
            'use_cross_encoder': rerank_config.get('use_cross_encoder', True),
        }
    
    def get_reranker_params(self) -> Dict[str, Any]:
        """Lấy reranker model parameters."""
        reranker_config = self.config.get('reranker', {})
        model_dir = reranker_config.get('model_dir')
        
        if model_dir is None:
            model_dir = str(self._get_root_dir() / "models" / "mmarco-mMiniLMv2-L12-H384-v1")
        else:
            model_path = Path(model_dir)
            if not model_path.is_absolute():
                model_dir = str(self._get_root_dir() / model_dir)
            else:
                model_dir = str(model_path)
        
        return {
            'model_dir': model_dir,
            'device': reranker_config.get('device', 'cpu'),
            'batch_size': reranker_config.get('batch_size', 32),
            'normalize_scores': reranker_config.get('normalize_scores', True),
            'max_length': reranker_config.get('max_length', 512),
        }
    
    def get_vector_store_params(self) -> Dict[str, Any]:
        """Lấy vector store parameters."""
        vector_store_config = self.config.get('vector_store', {})
        
        return {
            'collection_name': vector_store_config.get('collection_name', 'legal_documents'),
            'is_persist': vector_store_config.get('is_persist', True),
            'distance_metric': vector_store_config.get('distance_metric', 'ip'),
        }
    
    def get_embedding_model_dir(self) -> str:
        """Lấy embedding model directory."""
        embedding_config = self.config.get('embedding', {})
        model_dir = embedding_config.get('model_dir')
        
        if model_dir is None:
            return str(self._get_root_dir() / "models" / "Vietnamese_Embedding_v2")
        else:
            model_path = Path(model_dir)
            if not model_path.is_absolute():
                return str(self._get_root_dir() / model_dir)
            else:
                return str(model_path)
    
    @staticmethod
    def get_default_config() -> 'PipelineConfig':
        """Lấy default configuration."""
        return PipelineConfig()
