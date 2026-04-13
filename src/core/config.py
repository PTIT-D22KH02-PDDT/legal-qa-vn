from pathlib import Path
from typing import Any, Dict, Optional
import yaml


class BaseConfig:
    """Base configuration class - chứa common config loading logic."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Đường dẫn đến config file
        """
        self.root_dir = self._get_root_dir()
        self.chroma_db_dir = self.root_dir / "chroma_db"
        self.embedding_model_dir = self.root_dir / "models" / "Vietnamese_Embedding_v2"
        
        # Load config từ file
        if config_path is None:
            config_path = self._get_default_config_path()
        else:
            config_path = Path(config_path)
        
        self.config: Dict[str, Any] = self._load_config(config_path)
    
    def _get_root_dir(self) -> Path:
        """Subclass must implement this method."""
        raise NotImplementedError()
    
    def _get_default_config_path(self) -> Path:
        """Subclass must implement this method."""
        raise NotImplementedError()
    
    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load YAML config file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        return config or {}
    
    def get_embedding_params(self) -> Dict[str, Any]:
        """Get embedding parameters."""
        embedding_config = self.config.get('embedding', {})
        model_dir = embedding_config.get('model_dir')
        
        params = {
            'max_length': embedding_config.get('max_length', 256),
            'batch_size': embedding_config.get('batch_size', 32),
            'pooling': embedding_config.get('pooling', 'auto'),
            'normalize': embedding_config.get('normalize', False),
        }
        
        # Nếu model_dir không được set trong config, dùng mặc định
        if model_dir is None:
            params['model_dir'] = str(self.embedding_model_dir)
        else:
            params['model_dir'] = str(model_dir)
        
        # onnx_path là optional
        if 'onnx_path' in embedding_config:
            params['onnx_path'] = embedding_config['onnx_path']
        
        return params
    
    def get_store_params(self) -> Dict[str, Any]:
        """Get vector store parameters."""
        store_config = self.config.get('vector_store', {})
        
        return {
            'collection_name': store_config.get('collection_name', 'legal_documents'),
            'is_persist': store_config.get('is_persist', True),
            'persist_directory': str(self.chroma_db_dir),
            'distance_metric': store_config.get('distance_metric', 'ip')
        }
