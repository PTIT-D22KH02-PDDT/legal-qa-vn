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
        num_chunk: Số thứ tự của chunk trong văn bản, dùng để kiểm tra thứ tự khi trả về kết quả embedding
        text: Nội dung của chunk, lấy từ EmbeddingResult.text
        vector: Vector embedding của chunk, lấy từ EmbeddingResult.vector
    """
    chunk_id: str
    num_chunk: Optional[int] = None 
    vector: List[float]         
    text: str                   
    metadata: Dict[str, Any]    


class ChromaQueryRequest(BaseModel):
    """
    Yêu cầu truy vấn từ ChromaDB
    
    Attributes:
        query_vector: Vector embedding của câu truy vấn, được tạo ra từ module embedding
        top_k: Số lượng kết quả trả về, mặc định là 5
        filter: Bộ lọc theo metadata nếu cần, ví dụ {"section_id": "section_1"}
    """
    query_vector: List[float]                  
    top_k: int = Field(5, gt=0)
    filter: Optional[Dict[str, Any]] = None     


class ChromaQueryResult(BaseModel):
    """
    Kết quả trả về từ ChromaDB sau khi truy vấn
    
    Attributes:
        chunk_id: ID của chunk, lấy từ ChromaDB
        text: Nội dung của chunk, lấy từ ChromaDB
        metadata: Metadata của chunk, lấy từ ChromaDB
        distance: Khoảng cách giữa query_vector và vector của chunk trong ChromaDB, giá trị càng nhỏ thì càng gần nhau
    """
    chunk_id: str
    text: str
    metadata: Dict[str, Any]
    distance: float
