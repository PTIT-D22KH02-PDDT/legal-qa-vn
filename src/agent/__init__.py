"""
Legal QA Agent package.

Kiến trúc:
- `graph/`:  LangGraph build & state (logic chính của agent).
- `nodes/`:  các node trong graph (analyze / plan / execute / grade / ...).
- `tools/`:  tool gọi Chroma/DB + LLMQueryAnalyzer.
- `utils/`:  prompt templates.
- `runner.py`: entry point — boot infrastructure + gọi graph.
- `router.py`: logic chọn tool (dùng trong node plan_tools).
- `schemas.py`: toàn bộ Pydantic/Enum dùng chung.

Sử dụng nhanh:

    from src.agent.runner import LegalQARunner
    runner = LegalQARunner()
    result = runner.query("Điều 5 Luật 102/2017 nói gì?")
    print(result["answer"])

Hoặc chạy trực tiếp từ CLI:
    python -m src.agent.runner --interactive
"""

from .router import ToolRouter
from .tools import LegalDocumentTools, LLMQueryAnalyzer, QueryAnalysisError

# NOTE: `LegalQARunner` không re-export ở đây vì nó kéo theo ChromaStore,
# OnnxEmbeddingModel, SearchPipeline... làm nặng việc chỉ muốn import schema.
# Dùng trực tiếp: `from src.agent.runner import LegalQARunner`.
from .schemas import (
    Intent,
    Grade,
    QueryAnalysisResult,
    ToolExecutionResult,
    ToolOutput,
    ValidationResult,
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
    # Core classes
    "LLMQueryAnalyzer",
    "QueryAnalysisError",
    "ToolRouter",
    "LegalDocumentTools",
    # Schemas
    "Intent",
    "Grade",
    "QueryAnalysisResult",
    "ToolExecutionResult",
    "ToolOutput",
    "ValidationResult",
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
