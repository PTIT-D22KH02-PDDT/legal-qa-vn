from dataclasses import dataclass
from typing import Any, Dict, List, Union
from pydantic import BaseModel, Field, ConfigDict

from src.core.models import DocumentMetadata


class HierarchicalChunkInput(BaseModel):
    """Input schema for hierarchical chunking"""
    model_config = ConfigDict(populate_by_name=True)
    payload: Dict[str, Any] | List[Dict[str, Any]] = Field(
        alias="json",
        description="Raw JSON đầu vào dùng cho hierarchical chunker."
    )


@dataclass
class ProcessResult:
    metadata: DocumentMetadata|None = None
    tree : Union[HierarchicalChunkInput |Dict[str, Any] | List[Dict[str, Any]], None] =None
    md_text: str = ""