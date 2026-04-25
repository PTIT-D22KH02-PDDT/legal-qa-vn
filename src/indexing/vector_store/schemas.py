"""Schemas for vector store module."""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator


# Store in vector database

class ChromaConfig(BaseModel):
    collection_name: str
    persist_directory: Optional[str] = None      # Nơi lưu trữ
    distance_metric: Literal["cosine", "l2", "ip"] = "cosine"  # Khoảng cách sử dụng trong ChromaDB
    is_persist: bool = False

    @model_validator(mode='after')
    def validate_persistence(self):
        if self.is_persist and not self.persist_directory:
            raise ValueError('persist_directory is required when is_persist=True')
        return self

class ChromaUpsertRequest(BaseModel):
    """Dữ liệu cần upsert vào ChromaDB"""
    chunk_id: str
    vector: List[float]         # Lấy từ EmbeddingResult.vector
    text: str                   
    metadata: dict   # Lấy từ ChunkMetadata tương ứng và có thể thêm thông tin khác nếu cần

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator


class ChromaQueryRequest(BaseModel):
    """Query request với cả text và vector queries"""
    # Text query (high-level, from user)
    query: Optional[str] = None
    
    # Vector query (low-level, for ChromaDB)
    query_vector: Optional[List[float]] = None
    
    # Common parameters
    top_k: int = Field(5, ge=1, le=100, description="Số lượng kết quả trả về")
    
    # Filtering options
    filter: Optional[Dict[str, Any]] = None  # ChromaDB metadata filter
    filter_by_type: Optional[List[str]] = None  # Section type filter (dieu, khoan, etc)
    score_threshold: Optional[float] = Field(
        None,
        description="Ngưỡng score tối thiểu (0-1)"
    )
    
    @model_validator(mode='after')
    def validate_query(self):
        """At least one of query or query_vector must be provided"""
        if not self.query and not self.query_vector:
            raise ValueError('Either query (text) or query_vector must be provided')
        return self

class ChromaQueryResult(BaseModel):
    """Kết quả trả về từ ChromaDB sau khi truy vấn"""
    chunk_id: str
    text: str
    metadata: Optional[dict] = None
    distance: Optional[float] = None  # None khi query by ID (không có vector similarity)
    score_rerank: Optional[float] = None  # Điểm số từ reranker (nếu có rerank)