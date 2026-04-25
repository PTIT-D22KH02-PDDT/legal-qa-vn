"""Schemas for embedding module."""

from typing import List, Optional
from pydantic import BaseModel


class EmbeddingRequest(BaseModel):
    """Một đơn vị chunk cần embedding, hoặc truy vấn của người dùng"""
    chunk_id: str | None = None  # Duy nhất, lấy từ ChunkMetadata.section_id hoặc tự tạo khi khởi tạo
    text: str
    metadata : dict   # Thông tin metadata của chunk, có thể dùng để lưu vào vector database cùng với vector embedding

class EmbeddingResult(BaseModel):
    """Kết quả embed 1 chunk"""
    chunk_id: str | None = None
    text: str
    vector: List[float]     # Vector embedding
    token_count: Optional[int] = None   # Số token của chunk để kiểm tra có vượt giới hạn mô hình hay không
    metadata : dict