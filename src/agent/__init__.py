"""
Legal QA Agent Module
Cung cấp LangChain Agent để trả lời các câu hỏi về pháp luật Việt Nam.
"""
from .agent import LegalQAAgent
from .llm_query_analyzer import LLMQueryAnalyzer
from .query_analyzer import QueryAnalyzer
from .router import ToolRouter
from .tools import LegalDocumentTools
from .schemas import (
    QueryType,
    Intent,
    QueryAnalysisResult,
    ToolExecutionResult,
    AgentStep,
    AgentResponse,
    DocumentSearchResult,
    DocumentMetadataResult,
    ArticleBlock,
)
from .config import (
    AgentConfig,
    get_agent_config,
    reload_agent_config,
)

__all__ = [
    "LegalQAAgent",
    "LLMQueryAnalyzer",
    "QueryAnalyzer",
    "ToolRouter",
    "LegalDocumentTools",
    # Schemas
    "QueryType",
    "Intent",
    "QueryAnalysisResult",
    "ToolExecutionResult",
    "AgentStep",
    "AgentResponse",
    "DocumentSearchResult",
    "DocumentMetadataResult",
    "ArticleBlock",
    # Configuration
    "AgentConfig",
    "get_agent_config",
    "reload_agent_config",
]
