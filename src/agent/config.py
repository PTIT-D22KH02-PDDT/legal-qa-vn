"""
Configuration loader cho agent module.
"""
from pathlib import Path
from typing import Any, Dict, Optional
from src.core.config import BaseConfig
import os
class AgentConfig(BaseConfig):
    """Configuration class cho agent module."""
    
    def _get_root_dir(self) -> Path:
        """Lấy root directory (2 levels up từ agent/config.py)."""
        return Path(__file__).resolve().parents[2]
    
    def _get_default_config_path(self) -> Path:
        """Lấy default config path."""
        root_dir = self._get_root_dir()
        return root_dir / "configs" / "agent_config.yaml"
    
    def get_query_analyzer_params(self) -> Dict[str, Any]:
        """Lấy query analyzer parameters."""
        query_analyzer_config = self.config.get('query_analyzer', {})
        
        return {
            'llm_provider': query_analyzer_config.get('llm_provider', 'groq'),
            'use_fallback': query_analyzer_config.get('use_fallback', True),
            'fallback_on_error': query_analyzer_config.get('fallback_on_error', True),
        }
    
    def get_llm_provider_params(self, provider: str = None) -> Dict[str, Any]:
        """
        Lấy LLM provider-specific parameters.
        
        Args:
            provider: LLM provider name ('groq', 'openai', 'ollama'). 
                     If None, uses configured default.
        """
        if provider is None:
            provider = self.get_query_analyzer_params().get('llm_provider', 'groq')
        
        query_analyzer_config = self.config.get('query_analyzer', {})
        provider_config = query_analyzer_config.get(provider, {})
        
        # Apply environment variable overrides
        api_key = provider_config.get('api_key')
        if provider.upper() == 'GROQ':
            api_key = api_key or os.getenv('GROQ_API_KEY')
        elif provider.upper() == 'OPENAI':
            api_key = api_key or os.getenv('OPENAI_API_KEY')
        return {
            'model_name': provider_config.get('model_name'),
            'temperature': provider_config.get('temperature', 0.0),
            'api_key': api_key,
            'timeout': provider_config.get('timeout', 30),
            'base_url': provider_config.get('base_url', None),
        }
    
    def get_router_params(self) -> Dict[str, Any]:
        """Lấy router parameters."""
        router_config = self.config.get('router', {})
        
        return {
            'enable_multi_block': router_config.get('enable_multi_block', True),
            'routing_strategy': router_config.get('routing_strategy', 'priority'),
        }
    
    def get_tools_config(self) -> Dict[str, Dict[str, Any]]:
        """Lấy tools configuration."""
        router_config = self.config.get('router', {})
        tools_config = router_config.get('tools', {})
        
        return tools_config
    
    def get_enabled_tools(self) -> list[str]:
        """Lấy danh sách tools được enable."""
        tools_config = self.get_tools_config()
        enabled_tools = []
        
        for tool_name, tool_cfg in tools_config.items():
            if tool_cfg.get('enabled', True):
                enabled_tools.append(tool_name)
        
        return enabled_tools
    
    def get_tools_by_priority(self) -> list[str]:
        """Lấy tools sắp xếp theo priority (cao đến thấp)."""
        tools_config = self.get_tools_config()
        tools_with_priority = []
        
        for tool_name, tool_cfg in tools_config.items():
            if tool_cfg.get('enabled', True):
                priority = tool_cfg.get('priority', 1)
                tools_with_priority.append((tool_name, priority))
        
        # Sort by priority descending
        tools_with_priority.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in tools_with_priority]
    
    def get_execution_params(self) -> Dict[str, Any]:
        """Lấy execution parameters."""
        execution_config = self.config.get('execution', {})
        
        return {
            'max_tool_calls': execution_config.get('max_tool_calls', 10),
            'tool_timeout': execution_config.get('tool_timeout', 30),
            'max_steps': execution_config.get('max_steps', 5),
            'enable_logging': execution_config.get('enable_logging', True),
            'log_level': execution_config.get('log_level', 'INFO'),
        }
    
    def get_pipeline_params(self) -> Dict[str, Any]:
        """Lấy pipeline parameters."""
        pipeline_config = self.config.get('pipeline', {})
        
        return {
            'retrieval_top_k': pipeline_config.get('retrieval_top_k', 10),
            'score_threshold': pipeline_config.get('score_threshold'),
            'rerank_enabled': pipeline_config.get('rerank_enabled', True),
            'rerank_top_k': pipeline_config.get('rerank_top_k', 5),
            'use_cross_encoder': pipeline_config.get('use_cross_encoder', True),
        }
    
    def get_reranker_params(self) -> Dict[str, Any]:
        """Lấy reranker model parameters."""
        reranker_config = self.config.get('reranker', {})
        
        return {
            'model_name': reranker_config.get('model_name'),
            'device': reranker_config.get('device', 'cpu'),
            'batch_size': reranker_config.get('batch_size', 32),
            'normalize_scores': reranker_config.get('normalize_scores', True),
            'max_length': reranker_config.get('max_length', 512),
        }
    
    def get_generation_params(self) -> Dict[str, Any]:
        """Lấy generation parameters."""
        generation_config = self.config.get('generation', {})
        
        return {
            'max_answer_length': generation_config.get('max_answer_length', 1000),
            'temperature': generation_config.get('temperature', 0.3),
            'include_sources': generation_config.get('include_sources', True),
            'include_reasoning': generation_config.get('include_reasoning', False),
        }
    
    def get_prompts_files(self) -> Dict[str, str]:
        """Lấy prompt file paths."""
        prompts_config = self.config.get('prompts', {})
        
        return {
            'system_prompt_file': prompts_config.get('system_prompt_file', 
                                                     'configs/prompts/system_prompt.txt'),
            'answer_prompt_file': prompts_config.get('answer_prompt_file',
                                                     'configs/prompts/answer_prompt.txt'),
        }
    
    def get_monitoring_params(self) -> Dict[str, Any]:
        """Lấy monitoring parameters."""
        monitoring_config = self.config.get('monitoring', {})
        
        return {
            'enabled': monitoring_config.get('enabled', True),
            'log_file': monitoring_config.get('log_file', 'logs/agent.log'),
            'metrics_file': monitoring_config.get('metrics_file', 'logs/agent_metrics.json'),
            'track_latency': monitoring_config.get('track_latency', True),
            'track_tool_calls': monitoring_config.get('track_tool_calls', True),
            'track_errors': monitoring_config.get('track_errors', True),
        }
    
    @staticmethod
    def get_default_config() -> 'AgentConfig':
        """Lấy default configuration."""
        return AgentConfig()


# Singleton instance (lazy loaded)
_agent_config: Optional[AgentConfig] = None


def get_agent_config() -> AgentConfig:
    """
    Get global AgentConfig instance (singleton).
    
    Returns:
        AgentConfig loaded from config file
    """
    global _agent_config
    
    if _agent_config is None:
        _agent_config = AgentConfig()
    
    return _agent_config


def reload_agent_config() -> AgentConfig:
    """
    Reload agent configuration (bypass cache).
    
    Returns:
        Fresh AgentConfig instance
    """
    global _agent_config
    _agent_config = AgentConfig()
    return _agent_config
