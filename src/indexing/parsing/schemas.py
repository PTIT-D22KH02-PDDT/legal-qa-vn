from dataclasses import dataclass
from typing import Any, Dict, List, Union
from pydantic import BaseModel, Field, ConfigDict

from src.core.models import DocumentMetadata

@dataclass
class ProcessResult:
    metadata: DocumentMetadata|None = None
    tree : Union[Dict[str, Any] | List[Dict[str, Any]], None] =None