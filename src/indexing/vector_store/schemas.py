"""Schemas for vector store module."""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator


class ChromaConfig(BaseModel):
    """
    Configuration for ChromaDB
    
    Attributes:
        collection_name: Tên collection
        persist_directory: Nơi lưu trữ dữ liệu nếu is_persist=True
        distance_metric: Khoảng cách sử dụng trong ChromaDB, mặc định là cosine
        is_persist: Có lưu trữ dữ liệu vào ổ đĩa hay không, nếu False thì chỉ lưu trong bộ nhớ và mất dữ liệu khi tắt chương trình
    """
    collection_name: str
    persist_directory: Optional[str] = None     
    distance_metric: Literal["cosine", "l2", "ip"] = "cosine"
    is_persist: bool = False

    @model_validator(mode='after')
    def validate_persistence(self):
        if self.is_persist and not self.persist_directory:
            raise ValueError('persist_directory is required when is_persist=True')
        return self


class ChromaUpsertRequest(BaseModel):
    """
    Dữ liệu cần upsert vào ChromaDB
    
    Attributes:
        chunk_id: ID của chunk, lấy từ EmbeddingResult.chunk_id
        text: Nội dung của chunk, lấy từ EmbeddingResult.text
        vector: Vector embedding của chunk, lấy từ EmbeddingResult.vector
        metadata: Metadata của chunk (bao gồm cả chunk_index nếu có)
    """
    chunk_id: str
    vector: List[float]         
    text: str                   
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChromaQueryRequest(BaseModel):
    """
    Yêu cầu truy vấn từ ChromaDB. Query request với cả text và vector
    
    Attributes:
        query: Văn bản truy vấn, được tạo ra từ module embedding
        query_vector: Vector embedding của câu truy vấn, được tạo ra từ module embedding
        top_k: Số lượng kết quả trả về
        metadata_filter: Bộ lọc theo metadata cho ChromaDB nếu cần, ví dụ {"section_id": "section_1"}

    """
    query: Optional[str] = None
    query_vector: Optional[List[float]] = None  
    top_k: int = Field(5, ge=1, le=100, description="Số lượng kết quả trả về")
    metadata_filter: Optional[Dict[str, Any]] = None
    score_threshold: Optional[float] = Field(None, description="Ngưỡng điểm số để lọc kết quả, chỉ trả về các kết quả có điểm số thấp hơn ngưỡng này")

    @model_validator(mode='after')
    def validate_query(self):
        """
        Ít nhất một trong hai trường query hoặc query_vector phải được cung cấp
        """
        if not self.query and not self.query_vector:
            raise ValueError('Ít nhất một trong hai trường query hoặc query_vector phải được cung cấp')
        return self
    
class ChromaQueryResult(BaseModel):
    """
    Kết quả trả về từ ChromaDB sau khi truy vấn
    
    Attributes:
        chunk_id: ID của chunk, lấy từ ChromaDB
        text: Nội dung của chunk, lấy từ ChromaDB
        metadata: Metadata của chunk, lấy từ ChromaDB
        distance: Khoảng cách giữa query_vector và vector của chunk trong ChromaDB, giá trị càng nhỏ thì càng gần nhau
        score_rerank: Điểm số sau khi được tính toán lại với reranker
    """
    chunk_id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    distance: Optional[float] = None
    score_rerank: Optional[float] = None
